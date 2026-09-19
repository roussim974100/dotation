"""Materiel restitue disponible pour une nouvelle attribution."""
import json

from flask import Blueprint, jsonify

from auth import has_permission, login_required
from database import get_db
from models.inventory import list_available_units, resolve_identifier_key

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
        field_keys = {f["key"] for f in schema if isinstance(f, dict) and f.get("key")}
        items = list_available_units(connection, row["code"], identifier_key, field_keys) if identifier_key else []
    return jsonify({"identifierKey": identifier_key, "items": items})
