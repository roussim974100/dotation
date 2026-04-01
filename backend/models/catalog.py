import json

from utils import generate_id, utc_now, slugify_field_key
from models.workflow import normalize_resource_field_schema


CORE_RESOURCE_CODES = {
    "ordinateur",
    "ecran",
    "telephone",
    "vehicule",
    "badge",
    "veste",
    "chaussuresSecurite",
    "autre",
    "vpn",
    "email",
}

DEFAULT_RESOURCE_REFERENCES = [
    {"code": "ordinateur", "label": "Ordinateur", "description": "Poste informatique remis par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 10},
    {"code": "ecran", "label": "Ecran", "description": "Ecran remis par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 20},
    {"code": "telephone", "label": "Telephone", "description": "Telephone professionnel remis par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 30},
    {"code": "tablette", "label": "Tablette", "description": "Tablette professionnelle remise par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 40},
    {"code": "vpn", "label": "VPN", "description": "Acces distant securise", "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 50},
    {"code": "email", "label": "Email", "description": "Messagerie professionnelle", "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 60},
    {"code": "badge", "label": "Badge d'acces", "description": "Badge d'acces batiment", "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 70},
    {"code": "cles", "label": "Cle(s)", "description": "Cles remises par le service batiment", "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 80},
    {"code": "veste", "label": "Veste", "description": "Vetement de travail remis par le service batiment", "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 90},
    {"code": "chaussuresSecurite", "label": "Chaussures de securite", "description": "Chaussures de securite remises par le service batiment", "category": "materiel", "issuer_service": "Batiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 100},
    {"code": "zoneAlarme", "label": "Zone alarme", "description": "Zone d'alarme attribuee", "category": "immateriel", "issuer_service": "Batiment", "requires_return": 0, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 110},
    {"code": "vehicule", "label": "Vehicule", "description": "Vehicule attribue par un service", "category": "materiel", "issuer_service": "Autres services", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 120},
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
                "[]",
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
