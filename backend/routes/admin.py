import bcrypt
import csv
import io
import json
import os
import uuid

from flask import Blueprint, Response, jsonify, make_response, request, session

from utils import utc_now, generate_id, bool_to_int
from database import get_db, normalize_reference_row, normalize_service_row
from auth import (
    login_required, permission_required, admin_required,
    load_auth_config, save_auth_config,
    get_user_record, password_complexity_error, is_valid_username,
    current_user,
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
from config import CUSTOM_BRANDING_DIR

bp = Blueprint("admin", __name__)


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
    config = load_auth_config()
    return jsonify(config.get("groups", {}))


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
    config = load_auth_config()
    return jsonify([
        {
            "username": user["username"],
            "groups": user.get("groups", []),
            "is_active": user.get("is_active", True),
            "status": user.get("status", "active" if user.get("is_active", True) else "disabled"),
        }
        for user in config.get("users", [])
    ])


@bp.route("/api/admin/logs", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_logs():
    search = (request.args.get("q") or "").strip()
    limit = request.args.get("limit", default=200, type=int) or 200
    limit = max(1, min(limit, 500))
    query = """
        SELECT * FROM app_logs
    """
    params = []
    if search:
        query += """
            WHERE actor LIKE ?
               OR scope LIKE ?
               OR action_type LIKE ?
               OR action_label LIKE ?
               OR target_type LIKE ?
               OR target_id LIKE ?
               OR details_json LIKE ?
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern])
    query += """
        ORDER BY datetime(created_at) DESC, created_at DESC
        LIMIT ?
    """
    params.append(limit)
    with get_db() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return jsonify([
        {
            "id": row["id"],
            "actor": row["actor"],
            "scope": row["scope"],
            "action_type": row["action_type"],
            "action_label": row["action_label"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "details": json.loads(row["details_json"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ])


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
            config = load_auth_config()
            if get_user_record(payload.get("username")):
                return jsonify({"error": "user_exists"}), 409
            config.setdefault("users", []).append(payload)
            save_auth_config(config)
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
    config = load_auth_config()

    if not username or not password:
        return jsonify({"error": "username_and_password_required"}), 400
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    complexity_error = password_complexity_error(password)
    if complexity_error:
        return jsonify({"error": complexity_error}), 400
    if get_user_record(username):
        return jsonify({"error": "user_exists"}), 409

    status = "active" if is_active else "disabled"
    config["users"].append({
        "username": username,
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "groups": [group for group in groups if group in config.get("groups", {})],
        "is_active": is_active,
        "status": status,
    })
    save_auth_config(config)
    with get_db() as connection:
        insert_app_log(
            connection,
            "admin",
            "user_created",
            "Compte utilisateur cree",
            "user",
            username,
            {"groups": [group for group in groups if group in config.get("groups", {})], "is_active": is_active, "status": status},
        )
    return jsonify({"created": True}), 201


@bp.route("/api/admin/users/<username>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_user(username):
    payload = request.get_json(silent=True) or {}
    config = load_auth_config()
    user = next((item for item in config.get("users", []) if item.get("username") == username), None)
    if not user:
        return jsonify({"error": "not_found"}), 404

    user["groups"] = [group for group in payload.get("groups", user.get("groups", [])) if group in config.get("groups", {})]
    requested_status = payload.get("status")
    if requested_status in {"pending", "active", "disabled"}:
        user["status"] = requested_status
        user["is_active"] = requested_status != "disabled"
    else:
        user["is_active"] = bool(payload.get("is_active", user.get("is_active", True)))
        user["status"] = "active" if user.get("is_active", True) else "disabled"
    if payload.get("password"):
        complexity_error = password_complexity_error(payload["password"])
        if complexity_error:
            return jsonify({"error": complexity_error}), 400
        user["password_hash"] = bcrypt.hashpw(payload["password"].encode(), bcrypt.gensalt()).decode()

    save_auth_config(config)
    with get_db() as connection:
        insert_app_log(
            connection,
            "admin",
            "user_updated",
            "Compte utilisateur mis a jour",
            "user",
            username,
            {
                "groups": user.get("groups", []),
                "is_active": user.get("is_active", True),
                "status": user.get("status", "active"),
                "password_changed": bool(payload.get("password")),
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

    config = load_auth_config()
    users = config.get("users", [])
    deleted_user = next((user for user in users if user.get("username") == username), None)
    kept_users = [user for user in users if user.get("username") != username]
    if len(kept_users) == len(users):
        return jsonify({"error": "not_found"}), 404

    config["users"] = kept_users
    save_auth_config(config)
    with get_db() as connection:
        if deleted_user:
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
