import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
CUSTOM_BRANDING_DIR = os.path.join(FRONTEND_ASSETS_DIR, "custom")
A_QUAI_PDF_LOGO_PATH = os.path.join(FRONTEND_ASSETS_DIR, "a-quai-email-mark.png")
CITY_LOGO_URL = os.environ.get("CITY_LOGO_URL", "")
CITY_LOGO_PATH = os.environ.get("CITY_LOGO_PATH", os.path.join(FRONTEND_ASSETS_DIR, "city-logo.png"))

# DATA_DIR : dossier persistant (bases de données, clé secrète).
# En production Docker, monter ce dossier en volume nommé.
# Par défaut = répertoire backend (comportement local inchangé).
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "dotation.db")
DB_USERS_PATH = os.path.join(DATA_DIR, "users.db")
AUTH_CONFIG_PATH = os.path.join(DATA_DIR, "users.json")
APP_SECRET_PATH = os.path.join(DATA_DIR, ".app_secret_key")


def get_app_secret_key():
    env_secret = os.environ.get("APP_SECRET_KEY", "").strip()
    if env_secret:
        return env_secret

    try:
        if os.path.exists(APP_SECRET_PATH):
            with open(APP_SECRET_PATH, "r", encoding="utf-8") as f:
                stored = f.read().strip()
                if stored:
                    return stored
    except OSError:
        pass

    generated = secrets.token_hex(32)
    try:
        with open(APP_SECRET_PATH, "w", encoding="utf-8") as f:
            f.write(generated)
    except OSError:
        pass
    return generated
