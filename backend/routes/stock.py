"""Parc : stocks des ressources suivies par quantite (niveaux, mouvements, seuil d'alerte)."""
from flask import Blueprint, jsonify, request

from auth import current_user, has_permission, login_required, permission_required, rate_limit
from database import get_db
from models.audit import insert_app_log
from models.stock import StockError, add_manual_movement, list_movements, set_threshold, stock_levels

bp = Blueprint("stock", __name__)


def _masked():
    return (current_user() or {}).get("data_scope") == "masked"


@bp.route("/api/stock", methods=["GET"])
@login_required
def stock_list():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        return jsonify({"resources": stock_levels(connection)})


@bp.route("/api/stock/<resource_code>/movements", methods=["GET"])
@login_required
def stock_movements(resource_code):
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    variant = request.args.get("variant")
    with get_db() as connection:
        return jsonify({"movements": list_movements(connection, resource_code, variant, request.args.get("limit", 200), _masked())})


@bp.route("/api/stock/<resource_code>/movements", methods=["POST"])
@login_required
@permission_required("parc.manage")
@rate_limit(max_requests=60, window_seconds=60, scope="stock_movements")
def stock_add_movement(resource_code):
    payload = request.get_json(silent=True) or {}
    actor = (current_user() or {}).get("username")
    with get_db() as connection:
        try:
            signed = add_manual_movement(connection, resource_code, payload.get("kind"), payload.get("quantity"),
                                         payload.get("variant") or "", payload.get("notes") or "", actor)
        except StockError as error:
            return jsonify({"error": error.code, "message": error.message}), 400
        insert_app_log(connection, "admin", "stock_movement", "Mouvement de stock", "resource", resource_code,
                       {"kind": payload.get("kind"), "quantity": signed, "variant": payload.get("variant") or ""}, actor=actor)
        return jsonify({"resources": stock_levels(connection)}), 201


@bp.route("/api/stock/<resource_code>/threshold", methods=["PUT"])
@login_required
@permission_required("parc.manage")
@rate_limit(max_requests=60, window_seconds=60, scope="stock_threshold")
def stock_set_threshold(resource_code):
    payload = request.get_json(silent=True) or {}
    actor = (current_user() or {}).get("username")
    with get_db() as connection:
        try:
            value = set_threshold(connection, resource_code, payload.get("threshold"))
        except StockError as error:
            return jsonify({"error": error.code, "message": error.message}), 400
        insert_app_log(connection, "admin", "stock_threshold", "Seuil d'alerte de stock", "resource", resource_code,
                       {"threshold": value}, actor=actor)
        return jsonify({"resources": stock_levels(connection)})
