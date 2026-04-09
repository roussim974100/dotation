import json
import os
import re
import threading
import bcrypt
from datetime import datetime
from functools import wraps
from flask import has_request_context, jsonify, redirect, request, session

from config import BASE_DIR

# ---------------------------------------------------------------------------
# Fichier de configuration des utilisateurs
# ---------------------------------------------------------------------------

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
    "direction": {
        "label": "Direction",
        "description": "Acces complet aux dossiers avec visibilite sur les chemins reseau UNC. Ideal pour DGS, DRH et encadrement superieur.",
        "permissions": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "unc.view_all"],
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


# ---------------------------------------------------------------------------
# Rate limiting login : max 10 tentatives par IP sur une fenetre glissante de 10 minutes.
# ---------------------------------------------------------------------------

_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 600
_login_attempts: dict[str, list[float]] = {}
_login_attempts_lock = threading.Lock()


def _is_login_rate_limited(ip: str) -> bool:
    now = datetime.now().timestamp()
    with _login_attempts_lock:
        attempts = _login_attempts.get(ip, [])
        attempts = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            _login_attempts[ip] = attempts
            return True
        attempts.append(now)
        _login_attempts[ip] = attempts
        return False


# ---------------------------------------------------------------------------
# Rate limiting générique par IP + scope (endpoints API sensibles).
# ---------------------------------------------------------------------------

_API_RATE_STORES: dict[str, dict[str, list[float]]] = {}
_api_rate_lock = threading.Lock()


def _is_api_rate_limited(ip: str, scope: str, max_requests: int, window_seconds: int) -> bool:
    now = datetime.now().timestamp()
    with _api_rate_lock:
        store = _API_RATE_STORES.setdefault(scope, {})
        attempts = store.get(ip, [])
        attempts = [t for t in attempts if now - t < window_seconds]
        if len(attempts) >= max_requests:
            store[ip] = attempts
            return True
        attempts.append(now)
        store[ip] = attempts
        return False


def rate_limit(max_requests: int, window_seconds: int, scope: str = ""):
    """Décorateur : limite max_requests par IP sur window_seconds secondes.
    scope identifie le compteur (par défaut = nom de la fonction décorée)."""
    def decorator(view):
        _scope = scope or view.__name__

        @wraps(view)
        def wrapped_view(*args, **kwargs):
            ip = get_request_client_ip() or "unknown"
            if _is_api_rate_limited(ip, _scope, max_requests, window_seconds):
                return jsonify({"error": "rate_limit_exceeded"}), 429
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


# ---------------------------------------------------------------------------
# Helpers utilisateur
# ---------------------------------------------------------------------------

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
        "service": (user.get("service") or "") if user else "",
        "db_manage": bool(user.get("db_manage", False)) if user else False,
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
    if "*" in user["permissions"] or permission in user["permissions"]:
        return True
    # Flag individuel pour la gestion de base de données
    if permission == "db.manage" and user.get("db_manage"):
        return True
    return False


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


# ---------------------------------------------------------------------------
# Decorateurs d'acces
# ---------------------------------------------------------------------------

def login_required(view):
    # Middleware minimum: redirige les pages HTML vers /login
    # et renvoie un 401 JSON pour les appels API.
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication_required"}), 401
            from flask import current_app
            cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
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


# ---------------------------------------------------------------------------
# Extraction d'IP client
# ---------------------------------------------------------------------------

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
