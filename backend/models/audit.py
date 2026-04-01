import base64
import json
from flask import has_request_context, request, session

from utils import generate_id, utc_now
from auth import get_request_client_ip, extract_first_forwarded_ip


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

CLIENT_CONTEXT_COOKIE_NAME = "dotation_client_context_v1"


def current_actor(default="system"):
    return session.get("user") or default


# ---------------------------------------------------------------------------
# Contexte client (cookie + formulaire de login)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Persistance des événements
# ---------------------------------------------------------------------------

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
            json.dumps(merge_app_log_details(details), ensure_ascii=False),
            utc_now(),
        ),
    )
