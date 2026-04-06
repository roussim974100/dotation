import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
CUSTOM_BRANDING_DIR = os.path.join(FRONTEND_ASSETS_DIR, "custom")
A_QUAI_PDF_LOGO_PATH = os.path.join(FRONTEND_ASSETS_DIR, "a-quai-email-mark.png")
DB_PATH = os.path.join(BASE_DIR, "dotation.db")
APP_SECRET_PATH = os.path.join(BASE_DIR, ".app_secret_key")
CITY_LOGO_URL = os.environ.get("CITY_LOGO_URL", "")
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
