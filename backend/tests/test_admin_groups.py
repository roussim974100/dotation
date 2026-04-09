"""Tests pour la gestion des groupes : liste, toggle permissions, groupe direction."""


class TestAdminGroupsList:
    def test_list_groups_returns_dict(self, admin_client):
        r = admin_client.get("/api/admin/groups")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, dict)
        assert "admin" in data
        assert "redaction" in data

    def test_direction_group_present(self, admin_client):
        """Le groupe direction doit être automatiquement provisionné."""
        r = admin_client.get("/api/admin/groups")
        data = r.get_json()
        assert "direction" in data

    def test_direction_group_has_unc_permission(self, admin_client):
        r = admin_client.get("/api/admin/groups")
        direction = r.get_json().get("direction", {})
        assert "unc.view_all" in direction.get("permissions", [])

    def test_requires_auth(self, client):
        r = client.get("/api/admin/groups")
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        r = redac_client.get("/api/admin/groups")
        assert r.status_code == 403


class TestToggleGroupPermissions:
    def test_toggle_unc_on_redaction_group(self, admin_client):
        # S'assurer que unc.view_all n'est pas déjà dans redaction
        groups_before = admin_client.get("/api/admin/groups").get_json()
        perms_before = groups_before["redaction"].get("permissions", [])
        had_unc = "unc.view_all" in perms_before

        # Activer unc.view_all
        r = admin_client.put("/api/admin/groups/redaction", json={"unc.view_all": True})
        assert r.status_code == 200
        groups = r.get_json()
        assert "unc.view_all" in groups["redaction"]["permissions"]

        # Désactiver unc.view_all
        r2 = admin_client.put("/api/admin/groups/redaction", json={"unc.view_all": False})
        assert r2.status_code == 200
        groups2 = r2.get_json()
        assert "unc.view_all" not in groups2["redaction"]["permissions"]

    def test_cannot_edit_admin_group(self, admin_client):
        r = admin_client.put("/api/admin/groups/admin", json={"unc.view_all": True})
        assert r.status_code == 403
        assert r.get_json()["error"] == "cannot_edit_admin_group"

    def test_group_not_found(self, admin_client):
        r = admin_client.put("/api/admin/groups/inexistant", json={"unc.view_all": True})
        assert r.status_code == 404

    def test_requires_auth(self, client):
        r = client.put("/api/admin/groups/redaction", json={"unc.view_all": True})
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        r = redac_client.put("/api/admin/groups/redaction", json={"unc.view_all": True})
        assert r.status_code == 403

    def test_non_toggleable_permission_ignored(self, admin_client):
        """Les permissions non listées dans TOGGLEABLE_PERMISSIONS ne doivent pas être modifiables."""
        groups_before = admin_client.get("/api/admin/groups").get_json()
        perms_before = set(groups_before["redaction"].get("permissions", []))

        admin_client.put("/api/admin/groups/redaction", json={"forms.delete": True})

        groups_after = admin_client.get("/api/admin/groups").get_json()
        perms_after = set(groups_after["redaction"].get("permissions", []))
        # forms.delete ne devrait pas avoir été ajouté
        assert "forms.delete" not in perms_after - perms_before
