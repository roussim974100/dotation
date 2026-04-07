import bcrypt
import os
import secrets

from flask import Blueprint, jsonify, make_response, redirect, request, send_from_directory, session

from config import FRONTEND_DIR, FRONTEND_ASSETS_DIR, CITY_LOGO_URL, CITY_LOGO_PATH
from utils import utc_now
from database import get_db
from auth import (
    login_required, admin_required, has_permission,
    load_auth_config, save_auth_config,
    get_user_record, password_complexity_error, is_valid_username,
    get_request_client_ip, extract_first_forwarded_ip, check_user,
    current_user,
    _is_login_rate_limited,
)
from models.audit import insert_app_log, read_login_attempt_context
from models.settings import DEFAULT_APP_SETTINGS, get_app_settings, build_public_settings_payload
import re

bp = Blueprint("pages", __name__)


def build_login_forensic_details(username, auth_state):
    from auth import extract_first_forwarded_ip
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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
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
                    "Connexion reussie",
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
                "Echec de connexion",
                "user",
                username or "(vide)",
                build_login_forensic_details(username, auth_state),
                actor="anonymous",
            )
        return redirect(f"/login?error={auth_state}")

    return send_from_directory(FRONTEND_DIR, "login.html")


@bp.route("/signup", methods=["GET", "POST"])
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


@bp.route("/logout")
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
                {"ip": get_request_client_ip()},
                actor=username,
            )
    session.clear()
    return redirect("/login")


# ---------------------------------------------------------------------------
# Pages HTML
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@bp.route("/index.html")
@login_required
def index_page():
    return send_from_directory(FRONTEND_DIR, "index.html")


@bp.route("/historique-dossiers.html")
@login_required
def assignments_history_page():
    return send_from_directory(FRONTEND_DIR, "historique-dossiers.html")


@bp.route("/historique-restitutions.html")
@login_required
def restitutions_history_page():
    return send_from_directory(FRONTEND_DIR, "historique-restitutions.html")


@bp.route("/form.html")
@login_required
def form_page():
    return send_from_directory(FRONTEND_DIR, "form.html")


@bp.route("/restitution.html")
@login_required
def restitution_page():
    return send_from_directory(FRONTEND_DIR, "restitution.html")


@bp.route("/about.html")
@login_required
def about_page():
    return send_from_directory(FRONTEND_DIR, "about.html")


@bp.route("/contact.html")
@login_required
def contact_page():
    return send_from_directory(FRONTEND_DIR, "contact.html")


@bp.route("/help.html")
@login_required
def help_page():
    return send_from_directory(FRONTEND_DIR, "help.html")


@bp.route("/signature/<token>")
def signature_page(token):
    response = make_response(send_from_directory(FRONTEND_DIR, "signature.html"))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/restitution-signature/<token>")
def restitution_signature_page(token):
    response = make_response(send_from_directory(FRONTEND_DIR, "restitution-signature.html"))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/admin.html")
@login_required
def admin_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin.html")


@bp.route("/admin-comptes.html")
@login_required
def admin_accounts_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-comptes.html")


@bp.route("/admin-services.html")
@login_required
def admin_services_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-services.html")


@bp.route("/admin-ressources.html")
@login_required
def admin_resources_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-ressources.html")


@bp.route("/admin-ressources-ordre.html")
@login_required
def admin_resources_order_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-ressources-ordre.html")


@bp.route("/admin-personnalisation.html")
@login_required
def admin_branding_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "admin-personnalisation.html")


@bp.route("/logs.html")
@login_required
def logs_page():
    if not has_permission("users.manage"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "logs.html")


@bp.route("/trash.html")
@admin_required
def trash_page():
    return send_from_directory(FRONTEND_DIR, "trash.html")


@bp.route("/setup.html")
@login_required
def setup_page():
    return send_from_directory(FRONTEND_DIR, "setup.html")


# ---------------------------------------------------------------------------
# Fichiers statiques
# ---------------------------------------------------------------------------

@bp.route("/css/<path:path>")
def send_css(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, "css"), path)


@bp.route("/js/<path:path>")
def send_js(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, "js"), path)


@bp.route("/assets/<path:path>")
def send_assets(path):
    return send_from_directory(FRONTEND_ASSETS_DIR, path)


# ---------------------------------------------------------------------------
# API publiques légères
# ---------------------------------------------------------------------------

@bp.route("/api/settings/logo", methods=["GET"])
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


@bp.route("/api/csrf-token", methods=["GET"])
def csrf_token_route():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return jsonify({"token": session["csrf_token"]})


@bp.route("/api/client-context", methods=["GET"])
def client_context_route():
    return jsonify({
        "serverSeenIp": get_request_client_ip(),
        "forwardedFor": extract_first_forwarded_ip(request.headers.get("X-Forwarded-For")),
        "realIp": str(request.headers.get("X-Real-IP") or "").strip(),
    })


@bp.route("/api/session", methods=["GET"])
@login_required
def session_route():
    return jsonify(current_user())


@bp.route("/api/me/password", methods=["POST"])
@login_required
def change_own_password():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    current_pw = payload.get("current_password") or ""
    new_pw = payload.get("new_password") or ""
    if not current_pw or not new_pw:
        return jsonify({"error": "missing_fields"}), 400
    record = get_user_record(user["username"])
    if not record or not bcrypt.checkpw(current_pw.encode(), record["password_hash"].encode()):
        return jsonify({"error": "invalid_current_password"}), 403
    complexity_error = password_complexity_error(new_pw)
    if complexity_error:
        return jsonify({"error": complexity_error}), 400
    config = load_auth_config()
    for u in config["users"]:
        if u.get("username") == user["username"]:
            u["password_hash"] = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
            break
    save_auth_config(config)
    insert_app_log(get_db(), "security", "password_self_change", {
        "username": user["username"],
        "ip": get_request_client_ip(),
    })
    return jsonify({"ok": True})


@bp.route("/api/settings/public", methods=["GET"])
def public_settings_route():
    response = jsonify(build_public_settings_payload())
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
