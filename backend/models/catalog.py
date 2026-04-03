import json

from utils import generate_id, utc_now, slugify_field_key
from models.workflow import normalize_resource_field_schema


CORE_RESOURCE_CODES = {
    "ordinateur",
    "ecran",
    "telephone",
    "tablette",
    "vpn",
    "email",
    "badge",
    "cles",
    "veste",
    "chaussuresSecurite",
    "zoneAlarme",
    "vehicule",
    "plaquePorte",
    "cartesVisite",
    "autre",
}

DEFAULT_RESOURCE_REFERENCES = [
    {
        "code": "ordinateur", "label": "Ordinateur", "description": "Ordinateur portable remis par la DSI",
        "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 10,
        "field_schema": [
            {"key": "nomPoste", "label": "Nom du poste", "type": "text", "required": False, "placeholder": "Ex: PC-DSI-042"},
            {"key": "marque", "label": "Marque", "type": "text", "required": True, "placeholder": "Ex: Dell, Lenovo, HP"},
            {"key": "modele", "label": "Modele", "type": "text", "required": True, "placeholder": "Ex: Latitude 5540"},
            {"key": "numeroSerie", "label": "Numero de serie", "type": "text", "required": True, "placeholder": "Ex: SN-DELL-001"},
        ],
    },
    {
        "code": "ecran", "label": "Ecran", "description": "Ecran portable remis par la DSI",
        "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 20,
        "field_schema": [
            {"key": "marque", "label": "Marque", "type": "text", "required": True, "placeholder": "Ex: Dell, LG"},
            {"key": "modele", "label": "Modele", "type": "text", "required": True, "placeholder": "Ex: U2723QE"},
            {"key": "numeroSerie", "label": "Numero de serie", "type": "text", "required": True, "placeholder": ""},
        ],
    },
    {
        "code": "telephone", "label": "Telephone", "description": "Telephone portable professionnel remis par la DSI",
        "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 30,
        "field_schema": [
            {"key": "nomTelephone", "label": "Nom du telephone", "type": "text", "required": False, "placeholder": ""},
            {"key": "marque", "label": "Marque", "type": "text", "required": True, "placeholder": "Ex: Apple, Samsung"},
            {"key": "modele", "label": "Modele", "type": "text", "required": True, "placeholder": "Ex: iPhone 15"},
            {"key": "imei", "label": "IMEI", "type": "text", "required": True, "placeholder": "15 chiffres"},
        ],
    },
    {
        "code": "tablette", "label": "Tablette", "description": "Tablette portable professionnelle remise par la DSI",
        "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 40,
        "field_schema": [
            {"key": "nomTablette", "label": "Nom de la tablette", "type": "text", "required": False, "placeholder": ""},
            {"key": "marque", "label": "Marque", "type": "text", "required": True, "placeholder": "Ex: Apple, Samsung"},
            {"key": "modele", "label": "Modele", "type": "text", "required": True, "placeholder": "Ex: iPad Pro"},
            {"key": "numeroSerie", "label": "Numero de serie", "type": "text", "required": True, "placeholder": ""},
        ],
    },
    {
        "code": "vpn", "label": "VPN (teletravail)", "description": "Acces VPN pour le teletravail",
        "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital",
        "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 50,
        "field_schema": [
            {"key": "identifiant", "label": "Identifiant VPN", "type": "text", "required": False, "placeholder": ""},
        ],
    },
    {
        "code": "email", "label": "Email", "description": "Messagerie professionnelle",
        "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital",
        "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 60,
        "field_schema": [
            {"key": "adresse", "label": "Adresse email", "type": "email_with_domain", "required": True, "placeholder": "prenom.nom"},
        ],
    },
    {
        "code": "badge", "label": "Badge d'acces", "description": "Badge d'acces batiment",
        "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 70,
        "field_schema": [
            {"key": "numero", "label": "Numero de badge", "type": "text", "required": True, "placeholder": "Ex: B-2026-001"},
        ],
    },
    {
        "code": "cles", "label": "Cle(s)", "description": "Cles remises par le service batiment",
        "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 80,
        "field_schema": [
            {"key": "values", "label": "Cle", "type": "list", "required": True, "placeholder": "Intitule de la cle"},
        ],
    },
    {
        "code": "veste", "label": "Veste", "description": "Vetement de travail remis par le service batiment",
        "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 90,
        "field_schema": [],
    },
    {
        "code": "chaussuresSecurite", "label": "Chaussures de securite", "description": "Chaussures de securite remises par le service batiment",
        "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 100,
        "field_schema": [],
    },
    {
        "code": "zoneAlarme", "label": "Zone alarme", "description": "Zone d'alarme attribuee",
        "category": "immateriel", "issuer_service": "Batiment", "requires_return": 0, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 110,
        "field_schema": [
            {"key": "zones", "label": "Zone", "type": "list", "required": True, "placeholder": "Nom de la zone"},
        ],
    },
    {
        "code": "vehicule", "label": "Vehicule", "description": "Vehicule de service attribue par la DRH",
        "category": "materiel", "issuer_service": "DRH", "requires_return": 1, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 120,
        "field_schema": [
            {"key": "marque", "label": "Marque", "type": "text", "required": True, "placeholder": "Ex: Renault, Citroen"},
            {"key": "modele", "label": "Modele", "type": "text", "required": True, "placeholder": "Ex: Kangoo"},
            {"key": "immatriculation", "label": "Immatriculation", "type": "text", "required": True, "placeholder": "Format AA-123-AA"},
        ],
    },
    {
        "code": "plaquePorte", "label": "Plaque de porte", "description": "Plaque de porte avec nom, prenom et fonction",
        "category": "materiel", "issuer_service": "Communication", "requires_return": 0, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 1, "display_order": 130,
        "field_schema": [
            {"key": "nom", "label": "Nom", "type": "text", "required": True, "placeholder": ""},
            {"key": "prenom", "label": "Prenom", "type": "text", "required": True, "placeholder": ""},
            {"key": "fonction", "label": "Fonction", "type": "text", "required": True, "placeholder": ""},
        ],
    },
    {
        "code": "cartesVisite", "label": "Cartes de visite", "description": "Cartes de visite professionnelles",
        "category": "materiel", "issuer_service": "Communication", "requires_return": 0, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 1, "display_order": 140,
        "field_schema": [
            {"key": "nom", "label": "Nom", "type": "text", "required": True, "placeholder": ""},
            {"key": "prenom", "label": "Prenom", "type": "text", "required": True, "placeholder": ""},
            {"key": "fonction", "label": "Fonction", "type": "text", "required": True, "placeholder": ""},
            {"key": "telephone", "label": "Telephone", "type": "text", "required": False, "placeholder": ""},
            {"key": "email", "label": "Email", "type": "text", "required": False, "placeholder": ""},
        ],
    },
    {
        "code": "autre", "label": "Autre materiel", "description": "Autre materiel a preciser",
        "category": "materiel", "issuer_service": "", "requires_return": 1, "trigger_key": "",
        "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 150,
        "field_schema": [
            {"key": "description", "label": "Description", "type": "text", "required": True, "placeholder": "Description du materiel"},
        ],
    },
]

DEFAULT_SERVICE_REFERENCES = [
    "Affaires juridiques / Commande publique",
    "Batiment",
    "Cabinet du Maire",
    "CCAS",
    "Communication",
    "Culture et Patrimoine",
    "CTM",
    "DGS",
    "DRH",
    "DSI",
    "DST",
    "Finances",
    "PM",
    "Population",
    "SEJE",
    "Secretariat service technique",
    "Sports",
    "Subvention",
    "Urbanisme",
    "VRD",
]


def normalize_resource_catalog_payload(payload, existing_row=None):
    existing = dict(existing_row) if existing_row else {}
    code = str(payload.get("code") if payload.get("code") is not None else existing.get("code") or "").strip()
    label = str(payload.get("label") if payload.get("label") is not None else existing.get("label") or "").strip()
    description = str(payload.get("description") if payload.get("description") is not None else existing.get("description") or "").strip()
    category = str(payload.get("category") if payload.get("category") is not None else existing.get("category") or "materiel").strip() or "materiel"
    if category not in {"materiel", "immateriel"}:
        category = "materiel"
    issuer_service = str(payload.get("issuer_service") if payload.get("issuer_service") is not None else existing.get("issuer_service") or "").strip()
    trigger_key = str(payload.get("trigger_key") if payload.get("trigger_key") is not None else existing.get("trigger_key") or "").strip()
    raw_field_schema = payload.get("field_schema") if "field_schema" in payload else payload.get("fieldSchema")
    if raw_field_schema is None:
        try:
            raw_field_schema = json.loads(existing.get("field_schema_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            raw_field_schema = []
    field_schema = normalize_resource_field_schema(raw_field_schema)
    display_order = payload.get("display_order") if payload.get("display_order") is not None else existing.get("display_order", 100)
    try:
        display_order = int(display_order)
    except (TypeError, ValueError):
        display_order = 100
    requires_return = bool(payload.get("requires_return", bool(existing.get("requires_return", True))))
    has_assignment_date = bool(payload.get("has_assignment_date", bool(existing.get("has_assignment_date", True))))
    has_assignment_condition = bool(payload.get("has_assignment_condition", bool(existing.get("has_assignment_condition", category == "materiel"))))
    has_assignment_notes = bool(payload.get("has_assignment_notes", bool(existing.get("has_assignment_notes", category == "materiel"))))
    if category == "immateriel":
        has_assignment_condition = False
    is_active = bool(payload.get("is_active", bool(existing.get("is_active", True))))
    return {
        "code": code,
        "label": label,
        "description": description,
        "category": category,
        "issuer_service": issuer_service,
        "requires_return": requires_return,
        "has_assignment_date": has_assignment_date,
        "has_assignment_condition": has_assignment_condition,
        "has_assignment_notes": has_assignment_notes,
        "display_order": display_order,
        "trigger_key": trigger_key,
        "field_schema": field_schema,
        "is_active": is_active,
    }


def seed_reference_catalogs(connection):
    now = utc_now()
    for resource in DEFAULT_RESOURCE_REFERENCES:
        existing = connection.execute(
            "SELECT id FROM resource_catalog WHERE code = ?",
            (resource["code"],),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE resource_catalog
                SET label = ?, description = ?, issuer_service = ?, field_schema_json = ?,
                    has_assignment_date = ?, has_assignment_condition = ?, has_assignment_notes = ?,
                    display_order = ?, trigger_key = ?, requires_return = ?, category = ?,
                    updated_at = ?
                WHERE id = ? AND is_builtin = 1
                """,
                (
                    resource["label"],
                    resource.get("description", ""),
                    resource["issuer_service"],
                    json.dumps(resource.get("field_schema", [])),
                    resource.get("has_assignment_date", 1),
                    resource.get("has_assignment_condition", 0),
                    resource.get("has_assignment_notes", 1),
                    resource.get("display_order", 100),
                    resource.get("trigger_key", ""),
                    resource.get("requires_return", 1),
                    resource.get("category", "materiel"),
                    now,
                    existing["id"],
                ),
            )
            continue
        connection.execute(
            """
            INSERT INTO resource_catalog (
                id, code, label, description, category, issuer_service, requires_return,
                has_assignment_date, has_assignment_condition, has_assignment_notes, display_order,
                trigger_key, field_schema_json, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                generate_id("resource"),
                resource["code"],
                resource["label"],
                resource.get("description", ""),
                resource["category"],
                resource["issuer_service"],
                resource["requires_return"],
                resource.get("has_assignment_date", 1),
                resource.get("has_assignment_condition", 0),
                resource.get("has_assignment_notes", 1),
                resource.get("display_order", 100),
                resource["trigger_key"],
                json.dumps(resource.get("field_schema", [])),
                now,
                now,
            ),
        )


def seed_service_catalog(connection):
    now = utc_now()
    for label in DEFAULT_SERVICE_REFERENCES:
        existing = connection.execute(
            "SELECT id FROM service_catalog WHERE label = ?",
            (label,),
        ).fetchone()
        if existing:
            continue
        connection.execute(
            """
            INSERT INTO service_catalog (
                id, label, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, 1, 1, ?, ?)
            """,
            (
                generate_id("service"),
                label,
                now,
                now,
            ),
        )
