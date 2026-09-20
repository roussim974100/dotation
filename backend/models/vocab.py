"""Vocabulaire de l'application : libelles de statut et types de bénéficiaires, définis UNE fois ici (le serveur les publie au
navigateur via /api/settings/public : plus de listes recopiées dans chaque page)."""

STATUS_LABELS = {
    "draft": "À compléter",
    "partial_assignment": "Attribution partielle",
    "awaiting_signature": "En attente de signature",
    "active": "Attribution active",
    "returned": "Restitution terminée",
    "partial_return": "Restitution partielle",
    "cancelled": "Dossier annulé",
}


def status_label(status):
    return STATUS_LABELS.get(status, STATUS_LABELS["draft"])


def beneficiary_types(connection=None):
    """Types de bénéficiaires configurés (Administration > Personnalisation), sinon les deux types de départ."""
    from models.settings import _parse_beneficiary_types, get_app_settings
    return _parse_beneficiary_types(get_app_settings(connection).get("beneficiary_types") if connection is not None else get_app_settings().get("beneficiary_types"))


def beneficiary_label(value):
    try:
        for item in beneficiary_types():
            if item["value"] == value:
                return item["label"]
    except Exception:  # noqa: BLE001 - un libelle ne doit jamais faire echouer un export
        pass
    return {"agent": "Agent", "elu": "Élu(e)"}.get(value, value or "-")


def configured_beneficiary_values(connection=None):
    return {item["value"] for item in beneficiary_types(connection)}


def mandate_values(connection=None):
    """Identifiants des types de bénéficiaires qui portent un mandat (« élu » par défaut)."""
    return {item["value"] for item in beneficiary_types(connection) if item.get("mandate")}


def has_mandate(value, connection=None):
    try:
        return value in mandate_values(connection)
    except Exception:  # noqa: BLE001
        return value == "elu"
