import bcrypt
import csv
import io
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import uuid

logger = logging.getLogger(__name__)

from flask import Blueprint, Response, jsonify, make_response, request, session

from utils import utc_now, generate_id, bool_to_int
from database import get_db, normalize_reference_row, normalize_service_row
from auth import (
    login_required, permission_required, admin_required,
    get_user_record, password_complexity_error, is_valid_username,
    current_user, rate_limit,
    list_all_users, list_all_groups, update_group,
    create_user, update_user, delete_user,
)
from models.audit import current_actor, insert_app_log, insert_deleted_item
from models.settings import (
    DEFAULT_APP_SETTINGS, THEME_PRESETS,
    get_app_settings, save_app_settings,
    get_brand_logo_public_url, get_dpo_email,
    build_public_settings_payload, resolve_theme_id, resolve_dark_mode,
)
from models.catalog import normalize_resource_catalog_payload
from models.forms import persist_form
from config import CUSTOM_BRANDING_DIR, DB_PATH, BASE_DIR

bp = Blueprint("admin", __name__)

# Labels pour statuts et types
STATUS_LABELS = {
    "draft": "À compléter",
    "active": "Actif",
    "partial_assignment": "Attribution partielle",
    "awaiting_signature": "En attente de signature",
    "returned": "Restitué",
    "partial_return": "Restitution partielle",
    "cancelled": "Annulé"
}

TYPE_LABELS = {
    "arrivee": "Arrivée",
    "changement_service": "Changement de service",
    "mise_a_jour": "Mise à jour",
    "sortie": "Sortie"
}


@bp.route("/api/admin/unc-stats", methods=["GET"])
@login_required
@permission_required("users.manage")
def unc_stats():
    _ACCES = {"lecture": "Lecture", "lecture_ecriture": "Lecture / Écriture", "refuse": "Accès refusé"}
    _STATUT = {"demande": "Demandé", "en_cours": "En cours", "provisionne": "Provisionné"}
    rows = get_db().execute(
        "SELECT nom, prenom, service, payload_json FROM dotation_forms WHERE payload_json IS NOT NULL ORDER BY nom, prenom"
    ).fetchall()
    counts = {"demande": 0, "en_cours": 0, "provisionne": 0}
    agents_with_unc = set()
    detail = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        entries = payload.get("unc_acces") or []
        if entries:
            agents_with_unc.add(f"{row['nom']}|{row['prenom']}")
        for e in entries:
            statut = e.get("statut") or "demande"
            counts[statut] = counts.get(statut, 0) + 1
            detail.append({
                "nom": row["nom"] or "",
                "prenom": row["prenom"] or "",
                "service": row["service"] or "",
                "ref_ad": (payload.get("unc_ref_ad") or "").strip(),
                "chemin": e.get("chemin") or "",
                "acces": _ACCES.get(e.get("acces") or "", e.get("acces") or ""),
                "statut": _STATUT.get(statut, statut),
                "commentaire": e.get("commentaire") or "",
            })
    return jsonify({
        "counts": counts,
        "agents": len(agents_with_unc),
        "detail": detail,
    })


@bp.route("/api/admin/dashboard-stats", methods=["GET"])
@login_required
@permission_required("forms.view_all")
def dashboard_stats():
    period       = request.args.get("period", "30d")
    service_filter = request.args.get("service", "")
    type_filter  = request.args.get("type", "")
    status_filter  = request.args.get("statut", "")
    qualite_filter = request.args.get("qualite", "")
    date_from    = request.args.get("date_from", "")
    date_to      = request.args.get("date_to", "")
    try:
        alerte_seuil = max(1, min(365, int(request.args.get("alerte_seuil", "30"))))
    except (ValueError, TypeError):
        alerte_seuil = 30

    # Construire la clause WHERE commune à toutes les requêtes
    conditions = []
    base_params = []

    if date_from:
        conditions.append("created_at >= ?")
        base_params.append(date_from)
    elif period != "all":
        period_days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}.get(period, 30)
        conditions.append(f"created_at >= datetime('now', '-{period_days} days')")

    if date_to:
        conditions.append("created_at <= ?")
        base_params.append(date_to + " 23:59:59")

    if service_filter:
        conditions.append("service = ?")
        base_params.append(service_filter)

    if type_filter:
        conditions.append("dossier_type = ?")
        base_params.append(type_filter)

    if status_filter:
        conditions.append("status = ?")
        base_params.append(status_filter)

    if qualite_filter:
        conditions.append("beneficiary_type = ?")
        base_params.append(qualite_filter)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    db = get_db()

    # KPI 1 : Dossiers par statut
    by_status_rows = db.execute(
        f"SELECT status, COUNT(*) as count FROM dotation_forms {where_clause} GROUP BY status",
        base_params,
    ).fetchall()
    by_status = [
        {"status": row["status"], "label": STATUS_LABELS.get(row["status"], row["status"]), "count": row["count"]}
        for row in by_status_rows
    ]
    active_count = sum(s["count"] for s in by_status if s["status"] == "active")

    # KPI 2 : Dossiers par service (top 10) — sans filtre service pour garder la vue globale
    svc_conds = [c for c, p in zip(conditions, base_params) if "service" not in c] if service_filter else conditions
    svc_params = [p for c, p in zip(conditions, base_params) if "service" not in c] if service_filter else base_params
    svc_where = ("WHERE " + " AND ".join(svc_conds)) if svc_conds else ""
    by_service_rows = db.execute(
        f"""SELECT
            CASE WHEN beneficiary_type = 'elu'
                 THEN 'Élu(e)'
                 ELSE COALESCE(NULLIF(service,''), '—')
            END as service,
            COUNT(*) as count
            FROM dotation_forms {svc_where}
            GROUP BY 1 ORDER BY count DESC LIMIT 10""",
        svc_params,
    ).fetchall()
    by_service = [{"service": row["service"], "count": row["count"]} for row in by_service_rows]

    # KPI 3 : Dossiers par type
    by_type_rows = db.execute(
        f"SELECT dossier_type, COUNT(*) as count FROM dotation_forms {where_clause} GROUP BY dossier_type",
        base_params,
    ).fetchall()
    by_type = [
        {"type": row["dossier_type"], "label": TYPE_LABELS.get(row["dossier_type"], row["dossier_type"]), "count": row["count"]}
        for row in by_type_rows
    ]

    # KPI 4 : Ressources les plus attribuées (top 10)
    by_resource_rows = db.execute(
        "SELECT label, COUNT(*) as count FROM dotation_items WHERE assigned=1 GROUP BY label ORDER BY count DESC LIMIT 10"
    ).fetchall()
    by_resource = [{"label": row["label"], "count": row["count"]} for row in by_resource_rows]

    # KPI 5 : Taux de restitution (matériel)
    restitution_row = db.execute(
        "SELECT SUM(CASE WHEN returned=1 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) as taux FROM dotation_items WHERE category='materiel' AND assigned=1"
    ).fetchone()
    taux_restitution = round(restitution_row["taux"], 1) if restitution_row and restitution_row["taux"] else 0

    # KPI 6 : Tendance mensuelle (12 derniers mois)
    tendance_rows = list(reversed(db.execute(
        "SELECT strftime('%Y-%m', created_at) as mois, COUNT(*) as count FROM dotation_forms GROUP BY mois ORDER BY mois DESC LIMIT 12"
    ).fetchall()))
    tendance = [
        {"mois": row["mois"], "label": _format_month_label(row["mois"]), "count": row["count"]}
        for row in tendance_rows
    ]

    # KPI 7 : Alertes — dossiers bloqués (seuil configurable)
    alerte_conds = [c for i, (c, p) in enumerate(zip(conditions, base_params)) if "created_at" not in c]
    alerte_params = [p for c, p in zip(conditions, base_params) if "created_at" not in c]
    alerte_where = "WHERE status='draft' AND updated_at < datetime('now', ?)"
    alerte_params_full = [f"-{alerte_seuil} days"] + alerte_params
    if alerte_conds:
        alerte_where += " AND " + " AND ".join(alerte_conds)
    alertes_rows = db.execute(
        f"SELECT id, nom, prenom, service, status, updated_at FROM dotation_forms {alerte_where} ORDER BY updated_at",
        alerte_params_full,
    ).fetchall()
    alertes = [
        {"id": row["id"], "nom": row["nom"] or "", "prenom": row["prenom"] or "",
         "service": row["service"] or "—", "jours_blocage": _days_since(row["updated_at"]),
         "status": row["status"]}
        for row in alertes_rows
    ]

    # KPI Timing 1 : Durée moyenne de traitement
    timing_conds = ["status IN ('active', 'returned', 'partial_return')"] + conditions
    avg_treatment_row = db.execute(
        "SELECT AVG(CAST((julianday(updated_at) - julianday(created_at)) AS FLOAT)) as avg_days "
        f"FROM dotation_forms WHERE " + " AND ".join(timing_conds),
        base_params,
    ).fetchone()
    avg_treatment = round(avg_treatment_row["avg_days"], 1) if avg_treatment_row and avg_treatment_row["avg_days"] else 0

    # KPI Timing 2 : Durée moyenne de restitution
    restitution_conds = ["status IN ('returned', 'partial_return')", "returned_at IS NOT NULL", "assigned_at IS NOT NULL"] + conditions
    avg_restitution_row = db.execute(
        "SELECT AVG(CAST((julianday(returned_at) - julianday(assigned_at)) AS FLOAT)) as avg_days "
        f"FROM dotation_forms WHERE " + " AND ".join(restitution_conds),
        base_params,
    ).fetchone()
    avg_restitution = round(avg_restitution_row["avg_days"], 1) if avg_restitution_row and avg_restitution_row["avg_days"] else 0

    # KPI Timing 3 : % dossiers complétés en ≤ 7 jours
    fast_conds = ["status IN ('active', 'returned', 'partial_return')",
                  "CAST((julianday(updated_at) - julianday(created_at)) AS FLOAT) <= 7"] + conditions
    fast_count = db.execute(
        "SELECT COUNT(*) as count FROM dotation_forms WHERE " + " AND ".join(fast_conds),
        base_params,
    ).fetchone()["count"]
    pct_fast = round((fast_count * 100.0 / active_count) if active_count > 0 else 0, 0)

    # KPI Timing 4 : Distribution des délais
    timing_dist_conds = ["status IN ('active', 'returned', 'partial_return')"] + conditions
    timing_dist_rows = db.execute(
        "SELECT CASE "
        "  WHEN CAST((julianday(updated_at) - julianday(created_at)) AS FLOAT) <= 3 THEN 'rapide' "
        "  WHEN CAST((julianday(updated_at) - julianday(created_at)) AS FLOAT) <= 7 THEN 'normal' "
        "  ELSE 'long' END as categorie, COUNT(*) as count "
        f"FROM dotation_forms WHERE " + " AND ".join(timing_dist_conds) + " GROUP BY categorie",
        base_params,
    ).fetchall()
    timing_dist = {row["categorie"]: row["count"] for row in timing_dist_rows}
    timing_distribution = [
        {"categorie": "rapide", "label": "Rapide (≤3j)", "count": timing_dist.get("rapide", 0), "color": "#def7e7"},
        {"categorie": "normal", "label": "Normal (3-7j)", "count": timing_dist.get("normal", 0), "color": "#fff4d6"},
        {"categorie": "long", "label": "Long (>7j)", "count": timing_dist.get("long", 0), "color": "#fde2e2"},
    ]

    # Total global
    total = db.execute(
        f"SELECT COUNT(*) as count FROM dotation_forms {where_clause}", base_params
    ).fetchone()["count"]

    return jsonify({
        "period": {"label": _get_period_label(period), "days": period},
        "kpis": {
            "total": total,
            "actifs": active_count,
            "taux_restitution": taux_restitution,
            "alertes_blocage": len(alertes),
            "ressources_total": sum(r["count"] for r in by_resource),
            "avg_treatment": avg_treatment,
            "avg_restitution": avg_restitution,
            "pct_fast": pct_fast,
            "alerte_seuil": alerte_seuil,
        },
        "by_status": by_status,
        "by_service": by_service,
        "by_type": by_type,
        "by_resource": by_resource,
        "tendance": tendance,
        "alertes": alertes[:20],
        "timing_distribution": timing_distribution,
    })


def _get_period_label(period):
    labels = {"7d": "7 derniers jours", "30d": "30 derniers jours", "90d": "90 derniers jours", "365d": "Dernière année", "all": "Tous les temps"}
    return labels.get(period, "30 derniers jours")


def _format_month_label(mois_str):
    months = {
        "01": "Jan", "02": "Fév", "03": "Mar", "04": "Avr", "05": "Mai", "06": "Juin",
        "07": "Juil", "08": "Août", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Déc"
    }
    if len(mois_str) >= 7:
        return months.get(mois_str[5:7], mois_str)
    return mois_str


def _days_since(timestamp_str):
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        delta = datetime.now(dt.tzinfo) - dt if dt.tzinfo else datetime.now() - dt.replace(tzinfo=None)
        return delta.days
    except:
        return 0


@bp.route("/api/admin/settings", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_settings_route():
    settings = get_app_settings()
    payload = build_public_settings_payload(settings)
    payload["raw"] = {
        "org_name": settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"],
        "dpo_email": get_dpo_email(settings),
        "email_domains": settings.get("email_domains") or "",
        "brand_logo_mode": settings.get("brand_logo_mode") or DEFAULT_APP_SETTINGS["brand_logo_mode"],
        "brand_logo_url": settings.get("brand_logo_url") or DEFAULT_APP_SETTINGS["brand_logo_url"],
        "brand_logo_file": settings.get("brand_logo_file") or "",
        "theme_id": resolve_theme_id(settings),
        "dark_mode_policy": resolve_dark_mode(settings),
        "org_context": settings.get("org_context") or DEFAULT_APP_SETTINGS["org_context"],
        "beneficiary_types": settings.get("beneficiary_types") or DEFAULT_APP_SETTINGS["beneficiary_types"],
        "support_name": settings.get("support_name") or "",
        "support_email": settings.get("support_email") or "",
        "support_role": settings.get("support_role") or "",
    }
    payload["themeOptions"] = [
        {"id": key, "label": value["label"]}
        for key, value in THEME_PRESETS.items()
    ]
    return jsonify(payload)


@bp.route("/api/admin/settings", methods=["PUT"])
@login_required
@permission_required("users.manage")
@rate_limit(max_requests=20, window_seconds=60, scope="admin_settings_put")
def update_admin_settings_route():
    payload = request.get_json(silent=True) or {}
    with get_db() as connection:
        save_app_settings(connection, {
            "org_name": payload.get("org_name"),
            "dpo_email": payload.get("dpo_email") or DEFAULT_APP_SETTINGS["dpo_email"],
            "email_domains": payload.get("email_domains"),
            "brand_logo_mode": payload.get("brand_logo_mode"),
            "brand_logo_url": payload.get("brand_logo_url"),
            "theme_id": payload.get("theme_id"),
            "dark_mode_policy": payload.get("dark_mode_policy"),
            "org_context": payload.get("org_context"),
            "beneficiary_types": payload.get("beneficiary_types"),
            "support_name": payload.get("support_name"),
            "support_email": payload.get("support_email"),
            "support_role": payload.get("support_role"),
        })
        insert_app_log(
            connection,
            "admin",
            "settings_updated",
            "Parametres de personnalisation mis a jour",
            "settings",
            "branding",
            {
                "org_name": payload.get("org_name"),
                "dpo_email": payload.get("dpo_email"),
                "brand_logo_mode": payload.get("brand_logo_mode"),
                "theme_id": payload.get("theme_id"),
                "dark_mode_policy": payload.get("dark_mode_policy"),
            },
            actor=current_actor(),
        )
    return jsonify(build_public_settings_payload())


@bp.route("/api/setup/status", methods=["GET"])
@login_required
def setup_status_route():
    settings = get_app_settings()
    completed = settings.get("setup_completed", "0") == "1"
    return jsonify({
        "setupCompleted": completed,
        "orgName": settings.get("org_name") or "",
        "dpoEmail": settings.get("dpo_email") or "",
        "orgContext": settings.get("org_context") or DEFAULT_APP_SETTINGS["org_context"],
        "beneficiaryTypes": settings.get("beneficiary_types") or DEFAULT_APP_SETTINGS["beneficiary_types"],
        "supportName": settings.get("support_name") or "",
        "supportEmail": settings.get("support_email") or "",
        "supportRole": settings.get("support_role") or "",
    })


@bp.route("/api/setup/complete", methods=["POST"])
@login_required
@permission_required("users.manage")
@rate_limit(max_requests=5, window_seconds=600, scope="setup_complete")
def setup_complete_route():
    payload = request.get_json(silent=True) or {}
    updates = {
        "org_name": payload.get("org_name"),
        "dpo_email": payload.get("dpo_email"),
        "org_context": payload.get("org_context"),
        "beneficiary_types": payload.get("beneficiary_types"),
        "support_name": payload.get("support_name"),
        "support_email": payload.get("support_email"),
        "support_role": payload.get("support_role"),
        "setup_completed": "1",
    }
    with get_db() as connection:
        save_app_settings(connection, updates)
        insert_app_log(
            connection,
            "admin",
            "setup_completed",
            "Configuration initiale complétée via le wizard",
            "settings",
            "setup",
            {"org_name": payload.get("org_name"), "org_context": payload.get("org_context")},
            actor=current_actor(),
        )
    return jsonify(build_public_settings_payload())


@bp.route("/api/admin/settings/conflict-check", methods=["GET"])
@login_required
@permission_required("users.manage")
def settings_conflict_check_route():
    new_types_raw = request.args.get("beneficiary_types", "")
    new_keys = set()
    for part in new_types_raw.split(","):
        part = part.strip()
        if ":" in part:
            key = part.split(":")[0].strip()
            if key:
                new_keys.add(key)
    with get_db() as connection:
        rows = connection.execute(
            "SELECT beneficiary_type, COUNT(*) as cnt FROM dotation_forms"
            " WHERE beneficiary_type IS NOT NULL AND beneficiary_type != ''"
            " GROUP BY beneficiary_type"
        ).fetchall()
    conflicts = []
    total_affected = 0
    for row in rows:
        bt = row["beneficiary_type"]
        if bt not in new_keys:
            cnt = row["cnt"]
            conflicts.append({"type": bt, "count": cnt})
            total_affected += cnt
    return jsonify({
        "conflicts": conflicts,
        "totalAffected": total_affected,
        "hasConflicts": len(conflicts) > 0,
    })


@bp.route("/api/admin/settings/logo-upload", methods=["POST"])
@login_required
@permission_required("users.manage")
def upload_admin_logo_route():
    file = request.files.get("logo")
    if not file or not file.filename:
        return jsonify({"error": "logo_required"}), 400

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in {".png"}:
        return jsonify({"error": "invalid_logo_type"}), 400

    file_bytes = file.read(2 * 1024 * 1024 + 1)
    if len(file_bytes) > 2 * 1024 * 1024:
        return jsonify({"error": "logo_too_large"}), 400
    if file_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return jsonify({"error": "invalid_logo_type"}), 400

    os.makedirs(CUSTOM_BRANDING_DIR, exist_ok=True)
    file_name = f"brand_logo_{uuid.uuid4().hex}{extension}"
    absolute_path = os.path.join(CUSTOM_BRANDING_DIR, file_name)
    with open(absolute_path, "wb") as f:
        f.write(file_bytes)
    relative_path = f"custom/{file_name}"

    with get_db() as connection:
        save_app_settings(connection, {
            "brand_logo_mode": "file",
            "brand_logo_file": relative_path,
        })
        insert_app_log(
            connection,
            "admin",
            "branding_logo_uploaded",
            "Logo personnalise televerse",
            "settings",
            "branding_logo",
            {"file": relative_path},
            actor=current_actor(),
        )
    settings = get_app_settings()
    return jsonify({
        "uploaded": True,
        "logoUrl": get_brand_logo_public_url(settings),
        "brand_logo_file": relative_path,
    }), 201


@bp.route("/api/admin/groups", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_groups():
    groups = list_all_groups()
    return jsonify({g["key"]: g for g in groups})


TOGGLEABLE_PERMISSIONS = {"unc.view_all"}

@bp.route("/api/admin/groups/<key>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_group_permissions(key):
    groups = list_all_groups()
    group = next((g for g in groups if g["key"] == key), None)
    if not group:
        return jsonify({"error": "group_not_found"}), 404
    if "*" in group.get("permissions", []):
        return jsonify({"error": "cannot_edit_admin_group"}), 403
    payload = request.get_json(silent=True) or {}
    perms = list(group.get("permissions", []))
    for perm in TOGGLEABLE_PERMISSIONS:
        if perm in payload:
            if payload[perm] and perm not in perms:
                perms.append(perm)
            elif not payload[perm] and perm in perms:
                perms.remove(perm)
    update_group(key, perms)
    with get_db() as connection:
        insert_app_log(
            connection, "admin", "group_permissions_updated",
            f"Permissions du groupe {key} mises a jour",
            "group", key, {"permissions": perms},
            actor=current_actor(),
        )
    updated_groups = list_all_groups()
    return jsonify({g["key"]: g for g in updated_groups})


@bp.route("/api/catalog/suggestions/<resource_id>", methods=["GET"])
@login_required
def catalog_field_suggestions(resource_id):
    """Retourne les valeurs historiques pour les champs suggest d'une ressource catalogue.

    Réponse : { values: {fieldKey: [val, ...]}, linked: {fieldKey: {val: {otherKey: [val, ...]}}} }
    Les valeurs sont triées par fréquence décroissante. linked permet au frontend
    de filtrer les champs dépendants (ex : modèle selon marque) côté client.
    """
    from collections import Counter, defaultdict

    with get_db() as conn:
        cat_row = conn.execute(
            "SELECT field_schema_json FROM resource_catalog WHERE id = ? AND is_active = 1",
            (resource_id,),
        ).fetchone()

    if not cat_row:
        return jsonify({"values": {}, "linked": {}})

    try:
        schema = json.loads(cat_row["field_schema_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        schema = []

    suggest_keys = [f["key"] for f in schema if isinstance(f, dict) and f.get("suggest") and f.get("key")]
    if not suggest_keys:
        return jsonify({"values": {}, "linked": {}})

    with get_db() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM dotation_forms WHERE status NOT IN ('cancelled')"
        ).fetchall()

    freq = {k: Counter() for k in suggest_keys}
    linked: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))

    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        resources_obj = payload.get("resources", {})
        additional = resources_obj.get("additional", []) if isinstance(resources_obj, dict) else []
        for res in additional:
            if not isinstance(res, dict) or res.get("id") != resource_id or not res.get("selected"):
                continue
            fields = res.get("fields", {})
            if not isinstance(fields, dict):
                continue
            fields_ci = {k.lower(): str(v).strip() for k, v in fields.items() if str(v or "").strip()}
            present = {}
            for sk in suggest_keys:
                val = fields_ci.get(sk.lower(), "")
                if val:
                    present[sk] = val
                    freq[sk][val] += 1
            for ka, va in present.items():
                for kb, vb in present.items():
                    if ka != kb:
                        linked[ka][va][kb][vb] += 1

    values_out = {k: [v for v, _ in freq[k].most_common(50)] for k in suggest_keys}
    linked_out: dict = {}
    for ka, val_map in linked.items():
        linked_out[ka] = {}
        for va, dep_map in val_map.items():
            linked_out[ka][va] = {}
            for kb, counter in dep_map.items():
                linked_out[ka][va][kb] = [v for v, _ in counter.most_common(30)]

    return jsonify({"values": values_out, "linked": linked_out})


@bp.route("/api/reference/resources", methods=["GET"])
@login_required
def reference_resources():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM resource_catalog
            WHERE is_active = 1
            ORDER BY category ASC, display_order ASC, label COLLATE NOCASE ASC
            """
        ).fetchall()
    return jsonify([normalize_reference_row(row) for row in rows])


@bp.route("/api/reference/services", methods=["GET"])
@login_required
def reference_services():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM service_catalog
            WHERE is_active = 1
            ORDER BY label COLLATE NOCASE ASC
            """
        ).fetchall()
    return jsonify([normalize_service_row(row) for row in rows])


@bp.route("/api/admin/users", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_users():
    users = list_all_users()
    return jsonify([
        {
            "username": user["username"],
            "groups": user.get("groups", []),
            "is_active": user.get("is_active", True),
            "status": user.get("status", "active"),
            "service": user.get("service") or "",
            "db_manage": bool(user.get("db_manage", False)),
        }
        for user in users
    ])


@bp.route("/api/admin/logs", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_logs():
    search = (request.args.get("q") or "").strip()
    limit = request.args.get("limit", default=100, type=int) or 100
    limit = max(1, min(limit, 500))
    offset = max(0, request.args.get("offset", default=0, type=int))
    where_clause = ""
    params = []
    if search:
        where_clause = """
            WHERE actor LIKE ?
               OR scope LIKE ?
               OR action_type LIKE ?
               OR action_label LIKE ?
               OR target_type LIKE ?
               OR target_id LIKE ?
               OR target_label LIKE ?
               OR details_json LIKE ?
        """
        pattern = f"%{search}%"
        params.extend([pattern] * 8)
    with get_db() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM app_logs {where_clause}", tuple(params)
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM app_logs {where_clause} ORDER BY datetime(created_at) DESC, created_at DESC LIMIT ? OFFSET ?",
            tuple(params) + (limit, offset),
        ).fetchall()
    return jsonify({
        "items": [
            {
                "id": row["id"],
                "actor": row["actor"],
                "scope": row["scope"],
                "action_type": row["action_type"],
                "action_label": row["action_label"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "target_label": row["target_label"],
                "details": json.loads(row["details_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@bp.route("/api/admin/trash", methods=["GET"])
@admin_required
def admin_trash():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM deleted_items
            ORDER BY datetime(deleted_at) DESC, deleted_at DESC
            """
        ).fetchall()
    return jsonify([
        {
            "id": row["id"],
            "item_type": row["item_type"],
            "item_key": row["item_key"],
            "item_label": row["item_label"],
            "deleted_by": row["deleted_by"],
            "deleted_at": row["deleted_at"],
            "payload": json.loads(row["payload_json"] or "{}"),
        }
        for row in rows
    ])


@bp.route("/api/admin/trash/<trash_id>/restore", methods=["POST"])
@admin_required
def restore_trash_item(trash_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM deleted_items WHERE id = ?",
            (trash_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        payload = json.loads(row["payload_json"] or "{}")
        item_type = row["item_type"]
        item_key = row["item_key"]
        item_label = row["item_label"] or item_key

        if item_type == "form":
            form_data = persist_form(payload, allow_locked_update=True)
        elif item_type == "resource":
            existing_code = connection.execute(
                "SELECT id FROM resource_catalog WHERE code = ?",
                (payload.get("code"),),
            ).fetchone()
            if existing_code:
                return jsonify({"error": "resource_code_exists"}), 409
            connection.execute(
                """
                INSERT INTO resource_catalog (
                    id, code, label, category, issuer_service, requires_return, trigger_key,
                    field_schema_json, is_active, is_builtin, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("id"),
                    payload.get("code"),
                    payload.get("label"),
                    payload.get("category"),
                    payload.get("issuer_service"),
                    payload.get("requires_return", 1),
                    payload.get("trigger_key"),
                    payload.get("field_schema_json"),
                    payload.get("is_active", 1),
                    payload.get("is_builtin", 0),
                    payload.get("created_at") or utc_now(),
                    utc_now(),
                ),
            )
            form_data = {"restored": True}
        elif item_type == "user":
            if get_user_record(payload.get("username")):
                return jsonify({"error": "user_exists"}), 409
            username = payload.get("username")
            password_hash = payload.get("password_hash")
            groups = payload.get("groups", [])
            service = payload.get("service", "")
            is_active = bool(payload.get("is_active", True))
            status = payload.get("status", "active")
            db_manage = bool(payload.get("db_manage", False))
            if not create_user(username, password_hash, groups, service, is_active, status, db_manage):
                return jsonify({"error": "failed_to_restore_user"}), 500
            form_data = {"restored": True}
        else:
            return jsonify({"error": "unsupported_item_type"}), 400

        connection.execute("DELETE FROM deleted_items WHERE id = ?", (trash_id,))
        insert_app_log(
            connection,
            "admin",
            "trash_restored",
            "Element restaure depuis la corbeille",
            item_type,
            item_key,
            {"label": item_label},
            target_label=item_label or item_key,
        )
    return jsonify({"restored": True, "item_type": item_type, "item_key": item_key, "data": form_data})


@bp.route("/api/admin/trash/<trash_id>", methods=["DELETE"])
@admin_required
def delete_trash_item(trash_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT item_type, item_key, item_label FROM deleted_items WHERE id = ?",
            (trash_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        deleted = connection.execute(
            "DELETE FROM deleted_items WHERE id = ?",
            (trash_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "admin",
                "trash_deleted",
                "Element supprime definitivement depuis la corbeille",
                row["item_type"],
                row["item_key"],
                {"label": row["item_label"] or row["item_key"]},
                target_label=row["item_label"] or row["item_key"],
            )

    return jsonify({"deleted": bool(deleted)})


@bp.route("/api/admin/trash", methods=["DELETE"])
@admin_required
def empty_admin_trash():
    with get_db() as connection:
        deleted_count = connection.execute("SELECT COUNT(*) AS total FROM deleted_items").fetchone()["total"]
        connection.execute("DELETE FROM deleted_items")
        if deleted_count:
            insert_app_log(
                connection,
                "admin",
                "trash_emptied",
                "Corbeille videe definitivement",
                "trash",
                "all",
                {"deleted_count": deleted_count},
            )

    return jsonify({"deleted": True, "deleted_count": deleted_count})


@bp.route("/api/admin/services", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_services():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM service_catalog ORDER BY is_active DESC, label COLLATE NOCASE ASC"
        ).fetchall()
    return jsonify([normalize_service_row(row) for row in rows])


@bp.route("/api/admin/services", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_service():
    payload = request.get_json(silent=True) or {}
    label = (payload.get("label") or "").strip()
    is_active = bool(payload.get("is_active", True))
    if not label:
        return jsonify({"error": "label_required"}), 400

    now = utc_now()
    with get_db() as connection:
        existing = connection.execute(
            "SELECT id FROM service_catalog WHERE lower(label) = lower(?)",
            (label,),
        ).fetchone()
        if existing:
            return jsonify({"error": "service_exists"}), 409
        service_id = generate_id("service")
        connection.execute(
            """
            INSERT INTO service_catalog (
                id, label, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, 0, ?, ?)
            """,
            (
                service_id,
                label,
                bool_to_int(is_active),
                now,
                now,
            ),
        )
        insert_app_log(
            connection,
            "admin",
            "service_created",
            "Service cree",
            "service",
            service_id,
            {"label": label},
        )
    return jsonify({"created": True}), 201


@bp.route("/api/admin/services/<service_id>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_service(service_id):
    payload = request.get_json(silent=True) or {}
    now = utc_now()
    with get_db() as connection:
        row = connection.execute("SELECT * FROM service_catalog WHERE id = ?", (service_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        next_label = (payload.get("label") if payload.get("label") is not None else row["label"]).strip()
        if not next_label:
            return jsonify({"error": "label_required"}), 400

        duplicate = connection.execute(
            "SELECT id FROM service_catalog WHERE lower(label) = lower(?) AND id != ?",
            (next_label, service_id),
        ).fetchone()
        if duplicate:
            return jsonify({"error": "service_exists"}), 409

        next_is_active = bool_to_int(payload.get("is_active", bool(row["is_active"])))
        connection.execute(
            """
            UPDATE service_catalog
            SET label = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_label,
                next_is_active,
                now,
                service_id,
            ),
        )
        insert_app_log(
            connection,
            "admin",
            "service_updated",
            "Service mis a jour",
            "service",
            service_id,
            {"label": next_label, "is_active": bool(next_is_active)},
        )
    return jsonify({"updated": True})


@bp.route("/api/admin/services/<service_id>", methods=["DELETE"])
@login_required
@permission_required("users.manage")
def delete_admin_service(service_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM service_catalog WHERE id = ?",
            (service_id,),
        ).fetchone()
        deleted = connection.execute(
            "DELETE FROM service_catalog WHERE id = ?",
            (service_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "admin",
                "service_deleted",
                "Service supprime",
                "service",
                service_id,
                {"label": row["label"] if row else ""},
            )
    return jsonify({"deleted": bool(deleted)})


@bp.route("/api/admin/services/csv-template", methods=["GET"])
@login_required
@permission_required("users.manage")
def service_csv_template():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["label", "is_active"])
    writer.writerow(["Direction generale", "1"])
    writer.writerow(["Ressources humaines", "1"])
    writer.writerow(["Informatique", "1"])
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=modele_services.csv"
    return resp


@bp.route("/api/admin/services/export-csv", methods=["GET"])
@login_required
@permission_required("users.manage")
def export_services_csv():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT label, is_active FROM service_catalog ORDER BY label COLLATE NOCASE ASC"
        ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["label", "is_active"])
    for row in rows:
        writer.writerow([row["label"], row["is_active"]])
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=services.csv"
    return resp


@bp.route("/api/admin/services/import-csv", methods=["POST"])
@login_required
@permission_required("users.manage")
def import_services_csv():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no_file"}), 400
    mode = request.form.get("mode", "append")
    try:
        raw = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "invalid_encoding"}), 400
    delimiter = ";" if ";" in raw.split("\n")[0] else ","
    reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
    if not reader.fieldnames or "label" not in [f.strip().lower() for f in reader.fieldnames]:
        return jsonify({"error": "missing_label_column"}), 400
    field_map = {f.strip().lower(): f for f in reader.fieldnames}
    imported = 0
    skipped = 0
    errors = []
    now = utc_now()
    with get_db() as connection:
        existing_labels = {
            r["label"].strip().lower()
            for r in connection.execute("SELECT label FROM service_catalog").fetchall()
        }
        csv_labels = set()
        for i, row in enumerate(reader, start=2):
            label = (row.get(field_map.get("label", "label")) or "").strip()
            if not label:
                continue
            is_active_raw = (row.get(field_map.get("is_active", "is_active")) or "1").strip()
            is_active = is_active_raw not in ("0", "false", "non", "False")
            csv_labels.add(label.lower())
            if label.lower() in existing_labels:
                skipped += 1
                continue
            existing_labels.add(label.lower())
            connection.execute(
                """
                INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (generate_id("service"), label, bool_to_int(is_active), now, now),
            )
            imported += 1
        if mode == "replace":
            connection.execute(
                "UPDATE service_catalog SET is_active = 0, updated_at = ? WHERE lower(label) NOT IN ({})".format(
                    ",".join("?" for _ in csv_labels)
                ),
                [now] + list(csv_labels),
            )
        insert_app_log(connection, "admin", "services_csv_imported", "Import CSV services", details={
            "mode": mode, "imported": imported, "skipped": skipped,
        })
    return jsonify({"imported": imported, "skipped": skipped, "errors": errors})


@bp.route("/api/admin/resources", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_resources():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM resource_catalog ORDER BY is_active DESC, category ASC, display_order ASC, label COLLATE NOCASE ASC"
        ).fetchall()
    return jsonify([normalize_reference_row(row) for row in rows])


@bp.route("/api/admin/resources", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_resource():
    payload = request.get_json(silent=True) or {}
    resource_data = normalize_resource_catalog_payload(payload)

    if not resource_data["code"] or not resource_data["label"]:
        return jsonify({"error": "code_and_label_required"}), 400

    now = utc_now()
    with get_db() as connection:
        existing = connection.execute("SELECT id FROM resource_catalog WHERE code = ?", (resource_data["code"],)).fetchone()
        if existing:
            return jsonify({"error": "resource_exists"}), 409
        resource_id = generate_id("resource")
        connection.execute(
            """
            INSERT INTO resource_catalog (
                id, code, label, description, category, issuer_service, requires_return,
                has_assignment_date, has_assignment_condition, has_assignment_notes, display_order,
                trigger_key, field_schema_json, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                resource_id,
                resource_data["code"],
                resource_data["label"],
                resource_data["description"],
                resource_data["category"],
                resource_data["issuer_service"],
                bool_to_int(resource_data["requires_return"]),
                bool_to_int(resource_data["has_assignment_date"]),
                bool_to_int(resource_data["has_assignment_condition"]),
                bool_to_int(resource_data["has_assignment_notes"]),
                resource_data["display_order"],
                resource_data["trigger_key"],
                json.dumps(resource_data["field_schema"], ensure_ascii=False),
                bool_to_int(resource_data["is_active"]),
                now,
                now,
            ),
        )
        created_row = connection.execute("SELECT * FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
        insert_app_log(
            connection,
            "admin",
            "resource_created",
            "Ressource creee",
            "resource",
            resource_id,
            {
                "code": resource_data["code"],
                "label": resource_data["label"],
                "category": resource_data["category"],
                "issuer_service": resource_data["issuer_service"],
                "field_count": len(resource_data["field_schema"]),
            },
            target_label=resource_data["label"],
        )
    return jsonify({"created": True, "resource": normalize_reference_row(created_row)}), 201


@bp.route("/api/admin/resources/<resource_id>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_resource(resource_id):
    payload = request.get_json(silent=True) or {}
    now = utc_now()
    with get_db() as connection:
        row = connection.execute("SELECT * FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        resource_data = normalize_resource_catalog_payload(payload, row)
        next_code = resource_data["code"]
        if not next_code:
            return jsonify({"error": "code_required"}), 400
        duplicate = connection.execute(
            "SELECT id FROM resource_catalog WHERE code = ? AND id != ?",
            (next_code, resource_id),
        ).fetchone()
        if duplicate:
            return jsonify({"error": "resource_code_exists"}), 409
        connection.execute(
            """
            UPDATE resource_catalog
            SET code = ?, label = ?, description = ?, category = ?, issuer_service = ?, requires_return = ?,
                has_assignment_date = ?, has_assignment_condition = ?, has_assignment_notes = ?, display_order = ?,
                trigger_key = ?, field_schema_json = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                resource_data["code"],
                resource_data["label"],
                resource_data["description"],
                resource_data["category"],
                resource_data["issuer_service"],
                bool_to_int(resource_data["requires_return"]),
                bool_to_int(resource_data["has_assignment_date"]),
                bool_to_int(resource_data["has_assignment_condition"]),
                bool_to_int(resource_data["has_assignment_notes"]),
                resource_data["display_order"],
                resource_data["trigger_key"],
                json.dumps(resource_data["field_schema"], ensure_ascii=False),
                bool_to_int(resource_data["is_active"]),
                now,
                resource_id,
            ),
        )
        updated_row = connection.execute("SELECT * FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
        insert_app_log(
            connection,
            "admin",
            "resource_updated",
            "Ressource mise a jour",
            "resource",
            resource_id,
            {
                "code": next_code,
                "label": resource_data["label"],
                "category": resource_data["category"],
                "field_count": len(resource_data["field_schema"]),
            },
            target_label=resource_data["label"],
        )
    return jsonify({"updated": True, "resource": normalize_reference_row(updated_row)})


@bp.route("/api/admin/resources/<resource_id>", methods=["DELETE"])
@login_required
@permission_required("users.manage")
def delete_admin_resource(resource_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM resource_catalog WHERE id = ?",
            (resource_id,),
        ).fetchone()
        if row:
            insert_deleted_item(
                connection,
                "resource",
                resource_id,
                row["label"],
                {key: row[key] for key in row.keys()},
            )
        deleted = connection.execute(
            "DELETE FROM resource_catalog WHERE id = ?",
            (resource_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "admin",
                "resource_deleted",
                "Ressource supprimee",
                "resource",
                resource_id,
                {"code": row["code"] if row else "", "label": row["label"] if row else ""},
            )
    if not deleted:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"deleted": True})


@bp.route("/api/admin/users", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_user():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    groups = payload.get("groups") or []
    is_active = bool(payload.get("is_active", True))

    if not username or not password:
        return jsonify({"error": "username_and_password_required"}), 400
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    complexity_error = password_complexity_error(password)
    if complexity_error:
        return jsonify({"error": complexity_error}), 400
    if get_user_record(username):
        return jsonify({"error": "user_exists"}), 409

    all_groups = list_all_groups()
    valid_group_keys = {g["key"] for g in all_groups}
    valid_groups = [group for group in groups if group in valid_group_keys]

    service = (payload.get("service") or "").strip()
    status = "active" if is_active else "disabled"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db_manage = bool(payload.get("db_manage", False))

    if not create_user(username, password_hash, valid_groups, service, is_active, status, db_manage):
        return jsonify({"error": "failed_to_create_user"}), 500

    with get_db() as connection:
        insert_app_log(
            connection,
            "admin",
            "user_created",
            "Compte utilisateur cree",
            "user",
            username,
            {"groups": valid_groups, "is_active": is_active, "status": status},
        )
    return jsonify({"created": True}), 201


@bp.route("/api/admin/users/<username>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_user(username):
    payload = request.get_json(silent=True) or {}
    user = get_user_record(username)
    if not user:
        return jsonify({"error": "not_found"}), 404

    update_fields = {}

    all_groups = list_all_groups()
    valid_group_keys = {g["key"] for g in all_groups}
    if "groups" in payload:
        update_fields["groups"] = [group for group in payload.get("groups", []) if group in valid_group_keys]

    requested_status = payload.get("status")
    if requested_status in {"pending", "active", "disabled"}:
        update_fields["status"] = requested_status
        update_fields["is_active"] = int(requested_status != "disabled")
    elif "is_active" in payload:
        update_fields["is_active"] = int(bool(payload.get("is_active", True)))
        update_fields["status"] = "active" if update_fields["is_active"] else "disabled"

    if "service" in payload:
        service = (payload["service"] or "").strip()
        update_fields["service"] = service if service else None

    if "db_manage" in payload:
        update_fields["db_manage"] = int(bool(payload["db_manage"]))

    password_changed = False
    if payload.get("password"):
        complexity_error = password_complexity_error(payload["password"])
        if complexity_error:
            return jsonify({"error": complexity_error}), 400
        update_fields["password_hash"] = bcrypt.hashpw(payload["password"].encode(), bcrypt.gensalt()).decode()
        password_changed = True

    if update_fields:
        if not update_user(username, **update_fields):
            return jsonify({"error": "failed_to_update_user"}), 500

    with get_db() as connection:
        insert_app_log(
            connection,
            "admin",
            "user_updated",
            "Compte utilisateur mis a jour",
            "user",
            username,
            {
                "groups": update_fields.get("groups", user.get("groups", [])),
                "is_active": bool(update_fields.get("is_active", user.get("is_active", True))),
                "status": update_fields.get("status", user.get("status", "active")),
                "password_changed": password_changed,
            },
        )
    return jsonify({"updated": True})


@bp.route("/api/admin/users/<username>", methods=["DELETE"])
@login_required
@permission_required("users.manage")
def delete_admin_user(username):
    current_username = session.get("user")
    if current_username == username:
        return jsonify({"error": "cannot_delete_current_user"}), 400

    all_users = list_all_users()
    deleted_user = next((u for u in all_users if u.get("username") == username), None)
    if not deleted_user:
        return jsonify({"error": "not_found"}), 404

    if not delete_user(username):
        return jsonify({"error": "failed_to_delete_user"}), 500

    with get_db() as connection:
        insert_deleted_item(
            connection,
            "user",
            username,
            username,
            deleted_user,
        )
        insert_app_log(
            connection,
            "admin",
            "user_deleted",
            "Compte utilisateur supprime",
            "user",
            username,
        )
    return jsonify({"deleted": True})



# ---------------------------------------------------------------------------
# Gestion de la base de données (export / diagnose / import)
# ---------------------------------------------------------------------------

_REQUIRED_TABLES = {
    "dotation_forms", "dotation_items", "resource_catalog",
    "service_catalog", "app_settings", "app_logs",
}
_SQLITE_MAGIC = b"SQLite format 3\x00"
_DB_MAX_SIZE = 200 * 1024 * 1024  # 200 Mo
_BACKUP_DIR = os.path.join(BASE_DIR, "db_backups")


def _diagnose_db_file(path):
    issues = []
    warnings = []
    stats = {}

    try:
        with open(path, "rb") as fh:
            magic = fh.read(16)
        if magic != _SQLITE_MAGIC:
            return {"level": "error", "issues": ["Fichier non reconnu comme base SQLite valide."], "warnings": [], "stats": {}}
    except OSError as exc:
        return {"level": "error", "issues": [f"Impossible de lire le fichier : {exc}"], "warnings": [], "stats": {}}

    size = os.path.getsize(path)
    if size > _DB_MAX_SIZE:
        issues.append(f"Fichier trop volumineux ({size // (1024*1024)} Mo, maximum 200 Mo).")

    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            issues.append(f"Echec du controle d'integrite SQLite : {integrity}")
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = _REQUIRED_TABLES - existing
        if missing:
            issues.append(f"Tables manquantes : {', '.join(sorted(missing))}")
        if "dotation_forms" in existing:
            try:
                stats["dossiers"] = conn.execute(
                    "SELECT COUNT(*) FROM dotation_forms WHERE is_deleted = 0"
                ).fetchone()[0]
            except Exception as exc:
                logger.warning("Diagnostic : impossible de compter les dossiers : %s", exc)
                stats["dossiers"] = 0
        if "app_settings" in existing:
            try:
                org = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key='org_name'"
                ).fetchone()
                stats["org_name"] = (org["setting_value"] if org else "") or ""
            except Exception as exc:
                logger.warning("Diagnostic : impossible de lire org_name : %s", exc)
                stats["org_name"] = ""
        if "dotation_forms" in existing:
            try:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(dotation_forms)").fetchall()}
                for col in ("payload_json", "status", "service", "nom", "prenom"):
                    if col not in cols:
                        warnings.append(f"Colonne manquante dans dotation_forms : {col} (migration automatique possible)")
            except Exception as exc:
                logger.warning("Diagnostic : impossible de verifier le schema dotation_forms : %s", exc)
        conn.close()
    except sqlite3.Error as exc:
        issues.append(f"Erreur SQLite : {exc}")

    level = "error" if issues else ("warning" if warnings else "ok")
    return {"level": level, "issues": issues, "warnings": warnings, "stats": stats}


@bp.route("/api/admin/db/export", methods=["GET"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=20, window_seconds=60, scope="db_export")
def db_export():
    from datetime import datetime as _dt, timezone as _tz
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "db_not_found"}), 404
    date_str = _dt.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"aquai_db_{date_str}.db"
    with get_db() as conn:
        insert_app_log(conn, "admin", "db_exported", "Export base de donnees", details={"filename": filename})
    with open(DB_PATH, "rb") as fh:
        data = fh.read()
    resp = make_response(data)
    resp.headers["Content-Type"] = "application/octet-stream"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@bp.route("/api/admin/db/diagnose", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=10, window_seconds=60, scope="db_diagnose")
def db_diagnose():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no_file"}), 400
    raw = file.read()
    if len(raw) > _DB_MAX_SIZE:
        return jsonify({"error": "file_too_large"}), 400
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(raw)
    try:
        report = _diagnose_db_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    with get_db() as conn:
        insert_app_log(conn, "admin", "db_diagnosed", "Diagnostic base de donnees", details={"level": report["level"]})
    return jsonify(report)


@bp.route("/api/admin/db/import", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=3, window_seconds=600, scope="db_import")
def db_import():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no_file"}), 400
    raw = file.read()
    if len(raw) > _DB_MAX_SIZE:
        return jsonify({"error": "file_too_large"}), 400
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(raw)
    try:
        report = _diagnose_db_file(tmp_path)
        if report["level"] == "error":
            os.unlink(tmp_path)
            return jsonify({"error": "diagnose_failed", "report": report}), 422
        os.makedirs(_BACKUP_DIR, exist_ok=True)
        from datetime import datetime as _dt, timezone as _tz
        backup_name = f"dotation_backup_{_dt.now(_tz.utc).strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(_BACKUP_DIR, backup_name)
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)
        shutil.move(tmp_path, DB_PATH)
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return jsonify({"error": "import_failed", "detail": str(exc)}), 500
    try:
        with get_db() as conn:
            insert_app_log(conn, "admin", "db_imported", "Import base de donnees", details={
                "backup": backup_name, "stats": report.get("stats", {}),
            })
    except Exception as exc:
        logger.warning("Import DB : impossible d'ecrire le log d'audit : %s", exc)
    return jsonify({"imported": True, "backup": backup_name, "stats": report.get("stats", {})})
