"""
Fixtures partagées pour les tests d'intégration.

Chaque test reçoit une base SQLite vierge dans un répertoire temporaire,
ainsi qu'un fichier users.json isolé.  Les modules `database` et `auth`
sont patchés au niveau de leurs variables de module, ce qui suffit car
toutes les fonctions accèdent au chemin via ces variables.
"""

import json
import os
import sys
import pytest
import bcrypt

# Assure que le répertoire backend est dans sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_PASSWORD = "Admin1234!"
_REDAC_PASSWORD = "Redac5678!"


def _make_users_json(path: str) -> None:
    admin_hash = bcrypt.hashpw(_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
    redac_hash = bcrypt.hashpw(_REDAC_PASSWORD.encode(), bcrypt.gensalt()).decode()
    config = {
        "groups": {
            "admin": {
                "label": "Administration",
                "permissions": ["*"],
                "data_scope": "full",
            },
            "redaction": {
                "label": "Redaction",
                "permissions": [
                    "forms.read_list", "forms.read_detail",
                    "forms.create", "forms.edit", "forms.export",
                ],
                "data_scope": "full",
            },
        },
        "users": [
            {
                "username": "testadmin",
                "password_hash": admin_hash,
                "groups": ["admin"],
                "is_active": True,
                "status": "active",
            },
            {
                "username": "testredac",
                "password_hash": redac_hash,
                "groups": ["redaction"],
                "is_active": True,
                "status": "active",
            },
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Vide le rate limiter entre chaque test."""
    import auth
    auth._login_attempts.clear()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Application Flask avec DB et users.json isolés."""
    db_path = str(tmp_path / "test.db")
    users_path = str(tmp_path / "users.json")

    _make_users_json(users_path)

    # Patch avant tout import de l'app pour que get_db() et load_auth_config()
    # utilisent les chemins temporaires.
    import database
    import auth
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(auth, "USERS_FILE", users_path)

    from app import app as flask_app, init_db
    from models.settings import seed_app_settings

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"

    with flask_app.app_context():
        init_db()
        with database.get_db() as conn:
            seed_app_settings(conn)

    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _do_login(client, username, password):
    """Effectue la séquence CSRF + POST /login."""
    r = client.get("/api/csrf-token")
    token = r.get_json()["token"]
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


@pytest.fixture()
def admin_client(app):
    """Client déjà connecté en tant qu'admin (session indépendante)."""
    c = app.test_client()
    _do_login(c, "testadmin", _ADMIN_PASSWORD)
    return c


@pytest.fixture()
def redac_client(app):
    """Client connecté avec droits rédaction (session indépendante)."""
    c = app.test_client()
    _do_login(c, "testredac", _REDAC_PASSWORD)
    return c
