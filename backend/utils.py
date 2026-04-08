import base64
import json
import struct
import unicodedata
import uuid
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def bool_to_int(value):
    return 1 if value else 0


def mask_text(value):
    if not value:
        return value
    if len(value) <= 2:
        return value[0] + "*"
    return value[0] + ("*" * max(1, len(value) - 2)) + value[-1]


def mask_payload(payload):
    if not payload:
        return payload
    data = json.loads(json.dumps(payload))
    beneficiaire = data.get("beneficiaire", {})
    beneficiaire["nom"] = mask_text(beneficiaire.get("nom"))
    beneficiaire["prenom"] = mask_text(beneficiaire.get("prenom"))

    if data.get("immateriel", {}).get("email", {}).get("adresse"):
        data["immateriel"]["email"]["adresse"] = mask_text(data["immateriel"]["email"]["adresse"])
    if data.get("materiel", {}).get("badge", {}).get("numero"):
        data["materiel"]["badge"]["numero"] = mask_text(data["materiel"]["badge"]["numero"])
    if data.get("materiel", {}).get("telephone", {}).get("numeroSerie"):
        data["materiel"]["telephone"]["numeroSerie"] = mask_text(data["materiel"]["telephone"]["numeroSerie"])
    if data.get("materiel", {}).get("vehicule", {}).get("immatriculation"):
        data["materiel"]["vehicule"]["immatriculation"] = mask_text(data["materiel"]["vehicule"]["immatriculation"])
    data.setdefault("validation", {})["signatureDataUrl"] = ""
    return data


def slugify_field_key(value):
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    return "".join(
        character if character.isalnum() else "_"
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).strip("_")


def normalize_pdf_text(value):
    text = "" if value is None else str(value)
    for encoding in ("cp1252", "latin-1"):
        if any(marker in text for marker in ("Ã", "â", "ï¿½")):
            try:
                repaired = text.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if repaired.count("Ã") + repaired.count("â") + repaired.count("ï¿½") < text.count("Ã") + text.count("â") + text.count("ï¿½"):
                text = repaired
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text.encode("cp1252", "replace").decode("latin-1")


def _get_png_size(png_bytes):
    if not png_bytes or len(png_bytes) < 24 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0
    return struct.unpack(">II", png_bytes[16:24])


def slugify_filename(value, fallback="dossier_attribution"):
    raw = normalize_pdf_text(value).strip().lower()
    cleaned = []
    for character in raw:
        if character.isalnum():
            cleaned.append(character)
        elif character in {" ", "-", "_"}:
            cleaned.append("_")
    slug = "".join(cleaned).strip("_")
    return slug or fallback


def extract_signature_image(signature_data_url):
    if not signature_data_url or not signature_data_url.startswith("data:image/png;base64,"):
        return None
    try:
        return base64.b64decode(signature_data_url.split(",", 1)[1])
    except (ValueError, IndexError):
        return None


def build_title(payload):
    beneficiaire = payload.get("beneficiaire", {})
    prefix = (
        beneficiaire.get("mandat")
        if beneficiaire.get("qualite") == "elu"
        else beneficiaire.get("service")
    ) or ("MANDAT" if beneficiaire.get("qualite") == "elu" else "SERVICE")
    nom = (beneficiaire.get("nom") or "SANS NOM").upper()
    prenom = beneficiaire.get("prenom") or ""
    return f"{prefix.upper()} - {nom} {prenom}".strip()


def normalize_dossier_type(value):
    mapping = {
        "nouvel_agent": "arrivee",
        "nouvel_elu": "arrivee",
        "elu_en_place": "mise_a_jour",
        "changement_service": "changement_service",
        "sortie": "sortie",
        "arrivee": "arrivee",
        "mise_a_jour": "mise_a_jour",
    }
    return mapping.get(value, "arrivee")


def dossier_type_label(value):
    labels = {
        "arrivee": "Nouvelle arrivée",
        "changement_service": "Changement de service",
        "mise_a_jour": "Mise à jour de ressources",
        "sortie": "Sortie / restitution",
    }
    return labels.get(normalize_dossier_type(value), "Nouvelle arrivée")


def format_export_datetime(value):
    if not value:
        return "-"
    text = str(value).strip()
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def get_signature_datetime(payload):
    validation = payload.get("validation", {})
    meta = payload.get("meta", {})
    if not validation.get("signatureDataUrl"):
        return "-"
    return format_export_datetime(
        validation.get("signedAt")
        or meta.get("lockedAt")
        or meta.get("savedAt")
        or meta.get("assignedAt")
    )


def get_restitution_signature_datetime(payload):
    restitution = payload.get("restitution", {})
    if not restitution.get("signatureDataUrl"):
        return "-"
    return format_export_datetime(
        restitution.get("signedAt")
        or restitution.get("returnedAt")
        or payload.get("meta", {}).get("savedAt")
    )


def format_beneficiary_label(value):
    labels = {
        "agent": "Agent",
        "elu": "Élu(e)",
    }
    return labels.get(value, value or "-")


def format_status_label(status):
    labels = {
        "draft": "À compléter",
        "partial_assignment": "Attribution partielle",
        "awaiting_signature": "En attente de signature",
        "active": "Attribution active",
        "returned": "Restitution terminée",
        "partial_return": "Restitution partielle",
        "cancelled": "Dossier annulé",
    }
    return labels.get(status, "À compléter")


def format_restitution_state_label(state):
    labels = {
        "pending": "En attente",
        "returned": "Restitué",
        "returned_damaged": "Restitué abîmé",
        "missing": "Non restitué",
        "transferred": "Transféré",
        "conforme": "Conforme",
        "degrade": "Dégradé",
        "non_restitue": "Non restitué",
        "perdu": "Perdu",
        "autre": "Autre",
    }
    return labels.get(state or "", state or "En attente")


def format_restitution_signature_status(value):
    labels = {
        "signed": "Signature recueillie sur place",
        "impossible": "Signature impossible",
        "deferred": "Signature à distance par lien",
    }
    return labels.get(value or "", value or "-")


def format_restitution_decision_label(signature_status, signataire_decision):
    if signataire_decision == "with_reservation":
        return "Signée avec réserve"
    if signature_status == "signed":
        return "Restitution confirmée"
    if signature_status == "deferred":
        return "En attente de signature"
    if signature_status == "impossible":
        return "Signature impossible"
    return "-"


def format_assignment_condition_label(value):
    labels = {
        "neuf": "Neuf",
        "bon_etat": "Bon état",
        "etat_usage": "État d'usage",
        "degrade": "Dégradé",
    }
    return labels.get(value or "", value or "-")
