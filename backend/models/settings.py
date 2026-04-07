import json
import os
import urllib.request

from database import get_db
from utils import utc_now, slugify_field_key
from config import (
    CITY_LOGO_URL, CITY_LOGO_PATH,
    FRONTEND_ASSETS_DIR, A_QUAI_PDF_LOGO_PATH,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_APP_SETTINGS = {
    "org_name": "",
    "app_name": "A quai",
    "dpo_email": "",
    "email_domains": "",
    "brand_logo_mode": "url",
    "brand_logo_url": "",
    "brand_logo_file": "",
    "theme_id": "institutionnel",
    "dark_mode_policy": "disabled",
    "support_email": "",
    "support_name": "",
    "support_role": "",
    "org_context": "public_collectivite",
    "beneficiary_types": "agent:Agent,elu:Élu(e)",
}

VALID_ORG_CONTEXTS = {"public_collectivite", "public_administration", "private_company", "association"}


def _parse_beneficiary_types(raw):
    result = []
    for part in (raw or "").split(","):
        part = part.strip()
        if ":" in part:
            value, label = part.split(":", 1)
            value = value.strip()
            label = label.strip()
            if value and label:
                result.append({"value": value, "label": label})
    return result or [{"value": "agent", "label": "Agent"}, {"value": "elu", "label": "Élu(e)"}]

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

BRAND_LOGO_CACHE = {
    "loaded": False,
    "cache_key": None,
    "image": None,
}


# ---------------------------------------------------------------------------
# Persistance des paramètres
# ---------------------------------------------------------------------------

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
    if "org_context" in sanitized and sanitized["org_context"] not in VALID_ORG_CONTEXTS:
        sanitized["org_context"] = DEFAULT_APP_SETTINGS["org_context"]

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


# ---------------------------------------------------------------------------
# Logo et thème
# ---------------------------------------------------------------------------

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


def get_dpo_email(settings=None):
    settings = settings or get_app_settings()
    return settings.get("dpo_email") or DEFAULT_APP_SETTINGS["dpo_email"]


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
        "emailDomains": [d.strip() for d in (settings.get("email_domains") or "").split(",") if d.strip()],
        "supportEmail": settings.get("support_email") or "",
        "supportName": settings.get("support_name") or "",
        "supportRole": settings.get("support_role") or "",
        "orgContext": settings.get("org_context") or DEFAULT_APP_SETTINGS["org_context"],
        "beneficiaryTypes": _parse_beneficiary_types(settings.get("beneficiary_types")),
    }


# ---------------------------------------------------------------------------
# Chargement des images (logo et PDF)
# ---------------------------------------------------------------------------

def load_brand_logo_image():
    settings = get_app_settings()
    local_candidates, remote_url = get_brand_logo_candidates(settings)
    cache_key = json.dumps({
        "local": local_candidates,
        "remote": remote_url,
    }, ensure_ascii=False)

    if BRAND_LOGO_CACHE["loaded"] and BRAND_LOGO_CACHE.get("cache_key") == cache_key:
        return BRAND_LOGO_CACHE["image"]

    image_bytes = None
    for candidate in local_candidates:
        if candidate and os.path.exists(candidate):
            try:
                with open(candidate, "rb") as file:
                    data = file.read()
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    image_bytes = data
            except OSError:
                pass
            if image_bytes:
                break

    if not image_bytes and remote_url:
        try:
            request = urllib.request.Request(
                remote_url,
                headers={
                    "User-Agent": "Parcours-agents-elus/1.0",
                    "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(2 * 1024 * 1024)
            if len(data) >= 2 * 1024 * 1024:
                data = b""
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                image_bytes = data
                if image_bytes and CITY_LOGO_PATH:
                    try:
                        os.makedirs(os.path.dirname(CITY_LOGO_PATH), exist_ok=True)
                        with open(CITY_LOGO_PATH, "wb") as file:
                            file.write(image_bytes)
                    except OSError:
                        pass
        except Exception:
            pass

    BRAND_LOGO_CACHE["loaded"] = True
    BRAND_LOGO_CACHE["cache_key"] = cache_key
    BRAND_LOGO_CACHE["image"] = image_bytes
    return image_bytes


def load_a_quai_pdf_logo_image():
    if not A_QUAI_PDF_LOGO_PATH or not os.path.exists(A_QUAI_PDF_LOGO_PATH):
        return None
    try:
        with open(A_QUAI_PDF_LOGO_PATH, "rb") as file:
            data = file.read()
        return data if data[:8] == b"\x89PNG\r\n\x1a\n" else None
    except OSError:
        return None
