import json
import textwrap

from utils import (
    normalize_pdf_text, format_export_datetime,
    get_restitution_signature_datetime, format_status_label,
    format_beneficiary_label, format_restitution_state_label,
    format_restitution_signature_status, format_restitution_decision_label,
    extract_signature_image,
)
from auth import can_export_signature_assets
from models.settings import get_app_settings, DEFAULT_APP_SETTINGS, load_brand_logo_image, load_a_quai_pdf_logo_image
from models.workflow import (
    extract_items, is_restitution_eligible_material_details,
    summarize_dynamic_resource, describe_assignment_condition,
    collect_resource_entries,
)
from pdf.attribution import _AQuaiDoc


def build_restitution_pdf_bytes(title, payload):
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]

    beneficiaire = payload.get("beneficiaire", {})
    dossier = payload.get("dossier", {})
    workflow = payload.get("workflow", {})
    restitution = payload.get("restitution", {})
    signature_datetime = get_restitution_signature_datetime(payload)
    signature_status = restitution.get("signatureStatus") or ("signed" if restitution.get("signatureDataUrl") else "deferred")
    decision_label = format_restitution_decision_label(signature_status, restitution.get("signataireDecision"))
    signature_export_allowed = can_export_signature_assets()
    signature_present = bool(restitution.get("signatureDataUrl"))
    additional_resource_index = {
        resource.get("code") or resource.get("id"): resource
        for resource in payload.get("resources", {}).get("additional", [])
        if isinstance(resource, dict)
    }
    material_entries = {}
    for item in extract_items(payload):
        if item.get("category") != "materiel":
            continue
        details = json.loads(item.get("details_json") or "{}") if item.get("details_json") else {}
        if not is_restitution_eligible_material_details(details):
            continue
        detail_text = summarize_dynamic_resource(details) if details.get("fields") else " - ".join(
            str(value).strip()
            for key, value in details.items()
            if key not in {"selected", "conditionAttribution", "conditionNotes"} and str(value or "").strip()
        )
        material_entries[item["item_key"]] = {
            "itemKey": item["item_key"],
            "label": item["label"],
            "details": detail_text or "-",
            "assignmentSummary": " - ".join(describe_assignment_condition(details)),
        }

    for entry in collect_resource_entries(payload):
        if entry.get("category") != "materiel":
            continue
        resource_details = additional_resource_index.get(entry["itemKey"]) or {}
        if resource_details and not is_restitution_eligible_material_details(resource_details):
            continue
        existing = material_entries.get(entry["itemKey"], {})
        material_entries[entry["itemKey"]] = {
            "itemKey": entry["itemKey"],
            "label": entry.get("label") or existing.get("label") or entry["itemKey"],
            "details": entry.get("details") or existing.get("details") or "-",
            "assignmentSummary": entry.get("assignmentSummary") or existing.get("assignmentSummary") or "",
        }

    material_items = sorted(material_entries.values(), key=lambda item: item.get("label") or item.get("itemKey"))

    restitution_reason_labels = {
        "fin_de_fonction": "Fin de fonction",
        "demission": "Démission",
        "mutation": "Mutation",
        "fin_de_mandat": "Fin de mandat",
        "autre": "Autre",
    }
    restitution_reason = restitution.get("reason") or ""
    restitution_reason_label = restitution_reason_labels.get(restitution_reason) or ("-" if not restitution_reason else restitution_reason)

    sections = [
        (
            "Identification de la restitution",
            [
                f"État du dossier : {format_status_label(workflow.get('status') or 'draft')}",
                f"Date de prise de fonction : {format_export_datetime(payload.get('meta', {}).get('startAt'))}",
                f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
                f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
                f"Motif de restitution : {restitution_reason_label}",
            ],
        ),
        (
            "Bénéficiaire",
            [
                f"Nom : {beneficiaire.get('nom') or '-'}",
                f"Prénom : {beneficiaire.get('prenom') or '-'}",
                f"Qualité : {format_beneficiary_label(beneficiaire.get('qualite'))}",
                f"Service : {beneficiaire.get('service') or '-'}",
                f"Fonction : {beneficiaire.get('fonction') or '-'}",
                f"Mandat : {beneficiaire.get('mandat') or '-'}",
            ],
        ),
    ]

    restitution_lines = []
    for item in material_items:
        item_key = item["itemKey"]
        state = (restitution.get("items") or {}).get(item_key, {})
        state_label = format_restitution_state_label(state.get("state") or state.get("condition"))
        note = state.get("notes") or "-"
        restitution_lines.append(
            f"{item['label']} ({item.get('details') or '-'}) : {state_label} / {note}"
            f"{' / ' + item.get('assignmentSummary') if item.get('assignmentSummary') else ''}"
        )
    if not restitution_lines:
        restitution_lines.append("Aucun matériel n'a encore été renseigné dans la restitution.")
    sections.append(("État des matériels restitués", restitution_lines))

    if signature_export_allowed:
        sections.append(
            (
                "Validation de la restitution",
                [
                    f"Statut de signature : {format_restitution_signature_status(signature_status)}",
                    f"Date de signature : {signature_datetime}",
                    f"Motif si la signature n'a pas été recueillie : {restitution.get('signatureReason') or '-'}",
                    f"Décision du signataire : {decision_label}",
                    f"Réserve / réclamation du signataire : {restitution.get('signataireComment') or '-'}",
                    f"Observations générales : {restitution.get('notes') or '-'}",
                ],
            )
        )
    else:
        sections.append(
            (
                "Validation de la restitution",
                [
                    "Statut de signature : Masquée",
                    "Mention : la signature est réservée aux personnes autorisées.",
                    "Motif si la signature n'a pas été recueillie : Information réservée.",
                    f"Décision du signataire : {decision_label}",
                    f"Réserve / réclamation du signataire : {restitution.get('signataireComment') or '-'}",
                    f"Observations générales : {restitution.get('notes') or '-'}",
                ],
            )
        )

    if restitution.get("signataireDecision") == "with_reservation":
        sections.append(
            (
                "Réserve du signataire",
                [
                    "La restitution a été signée avec réserve par la personne concernée.",
                    f"Réclamation formulée : {restitution.get('signataireComment') or '-'}",
                ],
            )
        )

    brand_logo = load_brand_logo_image()
    aq_logo = load_a_quai_pdf_logo_image()
    sig_bytes = extract_signature_image(restitution.get("signatureDataUrl")) if signature_export_allowed else None

    pdf = _AQuaiDoc(
        normalize_pdf_text(title),
        "Bon de restitution et de suivi des ressources récupérées",
        org_name,
        brand_logo,
        aq_logo,
    )
    pdf.add_page()
    y = _AQuaiDoc._CONTENT_START
    for sec_title, sec_lines in sections:
        y = pdf._draw_section(y, sec_title, sec_lines)

    if sig_bytes:
        reservation_lines = (
            textwrap.wrap(
                normalize_pdf_text(f"Réserve : {restitution.get('signataireComment') or '-'}"),
                width=72,
            )
            if restitution.get("signataireDecision") == "with_reservation"
            else []
        )
        pdf._draw_signature_box(
            y,
            "Signature de restitution",
            signature_datetime,
            "Signature recueillie avec réserve." if restitution.get("signataireDecision") == "with_reservation" else "Signature recueillie lors de la restitution.",
            sig_bytes=sig_bytes,
            reservation_lines=reservation_lines,
        )
    elif signature_present and not signature_export_allowed:
        pdf._draw_masked_signature_box(
            y,
            "Signature de restitution",
            signature_datetime,
        )

    return bytes(pdf.output())
