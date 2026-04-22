import json

from flask import Blueprint, jsonify, request

from auth import login_required, has_permission
from database import get_db
from models.audit import insert_app_log
from models.audit import current_actor
from models import pools as pool_model
from utils import generate_id

bp = Blueprint("pools", __name__)


def _check_read():
    return has_permission("forms.read_list")


def _check_manage():
    return has_permission("pools.manage")


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------

@bp.route("/api/pools", methods=["GET"])
@login_required
def list_pools():
    if not _check_read():
        return jsonify({"error": "forbidden"}), 403
    with get_db() as conn:
        return jsonify(pool_model.list_pools(conn))


@bp.route("/api/pools", methods=["POST"])
@login_required
def create_pool():
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "label_required"}), 400
    with get_db() as conn:
        pool_id = pool_model.create_pool(conn, label, data.get("notes"))
        insert_app_log(conn, "admin", "create", "Création d'un parc mutualisé",
                       target_type="pool", target_id=pool_id,
                       target_label=label, actor=current_actor())
        return jsonify({"id": pool_id}), 201


@bp.route("/api/pools/<pool_id>", methods=["GET"])
@login_required
def get_pool(pool_id):
    if not _check_read():
        return jsonify({"error": "forbidden"}), 403
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
    if not pool:
        return jsonify({"error": "not_found"}), 404
    return jsonify(pool)


@bp.route("/api/pools/<pool_id>", methods=["PUT"])
@login_required
def update_pool(pool_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "label_required"}), 400
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        pool_model.update_pool(conn, pool_id, label, data.get("notes"))
        insert_app_log(conn, "admin", "update", "Modification d'un parc mutualisé",
                       target_type="pool", target_id=pool_id,
                       target_label=label, actor=current_actor())
    return jsonify({"ok": True})


@bp.route("/api/pools/<pool_id>", methods=["DELETE"])
@login_required
def delete_pool(pool_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        pool_model.delete_pool(conn, pool_id)
        insert_app_log(conn, "admin", "delete", "Suppression d'un parc mutualisé",
                       target_type="pool", target_id=pool_id,
                       target_label=pool["label"], actor=current_actor())
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@bp.route("/api/pools/<pool_id>/items", methods=["POST"])
@login_required
def add_item(pool_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    resource_type = (data.get("resource_type") or "").strip()
    if not label or not resource_type:
        return jsonify({"error": "label_and_type_required"}), 400
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        pool_model.add_item(conn, pool_id, resource_type, label,
                            data.get("serial_number"), data.get("notes"))
        insert_app_log(conn, "admin", "create", f"Ajout d'un équipement au parc « {pool['label']} »",
                       target_type="pool", target_id=pool_id,
                       target_label=pool["label"], actor=current_actor())
    return jsonify({"ok": True}), 201


@bp.route("/api/pools/<pool_id>/items/<int:item_id>", methods=["PUT"])
@login_required
def update_item(pool_id, item_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    resource_type = (data.get("resource_type") or "").strip()
    if not label or not resource_type:
        return jsonify({"error": "label_and_type_required"}), 400
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        pool_model.update_item(conn, item_id, pool_id, resource_type, label,
                               data.get("serial_number"), data.get("notes"))
    return jsonify({"ok": True})


@bp.route("/api/pools/<pool_id>/items/<int:item_id>", methods=["DELETE"])
@login_required
def delete_item(pool_id, item_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        pool_model.delete_item(conn, item_id, pool_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@bp.route("/api/pools/<pool_id>/members", methods=["POST"])
@login_required
def add_member(pool_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    form_id = (data.get("form_id") or "").strip() or None
    beneficiary_name = (data.get("beneficiary_name") or "").strip() or None
    if not form_id and not beneficiary_name:
        return jsonify({"error": "form_id_or_name_required"}), 400
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        if form_id:
            row = conn.execute("SELECT id FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
            if not row:
                return jsonify({"error": "form_not_found"}), 404
        pool_model.add_member(conn, pool_id, form_id, beneficiary_name)
        label = beneficiary_name or form_id
        insert_app_log(conn, "admin", "create", f"Ajout d'un membre au parc « {pool['label']} »",
                       target_type="pool", target_id=pool_id,
                       target_label=pool["label"], actor=current_actor())
    return jsonify({"ok": True}), 201


@bp.route("/api/pools/<pool_id>/members/<int:member_id>", methods=["PUT"])
@login_required
def update_member(pool_id, member_id):
    """Lie un membre sans dossier à un dossier existant."""
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    form_id = (data.get("form_id") or "").strip()
    if not form_id:
        return jsonify({"error": "form_id_required"}), 400
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        row = conn.execute("SELECT id FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
        if not row:
            return jsonify({"error": "form_not_found"}), 404
        pool_model.link_member_to_form(conn, member_id, pool_id, form_id)
        insert_app_log(conn, "admin", "update", f"Liaison dossier dans le parc « {pool['label']} »",
                       target_type="pool", target_id=pool_id,
                       target_label=pool["label"], actor=current_actor())
    return jsonify({"ok": True})


@bp.route("/api/pools/<pool_id>/members/<int:member_id>", methods=["DELETE"])
@login_required
def delete_member(pool_id, member_id):
    if not _check_manage():
        return jsonify({"error": "forbidden"}), 403
    with get_db() as conn:
        pool = pool_model.get_pool(conn, pool_id)
        if not pool:
            return jsonify({"error": "not_found"}), 404
        pool_model.delete_member(conn, member_id, pool_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Lookup : pools d'un dossier
# ---------------------------------------------------------------------------

@bp.route("/api/pools/for-form/<form_id>", methods=["GET"])
@login_required
def pools_for_form(form_id):
    if not _check_read():
        return jsonify({"error": "forbidden"}), 403
    with get_db() as conn:
        return jsonify(pool_model.get_pools_for_form(conn, form_id))
