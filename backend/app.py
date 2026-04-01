from flask import Flask, jsonify, make_response, redirect, request, send_from_directory, session, has_request_context
import base64
import bcrypt
import io
import json
import os
import secrets
import sqlite3
import urllib.parse
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from functools import wraps
from xml.sax.saxutils import escape as xml_escape
from werkzeug.middleware.proxy_fix import ProxyFix
import re

from config import (
    BASE_DIR, FRONTEND_DIR, FRONTEND_ASSETS_DIR, CUSTOM_BRANDING_DIR,
    DB_PATH, APP_SECRET_PATH,
    CITY_LOGO_URL, CITY_LOGO_PATH, get_app_secret_key,
)
from utils import (
    utc_now, generate_id, bool_to_int,
    mask_text, mask_payload,
    slugify_field_key, slugify_filename,
    build_title, normalize_dossier_type, dossier_type_label,
    format_export_datetime, get_signature_datetime, get_restitution_signature_datetime,
    format_beneficiary_label, format_status_label, format_restitution_state_label,
    format_restitution_decision_label,
)
from database import (
    get_db, _KNOWN_TABLES, table_columns, ensure_column,
    normalize_reference_row, normalize_service_row,
)
from auth import (
    USERS_FILE, DEFAULT_GROUPS,
    load_auth_config, save_auth_config,
    _LOGIN_MAX_ATTEMPTS, _LOGIN_WINDOW_SECONDS, _login_attempts, _login_attempts_lock,
    _is_login_rate_limited,
    login_required, permission_required, admin_required,
    get_user_record, password_complexity_error, is_valid_username,
    build_user_context, current_user, can_export_signature_assets, has_permission,
    check_user,
    extract_first_forwarded_ip, get_request_client_ip,
)
from models.dossier import sync_person_and_dossier, migrate_forms_to_dossiers
from models.audit import (
    CLIENT_CONTEXT_COOKIE_NAME,
    current_actor,
    read_client_context_cookie, read_login_attempt_context,
    build_request_client_log_details, merge_app_log_details,
    insert_audit_event, insert_app_log,
)
from models.signature import (
    signature_link_label, signature_link_scope,
    signature_link_public_url, signature_link_public_actor,
    signature_link_expiration, generate_signature_token,
    materialize_signature_link, serialize_signature_link,
    get_latest_signature_link, get_signature_link_by_id, get_signature_link_by_token,
    revoke_signature_links_for_form, create_signature_link, revoke_signature_link,
)
from models.settings import (
    DEFAULT_APP_SETTINGS, THEME_PRESETS, BRAND_LOGO_CACHE,
    seed_app_settings, get_app_settings, save_app_settings,
    sanitize_brand_file_name, get_brand_logo_public_url, get_brand_logo_candidates,
    resolve_theme_id, resolve_dark_mode, get_dpo_email,
    build_public_settings_payload,
    load_brand_logo_image, load_a_quai_pdf_logo_image,
)
from models.workflow import (
    normalize_resource_field_schema,
    summarize_dynamic_resource,
    uses_dynamic_resource_assignment_date,
    uses_dynamic_resource_assignment_condition,
    uses_dynamic_resource_assignment_notes,
    is_dynamic_resource_complete,
    is_dynamic_resource_payload,
    extract_items,
    summarize_assignment_progress,
    collect_resource_validation_errors,
    derive_restitution_workflow_status,
    compute_effective_workflow_status,
    derive_dossier_status,
    is_restitution_eligible_material_details,
    describe_assignment_condition,
    collect_resource_entries,
)
from pdf.attribution import _AQuaiDoc, build_pdf_bytes
from pdf.restitution import build_restitution_pdf_bytes


app = Flask(__name__, static_folder=None)
app.secret_key = get_app_secret_key()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SESSION_COOKIE_NAME"] = "publier_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


@app.after_request
def disable_frontend_cache(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        if "charset=" not in content_type:
            response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif "application/json" in content_type:
        if "charset=" not in content_type:
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif any(token in content_type for token in ("application/javascript", "text/css")):
        if "charset=" not in content_type:
            mime = "application/javascript" if "application/javascript" in content_type else "text/css"
            response.headers["Content-Type"] = f"{mime}; charset=utf-8"
        response.headers["Cache-Control"] = "public, no-cache, max-age=0, must-revalidate"
    elif response.status_code == 200 and request.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response

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
    {"code": "ecran", "label": "Écran", "description": "Écran remis par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 20},
    {"code": "telephone", "label": "Téléphone", "description": "Téléphone professionnel remis par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 30},
    {"code": "tablette", "label": "Tablette", "description": "Tablette professionnelle remise par la DSI", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 40},
    {"code": "vpn", "label": "VPN", "description": "Accès distant sécurisé", "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 50},
    {"code": "email", "label": "Email", "description": "Messagerie professionnelle", "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 60},
    {"code": "badge", "label": "Badge d'accès", "description": "Badge d'accès bâtiment", "category": "materiel", "issuer_service": "Bâtiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 70},
    {"code": "cles", "label": "Clé(s)", "description": "Clés remises par le service bâtiment", "category": "materiel", "issuer_service": "Bâtiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 80},
    {"code": "veste", "label": "Veste", "description": "Vêtement de travail remis par le service bâtiment", "category": "materiel", "issuer_service": "Bâtiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 90},
    {"code": "chaussuresSecurite", "label": "Chaussures de sécurité", "description": "Chaussures de sécurité remises par le service bâtiment", "category": "materiel", "issuer_service": "Bâtiment", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 100},
    {"code": "zoneAlarme", "label": "Zone alarme", "description": "Zone d'alarme attribuée", "category": "immateriel", "issuer_service": "Bâtiment", "requires_return": 0, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 0, "has_assignment_notes": 0, "display_order": 110},
    {"code": "vehicule", "label": "Véhicule", "description": "Véhicule attribué par un service", "category": "materiel", "issuer_service": "Autres services", "requires_return": 1, "trigger_key": "", "has_assignment_date": 1, "has_assignment_condition": 1, "has_assignment_notes": 1, "display_order": 120},
]

DEFAULT_SERVICE_REFERENCES = [
    "Affaires juridiques / Commande publique",
    "Bâtiment",
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
    "Secrétariat service technique",
    "Sports",
    "Subvention",
    "Urbanisme",
    "VRD",
]


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


def init_db():
    # Le schema reste volontairement compact:
    # - dotation_forms = dossier principal + payload JSON
    # - dotation_items = vision par ressource pour la restitution et les exports
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS dotation_forms (
                id TEXT PRIMARY KEY,
                dossier_id TEXT,
                dossier_type TEXT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                beneficiary_type TEXT,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                service TEXT,
                fonction TEXT,
                mandat TEXT,
                rgpd_accepted INTEGER NOT NULL DEFAULT 0,
                signature_data TEXT,
                assigned_at TEXT,
                returned_at TEXT,
                return_reason TEXT,
                return_notes TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dotation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                form_id TEXT NOT NULL,
                item_key TEXT NOT NULL,
                category TEXT NOT NULL,
                label TEXT NOT NULL,
                assigned INTEGER NOT NULL DEFAULT 0,
                returned INTEGER NOT NULL DEFAULT 0,
                returned_at TEXT,
                return_condition TEXT,
                notes TEXT,
                details_json TEXT,
                FOREIGN KEY(form_id) REFERENCES dotation_forms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS persons (
                id TEXT PRIMARY KEY,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                qualite TEXT NOT NULL,
                service TEXT,
                fonction TEXT,
                mandat TEXT,
                date_arrivee TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS onboarding_dossiers (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL,
                dossier_type TEXT NOT NULL DEFAULT 'arrivee',
                status TEXT NOT NULL DEFAULT 'a_preparer',
                assigned_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                dossier_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_label TEXT NOT NULL,
                actor TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(dossier_id) REFERENCES onboarding_dossiers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS app_logs (
                id TEXT PRIMARY KEY,
                actor TEXT,
                scope TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_label TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deleted_items (
                id TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,
                item_key TEXT NOT NULL,
                item_label TEXT,
                payload_json TEXT NOT NULL,
                deleted_by TEXT,
                deleted_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resource_catalog (
                id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL,
                issuer_service TEXT,
                requires_return INTEGER NOT NULL DEFAULT 1,
                has_assignment_date INTEGER NOT NULL DEFAULT 1,
                has_assignment_condition INTEGER NOT NULL DEFAULT 0,
                has_assignment_notes INTEGER NOT NULL DEFAULT 1,
                display_order INTEGER NOT NULL DEFAULT 100,
                trigger_key TEXT,
                field_schema_json TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_catalog (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signature_links (
                id TEXT PRIMARY KEY,
                form_id TEXT NOT NULL,
                link_type TEXT NOT NULL DEFAULT 'assignment',
                token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_by TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                revoked_at TEXT,
                revoked_by TEXT,
                last_opened_at TEXT,
                last_opened_ip TEXT,
                notes TEXT,
                FOREIGN KEY(form_id) REFERENCES dotation_forms(id) ON DELETE CASCADE
            );

            """
        )
        ensure_column(connection, "dotation_forms", "dossier_id", "dossier_id TEXT")
        ensure_column(connection, "dotation_forms", "dossier_type", "dossier_type TEXT")
        ensure_column(connection, "onboarding_dossiers", "dossier_type", "dossier_type TEXT NOT NULL DEFAULT 'arrivee'")
        ensure_column(connection, "resource_catalog", "description", "description TEXT")
        ensure_column(connection, "resource_catalog", "field_schema_json", "field_schema_json TEXT")
        ensure_column(connection, "resource_catalog", "has_assignment_date", "has_assignment_date INTEGER NOT NULL DEFAULT 1")
        ensure_column(connection, "resource_catalog", "has_assignment_condition", "has_assignment_condition INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "resource_catalog", "has_assignment_notes", "has_assignment_notes INTEGER NOT NULL DEFAULT 1")
        ensure_column(connection, "resource_catalog", "display_order", "display_order INTEGER NOT NULL DEFAULT 100")
        connection.execute(
            """
            UPDATE resource_catalog
            SET has_assignment_date = COALESCE(has_assignment_date, 1),
                has_assignment_condition = CASE
                    WHEN category = 'immatériel' THEN 0
                    WHEN category = 'immateriel' THEN COALESCE(has_assignment_condition, 0)
                    ELSE COALESCE(has_assignment_condition, 1)
                END,
                has_assignment_notes = COALESCE(has_assignment_notes, 1),
                display_order = COALESCE(display_order, 100)
            """
        )
        ensure_column(connection, "signature_links", "link_type", "link_type TEXT NOT NULL DEFAULT 'assignment'")
        seed_reference_catalogs(connection)
        seed_service_catalog(connection)
        seed_app_settings(connection)
        migrate_forms_to_dossiers(connection)


def build_login_forensic_details(username, auth_state):
    details = {
        "etat_authentification": auth_state,
        "identifiant_tente": username or "(vide)",
        "methode": request.method,
        "chemin": request.path,
        "hote": request.host,
        "ip": get_request_client_ip(),
        "ip_distante_socket": str(request.remote_addr or "").strip(),
        "ip_proxy_reelle": str(request.headers.get("X-Real-IP") or "").strip(),
        "ip_wan_proxy": extract_first_forwarded_ip(request.headers.get("X-Forwarded-For")),
        "chaine_proxy": str(request.headers.get("X-Forwarded-For") or "").strip(),
        "origine": str(request.headers.get("Origin") or "").strip(),
        "referer": str(request.headers.get("Referer") or "").strip(),
        "accept_language": str(request.headers.get("Accept-Language") or "").strip(),
    }
    details.update(read_login_attempt_context())
    return {key: value for key, value in details.items() if value not in {"", None}}




def insert_deleted_item(connection, item_type, item_key, item_label, payload):
    connection.execute(
        """
        INSERT INTO deleted_items (id, item_type, item_key, item_label, payload_json, deleted_by, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generate_id("trash"),
            item_type,
            item_key,
            item_label,
            json.dumps(payload, ensure_ascii=False),
            session.get("user"),
            utc_now(),
        ),
    )




def build_form_export_lines(payload):
    beneficiaire = payload.get("beneficiaire", {})
    workflow = payload.get("workflow", {})
    dossier = payload.get("dossier", {})
    validation = payload.get("validation", {})
    restitution = payload.get("restitution", {})
    signature_datetime = get_signature_datetime(payload)
    lines = [
        "DOSSIER D'ATTRIBUTION DE RESSOURCES",
        "",
        f"État : {format_status_label(workflow.get('status') or 'draft')}",
        f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
        f"Date de prise de fonction : {format_export_datetime(payload.get('meta', {}).get('startAt'))}",
        f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
        "",
        "Bénéficiaire",
        f"Nom : {beneficiaire.get('nom') or '-'}",
        f"Prénom : {beneficiaire.get('prenom') or '-'}",
        f"Qualité : {format_beneficiary_label(beneficiaire.get('qualite'))}",
        f"Service : {beneficiaire.get('service') or '-'}",
        f"Fonction : {beneficiaire.get('fonction') or '-'}",
        f"Mandat : {beneficiaire.get('mandat') or '-'}",
        f"Service de destination : {dossier.get('serviceDestination') or '-'}",
        "",
        "Ressources attribuées",
    ]

    resources = collect_resource_entries(payload)
    if resources:
        current_service = None
        for entry in resources:
            if entry["service"] != current_service:
                current_service = entry["service"]
                lines.append(f"{current_service}")
            lines.append(f"- {entry['label']} : {entry['details']}")
    else:
        lines.append("- Aucune ressource renseignée")

    lines.extend(
        [
            "",
            "Restitution",
            f"État de restitution : {format_status_label(workflow.get('status') or 'draft')}",
            f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
            f"Motif : {restitution.get('reason') or '-'}",
            f"Observations : {restitution.get('notes') or '-'}",
            "",
            "Validation",
            f"Information RGPD portée à connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
            f"Signature présente : {'Oui' if validation.get('signatureDataUrl') else 'Non'}",
            f"Date de signature : {signature_datetime}",
        ]
    )
    return lines


def normalize_workflow_before_save(payload):
    workflow = payload.setdefault("workflow", {})
    current_status = workflow.get("status") or "draft"
    restitution = payload.get("restitution", {})

    if current_status in {"returned", "partial_return", "cancelled"} or (
        current_status == "awaiting_signature"
        and (
            restitution.get("items")
            or restitution.get("returnedAt")
            or restitution.get("signatureStatus") == "deferred"
        )
    ):
        return payload

    resource_errors = collect_resource_validation_errors(payload)
    payload.setdefault("meta", {})["resourceValidationErrors"] = resource_errors
    workflow["status"] = compute_effective_workflow_status(payload)
    if workflow["status"] == "active":
        payload["meta"]["lockedAt"] = payload["meta"].get("lockedAt") or utc_now()
        return payload

    payload["meta"]["lockedAt"] = ""
    return payload


def persist_form(payload, allow_locked_update=False):
    # Point d'entree unique de creation / mise a jour d'une fiche.
    # Le verrouillage s'applique aux fiches signees sauf pour le flux de restitution dedie.
    if not payload.get("beneficiaire", {}).get("nom") or not payload.get("beneficiaire", {}).get("prenom"):
        raise ValueError("Les champs nom et prenom sont obligatoires.")

    payload = normalize_workflow_before_save(payload)
    form_id = payload.setdefault("meta", {}).get("id") or str(int(datetime.now().timestamp() * 1000))
    payload["meta"]["id"] = form_id
    payload["meta"]["savedAt"] = utc_now()

    title = build_title(payload)
    status = payload.get("workflow", {}).get("status") or "draft"
    beneficiaire = payload.get("beneficiaire", {})
    validation = payload.get("validation", {})
    restitution = payload.get("restitution", {})
    dossier = payload.get("dossier", {})
    assigned_at = payload.get("meta", {}).get("assignedAt") or payload["meta"]["savedAt"]
    payload["meta"]["startAt"] = payload.get("meta", {}).get("startAt") or ""

    row = {
        "id": form_id,
        "dossier_id": payload.get("meta", {}).get("dossierId"),
        "dossier_type": normalize_dossier_type(dossier.get("type")),
        "title": title,
        "status": status,
        "beneficiary_type": beneficiaire.get("qualite"),
        "nom": beneficiaire.get("nom", ""),
        "prenom": beneficiaire.get("prenom", ""),
        "service": beneficiaire.get("service"),
        "fonction": beneficiaire.get("fonction"),
        "mandat": beneficiaire.get("mandat"),
        "rgpd_accepted": bool_to_int(validation.get("rgpdAccepted")),
        "signature_data": validation.get("signatureDataUrl"),
        "assigned_at": assigned_at,
        "returned_at": restitution.get("returnedAt"),
        "return_reason": restitution.get("reason"),
        "return_notes": restitution.get("notes"),
        "payload_json": "",
        "created_at": payload.get("meta", {}).get("createdAt") or payload["meta"]["savedAt"],
        "updated_at": payload["meta"]["savedAt"],
    }

    items = extract_items(payload)

    with get_db() as connection:
        exists = connection.execute(
            "SELECT id, dossier_id, created_at, signature_data, payload_json FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).fetchone()
        if exists:
            existing_payload = json.loads(exists["payload_json"])
            if existing_payload.get("meta", {}).get("lockedAt") and not allow_locked_update:
                raise ValueError("Cette fiche est signée et verrouillée. Elle ne peut plus être modifiée.")
            row["created_at"] = exists["created_at"]
        _, dossier_id = sync_person_and_dossier(connection, payload, exists)
        row["dossier_id"] = dossier_id
        row["assigned_at"] = payload.get("meta", {}).get("assignedAt") or row["assigned_at"]
        row["payload_json"] = json.dumps(payload, ensure_ascii=False)

        if exists:
            connection.execute(
                """
                UPDATE dotation_forms
                SET title = :title,
                    dossier_id = :dossier_id,
                    dossier_type = :dossier_type,
                    status = :status,
                    beneficiary_type = :beneficiary_type,
                    nom = :nom,
                    prenom = :prenom,
                    service = :service,
                    fonction = :fonction,
                    mandat = :mandat,
                    rgpd_accepted = :rgpd_accepted,
                    signature_data = :signature_data,
                    assigned_at = :assigned_at,
                    returned_at = :returned_at,
                    return_reason = :return_reason,
                    return_notes = :return_notes,
                    payload_json = :payload_json,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                row,
            )
        else:
            connection.execute(
                """
                INSERT INTO dotation_forms (
                    id, dossier_id, dossier_type, title, status, beneficiary_type, nom, prenom, service, fonction, mandat,
                    rgpd_accepted, signature_data, assigned_at, returned_at, return_reason,
                    return_notes, payload_json, created_at, updated_at
                ) VALUES (
                    :id, :dossier_id, :dossier_type, :title, :status, :beneficiary_type, :nom, :prenom, :service, :fonction, :mandat,
                    :rgpd_accepted, :signature_data, :assigned_at, :returned_at, :return_reason,
                    :return_notes, :payload_json, :created_at, :updated_at
                )
                """,
                row,
            )

        connection.execute("DELETE FROM dotation_items WHERE form_id = ?", (form_id,))
        connection.executemany(
            """
            INSERT INTO dotation_items (
                form_id, item_key, category, label, assigned, returned,
                returned_at, return_condition, notes, details_json
            ) VALUES (
                :form_id, :item_key, :category, :label, :assigned, :returned,
                :returned_at, :return_condition, :notes, :details_json
            )
            """,
            [
                {
                    "form_id": form_id,
                    **item,
                    "assigned": bool_to_int(item["assigned"]),
                    "returned": bool_to_int(item["returned"]),
                }
                for item in items
            ],
        )
        insert_audit_event(
            connection,
            dossier_id,
            "form_updated" if exists else "form_created",
            "Dossier d'attribution mis a jour" if exists else "Dossier d'attribution cree",
            {"form_id": form_id, "status": status},
        )
        insert_app_log(
            connection,
            "dossier",
            "form_updated" if exists else "form_created",
            "Dossier d'attribution mis a jour" if exists else "Dossier d'attribution cree",
            "form",
            form_id,
            {"dossier_id": dossier_id, "status": status, "title": title},
        )

    return get_form(form_id)


def row_to_summary(row):
    # Resume leger pour la page d'accueil.
    payload = {}
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    effective_status = compute_effective_workflow_status(payload)
    progress = summarize_assignment_progress(payload)
    summary = {
        "id": row["id"],
        "dossierId": row["dossier_id"],
        "dossierType": row["dossier_type"],
        "title": row["title"],
        "status": effective_status,
        "isLocked": effective_status == "active",
        "beneficiaryType": row["beneficiary_type"],
        "nom": row["nom"],
        "prenom": row["prenom"],
        "service": row["service"],
        "fonction": row["fonction"],
        "mandat": row["mandat"],
        "assignedAt": row["assigned_at"],
        "startAt": progress["startAt"],
        "returnedAt": row["returned_at"],
        "updatedAt": row["updated_at"],
        "pendingFinalization": bool(payload.get("restitution", {}).get("pendingFinalization")),
        "completedResources": progress["completed"],
        "totalResources": progress["total"],
        "resourceProgressRatio": progress["ratio"],
        "timingStatus": progress["timingStatus"],
        "timingLabel": progress["timingLabel"],
    }
    user = current_user()
    if user and user.get("data_scope") == "masked":
        summary["nom"] = mask_text(summary["nom"])
        summary["prenom"] = mask_text(summary["prenom"])
        prefix = (summary["mandat"] if summary["beneficiaryType"] == "elu" else summary["service"]) or (
            "MANDAT" if summary["beneficiaryType"] == "elu" else "SERVICE"
        )
        summary["title"] = f"{str(prefix).upper()} - {summary['nom']} {summary['prenom']}".strip()
    return summary


def get_form(form_id):
    # Retourne a la fois:
    # - un summary pour l'affichage liste
    # - le payload complet pour l'edition / l'impression
    # - les items normalises pour la page de restitution
    with get_db() as connection:
        form_row = connection.execute(
            "SELECT * FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).fetchone()
        if not form_row:
            return None

        items = connection.execute(
            "SELECT * FROM dotation_items WHERE form_id = ? ORDER BY id ASC",
            (form_id,),
        ).fetchall()

    payload = json.loads(form_row["payload_json"])
    payload.setdefault("meta", {})
    payload.setdefault("dossier", {})
    payload["meta"]["id"] = form_row["id"]
    payload["meta"]["dossierId"] = form_row["dossier_id"]
    payload["meta"]["createdAt"] = form_row["created_at"]
    payload["meta"]["savedAt"] = form_row["updated_at"]
    payload["meta"]["assignedAt"] = form_row["assigned_at"]
    payload["dossier"]["type"] = normalize_dossier_type(payload.get("dossier", {}).get("type") or form_row["dossier_type"] or "arrivee")
    payload.setdefault("workflow", {})["status"] = compute_effective_workflow_status(payload)
    if payload["workflow"]["status"] != "active":
        payload["meta"]["lockedAt"] = ""
    user = current_user()
    if user and user.get("data_scope") == "masked":
        payload = mask_payload(payload)

    return {
        "summary": row_to_summary(form_row),
        "data": payload,
        "items": [
            {
                "id": item["id"],
                "itemKey": item["item_key"],
                "category": item["category"],
                "label": item["label"],
                "assigned": bool(item["assigned"]),
                "returned": bool(item["returned"]),
                "returnedAt": item["returned_at"],
                "returnCondition": item["return_condition"],
                "notes": item["notes"],
                "details": json.loads(item["details_json"]) if item["details_json"] else {},
            }
            for item in items
        ],
    }


def build_signature_public_payload(form_data, link_row):
    payload = form_data["data"]
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]
    dpo_email = get_dpo_email(settings)
    beneficiaire = payload.get("beneficiaire", {})
    grouped_resources = {"materiel": [], "immateriel": []}
    for entry in collect_resource_entries(payload):
        grouped_resources.setdefault(entry["category"], []).append({
            "label": entry["label"],
            "details": entry["details"],
            "service": entry["service"],
            "assignmentConditionLabel": entry.get("assignmentConditionLabel") or "",
            "assignmentConditionNotes": entry.get("assignmentConditionNotes") or "",
            "assignmentSummary": entry.get("assignmentSummary") or "",
        })

    return {
        "link": {
            "status": link_row["status"],
            "expiresAt": link_row["expires_at"],
            "type": link_row["link_type"],
        },
        "form": {
            "id": form_data["summary"]["id"],
            "title": form_data["summary"]["title"],
            "dossierType": form_data["summary"]["dossierType"],
            "beneficiaire": {
                "nom": beneficiaire.get("nom") or "",
                "prenom": beneficiaire.get("prenom") or "",
                "qualite": beneficiaire.get("qualite") or "",
                "service": beneficiaire.get("service") or "",
                "fonction": beneficiaire.get("fonction") or "",
                "mandat": beneficiaire.get("mandat") or "",
            },
            "resources": grouped_resources,
            "rgpdText": [
                f"Les donnees a caractere personnel renseignees dans ce dossier font l'objet d'un traitement par {org_name} afin d'assurer la gestion des attributions de ressources professionnelles, le suivi des remises et, le cas echeant, des restitutions.",
                "Conformement au reglement general sur la protection des donnees et a la loi Informatique et Libertes, la personne concernee dispose notamment de droits d'acces, de rectification, d'effacement, de limitation et d'opposition, dans les conditions prevues par la reglementation applicable.",
                f"Pour toute question relative au traitement de ses donnees personnelles ou pour exercer ses droits, la personne concernee peut contacter le delegue a la protection des donnees a l'adresse suivante : {dpo_email}.",
            ],
        },
    }


def build_restitution_signature_public_payload(form_data, link_row):
    payload = form_data["data"]
    beneficiaire = payload.get("beneficiaire", {})
    restitution = payload.get("restitution", {})
    material_index = {
        item["itemKey"]: item
        for item in (form_data.get("items") or [])
        if item.get("category") == "materiel" and is_restitution_eligible_material_details(item.get("details") or {})
    }
    restitution_items = []
    for item_key, state in (restitution.get("items") or {}).items():
        item = material_index.get(item_key, {})
        details = item.get("details") or {}
        detail_text = summarize_dynamic_resource(details) if details.get("fields") else " - ".join(
            str(value).strip()
            for key, value in details.items()
            if key not in {"selected", "conditionAttribution", "conditionNotes"} and str(value or "").strip()
        )
        restitution_items.append(
            {
                "label": item.get("label") or item_key,
                "details": detail_text or "Sans détail complémentaire",
                "state": state.get("state") or state.get("condition") or "conforme",
                "stateLabel": format_restitution_state_label(state.get("state") or state.get("condition") or "conforme"),
                "notes": state.get("notes") or "",
                "assignmentSummary": " - ".join(describe_assignment_condition(details)),
            }
        )

    return {
        "link": {
            "status": link_row["status"],
            "expiresAt": link_row["expires_at"],
            "type": link_row["link_type"],
        },
        "form": {
            "id": form_data["summary"]["id"],
            "title": form_data["summary"]["title"],
            "beneficiaire": {
                "nom": beneficiaire.get("nom") or "",
                "prenom": beneficiaire.get("prenom") or "",
                "qualite": beneficiaire.get("qualite") or "",
                "service": beneficiaire.get("service") or "",
                "fonction": beneficiaire.get("fonction") or "",
                "mandat": beneficiaire.get("mandat") or "",
            },
            "restitution": {
                "returnedAt": restitution.get("returnedAt") or "",
                "reason": restitution.get("reason") or "",
                "notes": restitution.get("notes") or "",
                "items": restitution_items,
                "signataireDecision": restitution.get("signataireDecision") or "confirmed",
                "signataireComment": restitution.get("signataireComment") or "",
            },
        },
    }


def download_response(file_bytes, filename, content_type):
    response = make_response(file_bytes)
    response.headers["Content-Type"] = content_type
    encoded_filename = urllib.parse.quote(filename, safe="")
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
    return response


init_db()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _is_login_rate_limited(get_request_client_ip()):
            return redirect("/login?error=rate_limited")
        submitted_token = request.form.get("csrf_token") or ""
        if not submitted_token or not secrets.compare_digest(submitted_token, session.get("csrf_token", "")):
            return redirect("/login?error=invalid")
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        auth_state = check_user(username, password)

        if auth_state == "ok":
            session["user"] = username
            with get_db() as connection:
                insert_app_log(
                    connection,
                    "security",
                    "login",
                    "Connexion réussie",
                    "user",
                    username,
                    {"ip": get_request_client_ip()},
                    actor=username,
                )
            return redirect("/")
        with get_db() as connection:
            insert_app_log(
                connection,
                "security",
                "login_failed",
                "Échec de connexion",
                "user",
                username or "(vide)",
                build_login_forensic_details(username, auth_state),
                actor="anonymous",
            )
        return redirect(f"/login?error={auth_state}")

    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token") or ""
        if not submitted_token or not secrets.compare_digest(submitted_token, session.get("csrf_token", "")):
            return redirect("/signup?error=invalid_request")
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""
        config = load_auth_config()

        if not username or not password or not password_confirm:
            return redirect("/signup?error=missing_fields")
        if not is_valid_username(username):
            return redirect("/signup?error=invalid_username")
        if get_user_record(username):
            return redirect("/signup?error=user_exists")
        if password != password_confirm:
            return redirect("/signup?error=password_mismatch")
        complexity_error = password_complexity_error(password)
        if complexity_error:
            return redirect(f"/signup?error={complexity_error}")

        config.setdefault("users", []).append({
            "username": username,
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "groups": ["lecture"],
            "is_active": True,
            "status": "pending",
        })
        save_auth_config(config)
        with get_db() as connection:
            insert_app_log(
                connection,
                "security",
                "signup_requested",
                "Demande d'inscription",
                "user",
                username,
                {"groups": ["lecture"], "status": "pending"},
                actor=username,
            )
        return redirect("/login?notice=signup_pending")

    return send_from_directory(FRONTEND_DIR, "signup.html")


@app.route("/logout")
def logout():
    username = session.get("user")
    if username:
        with get_db() as connection:
            insert_app_log(
                connection,
                "security",
                "logout",
                "Déconnexion",
                "user",
                username,
                {"ip": get_request_client_ip()},
                actor=username,
            )
    session.clear()
    return redirect("/login")


@app.route("/")
@login_required
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/index.html")
@login_required
def index_page():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/historique-dossiers.html")
@login_required
def assignments_history_page():
    return send_from_directory(FRONTEND_DIR, "historique-dossiers.html")


@app.route("/historique-restitutions.html")
@login_required
def restitutions_history_page():
    return send_from_directory(FRONTEND_DIR, "historique-restitutions.html")


@app.route("/form.html")
@login_required
def form_page():
    return send_from_directory(FRONTEND_DIR, "form.html")


@app.route("/restitution.html")
@login_required
def restitution_page():
    return send_from_directory(FRONTEND_DIR, "restitution.html")


@app.route("/about.html")
def about_page():
    return send_from_directory(FRONTEND_DIR, "about.html")


@app.route("/contact.html")
def contact_page():
    return send_from_directory(FRONTEND_DIR, "contact.html")


@app.route("/help.html")
@login_required
def help_page():
    return send_from_directory(FRONTEND_DIR, "help.html")


@app.route("/signature/<token>")
def signature_page(token):
    response = make_response(send_from_directory(FRONTEND_DIR, "signature.html"))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/restitution-signature/<token>")
def restitution_signature_page(token):
    response = make_response(send_from_directory(FRONTEND_DIR, "restitution-signature.html"))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/admin.html")
@login_required
def admin_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin.html")


@app.route("/admin-comptes.html")
@login_required
def admin_accounts_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-comptes.html")


@app.route("/admin-services.html")
@login_required
def admin_services_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-services.html")


@app.route("/admin-ressources.html")
@login_required
def admin_resources_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-ressources.html")


@app.route("/admin-ressources-ordre.html")
@login_required
def admin_resources_order_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-ressources-ordre.html")


@app.route("/admin-personnalisation.html")
@login_required
def admin_branding_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-personnalisation.html")


@app.route("/logs.html")
@login_required
def logs_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "logs.html")


@app.route("/trash.html")
@admin_required
def trash_page():
    return send_from_directory(FRONTEND_DIR, "trash.html")


@app.route("/css/<path:path>")
def send_css(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, "css"), path)


@app.route("/js/<path:path>")
def send_js(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, "js"), path)


@app.route("/assets/<path:path>")
def send_assets(path):
    return send_from_directory(FRONTEND_ASSETS_DIR, path)


@app.route("/api/settings/logo", methods=["GET"])
def public_logo_route():
    settings = get_app_settings()
    logo_mode = settings.get("brand_logo_mode") or DEFAULT_APP_SETTINGS["brand_logo_mode"]

    if logo_mode == "file":
        relative_path = (settings.get("brand_logo_file") or "").replace("\\", "/").lstrip("/")
        absolute_path = os.path.join(FRONTEND_ASSETS_DIR, relative_path) if relative_path else ""
        if relative_path and os.path.exists(absolute_path):
            response = send_from_directory(FRONTEND_ASSETS_DIR, relative_path)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

    if os.path.exists(CITY_LOGO_PATH):
        response = send_from_directory(FRONTEND_ASSETS_DIR, os.path.basename(CITY_LOGO_PATH))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    if logo_mode == "url":
        remote_url = settings.get("brand_logo_url") or CITY_LOGO_URL
        if remote_url and re.match(r"^https?://", remote_url, re.IGNORECASE):
            return redirect(remote_url, code=302)

    response = send_from_directory(FRONTEND_ASSETS_DIR, "app-icon.svg")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/csrf-token", methods=["GET"])
def csrf_token_route():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return jsonify({"token": session["csrf_token"]})


@app.route("/api/client-context", methods=["GET"])
def client_context_route():
    return jsonify({
        "serverSeenIp": get_request_client_ip(),
        "forwardedFor": extract_first_forwarded_ip(request.headers.get("X-Forwarded-For")),
        "realIp": str(request.headers.get("X-Real-IP") or "").strip(),
    })


@app.route("/api/forms", methods=["GET"])
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


@app.route("/api/forms/export", methods=["GET"])
@login_required
def export_forms():
    # Export Excel lisible en deux onglets : dossiers et ressources.
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


@app.route("/api/forms/<form_id>/pdf", methods=["GET"])
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


@app.route("/api/forms/<form_id>/restitution-pdf", methods=["GET"])
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


@app.route("/api/forms/export-pdf-batch", methods=["POST"])
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


@app.route("/api/forms/export-restitution-pdf-batch", methods=["POST"])
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


def csv_escape(value):
    text = "" if value is None else str(value)
    text = text.replace('"', '""')
    return f'"{text}"'


def spreadsheet_cell(value, style_id="cell"):
    text = "" if value is None else str(value)
    return (
        f'<Cell ss:StyleID="{style_id}">'
        f'<Data ss:Type="String">{xml_escape(text)}</Data>'
        f"</Cell>"
    )


def build_excel_workbook(rows, item_rows):
    headers = [
        "ID dossier",
        "Titre",
        "État",
        "Type de dossier",
        "Qualité",
        "Nom",
        "Prénom",
        "Service",
        "Fonction",
        "Mandat",
        "Service de destination",
        "Date de prise de fonction",
        "Date de remise",
        "Date de restitution",
        "RGPD",
        "Signature",
        "Ressources attribuées",
        "Motif restitution",
        "Observations",
        "Créé le",
        "Mis à jour le",
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
        "ID dossier",
        "Titre dossier",
        "Service émetteur",
        "Ressource",
        "Catégorie",
        "Détails",
        "État restitution",
        "Date restitution",
        "Observation",
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


@app.route("/api/forms/<form_id>", methods=["GET"])
@login_required
def get_form_route(form_id):
    if not has_permission("forms.read_detail"):
        return jsonify({"error": "forbidden"}), 403
    form_data = get_form(form_id)
    if not form_data:
        return jsonify({"error": "not_found"}), 404
    return jsonify(form_data)


@app.route("/api/forms/<form_id>/signature-link", methods=["GET"])
@login_required
def get_form_signature_link_route(form_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403
    if not get_form(form_id):
        return jsonify({"error": "not_found"}), 404
    with get_db() as connection:
        link_row = get_latest_signature_link(connection, form_id, link_type="assignment")
    return jsonify({"link": serialize_signature_link(link_row)})


@app.route("/api/forms/<form_id>/signature-link", methods=["POST"])
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
                connection,
                form_id,
                actor=current_actor(),
                expires_in_hours=validity_days * 24,
                link_type="assignment",
            )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"link": serialize_signature_link(link_row)}), 201


@app.route("/api/forms/<form_id>/restitution-signature-link", methods=["GET"])
@login_required
def get_form_restitution_signature_link_route(form_id):
    if not has_permission("forms.restitution"):
        return jsonify({"error": "forbidden"}), 403
    if not get_form(form_id):
        return jsonify({"error": "not_found"}), 404
    with get_db() as connection:
        link_row = get_latest_signature_link(connection, form_id, link_type="restitution")
    return jsonify({"link": serialize_signature_link(link_row)})


@app.route("/api/forms/<form_id>/restitution-signature-link", methods=["POST"])
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
                connection,
                form_id,
                actor=current_actor(),
                expires_in_hours=validity_days * 24,
                link_type="restitution",
            )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"link": serialize_signature_link(link_row)}), 201


@app.route("/api/signature-links/<link_id>", methods=["DELETE"])
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


@app.route("/api/signature/<token>", methods=["GET"])
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
            link_label = signature_link_label(link_row["link_type"])
            link_scope = signature_link_scope(link_row["link_type"])
            insert_app_log(
                connection,
                link_scope,
                "signature_link_opened",
                f"{link_label} ouvert",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": link_row["link_type"]},
                actor=signature_link_public_actor(link_row["link_type"]),
            )

    form_data = get_form(link_row["form_id"])
    if not form_data:
        return jsonify({"error": "not_found"}), 404
    return jsonify(build_signature_public_payload(form_data, link_row))


@app.route("/api/signature/<token>/submit", methods=["POST"])
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
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

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
            link_label = signature_link_label(link_row["link_type"])
            link_scope = signature_link_scope(link_row["link_type"])
            insert_audit_event(
                connection,
                form_row["dossier_id"],
                "signature_link_used",
                f"{link_label} utilise",
                {"form_id": link_row["form_id"], "title": form_row["title"], "link_type": link_row["link_type"]},
            )
            insert_app_log(
                connection,
                link_scope,
                "signature_link_used",
                f"{link_label} utilise",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": link_row["link_type"]},
                actor=signature_link_public_actor(link_row["link_type"]),
            )

    return jsonify({
        "success": True,
        "summary": saved["summary"],
        "link": serialize_signature_link(current_link),
    })


@app.route("/api/restitution-signature/<token>", methods=["GET"])
def get_restitution_signature_token_route(token):
    with get_db() as connection:
        link_row = get_signature_link_by_token(connection, token)
        if not link_row or link_row["link_type"] != "restitution":
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
                "restitution_signature",
                "signature_link_opened",
                "Lien de signature de restitution ouvert",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": "restitution"},
                actor=signature_link_public_actor("restitution"),
            )

    form_data = get_form(link_row["form_id"])
    if not form_data:
        return jsonify({"error": "not_found"}), 404
    response = jsonify(build_restitution_signature_public_payload(form_data, link_row))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/api/restitution-signature/<token>/submit", methods=["POST"])
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
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

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
                connection,
                form_row["dossier_id"],
                "signature_link_used",
                "Lien de signature de restitution utilise",
                {"form_id": link_row["form_id"], "title": form_row["title"], "link_type": "restitution"},
            )
            insert_app_log(
                connection,
                "restitution_signature",
                "signature_link_used",
                "Lien de signature de restitution utilise",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": get_request_client_ip(), "link_type": "restitution"},
                actor=signature_link_public_actor("restitution"),
            )

    return jsonify({
        "success": True,
        "summary": saved["summary"],
        "link": serialize_signature_link(current_link),
    })


@app.route("/api/forms", methods=["POST"])
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


@app.route("/api/forms/<form_id>", methods=["PUT"])
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


@app.route("/api/forms/<form_id>/reopen", methods=["POST"])
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

        payload = json.loads(row["payload_json"] or "{}")
        payload.setdefault("meta", {})
        payload["meta"]["reopenCount"] = int(payload["meta"].get("reopenCount") or 0) + 1
        payload["meta"]["lastReopenedAt"] = datetime.now(timezone.utc).isoformat()
        payload["meta"]["lastReopenedBy"] = session.get("user") or "system"

        connection.execute(
            "UPDATE dotation_forms SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), form_id),
        )
        insert_audit_event(
            connection,
            row["dossier_id"],
            "form_reopened",
            "Dossier rouvert",
            {
                "form_id": form_id,
                "title": row["title"],
                "reopen_count": payload["meta"]["reopenCount"],
            },
        )
        insert_app_log(
            connection,
            "dossier",
            "form_reopened",
            "Dossier rouvert",
            "form",
            form_id,
            {
                "title": row["title"],
                "reopen_count": payload["meta"]["reopenCount"],
            },
        )

    return jsonify({"meta": payload["meta"]})


@app.route("/api/forms/<form_id>/restitution", methods=["PATCH"])
@login_required
def update_restitution(form_id):
    # La restitution est le seul cas legitime de mise a jour sur fiche active verrouillee.
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


@app.route("/api/forms/<form_id>", methods=["DELETE"])
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


@app.route("/api/session", methods=["GET"])
@login_required
def session_route():
    return jsonify(current_user())


@app.route("/api/settings/public", methods=["GET"])
def public_settings_route():
    response = jsonify(build_public_settings_payload())
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/admin/settings", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_settings_route():
    settings = get_app_settings()
    payload = build_public_settings_payload(settings)
    payload["raw"] = {
        "org_name": settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"],
        "dpo_email": get_dpo_email(settings),
        "brand_logo_mode": settings.get("brand_logo_mode") or DEFAULT_APP_SETTINGS["brand_logo_mode"],
        "brand_logo_url": settings.get("brand_logo_url") or DEFAULT_APP_SETTINGS["brand_logo_url"],
        "brand_logo_file": settings.get("brand_logo_file") or "",
        "theme_id": resolve_theme_id(settings),
        "dark_mode_policy": resolve_dark_mode(settings),
    }
    payload["themeOptions"] = [
        {"id": key, "label": value["label"]}
        for key, value in THEME_PRESETS.items()
    ]
    return jsonify(payload)


@app.route("/api/admin/settings", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_settings_route():
    payload = request.get_json(silent=True) or {}
    with get_db() as connection:
        save_app_settings(connection, {
            "org_name": payload.get("org_name"),
            "dpo_email": payload.get("dpo_email") or DEFAULT_APP_SETTINGS["dpo_email"],
            "brand_logo_mode": payload.get("brand_logo_mode"),
            "brand_logo_url": payload.get("brand_logo_url"),
            "theme_id": payload.get("theme_id"),
            "dark_mode_policy": payload.get("dark_mode_policy"),
        })
        insert_app_log(
            connection,
            "admin",
            "settings_updated",
            "Parametres de personnalisation mis a jour",
            "settings",
            "branding",
            {
                "org_name": payload.get("org_name"),
                "dpo_email": payload.get("dpo_email"),
                "brand_logo_mode": payload.get("brand_logo_mode"),
                "theme_id": payload.get("theme_id"),
                "dark_mode_policy": payload.get("dark_mode_policy"),
            },
            actor=current_actor(),
        )
    return jsonify(build_public_settings_payload())


@app.route("/api/admin/settings/logo-upload", methods=["POST"])
@login_required
@permission_required("users.manage")
def upload_admin_logo_route():
    file = request.files.get("logo")
    if not file or not file.filename:
        return jsonify({"error": "logo_required"}), 400

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in {".png"}:
        return jsonify({"error": "invalid_logo_type"}), 400

    file_bytes = file.read(2 * 1024 * 1024 + 1)
    if len(file_bytes) > 2 * 1024 * 1024:
        return jsonify({"error": "logo_too_large"}), 400
    if file_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return jsonify({"error": "invalid_logo_type"}), 400

    os.makedirs(CUSTOM_BRANDING_DIR, exist_ok=True)
    file_name = f"brand_logo_{uuid.uuid4().hex}{extension}"
    absolute_path = os.path.join(CUSTOM_BRANDING_DIR, file_name)
    with open(absolute_path, "wb") as f:
        f.write(file_bytes)
    relative_path = f"custom/{file_name}"

    with get_db() as connection:
        save_app_settings(connection, {
            "brand_logo_mode": "file",
            "brand_logo_file": relative_path,
        })
        insert_app_log(
            connection,
            "admin",
            "branding_logo_uploaded",
            "Logo personnalise televerse",
            "settings",
            "branding_logo",
            {"file": relative_path},
            actor=current_actor(),
        )
    settings = get_app_settings()
    return jsonify({
        "uploaded": True,
        "logoUrl": get_brand_logo_public_url(settings),
        "brand_logo_file": relative_path,
    }), 201


@app.route("/api/admin/groups", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_groups():
    config = load_auth_config()
    return jsonify(config.get("groups", {}))


@app.route("/api/reference/resources", methods=["GET"])
@login_required
def reference_resources():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM resource_catalog
            WHERE is_active = 1
            ORDER BY category ASC, display_order ASC, label COLLATE NOCASE ASC
            """
        ).fetchall()
    return jsonify([normalize_reference_row(row) for row in rows])


@app.route("/api/reference/services", methods=["GET"])
@login_required
def reference_services():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM service_catalog
            WHERE is_active = 1
            ORDER BY label COLLATE NOCASE ASC
            """
        ).fetchall()
    return jsonify([normalize_service_row(row) for row in rows])


@app.route("/api/admin/users", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_users():
    config = load_auth_config()
    return jsonify([
        {
            "username": user["username"],
            "groups": user.get("groups", []),
            "is_active": user.get("is_active", True),
            "status": user.get("status", "active" if user.get("is_active", True) else "disabled"),
        }
        for user in config.get("users", [])
    ])


@app.route("/api/admin/logs", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_logs():
    search = (request.args.get("q") or "").strip()
    limit = request.args.get("limit", default=200, type=int) or 200
    limit = max(1, min(limit, 500))
    query = """
        SELECT * FROM app_logs
    """
    params = []
    if search:
        query += """
            WHERE actor LIKE ?
               OR scope LIKE ?
               OR action_type LIKE ?
               OR action_label LIKE ?
               OR target_type LIKE ?
               OR target_id LIKE ?
               OR details_json LIKE ?
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern])
    query += """
        ORDER BY datetime(created_at) DESC, created_at DESC
        LIMIT ?
    """
    params.append(limit)
    with get_db() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return jsonify([
        {
            "id": row["id"],
            "actor": row["actor"],
            "scope": row["scope"],
            "action_type": row["action_type"],
            "action_label": row["action_label"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "details": json.loads(row["details_json"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ])


@app.route("/api/admin/trash", methods=["GET"])
@admin_required
def admin_trash():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM deleted_items
            ORDER BY datetime(deleted_at) DESC, deleted_at DESC
            """
        ).fetchall()
    return jsonify([
        {
            "id": row["id"],
            "item_type": row["item_type"],
            "item_key": row["item_key"],
            "item_label": row["item_label"],
            "deleted_by": row["deleted_by"],
            "deleted_at": row["deleted_at"],
            "payload": json.loads(row["payload_json"] or "{}"),
        }
        for row in rows
    ])


@app.route("/api/admin/trash/<trash_id>/restore", methods=["POST"])
@admin_required
def restore_trash_item(trash_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM deleted_items WHERE id = ?",
            (trash_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        payload = json.loads(row["payload_json"] or "{}")
        item_type = row["item_type"]
        item_key = row["item_key"]
        item_label = row["item_label"] or item_key

        if item_type == "form":
            form_data = persist_form(payload, allow_locked_update=True)
        elif item_type == "resource":
            existing_code = connection.execute(
                "SELECT id FROM resource_catalog WHERE code = ?",
                (payload.get("code"),),
            ).fetchone()
            if existing_code:
                return jsonify({"error": "resource_code_exists"}), 409
            connection.execute(
                """
                INSERT INTO resource_catalog (
                    id, code, label, category, issuer_service, requires_return, trigger_key,
                    field_schema_json, is_active, is_builtin, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("id"),
                    payload.get("code"),
                    payload.get("label"),
                    payload.get("category"),
                    payload.get("issuer_service"),
                    payload.get("requires_return", 1),
                    payload.get("trigger_key"),
                    payload.get("field_schema_json"),
                    payload.get("is_active", 1),
                    payload.get("is_builtin", 0),
                    payload.get("created_at") or utc_now(),
                    utc_now(),
                ),
            )
            form_data = {"restored": True}
        elif item_type == "user":
            config = load_auth_config()
            if get_user_record(payload.get("username")):
                return jsonify({"error": "user_exists"}), 409
            config.setdefault("users", []).append(payload)
            save_auth_config(config)
            form_data = {"restored": True}
        else:
            return jsonify({"error": "unsupported_item_type"}), 400

        connection.execute("DELETE FROM deleted_items WHERE id = ?", (trash_id,))
        insert_app_log(
            connection,
            "admin",
            "trash_restored",
            "Element restaure depuis la corbeille",
            item_type,
            item_key,
            {"label": item_label},
        )
    return jsonify({"restored": True, "item_type": item_type, "item_key": item_key, "data": form_data})


@app.route("/api/admin/trash/<trash_id>", methods=["DELETE"])
@admin_required
def delete_trash_item(trash_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT item_type, item_key, item_label FROM deleted_items WHERE id = ?",
            (trash_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        deleted = connection.execute(
            "DELETE FROM deleted_items WHERE id = ?",
            (trash_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "admin",
                "trash_deleted",
                "Element supprime definitivement depuis la corbeille",
                row["item_type"],
                row["item_key"],
                {"label": row["item_label"] or row["item_key"]},
            )

    return jsonify({"deleted": bool(deleted)})


@app.route("/api/admin/trash", methods=["DELETE"])
@admin_required
def empty_admin_trash():
    with get_db() as connection:
        deleted_count = connection.execute("SELECT COUNT(*) AS total FROM deleted_items").fetchone()["total"]
        connection.execute("DELETE FROM deleted_items")
        if deleted_count:
            insert_app_log(
                connection,
                "admin",
                "trash_emptied",
                "Corbeille videe definitivement",
                "trash",
                "all",
                {"deleted_count": deleted_count},
            )

    return jsonify({"deleted": True, "deleted_count": deleted_count})


@app.route("/api/admin/services", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_services():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM service_catalog ORDER BY is_active DESC, label COLLATE NOCASE ASC"
        ).fetchall()
    return jsonify([normalize_service_row(row) for row in rows])


@app.route("/api/admin/services", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_service():
    payload = request.get_json(silent=True) or {}
    label = (payload.get("label") or "").strip()
    is_active = bool(payload.get("is_active", True))
    if not label:
        return jsonify({"error": "label_required"}), 400

    now = utc_now()
    with get_db() as connection:
        existing = connection.execute(
            "SELECT id FROM service_catalog WHERE lower(label) = lower(?)",
            (label,),
        ).fetchone()
        if existing:
            return jsonify({"error": "service_exists"}), 409
        service_id = generate_id("service")
        connection.execute(
            """
            INSERT INTO service_catalog (
                id, label, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, 0, ?, ?)
            """,
            (
                service_id,
                label,
                bool_to_int(is_active),
                now,
                now,
            ),
        )
        insert_app_log(
            connection,
            "admin",
            "service_created",
            "Service cree",
            "service",
            service_id,
            {"label": label},
        )
    return jsonify({"created": True}), 201


@app.route("/api/admin/services/<service_id>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_service(service_id):
    payload = request.get_json(silent=True) or {}
    now = utc_now()
    with get_db() as connection:
        row = connection.execute("SELECT * FROM service_catalog WHERE id = ?", (service_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        next_label = (payload.get("label") if payload.get("label") is not None else row["label"]).strip()
        if not next_label:
            return jsonify({"error": "label_required"}), 400

        duplicate = connection.execute(
            "SELECT id FROM service_catalog WHERE lower(label) = lower(?) AND id != ?",
            (next_label, service_id),
        ).fetchone()
        if duplicate:
            return jsonify({"error": "service_exists"}), 409

        next_is_active = bool_to_int(payload.get("is_active", bool(row["is_active"])))
        connection.execute(
            """
            UPDATE service_catalog
            SET label = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_label,
                next_is_active,
                now,
                service_id,
            ),
        )
        insert_app_log(
            connection,
            "admin",
            "service_updated",
            "Service mis a jour",
            "service",
            service_id,
            {"label": next_label, "is_active": bool(next_is_active)},
        )
    return jsonify({"updated": True})


@app.route("/api/admin/services/<service_id>", methods=["DELETE"])
@login_required
@permission_required("users.manage")
def delete_admin_service(service_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM service_catalog WHERE id = ?",
            (service_id,),
        ).fetchone()
        deleted = connection.execute(
            "DELETE FROM service_catalog WHERE id = ?",
            (service_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "admin",
                "service_deleted",
                "Service supprime",
                "service",
                service_id,
                {"label": row["label"] if row else ""},
            )
    return jsonify({"deleted": bool(deleted)})


@app.route("/api/admin/resources", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_resources():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM resource_catalog ORDER BY is_active DESC, category ASC, display_order ASC, label COLLATE NOCASE ASC"
        ).fetchall()
    return jsonify([normalize_reference_row(row) for row in rows])


@app.route("/api/admin/resources", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_resource():
    payload = request.get_json(silent=True) or {}
    resource_data = normalize_resource_catalog_payload(payload)

    if not resource_data["code"] or not resource_data["label"]:
        return jsonify({"error": "code_and_label_required"}), 400

    now = utc_now()
    with get_db() as connection:
        existing = connection.execute("SELECT id FROM resource_catalog WHERE code = ?", (resource_data["code"],)).fetchone()
        if existing:
            return jsonify({"error": "resource_exists"}), 409
        resource_id = generate_id("resource")
        connection.execute(
            """
            INSERT INTO resource_catalog (
                id, code, label, description, category, issuer_service, requires_return,
                has_assignment_date, has_assignment_condition, has_assignment_notes, display_order,
                trigger_key, field_schema_json, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                resource_id,
                resource_data["code"],
                resource_data["label"],
                resource_data["description"],
                resource_data["category"],
                resource_data["issuer_service"],
                bool_to_int(resource_data["requires_return"]),
                bool_to_int(resource_data["has_assignment_date"]),
                bool_to_int(resource_data["has_assignment_condition"]),
                bool_to_int(resource_data["has_assignment_notes"]),
                resource_data["display_order"],
                resource_data["trigger_key"],
                json.dumps(resource_data["field_schema"], ensure_ascii=False),
                bool_to_int(resource_data["is_active"]),
                now,
                now,
            ),
        )
        created_row = connection.execute("SELECT * FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
        insert_app_log(
            connection,
            "admin",
            "resource_created",
            "Ressource creee",
            "resource",
            resource_id,
            {
                "code": resource_data["code"],
                "label": resource_data["label"],
                "category": resource_data["category"],
                "issuer_service": resource_data["issuer_service"],
                "field_count": len(resource_data["field_schema"]),
            },
        )
    return jsonify({"created": True, "resource": normalize_reference_row(created_row)}), 201


@app.route("/api/admin/resources/<resource_id>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_resource(resource_id):
    payload = request.get_json(silent=True) or {}
    now = utc_now()
    with get_db() as connection:
        row = connection.execute("SELECT * FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        resource_data = normalize_resource_catalog_payload(payload, row)
        next_code = resource_data["code"]
        if not next_code:
            return jsonify({"error": "code_required"}), 400
        duplicate = connection.execute(
            "SELECT id FROM resource_catalog WHERE code = ? AND id != ?",
            (next_code, resource_id),
        ).fetchone()
        if duplicate:
            return jsonify({"error": "resource_code_exists"}), 409
        connection.execute(
            """
            UPDATE resource_catalog
            SET code = ?, label = ?, description = ?, category = ?, issuer_service = ?, requires_return = ?,
                has_assignment_date = ?, has_assignment_condition = ?, has_assignment_notes = ?, display_order = ?,
                trigger_key = ?, field_schema_json = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                resource_data["code"],
                resource_data["label"],
                resource_data["description"],
                resource_data["category"],
                resource_data["issuer_service"],
                bool_to_int(resource_data["requires_return"]),
                bool_to_int(resource_data["has_assignment_date"]),
                bool_to_int(resource_data["has_assignment_condition"]),
                bool_to_int(resource_data["has_assignment_notes"]),
                resource_data["display_order"],
                resource_data["trigger_key"],
                json.dumps(resource_data["field_schema"], ensure_ascii=False),
                bool_to_int(resource_data["is_active"]),
                now,
                resource_id,
            ),
        )
        updated_row = connection.execute("SELECT * FROM resource_catalog WHERE id = ?", (resource_id,)).fetchone()
        insert_app_log(
            connection,
            "admin",
            "resource_updated",
            "Ressource mise a jour",
            "resource",
            resource_id,
            {
                "code": next_code,
                "label": resource_data["label"],
                "category": resource_data["category"],
                "field_count": len(resource_data["field_schema"]),
            },
        )
    return jsonify({"updated": True, "resource": normalize_reference_row(updated_row)})


@app.route("/api/admin/resources/<resource_id>", methods=["DELETE"])
@login_required
@permission_required("users.manage")
def delete_admin_resource(resource_id):
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM resource_catalog WHERE id = ?",
            (resource_id,),
        ).fetchone()
        if row:
            insert_deleted_item(
                connection,
                "resource",
                resource_id,
                row["label"],
                {key: row[key] for key in row.keys()},
            )
        deleted = connection.execute(
            "DELETE FROM resource_catalog WHERE id = ?",
            (resource_id,),
        ).rowcount
        if deleted:
            insert_app_log(
                connection,
                "admin",
                "resource_deleted",
                "Ressource supprimee",
                "resource",
                resource_id,
                {"code": row["code"] if row else "", "label": row["label"] if row else ""},
            )
    if not deleted:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"deleted": True})


@app.route("/api/admin/users", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_user():
    # Creation d'un utilisateur local rattache a un ou plusieurs groupes.
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    groups = payload.get("groups") or []
    is_active = bool(payload.get("is_active", True))
    config = load_auth_config()

    if not username or not password:
        return jsonify({"error": "username_and_password_required"}), 400
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    complexity_error = password_complexity_error(password)
    if complexity_error:
        return jsonify({"error": complexity_error}), 400
    if get_user_record(username):
        return jsonify({"error": "user_exists"}), 409

    status = "active" if is_active else "disabled"
    config["users"].append({
        "username": username,
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "groups": [group for group in groups if group in config.get("groups", {})],
        "is_active": is_active,
        "status": status,
    })
    save_auth_config(config)
    with get_db() as connection:
        insert_app_log(
            connection,
            "admin",
            "user_created",
            "Compte utilisateur cree",
            "user",
            username,
            {"groups": [group for group in groups if group in config.get("groups", {})], "is_active": is_active, "status": status},
        )
    return jsonify({"created": True}), 201


@app.route("/api/admin/users/<username>", methods=["PUT"])
@login_required
@permission_required("users.manage")
def update_admin_user(username):
    payload = request.get_json(silent=True) or {}
    config = load_auth_config()
    user = next((item for item in config.get("users", []) if item.get("username") == username), None)
    if not user:
        return jsonify({"error": "not_found"}), 404

    user["groups"] = [group for group in payload.get("groups", user.get("groups", [])) if group in config.get("groups", {})]
    requested_status = payload.get("status")
    if requested_status in {"pending", "active", "disabled"}:
        user["status"] = requested_status
        user["is_active"] = requested_status != "disabled"
    else:
        user["is_active"] = bool(payload.get("is_active", user.get("is_active", True)))
        user["status"] = "active" if user.get("is_active", True) else "disabled"
    if payload.get("password"):
        complexity_error = password_complexity_error(payload["password"])
        if complexity_error:
            return jsonify({"error": complexity_error}), 400
        user["password_hash"] = bcrypt.hashpw(payload["password"].encode(), bcrypt.gensalt()).decode()

    save_auth_config(config)
    with get_db() as connection:
        insert_app_log(
            connection,
            "admin",
            "user_updated",
            "Compte utilisateur mis a jour",
            "user",
            username,
            {
                "groups": user.get("groups", []),
                "is_active": user.get("is_active", True),
                "status": user.get("status", "active"),
                "password_changed": bool(payload.get("password")),
            },
        )
    return jsonify({"updated": True})


@app.route("/api/admin/users/<username>", methods=["DELETE"])
@login_required
@permission_required("users.manage")
def delete_admin_user(username):
    current_username = session.get("user")
    if current_username == username:
        return jsonify({"error": "cannot_delete_current_user"}), 400

    config = load_auth_config()
    users = config.get("users", [])
    deleted_user = next((user for user in users if user.get("username") == username), None)
    kept_users = [user for user in users if user.get("username") != username]
    if len(kept_users) == len(users):
        return jsonify({"error": "not_found"}), 404

    config["users"] = kept_users
    save_auth_config(config)
    with get_db() as connection:
        if deleted_user:
            insert_deleted_item(
                connection,
                "user",
                username,
                username,
                deleted_user,
            )
        insert_app_log(
            connection,
            "admin",
            "user_deleted",
            "Compte utilisateur supprime",
            "user",
            username,
        )
    return jsonify({"deleted": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
