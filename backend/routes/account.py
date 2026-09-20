"""Page et API « Mon compte » : l'utilisateur consulte et complete son propre profil."""
from flask import Blueprint, jsonify, send_from_directory

import account_rules
from auth import get_user_record, list_all_groups, login_required, rate_limit, update_user
from config import FRONTEND_DIR
from database import get_db
from flask import request, session
from models.audit import insert_app_log

bp = Blueprint("account", __name__)

_ERROR_MESSAGES = {
    "invalid_email": "Adresse e-mail invalide.",
    "invalid_name": "Nom ou prénom invalide.",
    "identity_locked": "L'identifiant, le nom et le prénom ne peuvent plus être modifiés : contactez un administrateur.",
}


def _profile(username):
    record = get_user_record(username)
    if not record:
        return None
    labels = {group["key"]: group.get("label") or group["key"] for group in list_all_groups()}
    return {
        "username": record["username"],
        "first_name": record.get("first_name") or "",
        "last_name": record.get("last_name") or "",
        "email": record.get("email") or "",
        "service": record.get("service") or "",
        "status": record.get("status") or "active",
        "created_at": record.get("created_at"),
        "groups": [{"key": key, "label": labels.get(key, key)} for key in record.get("groups", [])],
        # Champs deja renseignes : verrouilles pour l'utilisateur (seul un administrateur peut les changer).
        "locked": {key: bool(record.get(key)) for key in account_rules.SELF_EDITABLE_ONCE},
    }


@bp.route("/account.html")
@login_required
def account_page():
    return send_from_directory(FRONTEND_DIR, "account.html")


@bp.route("/api/account", methods=["GET"])
@login_required
def account_get():
    profile = _profile(session.get("user"))
    if not profile:
        return jsonify({"error": "not_found"}), 404
    return jsonify(profile)


@bp.route("/api/account", methods=["PUT"])
@login_required
@rate_limit(max_requests=20, window_seconds=60, scope="account_update")
def account_update():
    username = session.get("user")
    record = get_user_record(username)
    if not record:
        return jsonify({"error": "not_found"}), 404
    fields, error = account_rules.build_self_update(record, request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error, "message": _ERROR_MESSAGES.get(error, error)}), 403 if error == "identity_locked" else 400
    if fields and not update_user(username, **fields):
        return jsonify({"error": "update_failed"}), 500
    if fields:
        with get_db() as connection:
            insert_app_log(connection, "security", "account_self_update", "Profil modifié par l'utilisateur",
                           "user", username, {"fields": sorted(fields)}, actor=username)
    return jsonify(_profile(username))
