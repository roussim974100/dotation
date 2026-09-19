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


def test_update_user_refuse_les_colonnes_hors_liste_blanche():
    from auth import UPDATABLE_USER_COLUMNS, update_user
    assert "password_hash" in UPDATABLE_USER_COLUMNS and "username" not in UPDATABLE_USER_COLUMNS
    assert update_user("nobody", **{"is_active=1, password_hash": "x"}) is False
    assert update_user("nobody", created_at="2020-01-01") is False


def test_limitation_de_connexion_ignore_x_forwarded_for_brut():
    """La cle de limitation vient de remote_addr : forger X-Forwarded-For ne change pas la cle."""
    import app as app_module
    from auth import get_rate_limit_key
    with app_module.app.test_request_context(
        "/", headers={"X-Forwarded-For": "1.2.3.4"}, environ_overrides={"REMOTE_ADDR": "9.9.9.9"}
    ):
        assert get_rate_limit_key() != "1.2.3.4"


def test_export_interdit_aux_groupes_a_portee_masquee(monkeypatch):
    import routes.forms as forms_routes
    monkeypatch.setattr(forms_routes, "has_permission", lambda perm: True)
    monkeypatch.setattr(forms_routes, "current_user", lambda: {"data_scope": "masked"})
    assert forms_routes.can_export_unmasked() is False
    monkeypatch.setattr(forms_routes, "current_user", lambda: {"data_scope": "full"})
    assert forms_routes.can_export_unmasked() is True
    monkeypatch.setattr(forms_routes, "has_permission", lambda perm: False)
    assert forms_routes.can_export_unmasked() is False


def _seen_by_app(remote_addr, forwarded_for, monkeypatch, setting=None):
    from proxy import AutoProxyFix
    if setting is None:
        monkeypatch.delenv("APP_TRUSTED_PROXIES", raising=False)
    else:
        monkeypatch.setenv("APP_TRUSTED_PROXIES", setting)
    captured = {}

    def inner(environ, start_response):
        captured["addr"] = environ.get("REMOTE_ADDR")
        return []

    AutoProxyFix(inner)({"REMOTE_ADDR": remote_addr, "HTTP_X_FORWARDED_FOR": forwarded_for}, lambda *a: None)
    return captured["addr"]


def test_proxy_auto_derriere_un_reverse_proxy_local(monkeypatch):
    """Appelant direct prive/loopback = reverse proxy : on lit l'IP client ajoutee par le proxy (dernier element)."""
    assert _seen_by_app("127.0.0.1", "6.6.6.6, 203.0.113.9", monkeypatch) == "203.0.113.9"
    assert _seen_by_app("192.168.1.10", "203.0.113.9", monkeypatch) == "203.0.113.9"


def test_proxy_auto_acces_direct_public_ignore_x_forwarded_for(monkeypatch):
    """Appelant direct public = pas de proxy : l'en-tete forge est ignore."""
    assert _seen_by_app("8.8.8.8", "1.2.3.4", monkeypatch) == "8.8.8.8"


def test_proxy_surcharges_explicites(monkeypatch):
    assert _seen_by_app("127.0.0.1", "203.0.113.9", monkeypatch, setting="0") == "127.0.0.1"
    assert _seen_by_app("8.8.4.4", "203.0.113.9", monkeypatch, setting="1") == "203.0.113.9"
