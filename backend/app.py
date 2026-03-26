from flask import Flask, jsonify, make_response, redirect, request, send_from_directory, session, has_request_context
import base64
import bcrypt
import io
import json
import os
import secrets
import sqlite3
import struct
import textwrap
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from functools import wraps
from xml.sax.saxutils import escape as xml_escape
import zlib
from werkzeug.middleware.proxy_fix import ProxyFix
import re


# Paths principaux du projet: frontend servi par Flask, base SQLite et cache catalogue.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
DB_PATH = os.path.join(BASE_DIR, "dotation.db")
CITY_LOGO_URL = os.environ.get(
    "CITY_LOGO_URL",
    "https://fr.wikipedia.org/wiki/Special:Redirect/file/Logo_ville_Publier_2022.png",
)
CITY_LOGO_PATH = os.environ.get("CITY_LOGO_PATH", os.path.join(FRONTEND_ASSETS_DIR, "city-logo.png"))

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("APP_SECRET_KEY", "publier-parcours-2026-session-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SESSION_COOKIE_NAME"] = "publier_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


@app.after_request
def disable_frontend_cache(response):
    content_type = (response.headers.get("Content-Type") or "").lower()
    if any(token in content_type for token in ("text/html", "application/javascript", "text/css")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
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
    {"code": "ordinateur", "label": "Ordinateur", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital"},
    {"code": "ecran", "label": "Ã‰cran", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital"},
    {"code": "telephone", "label": "TÃ©lÃ©phone", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital"},
    {"code": "tablette", "label": "Tablette", "category": "materiel", "issuer_service": "DSI", "requires_return": 1, "trigger_key": "digital"},
    {"code": "vpn", "label": "VPN", "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital"},
    {"code": "email", "label": "Email", "category": "immateriel", "issuer_service": "DSI", "requires_return": 0, "trigger_key": "digital"},
    {"code": "badge", "label": "Badge d'accÃ¨s", "category": "materiel", "issuer_service": "BÃ¢timent", "requires_return": 1, "trigger_key": ""},
    {"code": "cles", "label": "ClÃ©(s)", "category": "materiel", "issuer_service": "BÃ¢timent", "requires_return": 1, "trigger_key": ""},
    {"code": "veste", "label": "Veste", "category": "materiel", "issuer_service": "BÃ¢timent", "requires_return": 1, "trigger_key": ""},
    {"code": "chaussuresSecurite", "label": "Chaussures de sÃ©curitÃ©", "category": "materiel", "issuer_service": "BÃ¢timent", "requires_return": 1, "trigger_key": ""},
    {"code": "zoneAlarme", "label": "Zone alarme", "category": "immateriel", "issuer_service": "BÃ¢timent", "requires_return": 0, "trigger_key": ""},
    {"code": "vehicule", "label": "VÃ©hicule", "category": "materiel", "issuer_service": "Autres services", "requires_return": 1, "trigger_key": ""},
]

BRAND_LOGO_CACHE = {
    "loaded": False,
    "image": None,
}



# Configuration d'authentification stockee en JSON.
USERS_FILE = os.path.join(BASE_DIR, "users.json")
DEFAULT_GROUPS = {
    "lecture": {
        "label": "Lecture",
        "description": "Consultation seule, sans possibilite de saisie.",
        "permissions": ["forms.read_list", "forms.read_detail", "forms.export"],
        "data_scope": "full",
    },
    "redaction": {
        "label": "Redaction",
        "description": "Creation et modification des fiches en cours.",
        "permissions": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.export"],
        "data_scope": "full",
    },
    "gestion": {
        "label": "Gestion",
        "description": "Gestion avancee avec restitution et export.",
        "permissions": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export"],
        "data_scope": "full",
    },
    "admin": {
        "label": "Administration",
        "description": "Controle total et gestion des utilisateurs.",
        "permissions": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "users.manage", "*"],
        "data_scope": "full",
    },
}


def load_auth_config():
    # Supporte deux formats:
    # - ancien format {username: hash}
    # - nouveau format {groups: ..., users: ...}
    with open(USERS_FILE, encoding="utf-8") as file:
        raw = json.load(file)

    if "users" in raw and "groups" in raw:
        changed = False
        for user in raw.get("users", []):
            status = user.get("status")
            if not status:
                user["status"] = "active" if user.get("is_active", True) else "disabled"
                changed = True
            if "is_active" not in user:
                user["is_active"] = user.get("status") != "disabled"
                changed = True
        if changed:
            save_auth_config(raw)
        return raw

    migrated_users = [
        {
            "username": username,
            "password_hash": password_hash,
            "groups": ["admin"],
            "is_active": True,
        }
        for username, password_hash in raw.items()
    ]
    config = {"groups": DEFAULT_GROUPS, "users": migrated_users}
    save_auth_config(config)
    return config


def save_auth_config(config):
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    # Chaque requete ouvre une connexion courte avec rows accessibles par nom de colonne.
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def generate_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def table_columns(connection, table_name):
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def ensure_column(connection, table_name, column_name, column_sql):
    if column_name not in table_columns(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


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
                id, code, label, category, issuer_service, requires_return,
                trigger_key, field_schema_json, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                generate_id("resource"),
                resource["code"],
                resource["label"],
                resource["category"],
                resource["issuer_service"],
                resource["requires_return"],
                resource["trigger_key"],
                "[]",
                now,
                now,
            ),
        )

def normalize_reference_row(row):
    if not row:
        return None
    data = {
        key: row[key]
        for key in row.keys()
    }
    try:
        data["field_schema"] = json.loads(data.get("field_schema_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        data["field_schema"] = []
    return data


def slugify_field_key(value):
    return "".join(
        character if character.isalnum() else "_"
        for character in str(value or "").strip().lower()
    ).strip("_")


def normalize_resource_field_schema(raw_schema):
    normalized = []
    for index, field in enumerate(raw_schema or []):
        label = str(field.get("label") or "").strip()
        key = slugify_field_key(field.get("key") or label or f"champ_{index + 1}")
        if not label or not key:
            continue
        normalized.append({
            "key": key,
            "label": label,
            "type": str(field.get("type") or "text").strip() or "text",
            "placeholder": str(field.get("placeholder") or "").strip(),
            "required": bool(field.get("required", False)),
        })
    return normalized


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
                category TEXT NOT NULL,
                issuer_service TEXT,
                requires_return INTEGER NOT NULL DEFAULT 1,
                trigger_key TEXT,
                field_schema_json TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signature_links (
                id TEXT PRIMARY KEY,
                form_id TEXT NOT NULL,
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
        ensure_column(connection, "resource_catalog", "field_schema_json", "field_schema_json TEXT")
        seed_reference_catalogs(connection)
        migrate_forms_to_dossiers(connection)


def login_required(view):
    # Middleware minimum: redirige les pages HTML vers /login
    # et renvoie un 401 JSON pour les appels API.
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication_required"}), 401
            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            had_session_cookie = bool(request.cookies.get(cookie_name))
            return redirect("/login?error=session" if had_session_cookie else "/login")
        return view(*args, **kwargs)

    return wrapped_view


def permission_required(permission):
    # Garde reutilisable pour les routes d'administration ou d'actions sensibles.
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user" not in session:
                return jsonify({"error": "authentication_required"}), 401
            if not has_permission(permission):
                return jsonify({"error": "forbidden"}), 403
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication_required"}), 401
            return redirect("/login")
        if not user.get("is_admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "forbidden"}), 403
            return redirect("/")
        return view(*args, **kwargs)

    return wrapped_view


def get_user_record(username):
    config = load_auth_config()
    for user in config.get("users", []):
        if user.get("username") == username:
            return user
    return None


def password_complexity_error(password):
    value = str(password or "")
    if len(value) < 12:
        return "password_too_short"
    if not re.search(r"[A-Z]", value):
        return "password_missing_upper"
    if not re.search(r"[a-z]", value):
        return "password_missing_lower"
    if not re.search(r"\d", value):
        return "password_missing_digit"
    if not re.search(r"[^A-Za-z0-9]", value):
        return "password_missing_special"
    return None


def is_valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{3,64}", str(username or "").strip()))


def build_user_context(username):
    # Les permissions sont calculees a partir des groupes.
    # data_scope pilote ensuite le masquage RGPD des reponses.
    config = load_auth_config()
    user = get_user_record(username)
    groups = user.get("groups", []) if user else []
    group_objects = [config["groups"][group] for group in groups if group in config.get("groups", {})]
    permissions = sorted({permission for group in group_objects for permission in group.get("permissions", [])})
    data_scope = "masked" if group_objects and all(group.get("data_scope") == "masked" for group in group_objects) else "full"
    return {
        "username": username,
        "groups": groups,
        "permissions": permissions,
        "data_scope": data_scope,
        "is_admin": "admin" in groups or "*" in permissions,
    }


def current_user():
    username = session.get("user")
    if not username:
        return None
    return build_user_context(username)


def can_export_signature_assets():
    if not has_request_context():
        return True
    user = current_user()
    if not user:
        return False
    return "*" in user["permissions"] or "forms.edit" in user["permissions"] or "forms.restitution" in user["permissions"]


def has_permission(permission):
    user = current_user()
    if not user:
        return False
    return "*" in user["permissions"] or permission in user["permissions"]


def check_user(username, password):
    user = get_user_record(username)
    if not user:
        return "invalid"
    if user.get("status") == "pending":
        return "pending"
    if user.get("status") == "disabled" or not user.get("is_active", True):
        return "disabled"
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return "invalid"
    return "ok"


def bool_to_int(value):
    return 1 if value else 0


def mask_text(value):
    if not value:
        return value
    if len(value) <= 2:
        return value[0] + "*"
    return value[0] + ("*" * max(1, len(value) - 2)) + value[-1]


def mask_payload(payload):
    # Masquage "presentation" pour les profils lecture:
    # on ne modifie jamais la donnee source en base.
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
    if data.get("materiel", {}).get("telephone", {}).get("imei"):
        data["materiel"]["telephone"]["imei"] = mask_text(data["materiel"]["telephone"]["imei"])
    if data.get("materiel", {}).get("vehicule", {}).get("immatriculation"):
        data["materiel"]["vehicule"]["immatriculation"] = mask_text(data["materiel"]["vehicule"]["immatriculation"])
    data.setdefault("validation", {})["signatureDataUrl"] = ""
    return data


def derive_dossier_status(payload):
    workflow_status = payload.get("workflow", {}).get("status") or "draft"
    has_signature = bool(payload.get("validation", {}).get("signatureDataUrl"))
    has_items = any(
        item.get("selected")
        for section in [payload.get("materiel", {}), payload.get("immateriel", {})]
        for item in section.values()
        if isinstance(item, dict)
    )

    if workflow_status in {"returned", "partial_return"}:
        return "en_restitution"
    if workflow_status == "cancelled":
        return "clos"
    if workflow_status == "active":
        return "actif"
    if workflow_status == "partial_assignment":
        return "partiellement_complete"
    if has_items or has_signature:
        return "en_preparation"
    return "a_preparer"


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
        "arrivee": "Nouvelle arrivÃ©e",
        "changement_service": "Changement de service",
        "mise_a_jour": "Mise Ã  jour de ressources",
        "sortie": "Sortie / restitution",
    }
    return labels.get(normalize_dossier_type(value), "Nouvelle arrivÃ©e")


def insert_audit_event(connection, dossier_id, event_type, event_label, details=None):
    connection.execute(
        """
        INSERT INTO audit_events (id, dossier_id, event_type, event_label, actor, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generate_id("audit"),
            dossier_id,
            event_type,
            event_label,
            session.get("user"),
            json.dumps(details or {}, ensure_ascii=False),
            utc_now(),
        ),
    )


def insert_app_log(connection, scope, action_type, action_label, target_type=None, target_id=None, details=None, actor=None):
    connection.execute(
        """
        INSERT INTO app_logs (id, actor, scope, action_type, action_label, target_type, target_id, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generate_id("log"),
            actor or session.get("user") or "system",
            scope,
            action_type,
            action_label,
            target_type,
            target_id,
            json.dumps(details or {}, ensure_ascii=False),
            utc_now(),
        ),
    )


def current_actor(default="system"):
    return session.get("user") or default


def signature_link_expiration(hours=72):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def generate_signature_token():
    return secrets.token_urlsafe(32)


def materialize_signature_link(connection, row):
    if not row:
        return None

    data = {key: row[key] for key in row.keys()}
    if data["status"] == "active" and data.get("expires_at"):
        try:
            expired = datetime.fromisoformat(data["expires_at"]) <= datetime.now(timezone.utc)
        except ValueError:
            expired = False
        if expired:
            data["status"] = "expired"
            connection.execute(
                "UPDATE signature_links SET status = 'expired' WHERE id = ?",
                (data["id"],),
            )
    return data


def serialize_signature_link(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "formId": row["form_id"],
        "status": row["status"],
        "createdBy": row["created_by"],
        "createdAt": row["created_at"],
        "expiresAt": row["expires_at"],
        "usedAt": row["used_at"],
        "revokedAt": row["revoked_at"],
        "revokedBy": row["revoked_by"],
        "lastOpenedAt": row["last_opened_at"],
        "lastOpenedIp": row["last_opened_ip"],
        "notes": row["notes"] or "",
        "url": f"/signature/{row['token']}" if row["status"] == "active" else "",
    }


def get_latest_signature_link(connection, form_id):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE form_id = ? ORDER BY created_at DESC LIMIT 1",
        (form_id,),
    ).fetchone()
    return materialize_signature_link(connection, row)


def get_signature_link_by_id(connection, link_id):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE id = ?",
        (link_id,),
    ).fetchone()
    return materialize_signature_link(connection, row)


def get_signature_link_by_token(connection, token):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE token = ?",
        (token,),
    ).fetchone()
    return materialize_signature_link(connection, row)


def revoke_signature_links_for_form(connection, form_id, actor=None, except_id=None):
    actor = actor or current_actor()
    now = utc_now()
    rows = connection.execute(
        "SELECT * FROM signature_links WHERE form_id = ? AND status = 'active'",
        (form_id,),
    ).fetchall()
    revoked = []
    for row in rows:
        if except_id and row["id"] == except_id:
            continue
        connection.execute(
            """
            UPDATE signature_links
            SET status = 'revoked', revoked_at = ?, revoked_by = ?
            WHERE id = ?
            """,
            (now, actor, row["id"]),
        )
        revoked.append(row["id"])
    return revoked


def create_signature_link(connection, form_id, actor=None, expires_in_hours=72):
    actor = actor or current_actor()
    form_row = connection.execute(
        "SELECT id, dossier_id, title, payload_json FROM dotation_forms WHERE id = ?",
        (form_id,),
    ).fetchone()
    if not form_row:
        raise ValueError("Dossier introuvable.")

    payload = json.loads(form_row["payload_json"] or "{}")
    validation = payload.get("validation", {})
    if validation.get("signatureDataUrl"):
        raise ValueError("Ce dossier est deja signe.")

    revoke_signature_links_for_form(connection, form_id, actor=actor)
    now = utc_now()
    row = {
        "id": generate_id("siglink"),
        "form_id": form_id,
        "token": generate_signature_token(),
        "status": "active",
        "created_by": actor,
        "created_at": now,
        "expires_at": signature_link_expiration(expires_in_hours),
        "used_at": None,
        "revoked_at": None,
        "revoked_by": None,
        "last_opened_at": None,
        "last_opened_ip": None,
        "notes": "",
    }
    connection.execute(
        """
        INSERT INTO signature_links (
            id, form_id, token, status, created_by, created_at, expires_at,
            used_at, revoked_at, revoked_by, last_opened_at, last_opened_ip, notes
        ) VALUES (
            :id, :form_id, :token, :status, :created_by, :created_at, :expires_at,
            :used_at, :revoked_at, :revoked_by, :last_opened_at, :last_opened_ip, :notes
        )
        """,
        row,
    )
    insert_audit_event(
        connection,
        form_row["dossier_id"],
        "signature_link_created",
        "Lien de signature genere",
        {"form_id": form_id, "title": form_row["title"], "expires_at": row["expires_at"]},
    )
    insert_app_log(
        connection,
        "signature",
        "signature_link_created",
        "Lien de signature genere",
        "form",
        form_id,
        {"title": form_row["title"], "expires_at": row["expires_at"]},
        actor=actor,
    )
    return row


def revoke_signature_link(connection, link_id, actor=None):
    actor = actor or current_actor()
    row = get_signature_link_by_id(connection, link_id)
    if not row:
        return None
    if row["status"] in {"used", "revoked"}:
        return row
    now = utc_now()
    connection.execute(
        "UPDATE signature_links SET status = 'revoked', revoked_at = ?, revoked_by = ? WHERE id = ?",
        (now, actor, link_id),
    )
    form_row = connection.execute(
        "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
        (row["form_id"],),
    ).fetchone()
    if form_row:
        insert_audit_event(
            connection,
            form_row["dossier_id"],
            "signature_link_revoked",
            "Lien de signature revoque",
            {"form_id": row["form_id"], "title": form_row["title"]},
        )
        insert_app_log(
            connection,
            "signature",
            "signature_link_revoked",
            "Lien de signature revoque",
            "form",
            row["form_id"],
            {"title": form_row["title"]},
            actor=actor,
        )
    return get_signature_link_by_id(connection, link_id)


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


def sync_person_and_dossier(connection, payload, existing_row=None):
    beneficiaire = payload.get("beneficiaire", {})
    dossier = payload.get("dossier", {})
    meta = payload.setdefault("meta", {})
    saved_at = meta.get("savedAt") or utc_now()
    assigned_at = meta.get("assignedAt") or saved_at

    person_id = meta.get("personId")
    dossier_id = meta.get("dossierId")
    if existing_row:
      dossier_id = dossier_id or existing_row["dossier_id"]

    if dossier_id and not person_id:
        dossier_row = connection.execute(
            "SELECT person_id FROM onboarding_dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
        if dossier_row:
            person_id = dossier_row["person_id"]

    if not person_id:
        person_id = generate_id("person")
    if not dossier_id:
        dossier_id = generate_id("dossier")

    person_exists = connection.execute(
        "SELECT id, created_at FROM persons WHERE id = ?",
        (person_id,),
    ).fetchone()
    person_row = {
        "id": person_id,
        "nom": beneficiaire.get("nom", ""),
        "prenom": beneficiaire.get("prenom", ""),
        "qualite": beneficiaire.get("qualite") or "agent",
        "service": beneficiaire.get("service"),
        "fonction": beneficiaire.get("fonction"),
        "mandat": beneficiaire.get("mandat"),
        "date_arrivee": assigned_at,
        "is_active": 1,
        "created_at": person_exists["created_at"] if person_exists else saved_at,
        "updated_at": saved_at,
    }

    if person_exists:
        connection.execute(
            """
            UPDATE persons
            SET nom = :nom,
                prenom = :prenom,
                qualite = :qualite,
                service = :service,
                fonction = :fonction,
                mandat = :mandat,
                date_arrivee = :date_arrivee,
                is_active = :is_active,
                updated_at = :updated_at
            WHERE id = :id
            """,
            person_row,
        )
    else:
        connection.execute(
            """
            INSERT INTO persons (
                id, nom, prenom, qualite, service, fonction, mandat,
                date_arrivee, is_active, created_at, updated_at
            ) VALUES (
                :id, :nom, :prenom, :qualite, :service, :fonction, :mandat,
                :date_arrivee, :is_active, :created_at, :updated_at
            )
            """,
            person_row,
        )

    dossier_exists = connection.execute(
        "SELECT id, created_at FROM onboarding_dossiers WHERE id = ?",
        (dossier_id,),
    ).fetchone()
    dossier_row = {
        "id": dossier_id,
        "person_id": person_id,
        "dossier_type": normalize_dossier_type(dossier.get("type")),
        "status": derive_dossier_status(payload),
        "assigned_at": assigned_at,
        "notes": payload.get("restitution", {}).get("notes") or "",
        "created_at": dossier_exists["created_at"] if dossier_exists else saved_at,
        "updated_at": saved_at,
    }

    if dossier_exists:
        connection.execute(
            """
            UPDATE onboarding_dossiers
            SET person_id = :person_id,
                dossier_type = :dossier_type,
                status = :status,
                assigned_at = :assigned_at,
                notes = :notes,
                updated_at = :updated_at
            WHERE id = :id
            """,
            dossier_row,
        )
    else:
        connection.execute(
            """
            INSERT INTO onboarding_dossiers (id, person_id, dossier_type, status, assigned_at, notes, created_at, updated_at)
            VALUES (:id, :person_id, :dossier_type, :status, :assigned_at, :notes, :created_at, :updated_at)
            """,
            dossier_row,
        )

    meta["personId"] = person_id
    meta["dossierId"] = dossier_id
    meta["assignedAt"] = assigned_at
    return person_id, dossier_id


def migrate_forms_to_dossiers(connection):
    rows = connection.execute(
        "SELECT id, dossier_id, payload_json, created_at, updated_at FROM dotation_forms"
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload.setdefault("meta", {})
        payload["meta"].setdefault("id", row["id"])
        payload["meta"].setdefault("createdAt", row["created_at"])
        payload["meta"].setdefault("savedAt", row["updated_at"])
        _, dossier_id = sync_person_and_dossier(connection, payload, row)
        connection.execute(
            "UPDATE dotation_forms SET dossier_id = ?, payload_json = ? WHERE id = ?",
            (dossier_id, json.dumps(payload, ensure_ascii=False), row["id"]),
        )


def build_title(payload):
    # Titre fonctionnel de la fiche, utilise dans la liste et les exports.
    beneficiaire = payload.get("beneficiaire", {})
    prefix = (
        beneficiaire.get("mandat")
        if beneficiaire.get("qualite") == "elu"
        else beneficiaire.get("service")
    ) or ("MANDAT" if beneficiaire.get("qualite") == "elu" else "SERVICE")
    nom = (beneficiaire.get("nom") or "SANS NOM").upper()
    prenom = beneficiaire.get("prenom") or ""
    return f"{prefix.upper()} - {nom} {prenom}".strip()


def normalize_pdf_text(value):
    # PDF minimal sans police Unicode embarquee:
    # on degrade proprement vers Latin-1 pour garder un export robuste sans dependance externe.
    text = "" if value is None else str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text.encode("latin-1", "replace").decode("latin-1")


def pdf_escape(value):
    return normalize_pdf_text(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


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


def extract_png_image(png_bytes):
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return None

    position = 8
    width = None
    height = None
    bit_depth = None
    color_type = None
    compressed_data = bytearray()

    while position + 8 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[position:position + 4])[0]
        chunk_type = png_bytes[position + 4:position + 8]
        chunk_data = png_bytes[position + 8:position + 8 + length]
        position += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", chunk_data)
            if bit_depth != 8 or compression != 0 or filter_method != 0 or interlace != 0:
                return None
            if color_type not in {2, 6}:
                return None
        elif chunk_type == b"IDAT":
            compressed_data.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if not width or not height or not compressed_data:
        return None

    try:
        raw = zlib.decompress(bytes(compressed_data))
    except zlib.error:
        return None

    channels = 4 if color_type == 6 else 3
    row_stride = width * channels
    expected_size = height * (1 + row_stride)
    if len(raw) != expected_size:
        return None

    def paeth_predictor(left, up, up_left):
        prediction = left + up - up_left
        pa = abs(prediction - left)
        pb = abs(prediction - up)
        pc = abs(prediction - up_left)
        if pa <= pb and pa <= pc:
            return left
        if pb <= pc:
            return up
        return up_left

    rows = []
    previous = [0] * row_stride
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = list(raw[offset:offset + row_stride])
        offset += row_stride

        if filter_type == 1:
            for index in range(row_stride):
                left = row[index - channels] if index >= channels else 0
                row[index] = (row[index] + left) & 0xFF
        elif filter_type == 2:
            for index in range(row_stride):
                row[index] = (row[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(row_stride):
                left = row[index - channels] if index >= channels else 0
                up = previous[index]
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for index in range(row_stride):
                left = row[index - channels] if index >= channels else 0
                up = previous[index]
                up_left = previous[index - channels] if index >= channels else 0
                row[index] = (row[index] + paeth_predictor(left, up, up_left)) & 0xFF
        elif filter_type != 0:
            return None

        rows.append(row)
        previous = row

    rgb = bytearray()
    for row in rows:
        for index in range(0, len(row), channels):
            red = row[index]
            green = row[index + 1]
            blue = row[index + 2]
            alpha = row[index + 3] if channels == 4 else 255
            if alpha < 255:
                red = (red * alpha + 255 * (255 - alpha)) // 255
                green = (green * alpha + 255 * (255 - alpha)) // 255
                blue = (blue * alpha + 255 * (255 - alpha)) // 255
            rgb.extend((red, green, blue))

    return {
        "width": width,
        "height": height,
        "data": zlib.compress(bytes(rgb)),
    }


def extract_signature_image(signature_data_url):
    if not signature_data_url or not signature_data_url.startswith("data:image/png;base64,"):
        return None

    try:
        png_bytes = base64.b64decode(signature_data_url.split(",", 1)[1])
    except (ValueError, IndexError):
        return None

    return extract_png_image(png_bytes)


def load_brand_logo_image():
    if BRAND_LOGO_CACHE["loaded"]:
        return BRAND_LOGO_CACHE["image"]

    image = None
    local_candidates = [CITY_LOGO_PATH]
    for candidate in local_candidates:
        if candidate and os.path.exists(candidate):
            try:
                with open(candidate, "rb") as file:
                    image = extract_png_image(file.read())
            except OSError:
                image = None
            if image:
                break

    if not image and CITY_LOGO_URL:
        try:
            request = urllib.request.Request(
                CITY_LOGO_URL,
                headers={
                    "User-Agent": "Parcours-agents-elus/1.0",
                    "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                image_bytes = response.read()
                image = extract_png_image(image_bytes)
                if image and CITY_LOGO_PATH:
                    try:
                        os.makedirs(os.path.dirname(CITY_LOGO_PATH), exist_ok=True)
                        with open(CITY_LOGO_PATH, "wb") as file:
                            file.write(image_bytes)
                    except OSError:
                        pass
        except Exception:
            image = None

    BRAND_LOGO_CACHE["loaded"] = True
    BRAND_LOGO_CACHE["image"] = image
    return image


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
        "elu": "Ã‰lu(e)",
    }
    return labels.get(value, value or "-")


def summarize_dynamic_resource(resource):
    fields = resource.get("fields") or {}
    if isinstance(fields, dict):
        values = [str(value).strip() for value in fields.values() if str(value or "").strip()]
        if values:
            return " - ".join(values)
    return str(resource.get("details") or "").strip()


def collect_resource_entries(payload):
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    additional = payload.get("resources", {}).get("additional", [])

    entries = []

    def add_entry(item_key, category, service, label, details, include_if_empty=False):
        clean_details = [str(detail).strip() for detail in details if str(detail or "").strip()]
        if not clean_details and not include_if_empty:
            return
        entries.append(
            {
                "itemKey": item_key,
                "category": category or "materiel",
                "service": service or "Non dÃ©fini",
                "label": label,
                "details": " - ".join(clean_details) if clean_details else "-",
            }
        )

    if materiel.get("ordinateur", {}).get("selected"):
        item = materiel["ordinateur"]
        add_entry("ordinateur", "materiel", "DSI", "Ordinateur", [item.get("nomPoste"), item.get("marque"), item.get("modele"), item.get("numeroSerie")])
    if materiel.get("ecran", {}).get("selected"):
        item = materiel["ecran"]
        add_entry("ecran", "materiel", "DSI", "Ã‰cran", [item.get("marque"), item.get("modele"), item.get("numeroSerie")])
    if materiel.get("telephone", {}).get("selected"):
        item = materiel["telephone"]
        add_entry("telephone", "materiel", "DSI", "TÃ©lÃ©phone", [item.get("nomTelephone"), item.get("marque"), item.get("modele"), item.get("imei")])
    if materiel.get("tablette", {}).get("selected"):
        item = materiel["tablette"]
        add_entry("tablette", "materiel", "DSI", "Tablette", [item.get("nomTablette"), item.get("marque"), item.get("modele"), item.get("numeroSerie")])
    if immateriel.get("email", {}).get("selected"):
        add_entry("email", "immateriel", "DSI", "Messagerie", [immateriel["email"].get("adresse")])
    if immateriel.get("vpn", {}).get("selected"):
        add_entry("vpn", "immateriel", "DSI", "VPN", [], include_if_empty=True)
    if materiel.get("badge", {}).get("selected"):
        add_entry("badge", "materiel", "BÃ¢timent", "Badge d'accÃ¨s", [materiel["badge"].get("numero")])
    if materiel.get("cles", {}).get("selected"):
        add_entry("cles", "materiel", "BÃ¢timent", "ClÃ©(s)", materiel["cles"].get("values") or [])
    if materiel.get("veste", {}).get("selected"):
        add_entry("veste", "materiel", "BÃ¢timent", "Veste", [], include_if_empty=True)
    if materiel.get("chaussuresSecurite", {}).get("selected"):
        add_entry("chaussuresSecurite", "materiel", "BÃ¢timent", "Chaussures de sÃ©curitÃ©", [], include_if_empty=True)
    if immateriel.get("zoneAlarme", {}).get("selected"):
        add_entry("zoneAlarme", "immateriel", "BÃ¢timent", "Zone alarme", immateriel["zoneAlarme"].get("zones") or [])
    if materiel.get("vehicule", {}).get("selected"):
        item = materiel["vehicule"]
        add_entry("vehicule", "materiel", "Autres services", "VÃ©hicule", [item.get("marque"), item.get("modele"), item.get("immatriculation")])
    if materiel.get("autre", {}).get("selected"):
        add_entry("autre", "materiel", "Autres services", "Autre ressource", [materiel["autre"].get("description")])

    for resource in additional:
        if not resource.get("selected"):
            continue
        add_entry(
            resource.get("code") or resource.get("id") or generate_id("resource"),
            resource.get("category") or "materiel",
            resource.get("issuerService") or resource.get("issuer_service") or "Autres services",
            resource.get("label") or "Ressource complÃ©mentaire",
            [summarize_dynamic_resource(resource)],
        )

    return entries


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
        f"Ã‰tat : {format_status_label(workflow.get('status') or 'draft')}",
        f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
        f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
        "",
        "BÃ©nÃ©ficiaire",
        f"Nom : {beneficiaire.get('nom') or '-'}",
        f"PrÃ©nom : {beneficiaire.get('prenom') or '-'}",
        f"QualitÃ© : {format_beneficiary_label(beneficiaire.get('qualite'))}",
        f"Service : {beneficiaire.get('service') or '-'}",
        f"Fonction : {beneficiaire.get('fonction') or '-'}",
        f"Mandat : {beneficiaire.get('mandat') or '-'}",
        f"Service de destination : {dossier.get('serviceDestination') or '-'}",
        "",
        "Ressources attribuÃ©es",
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
        lines.append("- Aucune ressource renseignÃ©e")

    lines.extend(
        [
            "",
            "Restitution",
            f"Ã‰tat de restitution : {format_status_label(workflow.get('status') or 'draft')}",
            f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
            f"Motif : {restitution.get('reason') or '-'}",
            f"Observations : {restitution.get('notes') or '-'}",
            "",
            "Validation",
            f"Information RGPD portÃ©e Ã  connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
            f"Signature prÃ©sente : {'Oui' if validation.get('signatureDataUrl') else 'Non'}",
            f"Date de signature : {signature_datetime}",
        ]
    )
    return lines


def build_pdf_bytes(title, payload):
    page_width = 595
    page_height = 842
    margin = 42
    content_width = page_width - (margin * 2)
    top_content_start = 660
    bottom_margin = 52

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
                f"Ã‰tat : {format_status_label(workflow.get('status') or 'draft')}",
                f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
                f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
                f"Date de crÃ©ation : {format_export_datetime(payload.get('meta', {}).get('createdAt'))}",
            ],
        ),
        (
            "BÃ©nÃ©ficiaire",
            [
                f"Nom : {beneficiaire.get('nom') or '-'}",
                f"PrÃ©nom : {beneficiaire.get('prenom') or '-'}",
                f"QualitÃ© : {format_beneficiary_label(beneficiaire.get('qualite'))}",
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
                    f"Ressources attribuÃ©es - {service}",
                    [f"{entry['label']} : {entry['details']}" for entry in service_entries],
                )
            )
    else:
        sections.append(("Ressources attribuÃ©es", ["Aucune ressource renseignÃ©e."]))

    restitution_lines = [
        f"Statut : {format_status_label(workflow.get('status') or 'draft')}",
        f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
        f"Motif : {restitution.get('reason') or '-'}",
        f"Observations : {restitution.get('notes') or '-'}",
    ]
    for item_key, state in sorted((restitution.get("items") or {}).items()):
        item_label = next((entry["label"] for entry in resources if entry["itemKey"] == item_key), item_key)
        state_label = format_restitution_state_label(state.get("state") or state.get("condition"))
        note = state.get("notes") or "-"
        restitution_lines.append(
            f"{item_label} : {state_label}"
            f" / {note}"
        )
    sections.append(("Restitution", restitution_lines))
    sections.append(
        (
            "Validation et conformit??",
            [
                f"Information RGPD port??e ?? connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
                f"Signature du b??n??ficiaire : {'Oui' if validation.get('signatureDataUrl') else 'Non'}",
                f"Date de signature : {signature_datetime}",
            ],
        )
    )

    if not signature_export_allowed:
        sections[-1] = (
            sections[-1][0],
            [
                f"Information RGPD port?e ? connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
                "Signature du b?n?ficiaire : Masqu?e",
                "Mention : la signature est r?serv?e aux personnes autoris?es.",
            ],
        )


    objects = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    font_regular_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    logo_image = load_brand_logo_image()
    logo_image_id = None
    if logo_image:
        logo_stream = logo_image["data"]
        logo_image_id = add_object(
            f"<< /Type /XObject /Subtype /Image /Width {logo_image['width']} /Height {logo_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(logo_stream)} >>\n"
            f"stream\n{logo_stream.decode('latin-1')}\nendstream"
        )

    signature_image = extract_signature_image(validation.get("signatureDataUrl")) if signature_export_allowed else None
    signature_image_id = None
    if signature_image:
        signature_stream = signature_image["data"]
        signature_image_id = add_object(
            f"<< /Type /XObject /Subtype /Image /Width {signature_image['width']} /Height {signature_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(signature_stream)} >>\n"
            f"stream\n{signature_stream.decode('latin-1')}\nendstream"
        )

    pages = []
    current_page = []
    current_y = top_content_start

    def color_fill(r, g, b):
        return f"{r:.3f} {g:.3f} {b:.3f} rg"

    def color_stroke(r, g, b):
        return f"{r:.3f} {g:.3f} {b:.3f} RG"

    def draw_text(commands, x_pos, y_pos, text, font="F1", size=11, color=(0.12, 0.16, 0.2)):
        commands.append(
            f"q {color_fill(*color)} BT /{font} {size} Tf 1 0 0 1 {x_pos} {y_pos} Tm ({pdf_escape(text)}) Tj ET Q"
        )

    def draw_rect(commands, x_pos, y_pos, width, height, fill=None, stroke=None, line_width=1):
        rect_commands = ["q"]
        if fill:
            rect_commands.append(color_fill(*fill))
        if stroke:
            rect_commands.append(color_stroke(*stroke))
            rect_commands.append(f"{line_width} w")
        operator = "B" if fill and stroke else "f" if fill else "S"
        rect_commands.append(f"{x_pos} {y_pos} {width} {height} re {operator}")
        rect_commands.append("Q")
        commands.append(" ".join(rect_commands))

    def ensure_space(required_height):
        nonlocal current_page, current_y
        if current_y - required_height >= bottom_margin:
            return
        pages.append(current_page)
        current_page = []
        current_y = top_content_start

    def wrap_line(text, width=86):
        normalized = normalize_pdf_text(text)
        return textwrap.wrap(normalized, width=width) or [""]

    def add_section(title_text, raw_lines):
        nonlocal current_page, current_y
        wrapped_lines = []
        for raw_line in raw_lines:
            wrapped_lines.extend(wrap_line(raw_line))
        section_height = 28 + (len(wrapped_lines) * 15) + 18
        ensure_space(section_height)

        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.98, 0.985, 0.99), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, normalize_pdf_text(title_text), font="F2", size=12, color=(0.05, 0.26, 0.40))

        line_y = current_y - 40
        for line in wrapped_lines:
            draw_text(current_page, margin + 14, line_y, normalize_pdf_text(line), font="F1", size=10.5, color=(0.17, 0.20, 0.24))
            line_y -= 15

        current_y = box_bottom - 16

    for section_title, section_lines in sections:
        add_section(section_title, section_lines)

    if signature_image and signature_image_id:
        max_width = 220
        max_height = 90
        ratio = min(max_width / signature_image["width"], max_height / signature_image["height"])
        draw_width = round(signature_image["width"] * ratio, 2)
        draw_height = round(signature_image["height"] * ratio, 2)
        section_height = 90 + draw_height
        ensure_space(section_height)
        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.985, 0.99, 0.995), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, "Signature du bÃ©nÃ©ficiaire", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "Signature recueillie lors de la validation du dossier.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        current_page.append(
            f"q {draw_width} 0 0 {draw_height} {margin + 14} {box_bottom + 18} cm /SIG1 Do Q"
        )
        current_y = box_bottom - 16

    if signature_present and not signature_export_allowed:
        section_height = 92
        ensure_space(section_height)
        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.985, 0.99, 0.995), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, "Signature du b?n?ficiaire", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, "Signature masqu?e dans cet export.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "La signature est r?serv?e aux personnes autoris?es.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 70, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        current_y = box_bottom - 16

    if not current_page:
        current_page = []
    pages.append(current_page)

    page_object_ids = []
    total_pages = len(pages)
    generated_at = format_export_datetime(datetime.now().isoformat())

    for page_index, page_commands in enumerate(pages, start=1):
        commands = []
        draw_rect(commands, 0, page_height - 92, page_width, 92, fill=(0.05, 0.33, 0.52))
        draw_rect(commands, 0, page_height - 104, page_width, 12, fill=(0.84, 0.64, 0.25))
        if logo_image_id:
            logo_ratio = min(88 / logo_image["width"], 52 / logo_image["height"])
            logo_width = round(logo_image["width"] * logo_ratio, 2)
            logo_height = round(logo_image["height"] * logo_ratio, 2)
            commands.append(f"q {logo_width} 0 0 {logo_height} {margin} {page_height - 76} cm /LOGO Do Q")
        draw_text(commands, margin + 100, page_height - 48, "Ville de Publier", font="F2", size=18, color=(1, 1, 1))
        draw_text(commands, margin + 100, page_height - 68, "Parcours agents et Ã©lu(e)s", font="F2", size=13, color=(0.92, 0.96, 0.99))
        draw_text(commands, page_width - 190, page_height - 48, "Document interne", font="F2", size=10.5, color=(1, 1, 1))
        draw_text(commands, page_width - 190, page_height - 66, normalize_pdf_text(generated_at), font="F1", size=9.5, color=(0.92, 0.96, 0.99))

        draw_text(commands, margin, page_height - 118, normalize_pdf_text(title), font="F2", size=15, color=(0.07, 0.18, 0.26))
        draw_text(commands, margin, page_height - 136, "Document de remise et de suivi des ressources attribuÃ©es", font="F1", size=10.5, color=(0.35, 0.43, 0.50))

        commands.extend(page_commands)

        draw_rect(commands, margin, 34, content_width, 0.5, stroke=(0.80, 0.86, 0.90), line_width=0.8)
        draw_text(commands, margin, 20, "Parcours agents et Ã©lu(e)s - document exploitable RH / DGS", font="F1", size=8.5, color=(0.38, 0.45, 0.52))
        draw_text(commands, page_width - 90, 20, f"Page {page_index}/{total_pages}", font="F1", size=8.5, color=(0.38, 0.45, 0.52))

        stream = "\n".join(commands).encode("latin-1", "replace")
        content_object_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream"
        )

        resource_parts = [
            f"/Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >>"
        ]
        xobjects = []
        if logo_image_id:
            xobjects.append(f"/LOGO {logo_image_id} 0 R")
        if signature_image_id:
            xobjects.append(f"/SIG1 {signature_image_id} 0 R")
        if xobjects:
            resource_parts.append(f"/XObject << {' '.join(xobjects)} >>")

        page_object_id = add_object(
            f"<< /Type /Page /Parent PAGES_REF /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << {' '.join(resource_parts)} >> /Contents {content_object_id} 0 R >>"
        )
        page_object_ids.append(page_object_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    pages_object_id = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>")

    for page_id in page_object_ids:
        objects[page_id - 1] = objects[page_id - 1].replace("PAGES_REF", f"{pages_object_id} 0 R")

    info_object_id = add_object(
        f"<< /Title ({pdf_escape(title)}) /Producer (Parcours agents et Ã©lu(e)s) /CreationDate (D:{datetime.now().strftime('%Y%m%d%H%M%S')}) >>"
    )
    catalog_object_id = add_object(f"<< /Type /Catalog /Pages {pages_object_id} 0 R >>")

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, content in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode("latin-1"))
        buffer.write(content.encode("latin-1", "replace"))
        buffer.write(b"\nendobj\n")

    xref_position = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_object_id} 0 R /Info {info_object_id} 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF"
    )
    buffer.write(trailer.encode("latin-1"))
    return buffer.getvalue()


def build_restitution_pdf_bytes(title, payload):
    page_width = 595
    page_height = 842
    margin = 42
    content_width = page_width - (margin * 2)
    top_content_start = 660
    bottom_margin = 52

    beneficiaire = payload.get("beneficiaire", {})
    dossier = payload.get("dossier", {})
    workflow = payload.get("workflow", {})
    restitution = payload.get("restitution", {})
    signature_datetime = get_restitution_signature_datetime(payload)
    signature_status = restitution.get("signatureStatus") or ("signed" if restitution.get("signatureDataUrl") else "deferred")
    signature_export_allowed = can_export_signature_assets()
    signature_present = bool(restitution.get("signatureDataUrl"))
    resources = {entry["itemKey"]: entry for entry in collect_resource_entries(payload)}

    sections = [
        (
            "Identification de la restitution",
            [
                f"Ã‰tat du dossier : {format_status_label(workflow.get('status') or 'draft')}",
                f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
                f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
                f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
                f"Motif : {restitution.get('reason') or '-'}",
            ],
        ),
        (
            "BÃ©nÃ©ficiaire",
            [
                f"Nom : {beneficiaire.get('nom') or '-'}",
                f"PrÃ©nom : {beneficiaire.get('prenom') or '-'}",
                f"QualitÃ© : {format_beneficiary_label(beneficiaire.get('qualite'))}",
                f"Service : {beneficiaire.get('service') or '-'}",
                f"Fonction : {beneficiaire.get('fonction') or '-'}",
                f"Mandat : {beneficiaire.get('mandat') or '-'}",
            ],
        ),
    ]

    restitution_lines = []
    for item_key, state in sorted((restitution.get("items") or {}).items()):
        entry = resources.get(item_key, {"label": item_key, "details": "-"})
        state_label = format_restitution_state_label(state.get("state") or state.get("condition"))
        note = state.get("notes") or "-"
        restitution_lines.append(f"{entry['label']} ({entry['details']}) : {state_label} / {note}")
    if not restitution_lines:
        restitution_lines.append("Aucun matÃ©riel n'a encore Ã©tÃ© renseignÃ© dans la restitution.")
    sections.append(("Ã‰tat des matÃ©riels restituÃ©s", restitution_lines))
    sections.append(
        (
            "Validation de la restitution",
            [
                f"Statut de signature : {format_restitution_signature_status(signature_status)}",
                f"Date de signature : {signature_datetime}",
                f"Motif si la signature n'a pas Ã©tÃ© recueillie : {restitution.get('signatureReason') or '-'}",
                f"Observations gÃ©nÃ©rales : {restitution.get('notes') or '-'}",
            ],
        )
    )

    if not signature_export_allowed:
        sections[-1] = (
            sections[-1][0],
            [
                "Statut de signature : Masqu?e",
                "Mention : la signature est r?serv?e aux personnes autoris?es.",
                "Motif si la signature n'a pas ?t? recueillie : Information r?serv?e.",
                f"Observations g?n?rales : {restitution.get('notes') or '-'}",
            ],
        )

    objects = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    font_regular_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    logo_image = load_brand_logo_image()
    logo_image_id = None
    if logo_image:
        logo_stream = logo_image["data"]
        logo_image_id = add_object(
            f"<< /Type /XObject /Subtype /Image /Width {logo_image['width']} /Height {logo_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(logo_stream)} >>\n"
            f"stream\n{logo_stream.decode('latin-1')}\nendstream"
        )

    signature_image = extract_signature_image(restitution.get("signatureDataUrl")) if signature_export_allowed else None
    signature_image_id = None
    if signature_image:
        signature_stream = signature_image["data"]
        signature_image_id = add_object(
            f"<< /Type /XObject /Subtype /Image /Width {signature_image['width']} /Height {signature_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(signature_stream)} >>\n"
            f"stream\n{signature_stream.decode('latin-1')}\nendstream"
        )

    pages = []
    current_page = []
    current_y = top_content_start

    def color_fill(r, g, b):
        return f"{r:.3f} {g:.3f} {b:.3f} rg"

    def color_stroke(r, g, b):
        return f"{r:.3f} {g:.3f} {b:.3f} RG"

    def draw_text(commands, x_pos, y_pos, text, font="F1", size=11, color=(0.12, 0.16, 0.2)):
        commands.append(
            f"q {color_fill(*color)} BT /{font} {size} Tf 1 0 0 1 {x_pos} {y_pos} Tm ({pdf_escape(text)}) Tj ET Q"
        )

    def draw_rect(commands, x_pos, y_pos, width, height, fill=None, stroke=None, line_width=1):
        rect_commands = ["q"]
        if fill:
            rect_commands.append(color_fill(*fill))
        if stroke:
            rect_commands.append(color_stroke(*stroke))
            rect_commands.append(f"{line_width} w")
        operator = "B" if fill and stroke else "f" if fill else "S"
        rect_commands.append(f"{x_pos} {y_pos} {width} {height} re {operator}")
        rect_commands.append("Q")
        commands.append(" ".join(rect_commands))

    def ensure_space(required_height):
        nonlocal current_page, current_y
        if current_y - required_height >= bottom_margin:
            return
        pages.append(current_page)
        current_page = []
        current_y = top_content_start

    def wrap_line(text, width=86):
        normalized = normalize_pdf_text(text)
        return textwrap.wrap(normalized, width=width) or [""]

    def add_section(title_text, raw_lines):
        nonlocal current_page, current_y
        wrapped_lines = []
        for raw_line in raw_lines:
            wrapped_lines.extend(wrap_line(raw_line))
        section_height = 28 + (len(wrapped_lines) * 15) + 18
        ensure_space(section_height)

        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.98, 0.985, 0.99), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, normalize_pdf_text(title_text), font="F2", size=12, color=(0.05, 0.26, 0.40))

        line_y = current_y - 40
        for line in wrapped_lines:
            draw_text(current_page, margin + 14, line_y, normalize_pdf_text(line), font="F1", size=10.5, color=(0.17, 0.20, 0.24))
            line_y -= 15



    for section_title, section_lines in sections:
        add_section(section_title, section_lines)

    if signature_image and signature_image_id:
        max_width = 220
        max_height = 90
        ratio = min(max_width / signature_image["width"], max_height / signature_image["height"])
        draw_width = round(signature_image["width"] * ratio, 2)
        draw_height = round(signature_image["height"] * ratio, 2)
        section_height = 90 + draw_height
        ensure_space(section_height)
        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.985, 0.99, 0.995), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, "Signature de restitution", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "Signature recueillie lors de la restitution.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        current_page.append(
            f"q {draw_width} 0 0 {draw_height} {margin + 14} {box_bottom + 18} cm /SIG1 Do Q"
        )
        current_y = box_bottom - 16

    if signature_present and not signature_export_allowed:
        section_height = 92
        ensure_space(section_height)
        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.985, 0.99, 0.995), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, "Signature de restitution", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, "Signature masqu?e dans cet export.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "La signature est r?serv?e aux personnes autoris?es.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 70, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        current_y = box_bottom - 16

    if not current_page:
        current_page = []
    pages.append(current_page)

    page_object_ids = []
    total_pages = len(pages)
    generated_at = format_export_datetime(datetime.now().isoformat())

    for page_index, page_commands in enumerate(pages, start=1):
        commands = []
        draw_rect(commands, 0, page_height - 92, page_width, 92, fill=(0.05, 0.33, 0.52))
        draw_rect(commands, 0, page_height - 104, page_width, 12, fill=(0.84, 0.64, 0.25))
        if logo_image_id:
            logo_ratio = min(88 / logo_image["width"], 52 / logo_image["height"])
            logo_width = round(logo_image["width"] * logo_ratio, 2)
            logo_height = round(logo_image["height"] * logo_ratio, 2)
            commands.append(f"q {logo_width} 0 0 {logo_height} {margin} {page_height - 76} cm /LOGO Do Q")
        draw_text(commands, margin + 100, page_height - 48, "Ville de Publier", font="F2", size=18, color=(1, 1, 1))
        draw_text(commands, margin + 100, page_height - 68, "Parcours agents et Ã©lu(e)s", font="F2", size=13, color=(0.92, 0.96, 0.99))
        draw_text(commands, page_width - 190, page_height - 48, "Document interne", font="F2", size=10.5, color=(1, 1, 1))
        draw_text(commands, page_width - 190, page_height - 66, normalize_pdf_text(generated_at), font="F1", size=9.5, color=(0.92, 0.96, 0.99))

        draw_text(commands, margin, page_height - 118, normalize_pdf_text(title), font="F2", size=15, color=(0.07, 0.18, 0.26))
        draw_text(commands, margin, page_height - 136, "Bon de restitution et de suivi des ressources rÃ©cupÃ©rÃ©es", font="F1", size=10.5, color=(0.35, 0.43, 0.50))

        commands.extend(page_commands)

        draw_rect(commands, margin, 34, content_width, 0.5, stroke=(0.80, 0.86, 0.90), line_width=0.8)
        draw_text(commands, margin, 20, "Parcours agents et Ã©lu(e)s - document exploitable RH / DGS", font="F1", size=8.5, color=(0.38, 0.45, 0.52))
        draw_text(commands, page_width - 90, 20, f"Page {page_index}/{total_pages}", font="F1", size=8.5, color=(0.38, 0.45, 0.52))

        stream = "\n".join(commands).encode("latin-1", "replace")
        content_object_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream"
        )

        resource_parts = [
            f"/Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >>"
        ]
        xobjects = []
        if logo_image_id:
            xobjects.append(f"/LOGO {logo_image_id} 0 R")
        if signature_image_id:
            xobjects.append(f"/SIG1 {signature_image_id} 0 R")
        if xobjects:
            resource_parts.append(f"/XObject << {' '.join(xobjects)} >>")

        page_object_id = add_object(
            f"<< /Type /Page /Parent PAGES_REF /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << {' '.join(resource_parts)} >> /Contents {content_object_id} 0 R >>"
        )
        page_object_ids.append(page_object_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    pages_object_id = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>")

    for page_id in page_object_ids:
        objects[page_id - 1] = objects[page_id - 1].replace("PAGES_REF", f"{pages_object_id} 0 R")

    info_object_id = add_object(
        f"<< /Title ({pdf_escape(title)}) /Producer (Parcours agents et Ã©lu(e)s) /CreationDate (D:{datetime.now().strftime('%Y%m%d%H%M%S')}) >>"
    )
    catalog_object_id = add_object(f"<< /Type /Catalog /Pages {pages_object_id} 0 R >>")

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, content in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode("latin-1"))
        buffer.write(content.encode("latin-1", "replace"))
        buffer.write(b"\nendobj\n")

    xref_position = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_object_id} 0 R /Info {info_object_id} 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF"
    )
    buffer.write(trailer.encode("latin-1"))
    return buffer.getvalue()


def format_status_label(status):
    labels = {
        "draft": "Brouillon",
        "partial_assignment": "Attribution partielle",
        "active": "Attribution active",
        "returned": "Restitution terminÃ©e",
        "partial_return": "Restitution partielle",
        "cancelled": "Dossier annulÃ©",
    }
    return labels.get(status, "Brouillon")


def format_restitution_state_label(state):
    labels = {
        "pending": "En attente",
        "returned": "RestituÃ©",
        "returned_damaged": "RestituÃ© abÃ®mÃ©",
        "missing": "Non restituÃ©",
        "transferred": "TransfÃ©rÃ©",
        "conforme": "Conforme",
        "degrade": "DÃ©gradÃ©",
        "non_restitue": "Non restituÃ©",
        "perdu": "Perdu",
        "autre": "Autre",
    }
    return labels.get(state or "", state or "En attente")


def format_restitution_signature_status(value):
    labels = {
        "signed": "Signature recueillie",
        "impossible": "Signature impossible",
        "deferred": "Signature diffÃ©rÃ©e",
    }
    return labels.get(value or "", value or "-")


def extract_items(payload):
    # Transforme le payload metier en lignes d'equipements persistables.
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    restitution = payload.get("restitution", {})
    item_states = restitution.get("items", {})

    items = [
        ("ordinateur", "materiel", "Ordinateur", materiel.get("ordinateur", {})),
        ("ecran", "materiel", "Ã‰cran", materiel.get("ecran", {})),
        ("telephone", "materiel", "TÃ©lÃ©phone", materiel.get("telephone", {})),
        ("tablette", "materiel", "Tablette", materiel.get("tablette", {})),
        ("vehicule", "materiel", "VÃ©hicule", materiel.get("vehicule", {})),
        ("badge", "materiel", "Badge d'accÃ¨s", materiel.get("badge", {})),
        ("cles", "materiel", "ClÃ©(s)", materiel.get("cles", {})),
        ("veste", "materiel", "Veste", materiel.get("veste", {})),
        ("chaussuresSecurite", "materiel", "Chaussures de sÃ©curitÃ©", materiel.get("chaussuresSecurite", {})),
        ("autre", "materiel", "Autre matÃ©riel", materiel.get("autre", {})),
        ("vpn", "immateriel", "VPN", immateriel.get("vpn", {})),
        ("email", "immateriel", "Email", immateriel.get("email", {})),
        ("zoneAlarme", "immateriel", "Zone alarme", immateriel.get("zoneAlarme", {})),
    ]

    for resource in payload.get("resources", {}).get("additional", []):
        items.append((
            resource.get("code") or resource.get("id") or generate_id("resource"),
            resource.get("category") or "materiel",
            resource.get("label") or "Ressource complÃ©mentaire",
            resource,
        ))

    extracted = []
    for item_key, category, label, details in items:
        if not details.get("selected"):
            continue

        state = item_states.get(item_key, {})
        return_state = state.get("state") or state.get("condition") or "pending"
        extracted.append(
            {
                "item_key": item_key,
                "category": category,
                "label": label,
                "assigned": True,
                "returned": return_state in {"returned", "returned_damaged", "transferred", "conforme", "degrade"},
                "returned_at": state.get("returnedAt"),
                "return_condition": return_state,
                "notes": state.get("notes"),
                "details_json": json.dumps(details, ensure_ascii=False),
            }
        )

    return extracted


def summarize_dynamic_resource(resource):
    fields = resource.get("fields") or {}
    if isinstance(fields, dict):
        parts = [str(value).strip() for value in fields.values() if str(value or "").strip()]
        if parts:
            return " - ".join(parts)
    return str(resource.get("details") or "").strip()


def collect_resource_validation_errors(payload):
    errors = []
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    resources = payload.get("resources", {}).get("additional", [])

    fixed_rules = [
        ("ordinateur", materiel.get("ordinateur", {}), [
            ("Marque ordinateur", "marque", r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$"),
            ("ModÃ¨le ordinateur", "modele", r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$"),
            ("NumÃ©ro de sÃ©rie ordinateur", "numeroSerie", r"^[A-Za-z0-9-]{5,40}$"),
        ]),
        ("ecran", materiel.get("ecran", {}), [
            ("Marque Ã©cran", "marque", r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$"),
            ("ModÃ¨le Ã©cran", "modele", r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$"),
            ("NumÃ©ro de sÃ©rie Ã©cran", "numeroSerie", r"^[A-Za-z0-9-]{5,40}$"),
        ]),
        ("telephone", materiel.get("telephone", {}), [
            ("Marque tÃ©lÃ©phone", "marque", r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$"),
            ("ModÃ¨le tÃ©lÃ©phone", "modele", r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$"),
            ("IMEI", "imei", r"^\d{15}$"),
        ]),
        ("tablette", materiel.get("tablette", {}), [
            ("Marque tablette", "marque", r".+"),
            ("ModÃ¨le tablette", "modele", r".+"),
            ("NumÃ©ro de sÃ©rie tablette", "numeroSerie", r".+"),
        ]),
        ("vehicule", materiel.get("vehicule", {}), [
            ("Marque vÃ©hicule", "marque", r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$"),
            ("ModÃ¨le vÃ©hicule", "modele", r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$"),
            ("Immatriculation", "immatriculation", r"^[A-Z]{2}-\d{3}-[A-Z]{2}$"),
        ]),
        ("badge", materiel.get("badge", {}), [
            ("NumÃ©ro de badge", "numero", r"^[A-Za-z0-9-]{3,30}$"),
        ]),
        ("autre", materiel.get("autre", {}), [
            ("Description autre matÃ©riel", "description", r"^.{3,120}$"),
        ]),
        ("email", immateriel.get("email", {}), [
            ("Adresse email", "adresse", r"^[^\s@]+@[^\s@]+\.[^\s@]+$"),
        ]),
    ]

    for _, resource, rules in fixed_rules:
        if not resource.get("selected"):
            continue
        for label, key, _pattern in rules:
            value = str(resource.get(key) or "").strip()
            if not value:
                errors.append(f"{label} manquant")
                continue

    if materiel.get("cles", {}).get("selected") and not [value for value in materiel.get("cles", {}).get("values", []) if str(value).strip()]:
        errors.append("Au moins une clÃ© doit Ãªtre renseignÃ©e")

    if immateriel.get("zoneAlarme", {}).get("selected") and not [value for value in immateriel.get("zoneAlarme", {}).get("zones", []) if str(value).strip()]:
        errors.append("Au moins une zone alarme doit Ãªtre renseignÃ©e")

    for resource in resources:
        if not resource.get("selected"):
            continue
        field_schema = normalize_resource_field_schema(resource.get("fieldSchema") or resource.get("field_schema") or [])
        field_values = resource.get("fields") or {}
        if field_schema:
            for field in field_schema:
                value = str(field_values.get(field["key"]) or "").strip()
                if field.get("required") and not value:
                    errors.append(f"{resource.get('label') or 'Ressource'} : {field['label']} manquant")
                    continue
        elif not summarize_dynamic_resource(resource):
            errors.append(f"{resource.get('label') or 'Ressource complÃ©mentaire'} incomplÃ¨te")

    return errors


def normalize_workflow_before_save(payload):
    workflow = payload.setdefault("workflow", {})
    validation = payload.get("validation", {})
    has_signature = bool(validation.get("signatureDataUrl"))
    rgpd_accepted = bool(validation.get("rgpdAccepted"))
    current_status = workflow.get("status") or "draft"

    if current_status in {"returned", "partial_return", "cancelled"}:
        return payload

    resource_errors = collect_resource_validation_errors(payload)
    payload.setdefault("meta", {})["resourceValidationErrors"] = resource_errors

    if not has_signature or not rgpd_accepted:
        workflow["status"] = "draft"
        payload["meta"]["lockedAt"] = ""
        return payload

    if resource_errors:
        workflow["status"] = "partial_assignment"
        payload["meta"]["lockedAt"] = ""
        return payload

    if workflow.get("status") == "active":
        payload["meta"]["lockedAt"] = payload["meta"].get("lockedAt") or utc_now()
        return payload

    workflow["status"] = "partial_assignment"
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
                raise ValueError("Cette fiche est signÃ©e et verrouillÃ©e. Elle ne peut plus Ãªtre modifiÃ©e.")
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
    summary = {
        "id": row["id"],
        "dossierId": row["dossier_id"],
        "dossierType": row["dossier_type"],
        "title": row["title"],
        "status": row["status"],
        "isLocked": row["status"] == "active",
        "beneficiaryType": row["beneficiary_type"],
        "nom": row["nom"],
        "prenom": row["prenom"],
        "service": row["service"],
        "fonction": row["fonction"],
        "mandat": row["mandat"],
        "assignedAt": row["assigned_at"],
        "returnedAt": row["returned_at"],
        "updatedAt": row["updated_at"],
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
    beneficiaire = payload.get("beneficiaire", {})
    grouped_resources = {"materiel": [], "immateriel": []}
    for entry in collect_resource_entries(payload):
        grouped_resources.setdefault(entry["category"], []).append({
            "label": entry["label"],
            "details": entry["details"],
            "service": entry["service"],
        })

    return {
        "link": {
            "status": link_row["status"],
            "expiresAt": link_row["expires_at"],
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
                "Les donnees a caractere personnel renseignees dans ce dossier font l'objet d'un traitement par la commune de Publier afin d'assurer la gestion des attributions de ressources professionnelles, le suivi des remises et, le cas echeant, des restitutions.",
                "Conformement au reglement general sur la protection des donnees et a la loi Informatique et Libertes, la personne concernee dispose notamment de droits d'acces, de rectification, d'effacement, de limitation et d'opposition, dans les conditions prevues par la reglementation applicable.",
                "Pour toute question relative au traitement de ses donnees personnelles ou pour exercer ses droits, la personne concernee peut contacter le delegue a la protection des donnees a l'adresse suivante : dpo@ville-publier.fr.",
            ],
        },
    }


def download_response(file_bytes, filename, content_type):
    response = make_response(file_bytes)
    response.headers["Content-Type"] = content_type
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


init_db()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
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
                    "Connexion reussie",
                    "user",
                    username,
                    {"ip": request.remote_addr},
                    actor=username,
                )
            return redirect("/")
        return redirect(f"/login?error={auth_state}")

    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
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
                "Deconnexion",
                "user",
                username,
                {"ip": request.remote_addr},
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


@app.route("/form.html")
@login_required
def form_page():
    return send_from_directory(FRONTEND_DIR, "form.html")


@app.route("/restitution.html")
@login_required
def restitution_page():
    return send_from_directory(FRONTEND_DIR, "restitution.html")


@app.route("/signature/<token>")
def signature_page(token):
    return send_from_directory(FRONTEND_DIR, "signature.html")


@app.route("/admin.html")
@login_required
def admin_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin.html")


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
    filename = f"{slugify_filename(title)}.pdf"
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
            zip_file.writestr(f"{slugify_filename(title)}.pdf", pdf_bytes)
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
        "Ã‰tat",
        "Type de dossier",
        "QualitÃ©",
        "Nom",
        "PrÃ©nom",
        "Service",
        "Fonction",
        "Mandat",
        "Service de destination",
        "Date de remise",
        "Date de restitution",
        "RGPD",
        "Signature",
        "Ressources attribuÃ©es",
        "Motif restitution",
        "Observations",
        "CrÃ©Ã© le",
        "Mis Ã  jour le",
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
        "Service Ã©metteur",
        "Ressource",
        "CatÃ©gorie",
        "DÃ©tails",
        "Ã‰tat restitution",
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
            if key not in {"selected"} and str(value or "").strip()
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
        link_row = get_latest_signature_link(connection, form_id)
    return jsonify({"link": serialize_signature_link(link_row)})


@app.route("/api/forms/<form_id>/signature-link", methods=["POST"])
@login_required
def create_form_signature_link_route(form_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403
    try:
        with get_db() as connection:
            link_row = create_signature_link(connection, form_id, actor=current_actor())
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"link": serialize_signature_link(link_row)}), 201


@app.route("/api/signature-links/<link_id>", methods=["DELETE"])
@login_required
def revoke_signature_link_route(link_id):
    if not has_permission("forms.edit"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        link_row = revoke_signature_link(connection, link_id, actor=current_actor())
    if not link_row:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"link": serialize_signature_link(link_row)})


@app.route("/api/signature/<token>", methods=["GET"])
def get_signature_token_route(token):
    with get_db() as connection:
        link_row = get_signature_link_by_token(connection, token)
        if not link_row:
            return jsonify({"error": "invalid_link"}), 404
        if link_row["status"] != "active":
            return jsonify({"error": link_row["status"]}), 410

        now = utc_now()
        connection.execute(
            "UPDATE signature_links SET last_opened_at = ?, last_opened_ip = ? WHERE id = ?",
            (now, request.remote_addr or "", link_row["id"]),
        )
        form_row = connection.execute(
            "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
            (link_row["form_id"],),
        ).fetchone()
        if form_row:
            insert_app_log(
                connection,
                "signature",
                "signature_link_opened",
                "Lien de signature ouvert",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": request.remote_addr},
                actor="public_signature_link",
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
        if not link_row:
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
            (utc_now(), utc_now(), request.remote_addr or "", link_row["id"]),
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
                "Lien de signature utilise",
                {"form_id": link_row["form_id"], "title": form_row["title"]},
            )
            insert_app_log(
                connection,
                "signature",
                "signature_link_used",
                "Lien de signature utilise",
                "form",
                link_row["form_id"],
                {"title": form_row["title"], "ip": request.remote_addr},
                actor="public_signature_link",
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

        if row["status"] not in {"draft", "partial_assignment"}:
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
    payload["workflow"]["status"] = patch.get("status", payload["workflow"].get("status", "active"))
    payload["restitution"]["returnedAt"] = patch.get("returnedAt", payload["restitution"].get("returnedAt"))
    payload["restitution"]["reason"] = patch.get("reason", payload["restitution"].get("reason"))
    payload["restitution"]["notes"] = patch.get("notes", payload["restitution"].get("notes"))
    payload["restitution"]["items"] = patch.get("items", payload["restitution"].get("items", {}))
    payload["restitution"]["signatureStatus"] = patch.get("signatureStatus", payload["restitution"].get("signatureStatus"))
    payload["restitution"]["signatureReason"] = patch.get("signatureReason", payload["restitution"].get("signatureReason"))
    payload["restitution"]["signatureDataUrl"] = patch.get("signatureDataUrl", payload["restitution"].get("signatureDataUrl"))
    payload["restitution"]["signedAt"] = patch.get("signedAt", payload["restitution"].get("signedAt"))

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
            ORDER BY category ASC, label COLLATE NOCASE ASC
            """
        ).fetchall()
    return jsonify([normalize_reference_row(row) for row in rows])


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


@app.route("/api/admin/resources", methods=["GET"])
@login_required
@permission_required("users.manage")
def admin_resources():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM resource_catalog ORDER BY is_active DESC, category ASC, label COLLATE NOCASE ASC"
        ).fetchall()
    return jsonify([normalize_reference_row(row) for row in rows])


@app.route("/api/admin/resources", methods=["POST"])
@login_required
@permission_required("users.manage")
def create_admin_resource():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    label = (payload.get("label") or "").strip()
    category = (payload.get("category") or "").strip() or "materiel"
    issuer_service = (payload.get("issuer_service") or "").strip()
    trigger_key = (payload.get("trigger_key") or "").strip()
    field_schema = normalize_resource_field_schema(payload.get("field_schema") or payload.get("fieldSchema") or [])
    is_active = bool(payload.get("is_active", True))
    requires_return = bool(payload.get("requires_return", True))

    if not code or not label:
        return jsonify({"error": "code_and_label_required"}), 400

    now = utc_now()
    with get_db() as connection:
        existing = connection.execute("SELECT id FROM resource_catalog WHERE code = ?", (code,)).fetchone()
        if existing:
            return jsonify({"error": "resource_exists"}), 409
        resource_id = generate_id("resource")
        connection.execute(
            """
            INSERT INTO resource_catalog (
                id, code, label, category, issuer_service, requires_return, trigger_key,
                field_schema_json, is_active, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                resource_id,
                code,
                label,
                category,
                issuer_service,
                bool_to_int(requires_return),
                trigger_key,
                json.dumps(field_schema, ensure_ascii=False),
                bool_to_int(is_active),
                now,
                now,
            ),
        )
        insert_app_log(
            connection,
            "admin",
            "resource_created",
            "Ressource creee",
            "resource",
            resource_id,
            {"code": code, "label": label, "category": category, "issuer_service": issuer_service, "field_count": len(field_schema)},
        )
    return jsonify({"created": True}), 201


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
        next_code = (payload.get("code") or row["code"]).strip()
        if not next_code:
            return jsonify({"error": "code_required"}), 400
        duplicate = connection.execute(
            "SELECT id FROM resource_catalog WHERE code = ? AND id != ?",
            (next_code, resource_id),
        ).fetchone()
        if duplicate:
            return jsonify({"error": "resource_code_exists"}), 409
        raw_field_schema = payload.get("field_schema") if "field_schema" in payload else payload.get("fieldSchema")
        field_schema = normalize_resource_field_schema(
            raw_field_schema if raw_field_schema is not None else json.loads(row["field_schema_json"] or "[]")
        )
        connection.execute(
            """
            UPDATE resource_catalog
            SET code = ?, label = ?, category = ?, issuer_service = ?, requires_return = ?,
                trigger_key = ?, field_schema_json = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_code,
                (payload.get("label") or row["label"]).strip(),
                (payload.get("category") or row["category"]).strip(),
                (payload.get("issuer_service") if payload.get("issuer_service") is not None else row["issuer_service"]),
                bool_to_int(payload.get("requires_return", bool(row["requires_return"]))),
                (payload.get("trigger_key") if payload.get("trigger_key") is not None else row["trigger_key"]),
                json.dumps(field_schema, ensure_ascii=False),
                bool_to_int(payload.get("is_active", bool(row["is_active"]))),
                now,
                resource_id,
            ),
        )
        insert_app_log(
            connection,
            "admin",
            "resource_updated",
            "Ressource mise a jour",
            "resource",
            resource_id,
            {
                "code": next_code,
                "label": payload.get("label") or row["label"],
                "category": payload.get("category") or row["category"],
                "field_count": len(field_schema),
            },
        )
    return jsonify({"updated": True})


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
