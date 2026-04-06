"""Tests admin utilisateurs : CRUD + signup."""


class TestAdminUsers:
    def test_list_users(self, admin_client):
        r = admin_client.get("/api/admin/users")
        assert r.status_code == 200
        users = r.get_json()
        assert isinstance(users, list)
        assert len(users) >= 2  # testadmin + testredac from fixtures

    def test_create_user(self, admin_client):
        r = admin_client.post(
            "/api/admin/users",
            json={
                "username": "newuser",
                "password": "NewUser1234!",
                "groups": ["redaction"],
                "is_active": True,
            },
        )
        assert r.status_code == 201

    def test_create_user_duplicate(self, admin_client):
        admin_client.post(
            "/api/admin/users",
            json={"username": "dupuser", "password": "DupUser1234!", "groups": []},
        )
        r = admin_client.post(
            "/api/admin/users",
            json={"username": "dupuser", "password": "DupUser1234!", "groups": []},
        )
        assert r.status_code == 409

    def test_create_user_weak_password(self, admin_client):
        r = admin_client.post(
            "/api/admin/users",
            json={"username": "weakpwd", "password": "123", "groups": []},
        )
        assert r.status_code == 400

    def test_create_user_empty_username(self, admin_client):
        r = admin_client.post(
            "/api/admin/users",
            json={"username": "", "password": "Strong1234!", "groups": []},
        )
        assert r.status_code == 400

    def test_update_user(self, admin_client):
        admin_client.post(
            "/api/admin/users",
            json={"username": "upduser", "password": "UpdUser1234!", "groups": ["redaction"]},
        )
        r = admin_client.put(
            "/api/admin/users/upduser",
            json={"groups": ["admin"], "status": "active"},
        )
        assert r.status_code == 200

    def test_update_user_password(self, admin_client):
        admin_client.post(
            "/api/admin/users",
            json={"username": "pwduser", "password": "PwdUser1234!", "groups": []},
        )
        r = admin_client.put(
            "/api/admin/users/pwduser",
            json={"password": "NewPassword5678!"},
        )
        assert r.status_code == 200

    def test_update_user_not_found(self, admin_client):
        r = admin_client.put(
            "/api/admin/users/inexistant",
            json={"groups": []},
        )
        assert r.status_code == 404

    def test_delete_user(self, admin_client):
        admin_client.post(
            "/api/admin/users",
            json={"username": "deluser", "password": "DelUser1234!", "groups": []},
        )
        r = admin_client.delete("/api/admin/users/deluser")
        assert r.status_code == 200

    def test_delete_current_user_rejected(self, admin_client):
        r = admin_client.delete("/api/admin/users/testadmin")
        assert r.status_code == 400
        assert r.get_json()["error"] == "cannot_delete_current_user"

    def test_delete_user_not_found(self, admin_client):
        r = admin_client.delete("/api/admin/users/inexistant")
        assert r.status_code == 404

    def test_requires_admin(self, redac_client):
        r = redac_client.get("/api/admin/users")
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.get("/api/admin/users")
        assert r.status_code == 401


class TestAdminGroups:
    def test_list_groups(self, admin_client):
        r = admin_client.get("/api/admin/groups")
        assert r.status_code == 200
        data = r.get_json()
        assert "admin" in data or isinstance(data, list)

    def test_requires_admin(self, redac_client):
        r = redac_client.get("/api/admin/groups")
        assert r.status_code == 403


class TestSignup:
    def _signup(self, client, username, password, password_confirm=None):
        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        return client.post(
            "/signup",
            data={
                "username": username,
                "password": password,
                "password_confirm": password_confirm or password,
                "csrf_token": token,
            },
            follow_redirects=False,
        )

    def test_signup_success(self, client):
        r = self._signup(client, "nouveaucompte", "NouveauCompte1234!")
        assert r.status_code == 302
        assert "notice=signup_pending" in r.location

    def test_signup_password_mismatch(self, client):
        r = self._signup(client, "testmismatch", "Abc12345!", "Different1!")
        assert r.status_code == 302
        assert "error=password_mismatch" in r.location

    def test_signup_duplicate_user(self, client):
        """testadmin existe deja dans les fixtures."""
        r = self._signup(client, "testadmin", "Admin1234!")
        assert r.status_code == 302
        assert "error=user_exists" in r.location

    def test_signup_weak_password(self, client):
        r = self._signup(client, "weakpwduser", "123")
        assert r.status_code == 302
        assert "error=" in r.location

    def test_signup_missing_fields(self, client):
        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        r = client.post(
            "/signup",
            data={"username": "", "password": "", "password_confirm": "", "csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "error=missing_fields" in r.location

    def test_signup_missing_csrf(self, client):
        r = client.post(
            "/signup",
            data={"username": "nocsrf", "password": "Test1234!", "password_confirm": "Test1234!"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "error=" in r.location
