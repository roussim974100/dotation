import io
import textwrap
from datetime import datetime
from fpdf import FPDF

from utils import (
    normalize_pdf_text, _get_png_size, format_export_datetime,
    get_signature_datetime, format_status_label, dossier_type_label,
    format_beneficiary_label, format_restitution_state_label,
    extract_signature_image,
)
from auth import can_export_signature_assets
from models.settings import get_app_settings, DEFAULT_APP_SETTINGS, load_brand_logo_image, load_a_quai_pdf_logo_image
from models.workflow import collect_resource_entries


class _AQuaiDoc(FPDF):
    _MARGIN = 42
    _CONTENT_W = 511  # 595 - 2*42
    _CONTENT_START = 182  # 842 - 660
    _CONTENT_END = 790  # 842 - 52

    def __init__(self, page_title, page_subtitle, org_name, brand_logo_bytes, aq_logo_bytes):
        super().__init__(unit="pt", format=(595, 842))
        self.alias_nb_pages()
        self.set_auto_page_break(False)
        self._page_title = page_title
        self._page_subtitle = page_subtitle
        self._org_name = org_name
        self._brand_logo = brand_logo_bytes
        self._aq_logo = aq_logo_bytes
        self._generated_at = format_export_datetime(datetime.now().isoformat())

    def _scale_logo(self, png_bytes, max_w, max_h):
        w, h = _get_png_size(png_bytes)
        if not w or not h:
            return 0, 0
        ratio = min(max_w / w, max_h / h)
        return round(w * ratio, 2), round(h * ratio, 2)

    def header(self):
        # Blue banner
        self.set_fill_color(13, 84, 133)
        self.rect(0, 0, self.w, 92, "F")
        # Gold stripe
        self.set_fill_color(214, 163, 64)
        self.rect(0, 92, self.w, 12, "F")

        # Logo (a quai preferred, fall back to brand)
        logo_bytes = self._aq_logo or self._brand_logo
        if logo_bytes:
            lw, lh = self._scale_logo(logo_bytes, 88, 52)
            if lw and lh:
                self.image(io.BytesIO(logo_bytes), x=self._MARGIN, y=76 - lh, w=lw, h=lh)

        # Org name
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(255, 255, 255)
        self.text(self._MARGIN + 100, 48, normalize_pdf_text(self._org_name))

        # "A quai"
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(235, 245, 252)
        self.text(self._MARGIN + 100, 68, "A quai")

        # Right side header
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(255, 255, 255)
        self.text(self.w - 190, 48, "Document interne")

        self.set_font("Helvetica", "", 9)
        self.set_text_color(235, 245, 252)
        self.text(self.w - 190, 66, normalize_pdf_text(self._generated_at))

        # Document title (sub-header area below the banner)
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(18, 46, 66)
        self.text(self._MARGIN, 118, normalize_pdf_text(self._page_title))

        self.set_font("Helvetica", "", 10)
        self.set_text_color(89, 110, 128)
        self.text(self._MARGIN, 136, normalize_pdf_text(self._page_subtitle))

    def footer(self):
        # Separator line
        self.set_draw_color(204, 219, 230)
        self.set_line_width(0.8)
        self.line(self._MARGIN, self.h - 34, self._MARGIN + self._CONTENT_W, self.h - 34)

        # Left text
        self.set_font("Helvetica", "", 8)
        self.set_text_color(97, 115, 133)
        self.text(self._MARGIN, self.h - 20, "A quai - document exploitable RH / DGS")

        # Brand logo in footer
        if self._brand_logo:
            fw, fh = self._scale_logo(self._brand_logo, 54, 18)
            if fw and fh:
                self.image(io.BytesIO(self._brand_logo), x=self.w - 160, y=self.h - 13 - fh, w=fw, h=fh)

        # Page number
        self.text(self.w - 90, self.h - 20, "Page " + str(self.page_no()) + "/{nb}")

    def _draw_section(self, y_top, title, lines):
        wrapped = []
        for line in lines:
            wrapped.extend(textwrap.wrap(normalize_pdf_text(line), width=86) or [""])
        section_h = 28 + len(wrapped) * 15 + 18

        if y_top + section_h > self._CONTENT_END:
            self.add_page()
            y_top = self._CONTENT_START

        self.set_fill_color(250, 251, 252)
        self.set_draw_color(204, 219, 230)
        self.set_line_width(0.5)
        self.rect(self._MARGIN, y_top, self._CONTENT_W, section_h, "FD")

        self.set_font("Helvetica", "B", 12)
        self.set_text_color(13, 66, 102)
        self.text(self._MARGIN + 14, y_top + 18, normalize_pdf_text(title))

        self.set_font("Helvetica", "", 10)
        self.set_text_color(43, 51, 61)
        line_y = y_top + 40
        for line in wrapped:
            self.text(self._MARGIN + 14, line_y, normalize_pdf_text(line))
            line_y += 15

        return y_top + section_h + 16

    def _draw_signature_box(self, y_top, label, date_str, note_text,
                            sig_bytes=None, reservation_lines=None):
        reservation_lines = reservation_lines or []
        sig_w = sig_h = 0
        if sig_bytes:
            raw_w, raw_h = _get_png_size(sig_bytes)
            if raw_w and raw_h:
                ratio = min(220 / raw_w, 90 / raw_h)
                sig_w = round(raw_w * ratio, 2)
                sig_h = round(raw_h * ratio, 2)
        section_h = 90 + sig_h + len(reservation_lines) * 14

        if y_top + section_h > self._CONTENT_END:
            self.add_page()
            y_top = self._CONTENT_START

        self.set_fill_color(251, 252, 254)
        self.set_draw_color(204, 219, 230)
        self.set_line_width(0.5)
        self.rect(self._MARGIN, y_top, self._CONTENT_W, section_h, "FD")

        self.set_font("Helvetica", "B", 12)
        self.set_text_color(13, 66, 102)
        self.text(self._MARGIN + 14, y_top + 18, normalize_pdf_text(label))

        self.set_font("Helvetica", "", 10)
        self.set_text_color(71, 92, 112)
        self.text(self._MARGIN + 14, y_top + 38,
                  normalize_pdf_text("Date de signature : " + date_str))
        self.text(self._MARGIN + 14, y_top + 54, normalize_pdf_text(note_text))

        text_y = y_top + 70
        if reservation_lines:
            self.set_text_color(115, 43, 31)
            for line in reservation_lines:
                self.text(self._MARGIN + 14, text_y, normalize_pdf_text(line))
                text_y += 14

        if sig_bytes and sig_w and sig_h:
            img_y = y_top + section_h - 18 - sig_h
            try:
                self.image(io.BytesIO(sig_bytes), x=self._MARGIN + 14, y=img_y, w=sig_w, h=sig_h)
            except Exception:
                self.set_text_color(160, 160, 160)
                self.set_font("Helvetica", "I", 9)
                self.text(self._MARGIN + 14, img_y + sig_h / 2, normalize_pdf_text("[Image de signature non lisible]"))
                self.set_text_color(0, 0, 0)

        return y_top + section_h + 16

    def _draw_masked_signature_box(self, y_top, label, date_str, reservation_lines=None):
        reservation_lines = reservation_lines or []
        section_h = 92 + len(reservation_lines) * 14

        if y_top + section_h > self._CONTENT_END:
            self.add_page()
            y_top = self._CONTENT_START

        self.set_fill_color(251, 252, 254)
        self.set_draw_color(204, 219, 230)
        self.set_line_width(0.5)
        self.rect(self._MARGIN, y_top, self._CONTENT_W, section_h, "FD")

        self.set_font("Helvetica", "B", 12)
        self.set_text_color(13, 66, 102)
        self.text(self._MARGIN + 14, y_top + 18, normalize_pdf_text(label))

        self.set_font("Helvetica", "", 10)
        self.set_text_color(71, 92, 112)
        self.text(self._MARGIN + 14, y_top + 38,
                  normalize_pdf_text("Signature masquée dans cet export."))
        self.text(self._MARGIN + 14, y_top + 54,
                  normalize_pdf_text("La signature est réservée aux personnes autorisées."))
        self.text(self._MARGIN + 14, y_top + 70,
                  normalize_pdf_text("Date de signature : " + date_str))

        if reservation_lines:
            self.set_text_color(115, 43, 31)
            text_y = y_top + 86
            for line in reservation_lines:
                self.text(self._MARGIN + 14, text_y, normalize_pdf_text(line))
                text_y += 14

        return y_top + section_h + 16


def build_pdf_bytes(title, payload):
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]

    beneficiaire = payload.get("beneficiaire", {})
    dossier = payload.get("dossier", {})
    workflow = payload.get("workflow", {})
    validation = payload.get("validation", {})
    restitution = payload.get("restitution", {})
    signature_datetime = get_signature_datetime(payload)
    signature_export_allowed = can_export_signature_assets()
    signature_present = bool(validation.get("signatureDataUrl"))
    resources = collect_resource_entries(payload)
    resource_groups = {}
    for entry in resources:
        resource_groups.setdefault(entry["service"], []).append(entry)

    sections = [
        (
            "Identification du dossier",
            [
                f"État : {format_status_label(workflow.get('status') or 'draft')}",
                f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
                f"Date de prise de fonction : {format_export_datetime(payload.get('meta', {}).get('startAt'))}",
                f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
                f"Date de création : {format_export_datetime(payload.get('meta', {}).get('createdAt'))}",
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
                f"Service de destination : {dossier.get('serviceDestination') or '-'}",
            ],
        ),
    ]

    if resource_groups:
        for service, service_entries in sorted(resource_groups.items(), key=lambda item: item[0]):
            sections.append(
                (
                    f"Ressources attribuées - {service}",
                    [
                        f"{entry['label']} : {entry['details']}"
                        f"{' / ' + entry['assignmentSummary'] if entry.get('assignmentSummary') else ''}"
                        for entry in service_entries
                    ],
                )
            )
    else:
        sections.append(("Ressources attribuées", ["Aucune ressource renseignée."]))

    unc_entries = payload.get("unc_acces") or []
    unc_ref_ad = (payload.get("unc_ref_ad") or "").strip()
    if unc_entries or unc_ref_ad:
        _ACCES_LABEL = {"lecture": "Lecture", "lecture_ecriture": "Lecture / Écriture", "refuse": "Accès refusé"}
        _STATUT_LABEL = {"demande": "Demandé", "en_cours": "En cours", "provisionne": "Provisionné"}
        unc_lines = []
        if unc_ref_ad:
            unc_lines.append(f"Référence AD (copier les droits de) : {unc_ref_ad}")
        for e in unc_entries:
            chemin = e.get("chemin") or "-"
            acces = _ACCES_LABEL.get(e.get("acces") or "", e.get("acces") or "-")
            statut = _STATUT_LABEL.get(e.get("statut") or "", e.get("statut") or "-")
            commentaire = e.get("commentaire") or ""
            line = f"{chemin}  —  {acces}  —  {statut}"
            if commentaire:
                line += f"  ({commentaire})"
            unc_lines.append(line)
        sections.append(("Accès réseau (UNC)", unc_lines))

    restitution_lines = [
        f"Statut : {format_status_label(workflow.get('status') or 'draft')}",
        f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
        f"Motif : {restitution.get('reason') or '-'}",
        f"Observations : {restitution.get('notes') or '-'}",
    ]
    for item_key, state in sorted((restitution.get("items") or {}).items()):
        item_label = next((e["label"] for e in resources if e["itemKey"] == item_key), item_key)
        state_label = format_restitution_state_label(state.get("state") or state.get("condition"))
        restitution_lines.append(f"{item_label} : {state_label} / {state.get('notes') or '-'}")
    sections.append(("Restitution", restitution_lines))

    if signature_export_allowed:
        sections.append(
            (
                "Validation et conformité",
                [
                    f"Information RGPD portée à connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
                    f"Signature du bénéficiaire : {'Oui' if signature_present else 'Non'}",
                    f"Date de signature : {signature_datetime}",
                ],
            )
        )
    else:
        sections.append(
            (
                "Validation et conformité",
                [
                    f"Information RGPD portée à connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
                    "Signature du bénéficiaire : Masquée",
                    "Mention : la signature est réservée aux personnes autorisées.",
                ],
            )
        )

    brand_logo = load_brand_logo_image()
    aq_logo = load_a_quai_pdf_logo_image()
    sig_bytes = extract_signature_image(validation.get("signatureDataUrl")) if signature_export_allowed else None

    pdf = _AQuaiDoc(
        normalize_pdf_text(title),
        "Document de remise et de suivi des ressources attribuées",
        org_name,
        brand_logo,
        aq_logo,
    )
    pdf.add_page()
    y = _AQuaiDoc._CONTENT_START
    for sec_title, sec_lines in sections:
        y = pdf._draw_section(y, sec_title, sec_lines)

    if sig_bytes:
        pdf._draw_signature_box(
            y,
            "Signature du bénéficiaire",
            signature_datetime,
            "Signature recueillie lors de la validation du dossier.",
            sig_bytes=sig_bytes,
        )
    elif signature_present and not signature_export_allowed:
        reservation_lines = []
        if restitution.get("signataireDecision") == "with_reservation":
            reservation_lines = textwrap.wrap(
                normalize_pdf_text(f"Réserve : {restitution.get('signataireComment') or '-'}"),
                width=72,
            )
        pdf._draw_masked_signature_box(
            y,
            "Signature du bénéficiaire",
            signature_datetime,
            reservation_lines=reservation_lines,
        )

    return bytes(pdf.output())
