"""Tests des endpoints publics simples (session, client-context, settings/logo)."""


class TestSession:
    def test_session_returns_user_when_logged_in(self, admin_client):
        r = admin_client.get("/api/session")
        assert r.status_code == 200
        data = r.get_json()
        assert data["username"] == "testadmin"

    def test_session_requires_auth(self, client):
        r = client.get("/api/session")
        assert r.status_code == 401


class TestClientContext:
    def test_returns_ip_info(self, client):
        r = client.get("/api/client-context")
        assert r.status_code == 200
        data = r.get_json()
        assert "serverSeenIp" in data


class TestSettingsLogo:
    def test_logo_returns_image(self, client):
        r = client.get("/api/settings/logo")
        assert r.status_code in (200, 302)
