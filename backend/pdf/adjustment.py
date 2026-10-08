"""PDF d'UN ajustement de dossier actif (3.72.0) : la preuve, à remettre ou à archiver, de ce qui a été ajouté, retiré ou changé et de
la manière dont le geste a été signé (en présentiel, à distance, ou par un responsable à la place du bénéficiaire).

Même charte que les autres PDF (`_AQuaiDoc` : en-tête, logos, sections encadrées). L'image de la signature n'est incluse que pour qui
peut exporter les signatures (`can_export_signature_assets`) ; un ajustement encore « en attente de signature » le dit clairement."""
from auth import can_export_signature_assets
from models.settings import DEFAULT_APP_SETTINGS, get_app_settings, load_a_quai_pdf_logo_image, load_brand_logo_image
from pdf.attribution import _AQuaiDoc
from utils import extract_signature_image, format_beneficiary_label, format_export_datetime, normalize_pdf_text

STATE_LABELS = {"conforme": "Conforme", "degrade": "Dégradé", "autre": "Autre condition"}
MODE_LABELS = {"presentiel": "en présentiel", "distance": "à distance"}


def find_event(payload, event_id):
    return next((event for event in (payload.get("ajustements") or []) if event.get("id") == event_id), None)


def _sections(payload, event):
    beneficiaire = payload.get("beneficiaire", {})
    service_change = event.get("service") or {}
    service = beneficiaire.get("service") or "-"
    if service_change.get("from") or service_change.get("to"):
        service = f"{service_change.get('to') or '-'} (avant : {service_change.get('from') or '-'})"

    sections = [
        ("Identification de l'ajustement", [
            f"Bénéficiaire : {beneficiaire.get('nom') or '-'} {beneficiaire.get('prenom') or '-'}",
            f"Qualité : {format_beneficiary_label(beneficiaire.get('qualite'))}",
            f"Service : {service}",
            f"Date de l'ajustement : {format_export_datetime(event.get('at'))}",
            f"Enregistré par : {event.get('by') or '-'}",
        ]),
        ("Ressources ajoutées", [f"- {item.get('label') or item.get('key')}" for item in event.get("ajouts") or []] or ["Aucune ressource ajoutée."]),
        ("Ressources retirées", [
            f"- {item.get('label') or item.get('key')} : {STATE_LABELS.get(item.get('state'), item.get('state') or '-')}"
            + (f" / {item['notes']}" if item.get("notes") else "")
            for item in event.get("retraits") or []
        ] or ["Aucune ressource retirée."]),
    ]
    if service_change.get("from") or service_change.get("to"):
        sections.append(("Changement de service", [f"De « {service_change.get('from') or '-'} » à « {service_change.get('to') or '-'} »."]))
    return sections


def build_adjustment_pdf_bytes(payload, event_id):
    """PDF d'un ajustement. Lève LookupError si l'ajustement n'existe pas dans ce dossier."""
    event = find_event(payload, event_id)
    if event is None:
        raise LookupError(event_id)
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]
    beneficiaire = payload.get("beneficiaire", {})
    signature = event.get("signature") or {}
    status = signature.get("status")

    subtitle = "Fiche d'ajustement de dossier" + (" (en attente de signature)" if status not in ("signed", "substitute") else "")
    pdf = _AQuaiDoc(
        normalize_pdf_text(f"Ajustement - {beneficiaire.get('nom') or ''} {beneficiaire.get('prenom') or ''}".strip()),
        subtitle, org_name, load_brand_logo_image(), load_a_quai_pdf_logo_image(),
    )
    pdf.add_page()
    y = _AQuaiDoc._CONTENT_START
    for title, lines in _sections(payload, event):
        y = pdf._draw_section(y, title, lines)

    if status == "signed":
        mode = MODE_LABELS.get(signature.get("requestedMode") or signature.get("mode"), "")
        image = extract_signature_image(signature.get("signatureDataUrl")) if can_export_signature_assets() else None
        pdf._draw_signature_box(y, "Signature de l'ajustement", format_export_datetime(signature.get("signedAt")),
                                f"Signature recueillie {mode}." if mode else "Signature recueillie.", sig_bytes=image, reservation_lines=[])
    elif status == "substitute":
        substitute = signature.get("substitute") or {}
        pdf._draw_section(y, "Signature par un responsable", [
            f"La signature du bénéficiaire était impossible : {signature.get('reason') or '-'}",
            f"Signé à la place par : {substitute.get('name') or '-'} ({substitute.get('quality') or 'responsable'})",
            f"Date : {format_export_datetime(signature.get('signedAt'))}",
        ])
    else:
        pdf._draw_section(y, "Signature", [
            "En attente de la signature du bénéficiaire (signature à distance).",
            "Ce document n'a pas encore valeur de preuve : il sera complété une fois l'ajustement signé.",
        ])
    return bytes(pdf.output())
