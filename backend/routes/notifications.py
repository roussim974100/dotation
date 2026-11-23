"""Notifications et titulaires de service (voir models/notifications.py)."""
from flask import Blueprint, jsonify, request, send_from_directory, session

from auth import current_user, get_user_record, has_permission, login_required, permission_required
from config import FRONTEND_DIR
from database import get_db
from models.audit import insert_app_log
from models.notifications import (
    apply_service_assignments, clear_cache, open_tasks, service_referents, set_service_referents,
)
from models.service_tasks import form_service_tasks, mark_done, recently_done, reopen

bp = Blueprint("notifications", __name__)


@bp.route("/tasks.html")
@login_required
def tasks_page():
    """Page « Mes taches » : tout ce qui me concerne, avec « Fait » et l'historique recent."""
    return send_from_directory(FRONTEND_DIR, "tasks.html")


@bp.route("/api/notifications", methods=["GET"])
@login_required
def list_notifications():
    with get_db() as connection:
        tasks = open_tasks(connection, current_user())
    return jsonify({"tasks": tasks, "count": len(tasks)})


@bp.route("/api/admin/resources/services", methods=["POST"])
@login_required
@permission_required("users.manage")
def assign_resources_to_services():
    """Choix de l'administrateur : rattache des ressources a un service du catalogue (tout ou rien)."""
    payload = request.get_json(silent=True) or {}
    with get_db() as connection:
        count, error = apply_service_assignments(connection, payload.get("assignments"), session.get("user"))
        if error:
            return jsonify({"error": error}), 400
        remaining = open_tasks(connection, current_user())
    return jsonify({"assigned": count, "tasks": remaining, "count": len(remaining)})


def _is_active_account(username):
    record = get_user_record(username)
    return bool(record) and record.get("is_active", True) and record.get("status") not in ("pending", "disabled")


@bp.route("/api/admin/services/<service_id>/referents", methods=["GET"])
@login_required
@permission_required("users.manage")
def get_service_referents(service_id):
    with get_db() as connection:
        return jsonify({"usernames": service_referents(connection, service_id)})


@bp.route("/api/admin/services/<service_id>/referents", methods=["PUT"])
@login_required
@permission_required("users.manage")
def put_service_referents(service_id):
    """Remplace la liste des comptes titulaires du service (ils recoivent ses taches)."""
    payload = request.get_json(silent=True) or {}
    usernames = payload.get("usernames")
    if not isinstance(usernames, list):
        return jsonify({"error": "usernames_required"}), 400
    with get_db() as connection:
        saved, error = set_service_referents(connection, service_id, usernames, _is_active_account)
        if error:
            return jsonify({"error": error}), 404 if error == "not_found" else 400
        insert_app_log(connection, "admin", "service_referents_updated", "Titulaires d'un service mis a jour", "service", service_id,
                       {"usernames": saved}, actor=session.get("user"))
    return jsonify({"usernames": saved})


@bp.route("/api/service-tasks/done", methods=["POST"])
@login_required
def service_task_done():
    """« Fait » : un titulaire du service (ou un administrateur si le service n'a aucun titulaire actif) termine une tache ;
    elle disparait pour tous ses collegues."""
    payload = request.get_json(silent=True) or {}
    user = current_user()
    with get_db() as connection:
        ok, error = mark_done(connection, user, payload.get("kind"), payload.get("form_id"), payload.get("item_key"))
        if not ok:
            return jsonify({"error": error}), 404 if error == "task_not_found" else 400
        clear_cache()
        tasks = open_tasks(connection, user)
    return jsonify({"done": True, "tasks": tasks, "count": len(tasks)})


@bp.route("/api/service-tasks/recent", methods=["GET"])
@login_required
def service_tasks_recent():
    """Ce qui a ete termine ces 30 derniers jours dans mes services (page « Mes taches », avec possibilite de rouvrir)."""
    with get_db() as connection:
        return jsonify({"items": recently_done(connection, current_user())})


@bp.route("/api/service-tasks/reopen", methods=["POST"])
@login_required
def service_task_reopen():
    """Rouvre un « Fait » enregistre par erreur : la tache revient chez tous les titulaires du service."""
    payload = request.get_json(silent=True) or {}
    user = current_user()
    with get_db() as connection:
        ok, error = reopen(connection, user, payload.get("kind"), payload.get("form_id"), payload.get("item_key"))
        if not ok:
            return jsonify({"error": error}), 404 if error == "task_not_found" else 400
        clear_cache()
        tasks = open_tasks(connection, user)
    return jsonify({"reopened": True, "tasks": tasks, "count": len(tasks)})


@bp.route("/api/forms/<form_id>/service-tasks", methods=["GET"])
@login_required
def form_service_tasks_route(form_id):
    """Fiche d'un dossier : taches des services (a faire, faites par qui et quand). Meme droit que l'ouverture du dossier."""
    if not has_permission("forms.read_detail"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        if not connection.execute("SELECT 1 FROM dotation_forms WHERE id = ?", (form_id,)).fetchone():
            return jsonify({"error": "not_found"}), 404
        return jsonify({"items": form_service_tasks(connection, form_id)})
