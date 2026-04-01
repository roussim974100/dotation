from flask import Flask, jsonify, make_response, redirect, request, send_from_directory, session, has_request_context
import base64
import bcrypt
import io
import json
import os
import secrets
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
    slugify_filename,
    build_title, normalize_dossier_type, dossier_type_label,
    format_export_datetime, get_signature_datetime, get_restitution_signature_datetime,
    format_beneficiary_label, format_status_label, format_restitution_state_label,
    format_restitution_decision_label,
)
from database import (
    get_db, _KNOWN_TABLES, table_columns, ensure_column,
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
    DEFAULT_APP_SETTINGS,
    seed_app_settings, get_app_settings,
    build_public_settings_payload,
)
from models.workflow import (
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
    collect_resource_entries,
)
from pdf.attribution import build_pdf_bytes
from pdf.restitution import build_restitution_pdf_bytes
from models.catalog import seed_reference_catalogs, seed_service_catalog
from models.forms import (
    build_form_export_lines,
    persist_form, row_to_summary, get_form,
    build_signature_public_payload, build_restitution_signature_public_payload,
)
from models.audit import insert_deleted_item
from routes.admin import bp as admin_bp
from routes.pages import bp as pages_bp
from routes.forms import bp as forms_bp
from routes.signature import bp as signature_bp


app = Flask(__name__, static_folder=None)
app.secret_key = get_app_secret_key()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.register_blueprint(admin_bp)
app.register_blueprint(pages_bp)
app.register_blueprint(forms_bp)
app.register_blueprint(signature_bp)
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








init_db()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
