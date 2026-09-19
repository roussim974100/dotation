"""Durcissement securite : URL du logo distant et plafond de taille des requetes."""
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.settings import get_app_settings, save_app_settings, seed_app_settings


def _connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT)"
    )
    seed_app_settings(connection)
    return connection


def test_logo_url_refuse_les_schemas_non_http():
    """Le serveur telecharge cette URL : file://, ftp://, etc. sont vides (protection SSRF/lecture locale)."""
    connection = _connection()
    for bad in ("file:///etc/passwd", "ftp://exemple.fr/logo.png", "gopher://x", "//exemple.fr/logo.png"):
        save_app_settings(connection, {"brand_logo_url": bad})
        assert get_app_settings(connection)["brand_logo_url"] == "", bad


def test_logo_url_accepte_http_et_https():
    connection = _connection()
    for good in ("https://exemple.fr/logo.png", "http://exemple.fr/logo.png"):
        save_app_settings(connection, {"brand_logo_url": good})
        assert get_app_settings(connection)["brand_logo_url"] == good


def test_app_plafonne_la_taille_des_requetes():
    import app as app_module
    assert app_module.app.config["MAX_CONTENT_LENGTH"] >= 1024 * 1024
