from flask import Flask, jsonify, request, session
from flask.sessions import SecureCookieSessionInterface
import os
import secrets
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_app_secret_key, AUTH_CONFIG_PATH
from database import get_db, get_users_db, ensure_column
from models.dossier import migrate_forms_to_dossiers
from utils import utc_now
import json
from pathlib import Path
from models.settings import seed_app_settings
from models.catalog import seed_reference_catalogs, seed_service_catalog, migrate_suggest_flags, migrate_builtin_resource_schemas, migrate_builtin_resource_flags, migrate_missing_builtin_resources, migrate_cartes_visite_quantite, migrate_builtin_issuer_service, migrate_builtin_display_order, migrate_telephone_imei_field
from models.forms import migrate_field_suggestions_from_history
import importlib
import pkgutil
import routes as _routes_pkg


class _AutoSecureSessionInterface(SecureCookieSessionInterface):
    """Cookie Secure = True si la requête arrive en HTTPS, False sinon.
    Fonctionne automatiquement en dev (HTTP) et en prod (HTTPS via proxy)."""
    def get_cookie_secure(self, app):
        try:
            return request.is_secure
        except RuntimeError:
            return False


app = Flask(__name__, static_folder=None)
app.secret_key = get_app_secret_key()
app.session_interface = _AutoSecureSessionInterface()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

for _importer, _modname, _ispkg in pkgutil.iter_modules(_routes_pkg.__path__):
    _mod = importlib.import_module(f"routes.{_modname}")
    if hasattr(_mod, "bp"):
        app.register_blueprint(_mod.bp)
app.config["SESSION_COOKIE_NAME"] = "publier_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.before_request
def validate_csrf():
    """Valide le token CSRF sur toutes les mutations JSON des endpoints /api/
    pour lesquels l'utilisateur est authentifié."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if not request.path.startswith("/api/"):
        return
    # Les endpoints publics de signature ne nécessitent pas d'auth ni de CSRF
    if request.path.startswith("/api/signature/") or request.path.startswith("/api/restitution-signature/"):
        return
    # Les endpoints d'authentification (vérification de session) ne nécessitent pas de CSRF
    if request.path.startswith("/api/auth/"):
        return
    # Si pas de session utilisateur, l'endpoint sera rejeté par @login_required — pas besoin de CSRF
    if not session.get("user"):
        return
    token = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    if not expected or not token or not secrets.compare_digest(token, expected):
        return jsonify({"error": "csrf_invalid"}), 403


@app.after_request
def disable_frontend_cache(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    # CSP : self uniquement + CDN Bootstrap/CookieConsent autorisés explicitement
    # unsafe-inline nécessaire pour les styles Bootstrap injectés dynamiquement
    response.headers.setdefault(
        "Content-Security-Policy",
        (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'self'"
        ),
    )

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

def init_users_db():
    with get_users_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                service TEXT,
                db_manage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS groups (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT,
                permissions_json TEXT NOT NULL DEFAULT '[]',
                data_scope TEXT NOT NULL DEFAULT 'full',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_groups (
                username TEXT NOT NULL,
                group_key TEXT NOT NULL,
                PRIMARY KEY (username, group_key),
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY(group_key) REFERENCES groups(key) ON DELETE RESTRICT
            );
            """
        )
        migrate_users_from_json(connection)


def seed_default_groups(connection):
    """Crée les groupes par défaut. Crée les groupes manquants, met à jour les existants."""
    now = utc_now()
    default_groups = [
        ("admin", "Administrateur", "Accès complet à la gestion des utilisateurs et configurations",
         ["users.manage", "forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.delete", "forms.view_all", "forms.export", "forms.restitution", "db.manage", "unc.view_all", "pools.manage"], "full"),
        ("user", "Utilisateur", "Accès aux formulaires et restitutions",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.view_all"], "full"),
        ("administration", "Administration", "Complet total et gestion des utilisateurs",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage", "users.manage"], "full"),
        ("direction", "Direction", "Accès complet aux dossiers avec visibilité sur les chemins réseau UNC (idéal pour DG, DRH et encadrement supérieur)",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage", "unc.view_all"], "full"),
        ("gestion", "Gestion", "Gestion avancée avec restitution et export",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage"], "full"),
        ("lecture", "Lecture", "Consultation seule, sans possible de saisie",
         ["forms.read_list", "forms.read_detail", "forms.export", "forms.view_all"], "full"),
        ("redaction", "Rédaction", "Création et modification des fiches en cours",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.view_all"], "full"),
    ]
    for key, label, description, permissions, data_scope in default_groups:
        existing = connection.execute("SELECT permissions_json FROM groups WHERE key = ?", (key,)).fetchone()
        if existing:
            # Groupe existe déjà : mettre à jour label/description et permissions
            connection.execute(
                "UPDATE groups SET label = ?, description = ?, permissions_json = ?, data_scope = ?, updated_at = ? WHERE key = ?",
                (label, description, json.dumps(permissions), data_scope, now, key)
            )
        else:
            # Groupe n'existe pas : créer avec les permissions par défaut
            connection.execute(
                "INSERT INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (key, label, description, json.dumps(permissions), data_scope, now, now)
            )
    connection.commit()
    # Créer l'utilisateur admin par défaut s'il n'existe pas
    seed_default_admin(connection)


def seed_default_admin(connection):
    """Crée l'utilisateur admin/admin par défaut s'il n'existe pas."""
    import bcrypt
    user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count > 0:
        return
    now = utc_now()
    # Hash du mot de passe "admin"
    password_hash = bcrypt.hashpw("admin".encode(), bcrypt.gensalt()).decode()
    connection.execute(
        "INSERT INTO users (username, password_hash, is_active, status, service, db_manage, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("admin", password_hash, 1, "active", "", 0, now, now)
    )
    connection.execute(
        "INSERT OR IGNORE INTO user_groups (username, group_key) VALUES (?,?)",
        ("admin", "admin")
    )
    connection.commit()


def migrate_missing_groups(connection):
    """Ajoute les groupes manquants même si la base de données existe déjà."""
    now = utc_now()
    default_groups = [
        ("admin", "Administrateur", "Accès complet à la gestion des utilisateurs et configurations",
         ["users.manage", "forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.delete", "forms.view_all", "forms.export", "forms.restitution", "db.manage", "unc.view_all", "pools.manage"], "full"),
        ("user", "Utilisateur", "Accès aux formulaires et restitutions",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.view_all"], "full"),
        ("administration", "Administration", "Complet total et gestion des utilisateurs",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage", "users.manage"], "full"),
        ("direction", "Direction", "Accès complet aux dossiers avec visibilité sur les chemins réseau UNC (idéal pour DG, DRH et encadrement supérieur)",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage", "unc.view_all"], "full"),
        ("gestion", "Gestion", "Gestion avancée avec restitution et export",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage"], "full"),
        ("lecture", "Lecture", "Consultation seule, sans possible de saisie",
         ["forms.read_list", "forms.read_detail", "forms.export", "forms.view_all"], "full"),
        ("redaction", "Rédaction", "Création et modification des fiches en cours",
         ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.view_all"], "full"),
    ]
    for key, label, description, permissions, data_scope in default_groups:
        existing = connection.execute("SELECT permissions_json FROM groups WHERE key = ?", (key,)).fetchone()
        if existing:
            # Groupe existe : mettre à jour les permissions
            connection.execute(
                "UPDATE groups SET label = ?, description = ?, permissions_json = ?, data_scope = ?, updated_at = ? WHERE key = ?",
                (label, description, json.dumps(permissions), data_scope, now, key)
            )
        else:
            # Groupe n'existe pas : créer
            connection.execute(
                "INSERT INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (key, label, description, json.dumps(permissions), data_scope, now, now)
            )
    connection.commit()


def migrate_users_from_json(connection):
    count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        migrate_missing_groups(connection)
        return
    json_path = Path(AUTH_CONFIG_PATH)
    if not json_path.exists():
        seed_default_groups(connection)
        return
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        seed_default_groups(connection)
        return
    now = utc_now()
    for key, group in config.get("groups", {}).items():
        connection.execute(
            "INSERT OR IGNORE INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (key, group.get("label",""), group.get("description",""), json.dumps(group.get("permissions",[])), group.get("data_scope","full"), now, now)
        )
    for user in config.get("users", []):
        connection.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, is_active, status, service, db_manage, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["username"], user["password_hash"], int(user.get("is_active", True)), user.get("status","active"), user.get("service"), int(user.get("db_manage", False)), now, now)
        )
        for group_key in user.get("groups", []):
            connection.execute(
                "INSERT OR IGNORE INTO user_groups (username, group_key) VALUES (?,?)",
                (user["username"], group_key)
            )
    connection.commit()
    try:
        json_path.rename(json_path.parent / f"{json_path.name}.migrated")
    except Exception:
        pass


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

            CREATE TABLE IF NOT EXISTS field_suggestions (
                id TEXT PRIMARY KEY,
                field_key TEXT NOT NULL,
                value TEXT NOT NULL,
                service TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(field_key, value, service)
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

            CREATE INDEX IF NOT EXISTS idx_dotation_forms_updated_at
                ON dotation_forms(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_dotation_forms_status
                ON dotation_forms(status);

            CREATE TABLE IF NOT EXISTS shared_pools (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                notes TEXT,
                owner_form_id TEXT,
                resource_catalog_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shared_pool_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                label TEXT NOT NULL,
                serial_number TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pool_id) REFERENCES shared_pools(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shared_pool_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id TEXT NOT NULL,
                form_id TEXT,
                beneficiary_name TEXT,
                added_at TEXT NOT NULL,
                removed_at TEXT,
                FOREIGN KEY(pool_id) REFERENCES shared_pools(id) ON DELETE CASCADE,
                FOREIGN KEY(form_id) REFERENCES dotation_forms(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS signature_views (
                id TEXT PRIMARY KEY,
                form_id TEXT NOT NULL,
                username TEXT,
                viewed_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY(form_id) REFERENCES dotation_forms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS dotation_item_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                form_id TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                assigned_at TEXT,
                returned_at TEXT,
                returned_status TEXT,
                notes TEXT,
                FOREIGN KEY(form_id) REFERENCES dotation_forms(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_dotation_item_selections_form
                ON dotation_item_selections(form_id, returned_at);
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
        ensure_column(connection, "app_logs", "target_label", "target_label TEXT")
        ensure_column(connection, "shared_pools", "owner_form_id", "owner_form_id TEXT")
        ensure_column(connection, "shared_pools", "resource_catalog_id", "resource_catalog_id TEXT")
        ensure_column(connection, "shared_pool_members", "removed_at", "removed_at TEXT")
        ensure_column(connection, "dotation_forms", "source_form_id", "source_form_id TEXT")
        ensure_column(connection, "dotation_items", "resource_type", "resource_type TEXT")
        ensure_column(connection, "dotation_items", "serial_number", "serial_number TEXT")
        ensure_column(connection, "resource_catalog", "is_pool_resource", "is_pool_resource INTEGER NOT NULL DEFAULT 0")
        seed_reference_catalogs(connection)
        seed_service_catalog(connection)
        seed_app_settings(connection)
        migrate_forms_to_dossiers(connection)
        migrate_suggest_flags(connection)
        migrate_builtin_resource_schemas(connection)
        migrate_builtin_resource_flags(connection)
        migrate_builtin_issuer_service(connection)
        migrate_builtin_display_order(connection)
        migrate_telephone_imei_field(connection)
        migrate_missing_builtin_resources(connection)
        migrate_cartes_visite_quantite(connection)
        migrate_field_suggestions_from_history(connection)
        # Migration auto depuis users.json vers users.db (voir init_users_db)






init_db()
init_users_db()


if __name__ == "__main__":
    init_db()
    init_users_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
