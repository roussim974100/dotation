"""Tests d'authentification : login, logout, CSRF, permissions."""

import pytest


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        r = client.post(
            "/login",
            data={"username": "testadmin", "password": "Admin1234!", "csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.location in ("/", "http://localhost/")

    def test_login_wrong_password(self, client):
        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        r = client.post(
            "/login",
            data={"username": "testadmin", "password": "mauvais!", "csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "error=invalid" in r.location

    def test_login_unknown_user(self, client):
        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        r = client.post(
            "/login",
            data={"username": "inconnu", "password": "Admin1234!", "csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "error=invalid" in r.location

    def test_login_missing_csrf(self, client):
        """POST sans token CSRF → rejet."""
        r = client.post(
            "/login",
            data={"username": "testadmin", "password": "Admin1234!"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "error=invalid" in r.location

    def test_login_bad_csrf(self, client):
        """Token CSRF invalide → rejet même si credentials corrects."""
        r = client.post(
            "/login",
            data={"username": "testadmin", "password": "Admin1234!", "csrf_token": "mauvais"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "error=invalid" in r.location


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_clears_session(self, admin_client):
        # Vérifier qu'on est bien connecté
        r = admin_client.get("/api/forms")
        assert r.status_code == 200

        # Déconnexion
        r = admin_client.get("/logout", follow_redirects=False)
        assert r.status_code == 302

        # La session est vidée : API renvoie 401
        r = admin_client.get("/api/forms")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Protection des routes
# ---------------------------------------------------------------------------

class TestProtectedRoutes:
    def test_api_forms_requires_auth(self, client):
        r = client.get("/api/forms")
        assert r.status_code == 401
        assert r.get_json()["error"] == "authentication_required"

    def test_api_admin_settings_requires_auth(self, client):
        r = client.get("/api/admin/settings")
        assert r.status_code == 401

    def test_api_admin_settings_requires_admin(self, redac_client):
        r = redac_client.get("/api/admin/settings")
        assert r.status_code == 403

    def test_api_forms_delete_requires_permission(self, redac_client, admin_client):
        # Créer un dossier avec l'admin
        r = admin_client.post(
            "/api/forms",
            json={"beneficiaire": {"nom": "Dupont", "prenom": "Jean"}},
        )
        assert r.status_code == 201
        form_id = r.get_json()["summary"]["id"]

        # Le compte rédaction ne peut pas supprimer
        r = redac_client.delete(f"/api/forms/{form_id}")
        assert r.status_code == 403
