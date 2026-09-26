"""Ajustement d'un dossier ACTIF (3.63.0) : ajouter des ressources, en retirer et/ou changer le service d'une personne, sur son
dossier existant, sans repartir d'un nouveau dossier.

Choix de conception (voir docs/REPRISE_MAJ.md et la memoire du chantier) :
- le dossier reste `active` et verrouille : un ajustement n'est PAS une restitution (`derive_restitution_workflow_status` calcule
  `returned` / `partial_return`, pense pour une fin de mission) ; son propre etat est porte par l'evenement
  (`derive_adjustment_status`) dans `payload["ajustements"]`, historique horodate de tous les gestes ;
- chaque geste a SA signature : presentiel (geste), a distance (differee, recueillie ensuite), ou impossible (un responsable
  signe a la place : nom + qualite tracés séparément du bénéficiaire) ;
- les retraits reprennent le mecanisme existant (`restitution.items[cle]`) : le parc et le stock se resynchronisent seuls via
  `persist_form`, comme pour une restitution partielle ;
- fonctions pures (aucun acces base) : la route les appelle puis enregistre en UNE fois avec `persist_form`.
"""
from models.workflow import collect_resource_validation_errors, extract_items
from utils import AppError, generate_id, utc_now

SIGNATURE_MODES = ("presentiel", "distance", "impossible")
RETURN_STATES = ("conforme", "degrade", "autre")
MAX_SIGNATURE_BYTES = 1_048_576  # meme plafond que les liens de signature
MAX_TEXT = 500

# Etats d'un evenement d'ajustement (distincts des statuts de dossier)
STATUS_SIGNED = "signed"
STATUS_PENDING = "pending_signature"
STATUS_SIGNED_BY_SUBSTITUTE = "signed_by_substitute"


def derive_adjustment_status(signature):
    """Etat d'un ajustement d'apres sa signature (jamais d'apres le statut du dossier)."""
    status = (signature or {}).get("status")
    if status == "signed":
        return STATUS_SIGNED
    if status == "substitute":
        return STATUS_SIGNED_BY_SUBSTITUTE
    return STATUS_PENDING


def held_resource_keys(payload):
    """Cles des ressources actuellement detenues (attribuees et pas encore rendues)."""
    return {item["item_key"] for item in extract_items(payload) if item["assigned"] and not item["returned"]}


def _text(value, limit=MAX_TEXT):
    return str(value or "").strip()[:limit]


def _resource_key(resource):
    return str(resource.get("code") or resource.get("id") or "").strip()


def _build_signature(raw, now):
    """Signature d'un geste. `raw` = {mode, signatureDataUrl, reason, substitute: {name, quality}}."""
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode")
    if mode not in SIGNATURE_MODES:
        raise AppError("signature_mode_required", "Choisissez le mode de signature (présentiel, à distance ou impossible).", 400)
    if mode == "presentiel":
        data_url = raw.get("signatureDataUrl") or ""
        if not str(data_url).startswith("data:image/"):
            raise AppError("signature_required", "La signature est obligatoire en présentiel.", 400)
        if len(data_url) > MAX_SIGNATURE_BYTES:
            raise AppError("signature_too_large", "La signature est trop volumineuse.", 413)
        return {"mode": mode, "status": "signed", "signedAt": now, "signatureDataUrl": data_url}
    if mode == "distance":
        return {"mode": mode, "status": "pending"}
    reason = _text(raw.get("reason"))
    substitute = raw.get("substitute") if isinstance(raw.get("substitute"), dict) else {}
    name, quality = _text(substitute.get("name"), 120), _text(substitute.get("quality"), 120)
    if not reason:
        raise AppError("signature_reason_required", "Précisez pourquoi la signature est impossible.", 400)
    if not name:
        raise AppError("substitute_required", "Indiquez qui signe à la place (nom et qualité).", 400)
    return {"mode": mode, "status": "substitute", "signedAt": now, "reason": reason,
            "substitute": {"name": name, "quality": quality}}


def _resource_summary(resource):
    return {"key": _resource_key(resource), "label": _text(resource.get("label"), 200) or _resource_key(resource)}


def apply_adjustment(payload, body, actor, now=None):
    """Applique un ajustement au payload d'un dossier actif. Renvoie (payload, evenement). Leve AppError si invalide."""
    now = now or utc_now()
    body = body if isinstance(body, dict) else {}
    if (payload.get("workflow") or {}).get("status") != "active":
        raise AppError("not_adjustable", "Seul un dossier actif peut être ajusté.", 409)

    held = held_resource_keys(payload)
    additions, withdrawals = [], []
    resources = payload.setdefault("resources", {})
    if not isinstance(resources.get("additional"), list):
        resources["additional"] = []
    seen = set()

    for raw in body.get("ajouts") or []:
        if not isinstance(raw, dict) or not _resource_key(raw):
            raise AppError("invalid_addition", "Chaque ressource ajoutée doit avoir un code.", 400)
        key = _resource_key(raw)
        if key in held or key in seen:
            raise AppError("already_held", f"La ressource « {_text(raw.get('label')) or key} » est déjà détenue.", 409)
        seen.add(key)
        entry = {**raw, "selected": True, "category": raw.get("category") or "materiel"}
        additions.append(entry)

    for raw in body.get("retraits") or []:
        key = _text(raw.get("key") if isinstance(raw, dict) else "", 200)
        if not key or key not in held:
            raise AppError("not_held", "Cette ressource n'est pas détenue : impossible de la retirer.", 409)
        if key in seen:
            raise AppError("duplicate_gesture", "Une ressource ne peut pas être ajoutée et retirée en même temps.", 400)
        seen.add(key)
        state = raw.get("state") or "conforme"
        if state not in RETURN_STATES:
            raise AppError("invalid_state", "État de reprise inconnu.", 400)
        withdrawals.append({"key": key, "state": state, "notes": _text(raw.get("notes"))})

    beneficiaire = payload.setdefault("beneficiaire", {})
    new_service = _text(body.get("service"), 200)
    old_service = beneficiaire.get("service") or ""
    service_change = {"from": old_service, "to": new_service} if new_service and new_service != old_service else None

    if not additions and not withdrawals and not service_change:
        raise AppError("empty_adjustment", "Rien à ajuster : ajoutez ou retirez une ressource, ou changez le service.", 400)

    signature = _build_signature(body.get("signature"), now)
    event_id = generate_id("ajust")

    # Le libelle d'un retrait est celui de la ressource detenue (pas une valeur envoyee par le client).
    labels = {item["item_key"]: item["label"] for item in extract_items(payload)}
    restitution = payload.setdefault("restitution", {})
    items = restitution.get("items")
    if not isinstance(items, dict):
        items = restitution["items"] = {}
    for withdrawal in withdrawals:
        items[withdrawal["key"]] = {"state": withdrawal["state"], "notes": withdrawal["notes"], "returnedAt": now, "adjustmentId": event_id}
    for entry in additions:
        entry["adjustmentId"] = event_id
        entry["assignedAt"] = now
        resources["additional"].append(entry)
    if service_change:
        beneficiaire["service"] = new_service

    errors = collect_resource_validation_errors(payload)
    if errors:
        raise AppError("resource_incomplete", "Une ressource ajoutée n'est pas complètement renseignée : " + " ; ".join(map(str, errors[:3])), 400)

    event = {
        "id": event_id,
        "at": now,
        "by": actor,
        "ajouts": [_resource_summary(entry) for entry in additions],
        "retraits": [{"key": w["key"], "label": labels.get(w["key"], w["key"]), "state": w["state"], "notes": w["notes"]} for w in withdrawals],
        "service": service_change,
        "signature": signature,
        "status": derive_adjustment_status(signature),
    }
    payload.setdefault("ajustements", []).append(event)
    return payload, event


def complete_adjustment_signature(payload, event_id, raw_signature, now=None):
    """Recueille la signature d'un ajustement resté « en attente » (mode à distance). Renvoie (payload, evenement)."""
    now = now or utc_now()
    event = next((e for e in payload.get("ajustements") or [] if e.get("id") == event_id), None)
    if not event:
        raise AppError("not_found", "Ajustement introuvable.", 404)
    if event.get("status") != STATUS_PENDING:
        raise AppError("already_signed", "Cet ajustement est déjà signé.", 409)
    raw = dict(raw_signature) if isinstance(raw_signature, dict) else {}
    if raw.get("mode") == "distance":
        raise AppError("signature_mode_required", "Recueillez la signature (présentiel) ou indiquez qu'elle est impossible.", 400)
    event["signature"] = {**_build_signature(raw, now), "requestedMode": "distance"}
    event["status"] = derive_adjustment_status(event["signature"])
    return payload, event


def public_event(event):
    """Evenement sans l'image de la signature (jamais renvoyee par les routes d'ajustement)."""
    clean = dict(event)
    signature = dict(clean.get("signature") or {})
    signature.pop("signatureDataUrl", None)
    clean["signature"] = signature
    return clean
