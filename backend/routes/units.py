"""Parc : liste des unites et historique d'une unite (lecture)."""
from flask import Blueprint, jsonify, request

from auth import current_user, has_permission, login_required
from database import get_db
from models.units import get_unit, list_units

bp = Blueprint("units", __name__)


def _masked():
    user = current_user() or {}
    return user.get("data_scope") == "masked"


@bp.route("/api/units", methods=["GET"])
@login_required
def units_list():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        units = list_units(
            connection, request.args.get("resource") or None, (request.args.get("q") or "").strip(),
            request.args.get("status") or None, request.args.get("limit", 200), _masked(),
        )
    return jsonify({"units": units})


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
