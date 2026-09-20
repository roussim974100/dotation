"""Materiel restitue disponible pour une nouvelle attribution."""
import json

from flask import Blueprint, jsonify, request

from auth import has_permission, login_required
from database import get_db
from models.inventory import resolve_identifier_key
from models.units import available_units_for_resource, find_holder_unit

bp = Blueprint("inventory", __name__)


@bp.route("/api/catalog/available/<resource_id>", methods=["GET"])
@login_required
def available_units(resource_id):
    if not (has_permission("forms.create") or has_permission("forms.edit")):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        row = connection.execute(
            "SELECT code, category, field_schema_json FROM resource_catalog WHERE id = ? AND is_active = 1", (resource_id,)
        ).fetchone()
        if not row:
            return jsonify({"identifierKey": None, "items": []})
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        # Reutilisation reservee au materiel (pas aux acces numeriques comme un compte VPN).
        identifier_key = resolve_identifier_key(schema) if row["category"] == "materiel" else None
        items = available_units_for_resource(connection, row["code"]) if identifier_key else []
    return jsonify({"identifierKey": identifier_key, "items": items})


@bp.route("/api/catalog/holder/<resource_id>", methods=["GET"])
@login_required
def current_holder(resource_id):
    """Avertissement de doublon : ce materiel est-il deja attribue dans un autre dossier ?"""
    if not (has_permission("forms.create") or has_permission("forms.edit")):
        return jsonify({"error": "forbidden"}), 403
    value = (request.args.get("value") or "").strip()
    with get_db() as connection:
        row = connection.execute(
            "SELECT code, category, field_schema_json FROM resource_catalog WHERE id = ? AND is_active = 1", (resource_id,)
        ).fetchone()
        if not row or not value or row["category"] != "materiel":
            return jsonify({"holder": None})
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        identifier_key = resolve_identifier_key(schema)
        if not identifier_key:
            return jsonify({"holder": None})
        holder = find_holder_unit(connection, row["code"], value, request.args.get("exclude") or None)
    return jsonify({"holder": holder})
