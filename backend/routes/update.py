"""Administration : nouvelle version disponible et mise a jour depuis le navigateur.

Securite : l'application NE LANCE AUCUNE commande. Elle depose un fichier de demande ; une unite systemd (root, installee
par setup/install-web-update.sh) surveille ce fichier et lance deploy.sh, dont la branche est figee. Fonction desactivee
par defaut (APP_ALLOW_WEB_UPDATE=1 + unite installee). Reservee au droit users.manage, avec le mot de passe de l'administrateur.
"""
import update_check
from flask import Blueprint, jsonify, request

from auth import check_user, current_user, login_required, permission_required, rate_limit
from database import get_db
from models.audit import insert_app_log

bp = Blueprint("update", __name__)


@bp.route("/api/admin/update/status", methods=["GET"])
@login_required
@permission_required("users.manage")
def update_status():
    return jsonify(update_check.status())


@bp.route("/api/admin/update/check", methods=["POST"])
@login_required
@permission_required("users.manage")
@rate_limit(max_requests=10, window_seconds=600, scope="update_check")
def update_check_now():
    return jsonify(update_check.status(force=True))


@bp.route("/api/admin/update/start", methods=["POST"])
@login_required
@permission_required("users.manage")
@rate_limit(max_requests=3, window_seconds=600, scope="update_start")
def update_start():
    payload = request.get_json(silent=True) or {}
    username = (current_user() or {}).get("username")
    if not update_check.can_update():
        return jsonify({"error": "update_disabled", "message": "La mise à jour depuis le navigateur n'est pas activée sur ce serveur."}), 403
    if check_user(username, str(payload.get("password") or "")) != "ok":
        return jsonify({"error": "wrong_password", "message": "Mot de passe incorrect."}), 403
    if update_check.update_in_progress():
        return jsonify({"error": "already_running", "message": "Une mise à jour est déjà en cours."}), 409
    state = update_check.status(force=True)
    if not state["available"]:
        return jsonify({"error": "no_update", "message": "Aucune nouvelle version n'est disponible."}), 409
    try:
        update_check.request_update(username, state["latest"])
    except OSError:
        return jsonify({"error": "request_failed", "message": "Impossible de déposer la demande de mise à jour."}), 500
    with get_db() as connection:
        insert_app_log(connection, "admin", "update_requested", "Mise à jour demandée depuis le navigateur", "system", None,
                       {"from": state["current"], "to": state["latest"]}, actor=username)
    return jsonify({"requested": True, "from": state["current"], "to": state["latest"]}), 202
