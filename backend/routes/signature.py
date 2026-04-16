from flask import Blueprint, jsonify, request

from utils import utc_now, AppError
from database import get_db
from auth import login_required, has_permission, get_request_client_ip
from models.audit import current_actor, insert_audit_event, insert_app_log
from models.workflow import collect_resource_validation_errors, derive_restitution_workflow_status
from models.forms import get_form, persist_form, build_signature_public_payload, build_restitution_signature_public_payload
from models.signature import (
    signature_link_label, signature_link_scope, signature_link_public_actor,
    serialize_signature_link,
    get_latest_signature_link, get_signature_link_by_id, get_signature_link_by_token,
    create_signature_link, revoke_signature_link,
)

bp = Blueprint("signature", __name__)


@bp.route("/api/forms/<form_id>/signature-link", methods=["GET"])
@login_required
def get_form_signature_link_route(form_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403
    if not get_form(form_id):
        return jsonify({"error": "not_found"}), 404
    with get_db() as connection:
        link_row = get_latest_signature_link(connection, form_id, link_type="assignment")
    return jsonify({"link": serialize_signature_link(link_row)})


@bp.route("/api/forms/<form_id>/signature-link", methods=["POST"])
@login_required
def create_form_signature_link_route(form_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    validity_days = payload.get("validityDays", 7)
    try:
        validity_days = int(validity_days)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_validity_days"}), 400
    if validity_days < 1 or validity_days > 30:
        return jsonify({"error": "invalid_validity_days"}), 400
    try:
        with get_db() as connection:
            link_row = create_signature_link(
                connection, form_id,
                actor=current_actor(),
                expires_in_hours=validity_days * 24,
                link_type="assignment",
            )
    except AppError as error:
        return jsonify({"error": error.code}), error.status
    return jsonify({"link": serialize_signature_link(link_row)}), 201


@bp.route("/api/forms/<form_id>/restitution-signature-link", methods=["GET"])
@login_required
def get_form_restitution_signature_link_route(form_id):
    if not has_permission("forms.restitution"):
        return jsonify({"error": "forbidden"}), 403
    if not get_form(form_id):
        return jsonify({"error": "not_found"}), 404
    with get_db() as connection:
        link_row = get_latest_signature_link(connection, form_id, link_type="restitution")
    return jsonify({"link": serialize_signature_link(link_row)})


@bp.route("/api/forms/<form_id>/restitution-signature-link", methods=["POST"])
@login_required
def create_form_restitution_signature_link_route(form_id):
    if not has_permission("forms.restitution"):
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    validity_days = payload.get("validityDays", 7)
    try:
        validity_days = int(validity_days)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_validity_days"}), 400
    if validity_days < 1 or validity_days > 30:
        return jsonify({"error": "invalid_validity_days"}), 400
    try:
        with get_db() as connection:
            link_row = create_signature_link(
                connection, form_id,
                actor=current_actor(),
                expires_in_hours=validity_days * 24,
                link_type="restitution",
            )
    except AppError as error:
        return jsonify({"error": error.code}), error.status
    return jsonify({"link": serialize_signature_link(link_row)}), 201


@bp.route("/api/signature-links/<link_id>", methods=["DELETE"])
@login_required
def revoke_signature_link_route(link_id):
    with get_db() as connection:
        existing_link = get_signature_link_by_id(connection, link_id)
        if not existing_link:
            return jsonify({"error": "not_found"}), 404
        required_permission = "forms.restitution" if existing_link["link_type"] == "restitution" else "forms.edit"
        if not has_permission(required_permission):
            return jsonify({"error": "forbidden"}), 403
        link_row = revoke_signature_link(connection, link_id, actor=current_actor())
    if not link_row:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"link": serialize_signature_link(link_row)})


@bp.route("/api/signature/<token>", methods=["GET"])
def get_signature_token_route(token):
    with get_db() as connection:
        link_row = get_signature_link_by_token(connection, token)
        if not link_row or link_row["link_type"] != "assignment":
            return jsonify({"error": "invalid_link"}), 404
        if link_row["status"] != "active":
            return jsonify({"error": link_row["status"]}), 410

        now = utc_now()
        connection.execute(
            "UPDATE signature_links SET last_opened_at = ?, last_opened_ip = ? WHERE id = ?",
            (now, get_request_client_ip(), link_row["id"]),
        )
        form_row = connection.execute(
            "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
            (link_row["form_id"],),
        ).fetchone()
        if form_row:
            insert_app_log(
                connection,
                signature_link_scope(link_row["link_type"]),
                "signature_link_opened",
                f"{signature_link_label(link_row['link_type'])} ouvert",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": link_row["link_type"]},
                actor=signature_link_public_actor(link_row["link_type"]),
            )

    form_data = get_form(link_row["form_id"])
    if not form_data:
        return jsonify({"error": "not_found"}), 404
    return jsonify(build_signature_public_payload(form_data, link_row))


@bp.route("/api/signature/<token>/submit", methods=["POST"])
def submit_signature_token_route(token):
    payload = request.get_json(silent=True) or {}
    signature_data = payload.get("signatureDataUrl") or ""
    rgpd_accepted = bool(payload.get("rgpdAccepted"))
    if not signature_data or not rgpd_accepted:
        return jsonify({"error": "signature_and_rgpd_required"}), 400

    with get_db() as connection:
        link_row = get_signature_link_by_token(connection, token)
        if not link_row or link_row["link_type"] != "assignment":
            return jsonify({"error": "invalid_link"}), 404
        if link_row["status"] != "active":
            return jsonify({"error": link_row["status"]}), 410

    form_data = get_form(link_row["form_id"])
    if not form_data:
        return jsonify({"error": "not_found"}), 404

    dossier_payload = form_data["data"]
    dossier_payload.setdefault("validation", {})
    dossier_payload.setdefault("meta", {})
    dossier_payload.setdefault("workflow", {})
    dossier_payload["validation"]["rgpdAccepted"] = True
    dossier_payload["validation"]["signatureDataUrl"] = signature_data
    dossier_payload["validation"]["signedAt"] = utc_now()

    resource_errors = collect_resource_validation_errors(dossier_payload)
    dossier_payload["meta"]["resourceValidationErrors"] = resource_errors
    if resource_errors:
        dossier_payload["workflow"]["status"] = "partial_assignment"
        dossier_payload["meta"]["lockedAt"] = ""
    else:
        dossier_payload["workflow"]["status"] = "active"
        dossier_payload["meta"]["lockedAt"] = dossier_payload["meta"].get("lockedAt") or utc_now()

    try:
        saved = persist_form(dossier_payload)
    except AppError as error:
        return jsonify({"error": error.code}), error.status

    with get_db() as connection:
        connection.execute(
            "UPDATE signature_links SET status = 'used', used_at = ?, last_opened_at = ?, last_opened_ip = ? WHERE id = ?",
            (utc_now(), utc_now(), get_request_client_ip(), link_row["id"]),
        )
        current_link = get_signature_link_by_id(connection, link_row["id"])
        form_row = connection.execute(
            "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
            (link_row["form_id"],),
        ).fetchone()
        if form_row:
            insert_audit_event(
                connection, form_row["dossier_id"], "signature_link_used",
                f"{signature_link_label(link_row['link_type'])} utilise",
                {"form_id": link_row["form_id"], "title": form_row["title"], "link_type": link_row["link_type"]},
            )
            insert_app_log(
                connection,
                signature_link_scope(link_row["link_type"]),
                "signature_link_used",
                f"{signature_link_label(link_row['link_type'])} utilise",
                "form", link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": link_row["link_type"]},
                actor=signature_link_public_actor(link_row["link_type"]),
            )

    return jsonify({"success": True, "summary": saved["summary"], "link": serialize_signature_link(current_link)})


@bp.route("/api/restitution-signature/<token>", methods=["GET"])
def get_restitution_signature_token_route(token):
    with get_db() as connection:
        link_row = get_signature_link_by_token(connection, token)
        if not link_row or link_row["link_type"] != "restitution":
            return jsonify({"error": "invalid_link"}), 404
        if link_row["status"] != "active":
            return jsonify({"error": link_row["status"]}), 410

        connection.execute(
            "UPDATE signature_links SET last_opened_at = ?, last_opened_ip = ? WHERE id = ?",
            (utc_now(), get_request_client_ip(), link_row["id"]),
        )
        form_row = connection.execute(
            "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
            (link_row["form_id"],),
        ).fetchone()
        if form_row:
            insert_app_log(
                connection, "restitution_signature", "signature_link_opened",
                "Lien de signature de restitution ouvert",
                "form", link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": "restitution"},
                actor=signature_link_public_actor("restitution"),
            )

    form_data = get_form(link_row["form_id"])
    if not form_data:
        return jsonify({"error": "not_found"}), 404
    from flask import jsonify as _j
    response = _j(build_restitution_signature_public_payload(form_data, link_row))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/api/restitution-signature/<token>/submit", methods=["POST"])
def submit_restitution_signature_token_route(token):
    payload = request.get_json(silent=True) or {}
    signature_data = payload.get("signatureDataUrl") or ""
    signataire_decision = payload.get("signataireDecision") or "confirmed"
    signataire_comment = str(payload.get("signataireComment") or "").strip()
    if not signature_data:
        return jsonify({"error": "signature_required"}), 400
    if signataire_decision not in {"confirmed", "with_reservation"}:
        return jsonify({"error": "invalid_decision"}), 400
    if signataire_decision == "with_reservation" and not signataire_comment:
        return jsonify({"error": "reservation_comment_required"}), 400

    with get_db() as connection:
        link_row = get_signature_link_by_token(connection, token)
        if not link_row or link_row["link_type"] != "restitution":
            return jsonify({"error": "invalid_link"}), 404
        if link_row["status"] != "active":
            return jsonify({"error": link_row["status"]}), 410

    form_data = get_form(link_row["form_id"])
    if not form_data:
        return jsonify({"error": "not_found"}), 404

    dossier_payload = form_data["data"]
    dossier_payload.setdefault("restitution", {})
    dossier_payload["restitution"]["signatureStatus"] = "signed"
    dossier_payload["restitution"]["signatureReason"] = ""
    dossier_payload["restitution"]["signatureDataUrl"] = signature_data
    dossier_payload["restitution"]["signedAt"] = utc_now()
    dossier_payload["restitution"]["signataireDecision"] = signataire_decision
    dossier_payload["restitution"]["signataireComment"] = signataire_comment
    dossier_payload.setdefault("workflow", {})
    dossier_payload["workflow"]["status"] = derive_restitution_workflow_status(
        dossier_payload["restitution"].get("items", {}),
        dossier_payload["restitution"].get("signatureStatus") or "",
        dossier_payload["restitution"].get("signatureDataUrl") or "",
    )

    try:
        saved = persist_form(dossier_payload, allow_locked_update=True)
    except AppError as error:
        return jsonify({"error": error.code}), error.status

    with get_db() as connection:
        connection.execute(
            "UPDATE signature_links SET status = 'used', used_at = ?, last_opened_at = ?, last_opened_ip = ? WHERE id = ?",
            (utc_now(), utc_now(), get_request_client_ip(), link_row["id"]),
        )
        current_link = get_signature_link_by_id(connection, link_row["id"])
        form_row = connection.execute(
            "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
            (link_row["form_id"],),
        ).fetchone()
        if form_row:
            insert_audit_event(
                connection, form_row["dossier_id"], "signature_link_used",
                "Lien de signature de restitution utilise",
                {"form_id": link_row["form_id"], "title": form_row["title"], "link_type": "restitution"},
            )
            insert_app_log(
                connection, "restitution_signature", "signature_link_used",
                "Lien de signature de restitution utilise",
                "form", link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": "restitution"},
                actor=signature_link_public_actor("restitution"),
            )

    return jsonify({"success": True, "summary": saved["summary"], "link": serialize_signature_link(current_link)})
