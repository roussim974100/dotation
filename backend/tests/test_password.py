"""Tests du changement de mot de passe utilisateur (POST /api/me/password)."""


class TestChangeOwnPassword:
    def test_change_password_success(self, admin_client):
        r = admin_client.post("/api/me/password", json={
            "current_password": "Admin1234!",
            "new_password": "NewPass9876!",
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_change_password_wrong_current(self, admin_client):
        r = admin_client.post("/api/me/password", json={
            "current_password": "WrongPassword1!",
            "new_password": "NewPass9876!",
        })
        assert r.status_code == 403
        assert r.get_json()["error"] == "invalid_current_password"

    def test_change_password_missing_fields(self, admin_client):
        r = admin_client.post("/api/me/password", json={})
        assert r.status_code == 400
        assert r.get_json()["error"] == "missing_fields"

    def test_change_password_weak_new(self, admin_client):
        r = admin_client.post("/api/me/password", json={
            "current_password": "Admin1234!",
            "new_password": "abc",
        })
        assert r.status_code == 400

    def test_change_password_requires_auth(self, client):
        r = client.post("/api/me/password", json={
            "current_password": "Admin1234!",
            "new_password": "NewPass9876!",
        })
        assert r.status_code == 401
