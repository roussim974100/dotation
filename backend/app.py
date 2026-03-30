from flask import Flask, jsonify, make_response, redirect, request, send_from_directory, session, has_request_context
import base64
import bcrypt
import hashlib
import io
import json
import os
import secrets
import sqlite3
import struct
import textwrap
import unicodedata
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
CUSTOM_BRANDING_DIR = os.path.join(FRONTEND_ASSETS_DIR, "custom")
A_QUAI_PDF_LOGO_PATH = os.path.join(FRONTEND_ASSETS_DIR, "a-quai-email-mark.png")
PDF_CACHE_DIR = os.path.join(BASE_DIR, "pdf_cache")
DB_PATH = os.path.join(BASE_DIR, "dotation.db")
APP_SECRET_PATH = os.path.join(BASE_DIR, ".app_secret_key")
CITY_LOGO_URL = os.environ.get(
    "CITY_LOGO_URL",
    "https://fr.wikipedia.org/wiki/Special:Redirect/file/Logo_ville_Publier_2022.png",
)
CITY_LOGO_PATH = os.environ.get("CITY_LOGO_PATH", os.path.join(FRONTEND_ASSETS_DIR, "city-logo.png"))


def get_app_secret_key():
    env_secret = os.environ.get("APP_SECRET_KEY", "").strip()
    if env_secret:
        return env_secret

    try:
        if os.path.exists(APP_SECRET_PATH):
            with open(APP_SECRET_PATH, "r", encoding="utf-8") as secret_file:
                stored_secret = secret_file.read().strip()
                if stored_secret:
                    return stored_secret
    except OSError:
        pass

    generated_secret = secrets.token_hex(32)
    try:
        with open(APP_SECRET_PATH, "w", encoding="utf-8") as secret_file:
            secret_file.write(generated_secret)
    except OSError:
        pass
    return generated_secret


app = Flask(__name__, static_folder=None)
app.secret_key = get_app_secret_key()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SESSION_COOKIE_NAME"] = "publier_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


@app.after_request
def disable_frontend_cache(response):
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        if "charset=" not in content_type:
            response.headers["Content-Type"] = "text/html; charset=utf-8"
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

BRAND_LOGO_CACHE = {
    "loaded": False,
    "cache_key": None,
    "image": None,
}

DEFAULT_APP_SETTINGS = {
    "org_name": "Ville de Publier",
    "app_name": "A quai",
    "dpo_email": "dpo@ville-publier.fr",
    "brand_logo_mode": "url",
    "brand_logo_url": CITY_LOGO_URL,
    "brand_logo_file": "",
    "theme_id": "institutionnel",
    "dark_mode_policy": "disabled",
}

CLIENT_CONTEXT_COOKIE_NAME = "dotation_client_context_v1"

THEME_PRESETS = {
    "institutionnel": {
        "label": "Institutionnel bleu",
        "light": {
            "brand": "#0f5b8d",
            "brandDark": "#0a4267",
            "brandSoft": "#dbeaf3",
            "accent": "#d9a441",
            "surface": "#ffffff",
            "surfaceAlt": "#f5f8fb",
            "text": "#1f2933",
            "muted": "#607080",
            "border": "#d4dde6",
        },
        "dark": {
            "brand": "#68a7d1",
            "brandDark": "#0f5b8d",
            "brandSoft": "#17354a",
            "accent": "#e3b85f",
            "surface": "#10212d",
            "surfaceAlt": "#163040",
            "text": "#edf4f8",
            "muted": "#acc0ce",
            "border": "#2d4b5f",
        },
    },
    "lac_montagne": {
        "label": "Lac et montagne",
        "light": {
            "brand": "#1e6f74",
            "brandDark": "#174f53",
            "brandSoft": "#d7eeec",
            "accent": "#9b7b45",
            "surface": "#ffffff",
            "surfaceAlt": "#f2f7f6",
            "text": "#20313a",
            "muted": "#5d7682",
            "border": "#cfdedd",
        },
        "dark": {
            "brand": "#5fb2b7",
            "brandDark": "#1e6f74",
            "brandSoft": "#15353a",
            "accent": "#c6a26a",
            "surface": "#0f1d22",
            "surfaceAlt": "#16282f",
            "text": "#e7f4f3",
            "muted": "#a7c2c4",
            "border": "#335259",
        },
    },
    "ardoise": {
        "label": "Ardoise",
        "light": {
            "brand": "#43576b",
            "brandDark": "#2f4050",
            "brandSoft": "#e2e8ee",
            "accent": "#c48d45",
            "surface": "#ffffff",
            "surfaceAlt": "#f5f7fa",
            "text": "#22303c",
            "muted": "#677786",
            "border": "#d6dfe7",
        },
        "dark": {
            "brand": "#8da4b8",
            "brandDark": "#43576b",
            "brandSoft": "#1d2832",
            "accent": "#d3a05c",
            "surface": "#12181f",
            "surfaceAlt": "#1a232d",
            "text": "#eef3f7",
            "muted": "#aeb9c3",
            "border": "#364350",
        },
    },
    "sable": {
        "label": "Sable",
        "light": {
            "brand": "#9b6f3e",
            "brandDark": "#77522d",
            "brandSoft": "#f3e9dc",
            "accent": "#3f7b8a",
            "surface": "#fffdfa",
            "surfaceAlt": "#fbf5ee",
            "text": "#332820",
            "muted": "#7b6a5b",
            "border": "#e5d8ca",
        },
        "dark": {
            "brand": "#d2a06a",
            "brandDark": "#9b6f3e",
            "brandSoft": "#38281a",
            "accent": "#74aebe",
            "surface": "#1c1712",
            "surfaceAlt": "#272018",
            "text": "#f7efe6",
            "muted": "#c2b2a2",
            "border": "#4d3e2f",
        },
    },
    "foret": {
        "label": "Forêt",
        "light": {
            "brand": "#2f6d4f",
            "brandDark": "#24513b",
            "brandSoft": "#dceee4",
            "accent": "#c89b49",
            "surface": "#ffffff",
            "surfaceAlt": "#f4f8f5",
            "text": "#20332a",
            "muted": "#61786b",
            "border": "#d3e1d8",
        },
        "dark": {
            "brand": "#68b388",
            "brandDark": "#2f6d4f",
            "brandSoft": "#183225",
            "accent": "#dfb367",
            "surface": "#101914",
            "surfaceAlt": "#17231c",
            "text": "#edf5f0",
            "muted": "#adc4b7",
            "border": "#345241",
        },
    },
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
    data["requires_return"] = bool(data.get("requires_return"))
    data["has_assignment_date"] = bool(data.get("has_assignment_date", True))
    data["has_assignment_condition"] = bool(data.get("has_assignment_condition", False))
    data["has_assignment_notes"] = bool(data.get("has_assignment_notes", True))
    data["is_active"] = bool(data.get("is_active", True))
    data["is_builtin"] = bool(data.get("is_builtin", False))
    data["display_order"] = int(data.get("display_order") or 100)
    return data


def normalize_service_row(row):
    if not row:
        return None
    return {
        key: row[key]
        for key in row.keys()
    }


def seed_app_settings(connection):
    now = utc_now()
    for key, value in DEFAULT_APP_SETTINGS.items():
        existing = connection.execute(
            "SELECT setting_key FROM app_settings WHERE setting_key = ?",
            (key,),
        ).fetchone()
        if existing:
            continue
        connection.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, str(value), now),
        )


def get_app_settings(connection=None):
    close_after = False
    if connection is None:
        connection = get_db()
        close_after = True
    try:
        rows = connection.execute("SELECT setting_key, setting_value FROM app_settings").fetchall()
        settings = dict(DEFAULT_APP_SETTINGS)
        for row in rows:
            settings[row["setting_key"]] = row["setting_value"]
        return settings
    finally:
        if close_after:
            connection.close()


def save_app_settings(connection, updates):
    now = utc_now()
    sanitized = {}
    for key in DEFAULT_APP_SETTINGS.keys():
        if key not in updates:
            continue
        value = updates.get(key)
        sanitized[key] = "" if value is None else str(value).strip()

    if "brand_logo_mode" in sanitized and sanitized["brand_logo_mode"] not in {"default", "url", "file"}:
        sanitized["brand_logo_mode"] = DEFAULT_APP_SETTINGS["brand_logo_mode"]
    if "theme_id" in sanitized and sanitized["theme_id"] not in THEME_PRESETS:
        sanitized["theme_id"] = DEFAULT_APP_SETTINGS["theme_id"]
    if "dark_mode_policy" in sanitized and sanitized["dark_mode_policy"] not in {"disabled", "allowed", "forced"}:
        sanitized["dark_mode_policy"] = DEFAULT_APP_SETTINGS["dark_mode_policy"]

    for key, value in sanitized.items():
        connection.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
    BRAND_LOGO_CACHE["loaded"] = False
    BRAND_LOGO_CACHE["cache_key"] = None
    BRAND_LOGO_CACHE["image"] = None


def sanitize_brand_file_name(filename):
    stem, extension = os.path.splitext(str(filename or ""))
    extension = extension.lower()
    safe_stem = slugify_field_key(stem) or "logo"
    return f"{safe_stem}{extension}"


def get_brand_logo_public_url(settings):
    logo_mode = settings.get("brand_logo_mode") or DEFAULT_APP_SETTINGS["brand_logo_mode"]
    if logo_mode == "file":
        relative_path = (settings.get("brand_logo_file") or "").replace("\\", "/").lstrip("/")
        if relative_path and os.path.exists(os.path.join(FRONTEND_ASSETS_DIR, relative_path)):
            return f"/assets/{relative_path}"
    if logo_mode == "url":
        return settings.get("brand_logo_url") or CITY_LOGO_URL
    if os.path.exists(CITY_LOGO_PATH):
        return "/assets/city-logo.png"
    return CITY_LOGO_URL


def get_brand_logo_candidates(settings):
    logo_mode = settings.get("brand_logo_mode") or DEFAULT_APP_SETTINGS["brand_logo_mode"]
    local_candidates = []
    remote_url = ""

    if logo_mode == "file":
        relative_path = (settings.get("brand_logo_file") or "").replace("\\", "/").lstrip("/")
        if relative_path:
            local_candidates.append(os.path.join(FRONTEND_ASSETS_DIR, relative_path))
    elif logo_mode == "url":
        remote_url = settings.get("brand_logo_url") or CITY_LOGO_URL
    else:
        local_candidates.append(CITY_LOGO_PATH)
        remote_url = CITY_LOGO_URL

    return local_candidates, remote_url


def resolve_theme_id(settings):
    theme_id = settings.get("theme_id") or DEFAULT_APP_SETTINGS["theme_id"]
    return theme_id if theme_id in THEME_PRESETS else DEFAULT_APP_SETTINGS["theme_id"]


def resolve_dark_mode(settings):
    policy = settings.get("dark_mode_policy") or DEFAULT_APP_SETTINGS["dark_mode_policy"]
    return policy if policy in {"disabled", "allowed", "forced"} else DEFAULT_APP_SETTINGS["dark_mode_policy"]


def build_public_settings_payload(settings=None):
    settings = settings or get_app_settings()
    theme_id = resolve_theme_id(settings)
    return {
        "orgName": settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"],
        "appName": "A quai",
        "dpoEmail": get_dpo_email(settings),
        "logoUrl": "/api/settings/logo",
        "logoMode": settings.get("brand_logo_mode") or DEFAULT_APP_SETTINGS["brand_logo_mode"],
        "themeId": theme_id,
        "themeLabel": THEME_PRESETS[theme_id]["label"],
        "darkModePolicy": resolve_dark_mode(settings),
        "themes": {
            key: {"label": value["label"]}
            for key, value in THEME_PRESETS.items()
        },
    }


def slugify_field_key(value):
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    return "".join(
        character if character.isalnum() else "_"
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).strip("_")


def normalize_resource_field_schema(raw_schema):
    allowed_types = {"text", "textarea", "select", "date", "number", "checkbox"}
    normalized = []
    for index, field in enumerate(raw_schema or []):
        label = str(field.get("label") or "").strip()
        key = slugify_field_key(field.get("key") or label or f"champ_{index + 1}")
        if not label or not key:
            continue
        field_type = str(field.get("type") or "text").strip().lower() or "text"
        if field_type not in allowed_types:
            field_type = "text"
        options = field.get("options") or []
        if not isinstance(options, list):
            options = []
        normalized.append({
            "key": key,
            "label": label,
            "type": field_type,
            "placeholder": str(field.get("placeholder") or "").strip(),
            "required": bool(field.get("required", False)),
            "options": [str(option).strip() for option in options if str(option or "").strip()],
        })
    return normalized


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
    workflow_status = compute_effective_workflow_status(payload)
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
    if workflow_status == "awaiting_signature":
        return "en_signature"
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
        "arrivee": "Nouvelle arrivée",
        "changement_service": "Changement de service",
        "mise_a_jour": "Mise à jour de ressources",
        "sortie": "Sortie / restitution",
    }
    return labels.get(normalize_dossier_type(value), "Nouvelle arrivée")


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


def extract_first_forwarded_ip(value):
    for part in str(value or "").split(","):
        candidate = part.strip()
        if candidate:
            return candidate
    return ""


def get_request_client_ip():
    if not has_request_context():
        return ""
    forwarded_ip = extract_first_forwarded_ip(request.headers.get("X-Forwarded-For"))
    if forwarded_ip:
        return forwarded_ip
    real_ip = str(request.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip
    access_route = getattr(request, "access_route", None) or []
    for candidate in access_route:
        candidate = str(candidate or "").strip()
        if candidate:
            return candidate
    return str(request.remote_addr or "").strip()


def read_client_context_cookie():
    if not has_request_context():
        return {}
    raw_value = request.cookies.get(CLIENT_CONTEXT_COOKIE_NAME)
    if not raw_value:
        return {}
    try:
        padded = raw_value + ("=" * (-len(raw_value) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    sanitized = {}
    for key, value in payload.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            sanitized[str(key)] = text[:255]
    return sanitized


def read_login_attempt_context():
    if not has_request_context():
        return {}
    allowed_fields = {
        "client_device_label": "poste",
        "client_browser": "navigateur",
        "client_platform": "plateforme",
        "client_local_ip": "ip_locale",
        "client_local_host_hint": "reseau_local",
        "client_user_agent": "user_agent",
        "client_language": "langue",
        "client_languages": "langues",
        "client_timezone": "fuseau_horaire",
        "client_screen": "ecran",
        "client_viewport": "fenetre",
        "client_cookie_enabled": "cookies_actifs",
        "client_page_url": "page_connexion",
    }
    sanitized = {}
    for field_name, output_key in allowed_fields.items():
        value = str(request.form.get(field_name) or "").strip()
        if value:
            sanitized[output_key] = value[:512]
    return sanitized


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


def build_request_client_log_details():
    if not has_request_context():
        return {}
    client_context = read_client_context_cookie()
    login_attempt_context = read_login_attempt_context()
    details = {}
    device_label = login_attempt_context.get("poste") or client_context.get("deviceLabel") or ""
    local_ip = login_attempt_context.get("ip_locale") or client_context.get("localIp") or ""
    local_network_hint = login_attempt_context.get("reseau_local") or client_context.get("localHostHint") or ""
    browser_name = login_attempt_context.get("navigateur") or client_context.get("browser") or ""
    platform_name = login_attempt_context.get("plateforme") or client_context.get("platform") or ""
    server_seen_ip = client_context.get("serverSeenIp") or get_request_client_ip()
    real_ip = str(request.headers.get("X-Real-IP") or "").strip()

    if device_label:
        details["poste"] = device_label
    if local_ip:
        details["ip_locale"] = local_ip
    if local_network_hint and local_network_hint != local_ip:
        details["reseau_local"] = local_network_hint
    if server_seen_ip:
        details["ip_vue_serveur"] = server_seen_ip
    if real_ip and real_ip != server_seen_ip:
        details["ip_reelle_proxy"] = real_ip
    if browser_name:
        details["navigateur"] = browser_name
    if platform_name:
        details["plateforme"] = platform_name
    return details


def merge_app_log_details(details=None):
    merged = dict(details or {})
    request_details = build_request_client_log_details()
    for key, value in request_details.items():
        merged.setdefault(key, value)
    if merged.get("ip") and not merged.get("ip_vue_serveur"):
        merged["ip_vue_serveur"] = merged["ip"]
    return merged


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
            json.dumps(merge_app_log_details(details), ensure_ascii=False),
            utc_now(),
        ),
    )


def current_actor(default="system"):
    return session.get("user") or default


def signature_link_label(link_type):
    if link_type == "restitution":
        return "Lien de signature de restitution"
    return "Lien de signature"


def signature_link_scope(link_type):
    if link_type == "restitution":
        return "restitution_signature"
    return "signature"


def signature_link_public_url(link_type, token):
    if link_type == "restitution":
        return f"/restitution-signature/{token}"
    return f"/signature/{token}"


def signature_link_public_actor(link_type):
    if link_type == "restitution":
        return "public_restitution_signature_link"
    return "public_signature_link"


def signature_link_expiration(hours=72):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def generate_signature_token():
    return secrets.token_urlsafe(32)


def materialize_signature_link(connection, row):
    # Lecture normalisée d'un lien avec expiration recalculée à la volée,
    # pour éviter d'éparpiller cette logique dans plusieurs routes.
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
        "type": row["link_type"],
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
        "url": signature_link_public_url(row["link_type"], row["token"]) if row["status"] == "active" else "",
    }


def get_latest_signature_link(connection, form_id, link_type="assignment"):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE form_id = ? AND link_type = ? ORDER BY created_at DESC LIMIT 1",
        (form_id, link_type),
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


def revoke_signature_links_for_form(connection, form_id, actor=None, except_id=None, link_type="assignment"):
    actor = actor or current_actor()
    now = utc_now()
    rows = connection.execute(
        "SELECT * FROM signature_links WHERE form_id = ? AND link_type = ? AND status = 'active'",
        (form_id, link_type),
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


def create_signature_link(connection, form_id, actor=None, expires_in_hours=72, link_type="assignment"):
    actor = actor or current_actor()
    form_row = connection.execute(
        "SELECT id, dossier_id, title, payload_json FROM dotation_forms WHERE id = ?",
        (form_id,),
    ).fetchone()
    if not form_row:
        raise ValueError("Dossier introuvable.")

    payload = json.loads(form_row["payload_json"] or "{}")
    if link_type == "restitution":
        restitution = payload.get("restitution", {})
        has_restitution = bool(
            restitution.get("returnedAt")
        )
        if not has_restitution:
            raise ValueError("La restitution doit être préparée avant de générer un lien.")
        if restitution.get("signatureDataUrl"):
            raise ValueError("Cette restitution est déjà signée.")
    else:
        validation = payload.get("validation", {})
        if validation.get("signatureDataUrl"):
            raise ValueError("Ce dossier est deja signe.")

    revoke_signature_links_for_form(connection, form_id, actor=actor, link_type=link_type)
    now = utc_now()
    row = {
        "id": generate_id("siglink"),
        "form_id": form_id,
        "link_type": link_type,
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
            id, form_id, link_type, token, status, created_by, created_at, expires_at,
            used_at, revoked_at, revoked_by, last_opened_at, last_opened_ip, notes
        ) VALUES (
            :id, :form_id, :link_type, :token, :status, :created_by, :created_at, :expires_at,
            :used_at, :revoked_at, :revoked_by, :last_opened_at, :last_opened_ip, :notes
        )
        """,
        row,
    )
    link_label = signature_link_label(link_type)
    link_scope = signature_link_scope(link_type)
    insert_audit_event(
        connection,
        form_row["dossier_id"],
        "signature_link_created",
        f"{link_label} genere",
        {"form_id": form_id, "title": form_row["title"], "expires_at": row["expires_at"], "link_type": link_type},
    )
    insert_app_log(
        connection,
        link_scope,
        "signature_link_created",
        f"{link_label} genere",
        "form",
        form_id,
        {"title": form_row["title"], "expires_at": row["expires_at"], "link_type": link_type},
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
        link_label = signature_link_label(row["link_type"])
        link_scope = signature_link_scope(row["link_type"])
        insert_audit_event(
            connection,
            form_row["dossier_id"],
            "signature_link_revoked",
            f"{link_label} revoque",
            {"form_id": row["form_id"], "title": form_row["title"], "link_type": row["link_type"]},
        )
        insert_app_log(
            connection,
            link_scope,
            "signature_link_revoked",
            f"{link_label} revoque",
            "form",
            row["form_id"],
            {"title": form_row["title"], "link_type": row["link_type"]},
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
    start_at = meta.get("startAt") or assigned_at

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
        "date_arrivee": start_at,
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
    meta["startAt"] = start_at
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
    # Le PDF utilise WinAnsiEncoding (CP1252).
    # On repare d'abord les chaines mojibakees les plus courantes, puis on force un encodage CP1252
    # avant de retransformer en chaine "byte-safe" pour l'ecriture finale du flux PDF.
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
    settings = get_app_settings()
    local_candidates, remote_url = get_brand_logo_candidates(settings)
    cache_key = json.dumps({
        "local": local_candidates,
        "remote": remote_url,
    }, ensure_ascii=False)

    if BRAND_LOGO_CACHE["loaded"] and BRAND_LOGO_CACHE.get("cache_key") == cache_key:
        return BRAND_LOGO_CACHE["image"]

    image = None
    for candidate in local_candidates:
        if candidate and os.path.exists(candidate):
            try:
                with open(candidate, "rb") as file:
                    image = extract_png_image(file.read())
            except OSError:
                image = None
            if image:
                break

    if not image and remote_url:
        try:
            request = urllib.request.Request(
                remote_url,
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
    BRAND_LOGO_CACHE["cache_key"] = cache_key
    BRAND_LOGO_CACHE["image"] = image
    return image


def load_a_quai_pdf_logo_image():
    if not A_QUAI_PDF_LOGO_PATH or not os.path.exists(A_QUAI_PDF_LOGO_PATH):
        return None

    try:
        with open(A_QUAI_PDF_LOGO_PATH, "rb") as file:
            return extract_png_image(file.read())
    except OSError:
        return None


def get_file_signature(path):
    if not path or not os.path.exists(path):
        return {"exists": False}

    try:
        stats = os.stat(path)
        with open(path, "rb") as file:
            digest = hashlib.sha256(file.read()).hexdigest()
    except OSError:
        return {"exists": False}

    return {
        "exists": True,
        "size": stats.st_size,
        "mtime_ns": stats.st_mtime_ns,
        "sha256": digest,
    }


def build_pdf_cache_key(pdf_kind, title, payload):
    settings = get_app_settings()
    local_candidates, remote_url = get_brand_logo_candidates(settings)
    source = {
        "kind": pdf_kind,
        "title": title,
        "payload": payload,
        "settings": settings,
        "app_file": get_file_signature(__file__),
        "brand_logo_candidates": [get_file_signature(candidate) for candidate in local_candidates],
        "brand_logo_remote_url": remote_url,
        "a_quai_logo": get_file_signature(A_QUAI_PDF_LOGO_PATH),
    }
    serialized = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def cleanup_cached_pdf_versions(cache_dir, keep_name):
    if not os.path.isdir(cache_dir):
        return

    try:
        for entry in os.listdir(cache_dir):
            if not entry.lower().endswith(".pdf") or entry == keep_name:
                continue
            try:
                os.remove(os.path.join(cache_dir, entry))
            except OSError:
                continue
    except OSError:
        return


def get_or_build_cached_pdf(form_id, pdf_kind, title, payload, generator):
    cache_key = build_pdf_cache_key(pdf_kind, title, payload)
    cache_dir = os.path.join(PDF_CACHE_DIR, pdf_kind, slugify_field_key(form_id) or "form")
    cache_name = f"{cache_key}.pdf"
    cache_path = os.path.join(cache_dir, cache_name)

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as file:
                return file.read()
        except OSError:
            pass

    pdf_bytes = generator(title, payload)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        temp_path = os.path.join(cache_dir, f"{cache_key}.tmp")
        with open(temp_path, "wb") as file:
            file.write(pdf_bytes)
        os.replace(temp_path, cache_path)
        cleanup_cached_pdf_versions(cache_dir, cache_name)
    except OSError:
        return pdf_bytes

    return pdf_bytes


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


def get_dpo_email(settings=None):
    settings = settings or get_app_settings()
    return settings.get("dpo_email") or DEFAULT_APP_SETTINGS["dpo_email"]


def derive_restitution_workflow_status(item_states, signature_status="", signature_data=""):
    states = list((item_states or {}).values())
    base_status = "returned"
    if states and any((state or {}).get("state") == "non_restitue" for state in states):
        base_status = "partial_return"

    # Une restitution preparee pour signature a distance ne doit pas etre
    # consideree comme terminee tant que la signature de restitution n'a pas
    # ete effectivement recueillie.
    if base_status == "returned" and signature_status == "deferred" and not signature_data:
        return "awaiting_signature"

    return base_status


def format_beneficiary_label(value):
    labels = {
        "agent": "Agent",
        "elu": "Élu(e)",
    }
    return labels.get(value, value or "-")


def summarize_dynamic_resource(resource):
    # Une ressource dynamique peut être décrite par plusieurs champs saisis
    # ou par un simple détail libre; on prépare ici un résumé stable.
    fields = resource.get("fields") or {}
    if isinstance(fields, dict):
        values = [str(value).strip() for value in fields.values() if str(value or "").strip()]
        if values:
            return " - ".join(values)
    return str(resource.get("details") or "").strip()


def uses_dynamic_resource_assignment_date(resource):
    if not isinstance(resource, dict):
        return True
    if "hasAssignmentDate" in resource or "has_assignment_date" in resource:
        return bool(resource.get("hasAssignmentDate", resource.get("has_assignment_date")))
    return True


def uses_dynamic_resource_assignment_condition(resource):
    if not isinstance(resource, dict):
        return False
    if "hasAssignmentCondition" in resource or "has_assignment_condition" in resource:
        return bool(resource.get("hasAssignmentCondition", resource.get("has_assignment_condition")))
    return False


def uses_dynamic_resource_assignment_notes(resource):
    if not isinstance(resource, dict):
        return False
    if "hasAssignmentNotes" in resource or "has_assignment_notes" in resource:
        return bool(resource.get("hasAssignmentNotes", resource.get("has_assignment_notes")))
    return False


def is_dynamic_resource_complete(resource):
    if not isinstance(resource, dict) or not resource.get("selected"):
        return False
    field_schema = normalize_resource_field_schema(resource.get("fieldSchema") or resource.get("field_schema") or [])
    field_values = resource.get("fields") or {}
    if field_schema:
        for field in field_schema:
            value = str(field_values.get(field["key"]) or "").strip()
            if field.get("required") and not value:
                return False
    elif not summarize_dynamic_resource(resource):
        return False
    if uses_dynamic_resource_assignment_date(resource) and not str(resource.get("assignedAt") or "").strip():
        return False
    return True


def is_dynamic_resource_payload(resource):
    if not isinstance(resource, dict):
        return False
    marker_keys = {
        "fieldSchema",
        "field_schema",
        "fields",
        "issuerService",
        "issuer_service",
        "triggerKey",
        "trigger_key",
        "displayOrder",
        "display_order",
        "requiresReturn",
        "requires_return",
    }
    return any(key in resource for key in marker_keys)


def is_restitution_eligible_material_details(details):
    if not isinstance(details, dict):
        return True
    if (details.get("category") or "") != "materiel":
        return False
    if "requiresReturn" in details or "requires_return" in details:
        return bool(details.get("requiresReturn", details.get("requires_return")))
    return True


def collect_resource_entries(payload):
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    additional = payload.get("resources", {}).get("additional", [])

    entries = []

    def add_entry(item_key, category, service, label, details, include_if_empty=False, assignment_source=None):
        clean_details = [str(detail).strip() for detail in details if str(detail or "").strip()]
        if not clean_details and not include_if_empty:
            return
        assignment_summary = " - ".join(describe_assignment_condition(assignment_source))
        entries.append(
            {
                "itemKey": item_key,
                "category": category or "materiel",
                "service": service or "Non défini",
                "label": label,
                "details": " - ".join(clean_details) if clean_details else "-",
                "assignedAt": assignment_source.get("assignedAt") if isinstance(assignment_source, dict) else "",
                "assignmentCondition": assignment_source.get("conditionAttribution") if isinstance(assignment_source, dict) else "",
                "assignmentConditionLabel": format_assignment_condition_label(assignment_source.get("conditionAttribution")) if isinstance(assignment_source, dict) and assignment_source.get("conditionAttribution") else "",
                "assignmentConditionNotes": assignment_source.get("conditionNotes") if isinstance(assignment_source, dict) else "",
                "assignmentSummary": assignment_summary,
            }
        )

    if materiel.get("ordinateur", {}).get("selected"):
        item = materiel["ordinateur"]
        add_entry("ordinateur", "materiel", "DSI", "Ordinateur", [item.get("nomPoste"), item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if materiel.get("ecran", {}).get("selected"):
        item = materiel["ecran"]
        add_entry("ecran", "materiel", "DSI", "Écran", [item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if materiel.get("telephone", {}).get("selected"):
        item = materiel["telephone"]
        add_entry("telephone", "materiel", "DSI", "Téléphone", [item.get("nomTelephone"), item.get("marque"), item.get("modele"), item.get("imei")], assignment_source=item)
    if materiel.get("tablette", {}).get("selected"):
        item = materiel["tablette"]
        add_entry("tablette", "materiel", "DSI", "Tablette", [item.get("nomTablette"), item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if immateriel.get("email", {}).get("selected"):
        add_entry("email", "immateriel", "DSI", "Messagerie", [immateriel["email"].get("adresse")], assignment_source=immateriel["email"])
    if immateriel.get("vpn", {}).get("selected"):
        add_entry("vpn", "immateriel", "DSI", "VPN", [], include_if_empty=True, assignment_source=immateriel["vpn"])
    if materiel.get("badge", {}).get("selected"):
        add_entry("badge", "materiel", "Bâtiment", "Badge d'accès", [materiel["badge"].get("numero")], assignment_source=materiel["badge"])
    if materiel.get("cles", {}).get("selected"):
        add_entry("cles", "materiel", "Bâtiment", "Clé(s)", materiel["cles"].get("values") or [], assignment_source=materiel["cles"])
    if materiel.get("veste", {}).get("selected"):
        add_entry("veste", "materiel", "Bâtiment", "Veste", [], include_if_empty=True, assignment_source=materiel["veste"])
    if materiel.get("chaussuresSecurite", {}).get("selected"):
        add_entry("chaussuresSecurite", "materiel", "Bâtiment", "Chaussures de sécurité", [], include_if_empty=True, assignment_source=materiel["chaussuresSecurite"])
    if immateriel.get("zoneAlarme", {}).get("selected"):
        add_entry("zoneAlarme", "immateriel", "Bâtiment", "Zone alarme", immateriel["zoneAlarme"].get("zones") or [], assignment_source=immateriel["zoneAlarme"])
    if materiel.get("vehicule", {}).get("selected"):
        item = materiel["vehicule"]
        add_entry("vehicule", "materiel", "Autres services", "Véhicule", [item.get("marque"), item.get("modele"), item.get("immatriculation")], assignment_source=item)
    if materiel.get("autre", {}).get("selected"):
        add_entry("autre", "materiel", "Autres services", "Autre ressource", [materiel["autre"].get("description")], assignment_source=materiel["autre"])

    for resource in additional:
        if not resource.get("selected"):
            continue
        add_entry(
            resource.get("code") or resource.get("id") or generate_id("resource"),
            resource.get("category") or "materiel",
            resource.get("issuerService") or resource.get("issuer_service") or "Autres services",
            resource.get("label") or "Ressource complémentaire",
            [summarize_dynamic_resource(resource)],
            assignment_source=resource,
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


def build_pdf_bytes(title, payload):
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]
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
            "Validation et conformité",
            [
                f"Information RGPD portée à connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
                f"Signature du bénéficiaire : {'Oui' if validation.get('signatureDataUrl') else 'Non'}",
                f"Date de signature : {signature_datetime}",
            ],
        )
    )

    if not signature_export_allowed:
        sections[-1] = (
            sections[-1][0],
            [
                f"Information RGPD portée à connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
                "Signature du bénéficiaire : Masquée",
                "Mention : la signature est réservée aux personnes autorisées.",
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

    a_quai_logo_image = load_a_quai_pdf_logo_image()
    a_quai_logo_image_id = None
    if a_quai_logo_image:
        a_quai_logo_stream = a_quai_logo_image["data"]
        a_quai_logo_image_id = add_object(
            f"<< /Type /XObject /Subtype /Image /Width {a_quai_logo_image['width']} /Height {a_quai_logo_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(a_quai_logo_stream)} >>\n"
            f"stream\n{a_quai_logo_stream.decode('latin-1')}\nendstream"
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
        draw_text(current_page, margin + 14, current_y - 18, "Signature du bénéficiaire", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "Signature recueillie lors de la validation du dossier.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        current_page.append(
            f"q {draw_width} 0 0 {draw_height} {margin + 14} {box_bottom + 18} cm /SIG1 Do Q"
        )
        current_y = box_bottom - 16

    if signature_present and not signature_export_allowed:
        reservation_lines = wrap_line(f"Réserve : {restitution.get('signataireComment') or '-'}", width=72) if restitution.get("signataireDecision") == "with_reservation" else []
        section_height = 92 + (len(reservation_lines) * 14)
        ensure_space(section_height)
        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.985, 0.99, 0.995), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, "Signature du bénéficiaire", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, "Signature masquée dans cet export.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "La signature est réservée aux personnes autorisées.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 70, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        text_y = current_y - 86
        for line in reservation_lines:
            draw_text(current_page, margin + 14, text_y, normalize_pdf_text(line), font="F1", size=10, color=(0.45, 0.17, 0.12))
            text_y -= 14
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
        if a_quai_logo_image_id:
            a_quai_ratio = min(88 / a_quai_logo_image["width"], 52 / a_quai_logo_image["height"])
            a_quai_width = round(a_quai_logo_image["width"] * a_quai_ratio, 2)
            a_quai_height = round(a_quai_logo_image["height"] * a_quai_ratio, 2)
            commands.append(
                f"q {a_quai_width} 0 0 {a_quai_height} {margin} {page_height - 76} cm /AQLOGO Do Q"
            )
        elif logo_image_id:
            logo_ratio = min(88 / logo_image["width"], 52 / logo_image["height"])
            logo_width = round(logo_image["width"] * logo_ratio, 2)
            logo_height = round(logo_image["height"] * logo_ratio, 2)
            commands.append(f"q {logo_width} 0 0 {logo_height} {margin} {page_height - 76} cm /LOGO Do Q")
        draw_text(commands, margin + 100, page_height - 48, org_name, font="F2", size=18, color=(1, 1, 1))
        draw_text(commands, margin + 100, page_height - 68, "A quai", font="F2", size=13, color=(0.92, 0.96, 0.99))
        draw_text(commands, page_width - 190, page_height - 48, "Document interne", font="F2", size=10.5, color=(1, 1, 1))
        draw_text(commands, page_width - 190, page_height - 66, normalize_pdf_text(generated_at), font="F1", size=9.5, color=(0.92, 0.96, 0.99))

        draw_text(commands, margin, page_height - 118, normalize_pdf_text(title), font="F2", size=15, color=(0.07, 0.18, 0.26))
        draw_text(commands, margin, page_height - 136, "Document de remise et de suivi des ressources attribuées", font="F1", size=10.5, color=(0.35, 0.43, 0.50))

        commands.extend(page_commands)

        draw_rect(commands, margin, 34, content_width, 0.5, stroke=(0.80, 0.86, 0.90), line_width=0.8)
        draw_text(commands, margin, 20, "A quai - document exploitable RH / DGS", font="F1", size=8.5, color=(0.38, 0.45, 0.52))
        if logo_image_id:
            footer_logo_ratio = min(54 / logo_image["width"], 18 / logo_image["height"])
            footer_logo_width = round(logo_image["width"] * footer_logo_ratio, 2)
            footer_logo_height = round(logo_image["height"] * footer_logo_ratio, 2)
            commands.append(
                f"q {footer_logo_width} 0 0 {footer_logo_height} {page_width - 160} {13} cm /LOGO Do Q"
            )
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
        if a_quai_logo_image_id:
            xobjects.append(f"/AQLOGO {a_quai_logo_image_id} 0 R")
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
        f"<< /Title ({pdf_escape(title)}) /Producer (A quai) /CreationDate (D:{datetime.now().strftime('%Y%m%d%H%M%S')}) >>"
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
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]
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

    sections = [
        (
            "Identification de la restitution",
            [
                f"État du dossier : {format_status_label(workflow.get('status') or 'draft')}",
                f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
                f"Date de prise de fonction : {format_export_datetime(payload.get('meta', {}).get('startAt'))}",
                f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
                f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
                f"Motif : {restitution.get('reason') or '-'}",
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

    returned_resource_lines = []
    restitution_lines = []
    for item in material_items:
        item_key = item["itemKey"]
        state = (restitution.get("items") or {}).get(item_key, {})
        state_label = format_restitution_state_label(state.get("state") or state.get("condition"))
        note = state.get("notes") or "-"
        if (state.get("state") or state.get("condition")) in {"conforme", "degrade", "returned", "returned_damaged"}:
            returned_resource_lines.append(
                f"{item['label']} ({item.get('details') or '-'})"
                f"{' / ' + item.get('assignmentSummary') if item.get('assignmentSummary') else ''}"
            )
        restitution_lines.append(
            f"{item['label']} ({item.get('details') or '-'}) : {state_label} / {note}"
            f"{' / ' + item.get('assignmentSummary') if item.get('assignmentSummary') else ''}"
        )
    if returned_resource_lines:
        sections.append(("Ressources restituées", returned_resource_lines))
    if not restitution_lines:
        restitution_lines.append("Aucun matériel n'a encore été renseigné dans la restitution.")
    sections.append(("État des matériels restitués", restitution_lines))
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

    if not signature_export_allowed:
        sections[-1] = (
            sections[-1][0],
            [
                "Statut de signature : Masquée",
                "Mention : la signature est réservée aux personnes autorisées.",
                "Motif si la signature n'a pas été recueillie : Information réservée.",
                f"Décision du signataire : {decision_label}",
                f"Réserve / réclamation du signataire : {restitution.get('signataireComment') or '-'}",
                f"Observations générales : {restitution.get('notes') or '-'}",
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

    a_quai_logo_image = load_a_quai_pdf_logo_image()
    a_quai_logo_image_id = None
    if a_quai_logo_image:
        a_quai_logo_stream = a_quai_logo_image["data"]
        a_quai_logo_image_id = add_object(
            f"<< /Type /XObject /Subtype /Image /Width {a_quai_logo_image['width']} /Height {a_quai_logo_image['height']} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(a_quai_logo_stream)} >>\n"
            f"stream\n{a_quai_logo_stream.decode('latin-1')}\nendstream"
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
        reservation_lines = wrap_line(f"Réserve : {restitution.get('signataireComment') or '-'}", width=72) if restitution.get("signataireDecision") == "with_reservation" else []
        section_height = 90 + draw_height + (len(reservation_lines) * 14)
        ensure_space(section_height)
        box_bottom = current_y - section_height
        draw_rect(current_page, margin, box_bottom, content_width, section_height, fill=(0.985, 0.99, 0.995), stroke=(0.80, 0.86, 0.90))
        draw_text(current_page, margin + 14, current_y - 18, "Signature de restitution", font="F2", size=12, color=(0.05, 0.26, 0.40))
        draw_text(current_page, margin + 14, current_y - 38, f"Date de signature : {normalize_pdf_text(signature_datetime)}", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(
            current_page,
            margin + 14,
            current_y - 54,
            "Signature recueillie avec réserve." if restitution.get("signataireDecision") == "with_reservation" else "Signature recueillie lors de la restitution.",
            font="F1",
            size=10,
            color=(0.28, 0.36, 0.44),
        )
        text_y = current_y - 70
        for line in reservation_lines:
            draw_text(current_page, margin + 14, text_y, normalize_pdf_text(line), font="F1", size=10, color=(0.45, 0.17, 0.12))
            text_y -= 14
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
        draw_text(current_page, margin + 14, current_y - 38, "Signature masquée dans cet export.", font="F1", size=10, color=(0.28, 0.36, 0.44))
        draw_text(current_page, margin + 14, current_y - 54, "La signature est réservée aux personnes autorisées.", font="F1", size=10, color=(0.28, 0.36, 0.44))
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
        if a_quai_logo_image_id:
            a_quai_ratio = min(88 / a_quai_logo_image["width"], 52 / a_quai_logo_image["height"])
            a_quai_width = round(a_quai_logo_image["width"] * a_quai_ratio, 2)
            a_quai_height = round(a_quai_logo_image["height"] * a_quai_ratio, 2)
            commands.append(
                f"q {a_quai_width} 0 0 {a_quai_height} {margin} {page_height - 76} cm /AQLOGO Do Q"
            )
        elif logo_image_id:
            logo_ratio = min(88 / logo_image["width"], 52 / logo_image["height"])
            logo_width = round(logo_image["width"] * logo_ratio, 2)
            logo_height = round(logo_image["height"] * logo_ratio, 2)
            commands.append(f"q {logo_width} 0 0 {logo_height} {margin} {page_height - 76} cm /LOGO Do Q")
        draw_text(commands, margin + 100, page_height - 48, org_name, font="F2", size=18, color=(1, 1, 1))
        draw_text(commands, margin + 100, page_height - 68, "A quai", font="F2", size=13, color=(0.92, 0.96, 0.99))
        draw_text(commands, page_width - 190, page_height - 48, "Document interne", font="F2", size=10.5, color=(1, 1, 1))
        draw_text(commands, page_width - 190, page_height - 66, normalize_pdf_text(generated_at), font="F1", size=9.5, color=(0.92, 0.96, 0.99))

        draw_text(commands, margin, page_height - 118, normalize_pdf_text(title), font="F2", size=15, color=(0.07, 0.18, 0.26))
        draw_text(commands, margin, page_height - 136, "Bon de restitution et de suivi des ressources récupérées", font="F1", size=10.5, color=(0.35, 0.43, 0.50))

        commands.extend(page_commands)

        draw_rect(commands, margin, 34, content_width, 0.5, stroke=(0.80, 0.86, 0.90), line_width=0.8)
        draw_text(commands, margin, 20, "A quai - document exploitable RH / DGS", font="F1", size=8.5, color=(0.38, 0.45, 0.52))
        if logo_image_id:
            footer_logo_ratio = min(54 / logo_image["width"], 18 / logo_image["height"])
            footer_logo_width = round(logo_image["width"] * footer_logo_ratio, 2)
            footer_logo_height = round(logo_image["height"] * footer_logo_ratio, 2)
            commands.append(
                f"q {footer_logo_width} 0 0 {footer_logo_height} {page_width - 160} {13} cm /LOGO Do Q"
            )
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
        if a_quai_logo_image_id:
            xobjects.append(f"/AQLOGO {a_quai_logo_image_id} 0 R")
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
        f"<< /Title ({pdf_escape(title)}) /Producer (A quai) /CreationDate (D:{datetime.now().strftime('%Y%m%d%H%M%S')}) >>"
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


def describe_assignment_condition(item):
    if not isinstance(item, dict):
        return []
    parts = []
    is_immaterial = item.get("category") == "immateriel"
    show_assignment_date = True
    if is_dynamic_resource_payload(item):
        show_assignment_date = uses_dynamic_resource_assignment_date(item)
    if show_assignment_date and item.get("assignedAt"):
        parts.append(f"Date d'attribution : {format_export_datetime(item.get('assignedAt'))}")
    show_assignment_condition = not is_immaterial
    if is_dynamic_resource_payload(item):
        show_assignment_condition = uses_dynamic_resource_assignment_condition(item)
    if show_assignment_condition and item.get("conditionAttribution"):
        parts.append(f"État à la remise : {format_assignment_condition_label(item.get('conditionAttribution'))}")
    notes = str(item.get("conditionNotes") or "").strip()
    show_assignment_notes = not is_immaterial
    if is_dynamic_resource_payload(item):
        show_assignment_notes = uses_dynamic_resource_assignment_notes(item)
    if notes and show_assignment_notes:
        parts.append(f"Observation de remise : {notes}")
    return parts


def summarize_assignment_progress(payload):
    requested_items = extract_items(payload)
    total_requested = len(requested_items)
    completed = 0
    for item in requested_items:
        try:
            details = json.loads(item.get("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        if isinstance(details, dict) and (
            is_dynamic_resource_complete(details)
            if is_dynamic_resource_payload(details)
            else bool(details.get("assignedAt"))
        ):
            completed += 1
    start_at = (
        payload.get("meta", {}).get("startAt")
        or payload.get("beneficiaire", {}).get("datePriseFonction")
        or ""
    )
    if total_requested == 0:
        return {
            "startAt": start_at,
            "completed": 0,
            "total": 0,
            "ratio": 0,
            "timingStatus": "neutral",
            "timingLabel": "À planifier",
        }

    if completed >= total_requested:
        return {
            "startAt": start_at,
            "completed": completed,
            "total": total_requested,
            "ratio": 1,
            "timingStatus": "ok",
            "timingLabel": "Prêt",
        }

    if not start_at:
        return {
            "startAt": "",
            "completed": completed,
            "total": total_requested,
            "ratio": round(completed / total_requested, 4),
            "timingStatus": "neutral",
            "timingLabel": "À planifier",
        }

    try:
        if len(start_at) == 10:
            start_date = datetime.strptime(start_at, "%Y-%m-%d").date()
        else:
            start_date = datetime.fromisoformat(start_at.replace("Z", "+00:00")).date()
        days_until_start = (start_date - datetime.now().date()).days
    except ValueError:
        days_until_start = None

    if days_until_start is None:
        timing_status = "neutral"
        timing_label = "À planifier"
    elif days_until_start < 0:
        timing_status = "late"
        timing_label = "En retard"
    elif days_until_start <= 3:
        timing_status = "warning"
        timing_label = "En danger"
    else:
        timing_status = "ok"
        timing_label = "Dans les temps"

    return {
        "startAt": start_at,
        "completed": completed,
        "total": total_requested,
        "ratio": round(completed / total_requested, 4),
        "timingStatus": timing_status,
        "timingLabel": timing_label,
    }


def extract_items(payload):
    # Transforme le payload metier en lignes d'equipements persistables.
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    restitution = payload.get("restitution", {})
    item_states = restitution.get("items", {})

    items = [
        ("ordinateur", "materiel", "Ordinateur", materiel.get("ordinateur", {})),
        ("ecran", "materiel", "Écran", materiel.get("ecran", {})),
        ("telephone", "materiel", "Téléphone", materiel.get("telephone", {})),
        ("tablette", "materiel", "Tablette", materiel.get("tablette", {})),
        ("vehicule", "materiel", "Véhicule", materiel.get("vehicule", {})),
        ("badge", "materiel", "Badge d'accès", materiel.get("badge", {})),
        ("cles", "materiel", "Clé(s)", materiel.get("cles", {})),
        ("veste", "materiel", "Veste", materiel.get("veste", {})),
        ("chaussuresSecurite", "materiel", "Chaussures de sécurité", materiel.get("chaussuresSecurite", {})),
        ("autre", "materiel", "Autre matériel", materiel.get("autre", {})),
        ("vpn", "immateriel", "VPN", immateriel.get("vpn", {})),
        ("email", "immateriel", "Email", immateriel.get("email", {})),
        ("zoneAlarme", "immateriel", "Zone alarme", immateriel.get("zoneAlarme", {})),
    ]

    for resource in payload.get("resources", {}).get("additional", []):
        items.append((
            resource.get("code") or resource.get("id") or generate_id("resource"),
            resource.get("category") or "materiel",
            resource.get("label") or "Ressource complémentaire",
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

def collect_resource_validation_errors(payload):
    errors = []
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    resources = payload.get("resources", {}).get("additional", [])

    fixed_rules = [
        ("ordinateur", materiel.get("ordinateur", {}), [
            ("Marque ordinateur", "marque"),
            ("Modèle ordinateur", "modele"),
            ("Numéro de série ordinateur", "numeroSerie"),
        ]),
        ("ecran", materiel.get("ecran", {}), [
            ("Marque écran", "marque"),
            ("Modèle écran", "modele"),
            ("Numéro de série écran", "numeroSerie"),
        ]),
        ("telephone", materiel.get("telephone", {}), [
            ("Marque téléphone", "marque"),
            ("Modèle téléphone", "modele"),
            ("IMEI", "imei"),
        ]),
        ("tablette", materiel.get("tablette", {}), [
            ("Marque tablette", "marque"),
            ("Modèle tablette", "modele"),
            ("Numéro de série tablette", "numeroSerie"),
        ]),
        ("vehicule", materiel.get("vehicule", {}), [
            ("Marque véhicule", "marque"),
            ("Modèle véhicule", "modele"),
            ("Immatriculation", "immatriculation"),
        ]),
        ("badge", materiel.get("badge", {}), [
            ("Numéro de badge", "numero"),
        ]),
        ("autre", materiel.get("autre", {}), [
            ("Description autre matériel", "description"),
        ]),
        ("email", immateriel.get("email", {}), [
            ("Adresse email", "adresse"),
        ]),
    ]

    for _, resource, rules in fixed_rules:
        if not resource.get("selected"):
            continue
        for label, key in rules:
            value = str(resource.get(key) or "").strip()
            if not value:
                errors.append(f"{label} manquant")
                continue

    if materiel.get("cles", {}).get("selected") and not [value for value in materiel.get("cles", {}).get("values", []) if str(value).strip()]:
        errors.append("Au moins une clé doit être renseignée")

    if immateriel.get("zoneAlarme", {}).get("selected") and not [value for value in immateriel.get("zoneAlarme", {}).get("zones", []) if str(value).strip()]:
        errors.append("Au moins une zone alarme doit être renseignée")

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
            errors.append(f"{resource.get('label') or 'Ressource complémentaire'} incomplète")
        if uses_dynamic_resource_assignment_date(resource) and not str(resource.get("assignedAt") or "").strip():
            errors.append(f"{resource.get('label') or 'Ressource'} : date d'attribution manquante")

    return errors


def compute_effective_workflow_status(payload):
    # Recalcule le statut metier a partir de l'etat reel du dossier.
    # Cela permet aussi de corriger a l'affichage les anciennes fiches
    # enregistrees avec "active" alors que toutes les attributions
    # n'etaient pas encore datees.
    workflow = payload.get("workflow", {})
    current_status = workflow.get("status") or "draft"
    restitution = payload.get("restitution", {})

    if current_status == "cancelled":
        return current_status
    if current_status in {"returned", "partial_return"} or (
        current_status == "awaiting_signature"
        and (
            restitution.get("items")
            or restitution.get("returnedAt")
            or restitution.get("signatureStatus") == "deferred"
        )
    ):
        return derive_restitution_workflow_status(
            restitution.get("items", {}),
            restitution.get("signatureStatus") or "",
            restitution.get("signatureDataUrl") or "",
        )

    validation = payload.get("validation", {})
    has_signature = bool(validation.get("signatureDataUrl"))
    rgpd_accepted = bool(validation.get("rgpdAccepted"))
    resource_errors = payload.get("meta", {}).get("resourceValidationErrors")
    if not isinstance(resource_errors, list):
        resource_errors = collect_resource_validation_errors(payload)

    progress = summarize_assignment_progress(payload)
    if not has_signature and not resource_errors and progress["total"] > 0 and progress["completed"] >= progress["total"]:
        return "awaiting_signature"
    if not has_signature or not rgpd_accepted:
        return "draft"
    if resource_errors or progress["completed"] < progress["total"]:
        return "partial_assignment"

    if current_status == "active":
        return "active"

    return "partial_assignment"


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
        if remote_url:
            return redirect(remote_url, code=302)

    response = send_from_directory(FRONTEND_ASSETS_DIR, "app-icon.svg")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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
    pdf_bytes = get_or_build_cached_pdf(form_id, "attribution", title, form_data["data"], build_pdf_bytes)
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
    pdf_bytes = get_or_build_cached_pdf(form_id, "restitution", title, form_data["data"], build_restitution_pdf_bytes)
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
            pdf_bytes = get_or_build_cached_pdf(str(form_id), "attribution", title, form_data["data"], build_pdf_bytes)
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
            pdf_bytes = get_or_build_cached_pdf(str(form_id), "restitution", title, form_data["data"], build_restitution_pdf_bytes)
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

    os.makedirs(CUSTOM_BRANDING_DIR, exist_ok=True)
    file_name = f"brand_logo_{uuid.uuid4().hex}{extension}"
    absolute_path = os.path.join(CUSTOM_BRANDING_DIR, file_name)
    file.save(absolute_path)
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
