"""Administration : assistant d'organisation (catalogue de suggestions, apercu, application).

Le navigateur n'envoie que des choix (contexte, reglages, codes/modeles de ressources) ; le serveur valide, calcule le plan
(models/org_wizard.py) et n'applique que ce qui a ete apercu (hash du plan). Ajout seulement : rien d'utilise n'est supprime.
"""
from flask import Blueprint, jsonify, request

from auth import login_required, permission_required, rate_limit
from database import get_db
from models import org_presets, org_wizard
from models.audit import current_actor
from models.settings import SettingsValidationError, get_app_settings

bp = Blueprint("org_wizard", __name__)


@bp.route("/api/admin/org-presets", methods=["GET"])
@login_required
@permission_required("users.manage")
def org_presets_route():
    """Catalogue de suggestions + etat courant (reglages et ressources) pour pre-remplir l'assistant."""
    with get_db() as connection:
        settings = get_app_settings(connection)
        resources = [dict(row) for row in connection.execute(
            "SELECT code, label, category, tracking_mode, is_active, is_builtin FROM resource_catalog ORDER BY display_order, label").fetchall()]
        for resource in resources:
            resource["used"] = org_wizard._resource_usage(connection, resource["code"]) > 0
        used_types = [row[0] for row in connection.execute(
            "SELECT DISTINCT beneficiary_type FROM dotation_forms WHERE beneficiary_type IS NOT NULL AND beneficiary_type != ''").fetchall()]
    keys = org_presets.WIZARD_SETTING_KEYS + ("setup_completed",)
    return jsonify({**org_presets.catalog_payload(), "current": {key: settings.get(key, "") for key in keys}, "resources": resources,
                    "used_beneficiary_types": used_types})


@bp.route("/api/admin/org-wizard/preview", methods=["POST"])
@login_required
@permission_required("users.manage")
@rate_limit(max_requests=60, window_seconds=600, scope="org_wizard_preview")
def org_wizard_preview():
    payload = request.get_json(silent=True) or {}
    try:
        with get_db() as connection:
            plan = org_wizard.plan_org_wizard(connection, payload)
    except SettingsValidationError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(org_wizard.public_plan(plan))


@bp.route("/api/admin/org-wizard/apply", methods=["POST"])
@login_required
@permission_required("users.manage")
@rate_limit(max_requests=5, window_seconds=600, scope="org_wizard_apply")
def org_wizard_apply():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmed") is not True:
        return jsonify({"error": "Confirmez l'aperçu avant d'appliquer."}), 400
    try:
        result = org_wizard.apply_org_wizard(payload, payload.get("plan_hash"), actor=current_actor())
    except SettingsValidationError as error:
        return jsonify({"error": str(error)}), 400
    except org_wizard.PlanChanged:
        return jsonify({"error": "Le plan a changé depuis l'aperçu : relancez l'aperçu.", "code": "plan_changed"}), 409
    return jsonify(result)


@bp.route("/api/admin/startup-checklist", methods=["GET"])
@login_required
@permission_required("users.manage")
def startup_checklist():
    """Ce qu'il reste a faire pour bien demarrer : chaque point est calcule sur l'etat reel (pas sur des cases cochees a la main)."""
    import backup_schedule
    import backup_targets
    with get_db() as connection:
        settings = get_app_settings(connection)
        wizard_run = connection.execute("SELECT 1 FROM app_logs WHERE action_type = 'org_wizard_applied' LIMIT 1").fetchone()
        active_resources = connection.execute("SELECT COUNT(*) FROM resource_catalog WHERE is_active = 1").fetchone()[0]
    try:
        backup_config = backup_targets.load_config()
        backup_ok = bool(backup_config["schedule"]["enabled"]) and any(d.get("enabled") for d in backup_config["destinations"])
    except Exception:
        backup_ok = False
    items = [
        {"id": "org_name", "label": "Nom de l'organisation renseigné", "done": bool(settings.get("org_name")), "link": "#wizard", "required": True},
        {"id": "wizard", "label": "Assistant d'organisation passé (type, bénéficiaires, ressources)",
         "done": bool(wizard_run) or settings.get("setup_completed") == "1", "link": "#wizard", "required": True},
        {"id": "resources", "label": "Au moins une ressource active", "done": active_resources > 0, "link": "admin-ressources.html", "required": True},
        {"id": "dpo", "label": "Contact protection des données (DPO / référent) renseigné", "done": bool(settings.get("dpo_email")), "link": "#wizard", "required": True},
        {"id": "backup", "label": "Sauvegarde automatique activée avec une destination", "done": backup_ok, "link": "admin-db.html", "required": True},
        {"id": "support", "label": "Contact support renseigné", "done": bool(settings.get("support_email")), "link": "#wizard", "required": False},
        {"id": "domains", "label": "Domaines e-mail autorisés définis", "done": bool(settings.get("email_domains")), "link": "admin-personnalisation.html", "required": False},
    ]
    done = sum(1 for item in items if item["done"])
    return jsonify({"items": items, "done": done, "total": len(items), "percent": round(100 * done / len(items))})
