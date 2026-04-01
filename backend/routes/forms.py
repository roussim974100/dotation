import io
import json
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from flask import Blueprint, jsonify, make_response, request, session

from utils import (
    utc_now, format_export_datetime, format_status_label,
    format_beneficiary_label, format_restitution_state_label,
    dossier_type_label, slugify_filename,
)
from database import get_db
from auth import login_required, has_permission, get_request_client_ip
from models.audit import insert_audit_event, insert_app_log, insert_deleted_item
from models.workflow import (
    summarize_dynamic_resource, collect_resource_entries,
    derive_restitution_workflow_status, collect_resource_validation_errors,
)
from models.forms import persist_form, row_to_summary, get_form
from pdf.attribution import build_pdf_bytes
from pdf.restitution import build_restitution_pdf_bytes
import urllib.parse

bp = Blueprint("forms", __name__)


def download_response(file_bytes, filename, content_type):
    response = make_response(file_bytes)
    response.headers["Content-Type"] = content_type
    encoded_filename = urllib.parse.quote(filename, safe="")
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
    return response


def spreadsheet_cell(value, style_id="cell"):
    text = "" if value is None else str(value)
    return (
        f'<Cell ss:StyleID="{style_id}">'
        f'<Data ss:Type="String">{xml_escape(text)}</Data>'
        f"</Cell>"
    )


def build_excel_workbook(rows, item_rows):
    headers = [
        "ID dossier", "Titre", "Etat", "Type de dossier", "Qualite",
        "Nom", "Prenom", "Service", "Fonction", "Mandat",
        "Service de destination", "Date de prise de fonction",
        "Date de remise", "Date de restitution", "RGPD", "Signature",
        "Ressources attribuees", "Motif restitution", "Observations",
        "Cree le", "Mis a jour le",
    ]

    workbook_rows = [
        "<Row>" + "".join(spreadsheet_cell(value, "header") for value in headers) + "</Row>"
    ]

    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        beneficiaire = payload.get("beneficiaire", {})
        dossier = payload.get("dossier", {})
        validation = payload.get("validation", {})
        resources = collect_resource_entries(payload)
        workbook_rows.append(
            "<Row>" + "".join(
                [
                    spreadsheet_cell(row["id"]),
                    spreadsheet_cell(row["title"]),
                    spreadsheet_cell(format_status_label(row["status"])),
                    spreadsheet_cell(dossier_type_label(row["dossier_type"])),
                    spreadsheet_cell(format_beneficiary_label(row["beneficiary_type"])),
                    spreadsheet_cell(beneficiaire.get("nom") or row["nom"]),
                    spreadsheet_cell(beneficiaire.get("prenom") or row["prenom"]),
                    spreadsheet_cell(beneficiaire.get("service") or row["service"]),
                    spreadsheet_cell(beneficiaire.get("fonction") or row["fonction"]),
                    spreadsheet_cell(beneficiaire.get("mandat") or row["mandat"]),
                    spreadsheet_cell(dossier.get("serviceDestination") or "-"),
                    spreadsheet_cell(format_export_datetime(payload.get("meta", {}).get("startAt"))),
                    spreadsheet_cell(format_export_datetime(row["assigned_at"])),
                    spreadsheet_cell(format_export_datetime(row["returned_at"])),
                    spreadsheet_cell("Oui" if row["rgpd_accepted"] else "Non"),
                    spreadsheet_cell("Oui" if validation.get("signatureDataUrl") else "Non"),
                    spreadsheet_cell("\n".join(f"{item['service']} - {item['label']} : {item['details']}" for item in resources) or "-"),
                    spreadsheet_cell(row["return_reason"] or "-"),
                    spreadsheet_cell(row["return_notes"] or "-"),
                    spreadsheet_cell(format_export_datetime(row["created_at"])),
                    spreadsheet_cell(format_export_datetime(row["updated_at"])),
                ]
            ) + "</Row>"
        )

    item_headers = [
        "ID dossier", "Titre dossier", "Service emetteur", "Ressource",
        "Categorie", "Details", "Etat restitution", "Date restitution", "Observation",
    ]
    resource_rows_xml = [
        "<Row>" + "".join(spreadsheet_cell(value, "header") for value in item_headers) + "</Row>"
    ]

    for row in item_rows:
        details = json.loads(row["details_json"] or "{}")
        detail_text = summarize_dynamic_resource(details) if details.get("fields") else " - ".join(
            str(value).strip()
            for key, value in details.items()
            if key not in {"selected", "conditionAttribution", "conditionNotes"} and str(value or "").strip()
        )
        resource_rows_xml.append(
            "<Row>" + "".join(
                [
                    spreadsheet_cell(row["form_id"]),
                    spreadsheet_cell(row["title"]),
                    spreadsheet_cell(details.get("issuerService") or details.get("issuer_service") or "-"),
                    spreadsheet_cell(row["label"]),
                    spreadsheet_cell(row["category"]),
                    spreadsheet_cell(detail_text or "-"),
                    spreadsheet_cell(format_restitution_state_label(row["return_condition"])),
                    spreadsheet_cell(format_export_datetime(row["returned_at"])),
                    spreadsheet_cell(row["notes"] or "-"),
                ]
            ) + "</Row>"
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Styles>
    <Style ss:ID="Default" ss:Name="Normal">
      <Alignment ss:Vertical="Top" ss:WrapText="1"/>
      <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#1F2933"/>
      <Interior ss:Color="#FFFFFF" ss:Pattern="Solid"/>
      <Borders>
        <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D4DDE6"/>
        <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D4DDE6"/>
        <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D4DDE6"/>
        <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D4DDE6"/>
      </Borders>
    </Style>
    <Style ss:ID="header">
      <Alignment ss:Vertical="Center" ss:WrapText="1"/>
      <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#FFFFFF"/>
      <Interior ss:Color="#0F5B8D" ss:Pattern="Solid"/>
      <Borders>
        <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#0A4267"/>
        <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#0A4267"/>
        <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#0A4267"/>
        <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#0A4267"/>
      </Borders>
    </Style>
    <Style ss:ID="cell">
      <Alignment ss:Vertical="Top" ss:WrapText="1"/>
      <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#1F2933"/>
    </Style>
  </Styles>
  <Worksheet ss:Name="Dossiers">
    <Table>
      {''.join(workbook_rows)}
    </Table>
  </Worksheet>
  <Worksheet ss:Name="Ressources">
    <Table>
      {''.join(resource_rows_xml)}
    </Table>
  </Worksheet>
</Workbook>"""


@bp.route("/api/forms/unc-paths", methods=["GET"])
@login_required
def list_unc_paths():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    rows = get_db().execute("SELECT payload_json FROM dotation_forms WHERE payload_json IS NOT NULL").fetchall()
    seen = set()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        for e in payload.get("unc_acces") or []:
            chemin = (e.get("chemin") or "").strip()
            if chemin:
                seen.add(chemin)
    return jsonify(sorted(seen, key=str.lower))


@bp.route("/api/forms", methods=["GET"])
@login_required
def list_forms():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    status = request.args.get("status")
    search = request.args.get("search")
    query = "SELECT * FROM dotation_forms"
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)

    if search:
        conditions.append("(nom LIKE ? OR prenom LIKE ? OR title LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY updated_at DESC"

    with get_db() as connection:
        rows = connection.execute(query, params).fetchall()

    return jsonify([row_to_summary(row) for row in rows])


@bp.route("/api/forms/export", methods=["GET"])
@login_required
def export_forms():
    if not has_permission("forms.export"):
        return jsonify({"error": "forbidden"}), 403

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, title, status, beneficiary_type, nom, prenom, service, fonction,
                   mandat, dossier_type, rgpd_accepted, assigned_at, returned_at, return_reason,
                   return_notes, created_at, updated_at, payload_json
            FROM dotation_forms
            ORDER BY updated_at DESC
            """
        ).fetchall()
        item_rows = connection.execute(
            """
            SELECT di.*, df.title
            FROM dotation_items di
            JOIN dotation_forms df ON df.id = di.form_id
            ORDER BY df.updated_at DESC, di.id ASC
            """
        ).fetchall()

    workbook_xml = build_excel_workbook(rows, item_rows)
    response = make_response(workbook_xml)
    response.headers["Content-Type"] = "application/vnd.ms-excel; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="dossiers_attribution_export.xls"'
    return response


@bp.route("/api/forms/<form_id>/pdf", methods=["GET"])
@login_required
def export_form_pdf(form_id):
    if not has_permission("forms.export"):
        return jsonify({"error": "forbidden"}), 403
    form_data = get_form(form_id)
    if not form_data:
        return jsonify({"error": "not_found"}), 404

    title = form_data["summary"]["title"]
    pdf_bytes = build_pdf_bytes(title, form_data["data"])
    filename = f"attribution_{slugify_filename(title, 'dossier_attribution')}.pdf"
    return download_response(pdf_bytes, filename, "application/pdf")


@bp.route("/api/forms/<form_id>/restitution-pdf", methods=["GET"])
@login_required
def export_restitution_pdf(form_id):
    if not has_permission("forms.export"):
        return jsonify({"error": "forbidden"}), 403
    form_data = get_form(form_id)
    if not form_data:
        return jsonify({"error": "not_found"}), 404

    restitution = form_data["data"].get("restitution", {})
    if not (
        restitution.get("returnedAt")
        or restitution.get("notes")
        or restitution.get("reason")
        or restitution.get("signatureDataUrl")
        or restitution.get("signatureReason")
        or restitution.get("items")
    ):
        return jsonify({"error": "restitution_not_ready"}), 400

    title = f"Restitution - {form_data['summary']['title']}"
    pdf_bytes = build_restitution_pdf_bytes(title, form_data["data"])
    filename = f"{slugify_filename(title, 'restitution')}.pdf"
    return download_response(pdf_bytes, filename, "application/pdf")


@bp.route("/api/forms/export-pdf-batch", methods=["POST"])
@login_required
def export_forms_pdf_batch():
    if not has_permission("forms.export"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ids_required"}), 400

    archive = io.BytesIO()
    exported_count = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for form_id in ids:
            form_data = get_form(str(form_id))
            if not form_data:
                continue
            title = form_data["summary"]["title"]
            pdf_bytes = build_pdf_bytes(title, form_data["data"])
            zip_file.writestr(f"attribution_{slugify_filename(title, 'dossier_attribution')}.pdf", pdf_bytes)
            exported_count += 1

    if exported_count == 0:
        return jsonify({"error": "not_found"}), 404

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return download_response(archive.getvalue(), f"dossiers_attribution_pdf_{timestamp}.zip", "application/zip")


@bp.route("/api/forms/export-restitution-pdf-batch", methods=["POST"])
@login_required
def export_restitution_forms_pdf_batch():
    if not has_permission("forms.export"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "invalid_ids"}), 400

    archive = io.BytesIO()
    exported_count = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for form_id in ids:
            form_data = get_form(str(form_id))
            if not form_data:
                continue
            restitution = form_data["data"].get("restitution", {})
            if not (
                restitution.get("returnedAt")
                or restitution.get("notes")
                or restitution.get("reason")
                or restitution.get("signatureDataUrl")
                or restitution.get("signatureReason")
                or restitution.get("items")
            ):
                continue
            title = f"Restitution - {form_data['summary']['title']}"
            pdf_bytes = build_restitution_pdf_bytes(title, form_data["data"])
            zip_file.writestr(f"{slugify_filename(title, 'restitution')}.pdf", pdf_bytes)
            exported_count += 1

    if exported_count == 0:
        return jsonify({"error": "not_found"}), 404

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return download_response(archive.getvalue(), f"restitutions_pdf_{timestamp}.zip", "application/zip")


@bp.route("/api/forms/<form_id>", methods=["GET"])
@login_required
def get_form_route(form_id):
    if not has_permission("forms.read_detail"):
        return jsonify({"error": "forbidden"}), 403
    form_data = get_form(form_id)
    if not form_data:
        return jsonify({"error": "not_found"}), 404
    return jsonify(form_data)


@bp.route("/api/forms", methods=["POST"])
@login_required
def create_form():
    if not has_permission("forms.create"):
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    try:
        form_data = persist_form(payload)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(form_data), 201


@bp.route("/api/forms/<form_id>", methods=["PUT"])
@login_required
def update_form(form_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    payload.setdefault("meta", {})["id"] = form_id
    try:
        form_data = persist_form(payload)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(form_data)


@bp.route("/api/forms/<form_id>/reopen", methods=["POST"])
@login_required
def reopen_form(form_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403

    with get_db() as connection:
        row = connection.execute(
            "SELECT id, dossier_id, status, title, payload_json FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        if row["status"] not in {"draft", "partial_assignment", "awaiting_signature"}:
            return jsonify({"error": "not_reopenable"}), 400

        import json as _json
        payload = _json.loads(row["payload_json"] or "{}")
        payload.setdefault("meta", {})
        payload["meta"]["reopenCount"] = int(payload["meta"].get("reopenCount") or 0) + 1
        payload["meta"]["lastReopenedAt"] = datetime.now(timezone.utc).isoformat()
        payload["meta"]["lastReopenedBy"] = session.get("user") or "system"

        connection.execute(
            "UPDATE dotation_forms SET payload_json = ? WHERE id = ?",
            (_json.dumps(payload, ensure_ascii=False), form_id),
        )
        insert_audit_event(
            connection,
            row["dossier_id"],
            "form_reopened",
            "Dossier rouvert",
            {"form_id": form_id, "title": row["title"], "reopen_count": payload["meta"]["reopenCount"]},
        )
        insert_app_log(
            connection,
            "dossier",
            "form_reopened",
            "Dossier rouvert",
            "form",
            form_id,
            {"title": row["title"], "reopen_count": payload["meta"]["reopenCount"]},
        )

    return jsonify({"meta": payload["meta"]})


@bp.route("/api/forms/<form_id>/restitution", methods=["PATCH"])
@login_required
def update_restitution(form_id):
    if not has_permission("forms.restitution"):
        return jsonify({"error": "forbidden"}), 403
    existing = get_form(form_id)
    if not existing:
        return jsonify({"error": "not_found"}), 404

    patch = request.get_json(silent=True) or {}
    payload = existing["data"]
    payload.setdefault("workflow", {})
    payload.setdefault("restitution", {})
    payload["restitution"]["returnedAt"] = patch.get("returnedAt", payload["restitution"].get("returnedAt"))
    payload["restitution"]["reason"] = patch.get("reason", payload["restitution"].get("reason"))
    payload["restitution"]["notes"] = patch.get("notes", payload["restitution"].get("notes"))
    payload["restitution"]["items"] = patch.get("items", payload["restitution"].get("items", {}))
    payload["restitution"]["signatureStatus"] = patch.get("signatureStatus", payload["restitution"].get("signatureStatus"))
    payload["restitution"]["signatureReason"] = patch.get("signatureReason", payload["restitution"].get("signatureReason"))
    payload["restitution"]["signatureDataUrl"] = patch.get("signatureDataUrl", payload["restitution"].get("signatureDataUrl"))
    payload["restitution"]["signedAt"] = patch.get("signedAt", payload["restitution"].get("signedAt"))
    payload["restitution"]["signataireDecision"] = patch.get("signataireDecision", payload["restitution"].get("signataireDecision"))
    payload["restitution"]["signataireComment"] = patch.get("signataireComment", payload["restitution"].get("signataireComment"))
    computed_status = derive_restitution_workflow_status(
        payload["restitution"].get("items", {}),
        payload["restitution"].get("signatureStatus") or "",
        payload["restitution"].get("signatureDataUrl") or "",
    )
    payload["workflow"]["status"] = "partial_return" if patch.get("keepPending") else computed_status

    form_data = persist_form(payload, allow_locked_update=True)
    with get_db() as connection:
        insert_app_log(
            connection,
            "restitution",
            "restitution_updated",
            "Restitution mise a jour",
            "form",
            form_id,
            {
                "status": payload.get("workflow", {}).get("status"),
                "returned_at": payload.get("restitution", {}).get("returnedAt"),
            },
        )
    return jsonify(form_data)


@bp.route("/api/forms/<form_id>", methods=["DELETE"])
@login_required
def delete_form(form_id):
    if not has_permission("forms.delete"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        row = connection.execute(
            "SELECT title, dossier_id, payload_json FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).fetchone()
        if row:
            insert_deleted_item(
                connection,
                "form",
                form_id,
                row["title"],
                json.loads(row["payload_json"] or "{}"),
            )
        deleted = connection.execute(
            "DELETE FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "dossier",
                "form_deleted",
                "Dossier d'attribution supprime",
                "form",
                form_id,
                {"title": row["title"] if row else "", "dossier_id": row["dossier_id"] if row else ""},
            )

    if not deleted:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"deleted": True})
