"""Parc : liste des unites et historique d'une unite (lecture)."""
from flask import Blueprint, jsonify, redirect, request, send_from_directory

from auth import current_user, has_permission, login_required, permission_required, rate_limit
from config import FRONTEND_DIR
from database import get_db
from models.audit import insert_app_log
from models.units import UnitActionError, apply_manual_action, count_units_by_status, get_unit, list_units, release_stale_reservations

bp = Blueprint("units", __name__)


def _masked():
    user = current_user() or {}
    return user.get("data_scope") == "masked"


@bp.route("/parc.html")
@login_required
def parc_page():
    if not has_permission("forms.read_list"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "parc.html")


@bp.route("/api/units", methods=["GET"])
@login_required
def units_list():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        release_stale_reservations(connection)  # requete legere : garde les reservations honnetes sans tache planifiee
        units = list_units(
            connection, request.args.get("resource") or None, (request.args.get("q") or "").strip(),
            request.args.get("status") or None, request.args.get("limit", 200), _masked(),
        )
        counts = count_units_by_status(connection, request.args.get("resource") or None)
    return jsonify({"units": units, "counts": counts})


@bp.route("/api/units/<unit_id>", methods=["GET"])
@login_required
def unit_detail(unit_id):
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        unit = get_unit(connection, unit_id, _masked())
    if not unit:
        return jsonify({"error": "not_found"}), 404
    return jsonify(unit)


_ACTION_STATUS = {"holder_required": 400, "unknown_unit": 404, "invalid_state": 409, "identifier_exists": 409, "different_resource": 409}


@bp.route("/api/units/<unit_id>/actions", methods=["POST"])
@login_required
@permission_required("parc.manage")
@rate_limit(max_requests=60, window_seconds=60, scope="units_actions")
def unit_action(unit_id):
    payload = request.get_json(silent=True) or {}
    actor = (current_user() or {}).get("username")
    with get_db() as connection:
        try:
            unit = apply_manual_action(connection, unit_id, payload.get("action"), payload.get("notes"), actor, payload)
        except UnitActionError as error:
            return jsonify({"error": error.code, "message": error.message}), _ACTION_STATUS.get(error.code, 400)
        insert_app_log(connection, "admin", "unit_action", "Action sur une unité du parc", "unit", unit_id,
                       {"action": payload.get("action")}, actor=actor)
    return jsonify(unit)
