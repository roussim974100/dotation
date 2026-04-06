"""Tests admin corbeille : liste, restauration, suppression definitive, vidage."""


_MINIMAL = {"beneficiaire": {"nom": "Dupont", "prenom": "Jean"}}


def _create_and_delete(admin_client):
    """Cree un dossier puis le supprime pour alimenter la corbeille."""
    r = admin_client.post("/api/forms", json=_MINIMAL)
    form_id = r.get_json()["summary"]["id"]
    admin_client.delete(f"/api/forms/{form_id}")
    return form_id


class TestTrashList:
    def test_trash_empty(self, admin_client):
        r = admin_client.get("/api/admin/trash")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_trash_after_delete(self, admin_client):
        _create_and_delete(admin_client)
        r = admin_client.get("/api/admin/trash")
        assert r.status_code == 200
        items = r.get_json()
        assert len(items) >= 1
        assert items[0]["item_type"] == "form"

    def test_requires_admin(self, redac_client):
        r = redac_client.get("/api/admin/trash")
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.get("/api/admin/trash")
        assert r.status_code == 401


class TestTrashRestore:
    def test_restore_form(self, admin_client):
        _create_and_delete(admin_client)
        trash = admin_client.get("/api/admin/trash").get_json()
        trash_id = trash[0]["id"]
        r = admin_client.post(f"/api/admin/trash/{trash_id}/restore")
        assert r.status_code == 200
        assert r.get_json()["restored"] is True

        # La corbeille est vide apres restauration
        trash_after = admin_client.get("/api/admin/trash").get_json()
        assert len(trash_after) == 0

    def test_restore_not_found(self, admin_client):
        r = admin_client.post("/api/admin/trash/inexistant/restore")
        assert r.status_code == 404


class TestTrashDelete:
    def test_delete_permanently(self, admin_client):
        _create_and_delete(admin_client)
        trash = admin_client.get("/api/admin/trash").get_json()
        trash_id = trash[0]["id"]
        r = admin_client.delete(f"/api/admin/trash/{trash_id}")
        assert r.status_code == 200
        assert r.get_json()["deleted"] is True

    def test_delete_not_found(self, admin_client):
        r = admin_client.delete("/api/admin/trash/inexistant")
        assert r.status_code == 404


class TestTrashEmpty:
    def test_empty_trash(self, admin_client):
        _create_and_delete(admin_client)
        _create_and_delete(admin_client)
        r = admin_client.delete("/api/admin/trash")
        assert r.status_code == 200

        trash = admin_client.get("/api/admin/trash").get_json()
        assert len(trash) == 0
