"""Tests du module parc mutualisé (shared_pools)."""
import pytest


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

class TestPoolsRead:
    def test_list_pools_empty(self, redac_client):
        r = redac_client.get("/api/pools")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_pools_unauthenticated(self, client):
        r = client.get("/api/pools")
        assert r.status_code in (401, 302)

    def test_get_pool_not_found(self, redac_client):
        r = redac_client.get("/api/pools/nonexistent")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# CRUD pools (admin_client injecte automatiquement X-CSRF-Token)
# ---------------------------------------------------------------------------

class TestPoolsCRUD:
    def test_create_pool(self, admin_client):
        r = admin_client.post("/api/pools", json={"label": "Saccoche TT-01", "notes": "Télétravail"})
        assert r.status_code == 201
        assert "id" in r.get_json()

    def test_create_pool_no_label(self, admin_client):
        r = admin_client.post("/api/pools", json={"label": ""})
        assert r.status_code == 400

    def test_get_pool(self, admin_client):
        pool_id = admin_client.post("/api/pools", json={"label": "PC mutualisé"}).get_json()["id"]
        r = admin_client.get(f"/api/pools/{pool_id}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["label"] == "PC mutualisé"
        assert data["items"] == []
        assert data["members"] == []

    def test_update_pool(self, admin_client):
        pool_id = admin_client.post("/api/pools", json={"label": "Avant"}).get_json()["id"]
        r = admin_client.put(f"/api/pools/{pool_id}", json={"label": "Après", "notes": "MAJ"})
        assert r.status_code == 200
        updated = admin_client.get(f"/api/pools/{pool_id}").get_json()
        assert updated["label"] == "Après"
        assert updated["notes"] == "MAJ"

    def test_delete_pool(self, admin_client):
        pool_id = admin_client.post("/api/pools", json={"label": "À supprimer"}).get_json()["id"]
        r = admin_client.delete(f"/api/pools/{pool_id}")
        assert r.status_code == 200
        assert admin_client.get(f"/api/pools/{pool_id}").status_code == 404

    def test_create_pool_forbidden_for_redac(self, redac_client):
        r = redac_client.post("/api/pools", json={"label": "Test"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

class TestPoolItems:
    def _make_pool(self, admin_client):
        return admin_client.post("/api/pools", json={"label": "Saccoche"}).get_json()["id"]

    def test_add_item(self, admin_client):
        pool_id = self._make_pool(admin_client)
        r = admin_client.post(
            f"/api/pools/{pool_id}/items",
            json={"resource_type": "ordinateur", "label": "Dell Latitude", "serial_number": "SN-001"},
        )
        assert r.status_code == 201
        pool = admin_client.get(f"/api/pools/{pool_id}").get_json()
        assert len(pool["items"]) == 1
        assert pool["items"][0]["label"] == "Dell Latitude"
        assert pool["items"][0]["serial_number"] == "SN-001"

    def test_add_item_missing_fields(self, admin_client):
        pool_id = self._make_pool(admin_client)
        r = admin_client.post(f"/api/pools/{pool_id}/items", json={"resource_type": "ordinateur"})
        assert r.status_code == 400

    def test_update_item(self, admin_client):
        pool_id = self._make_pool(admin_client)
        admin_client.post(f"/api/pools/{pool_id}/items",
            json={"resource_type": "clavier", "label": "Clavier original"})
        item_id = admin_client.get(f"/api/pools/{pool_id}").get_json()["items"][0]["id"]
        r = admin_client.put(f"/api/pools/{pool_id}/items/{item_id}",
            json={"resource_type": "clavier", "label": "Clavier modifié"})
        assert r.status_code == 200
        pool = admin_client.get(f"/api/pools/{pool_id}").get_json()
        assert pool["items"][0]["label"] == "Clavier modifié"

    def test_delete_item(self, admin_client):
        pool_id = self._make_pool(admin_client)
        admin_client.post(f"/api/pools/{pool_id}/items",
            json={"resource_type": "souris", "label": "Souris"})
        item_id = admin_client.get(f"/api/pools/{pool_id}").get_json()["items"][0]["id"]
        r = admin_client.delete(f"/api/pools/{pool_id}/items/{item_id}")
        assert r.status_code == 200
        assert admin_client.get(f"/api/pools/{pool_id}").get_json()["items"] == []


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

class TestPoolMembers:
    def _make_pool(self, admin_client):
        return admin_client.post("/api/pools", json={"label": "Pool test"}).get_json()["id"]

    def test_add_member_by_name(self, admin_client):
        pool_id = self._make_pool(admin_client)
        r = admin_client.post(f"/api/pools/{pool_id}/members",
            json={"beneficiary_name": "Dupont Jean"})
        assert r.status_code == 201
        pool = admin_client.get(f"/api/pools/{pool_id}").get_json()
        assert len(pool["members"]) == 1
        assert pool["members"][0]["beneficiary_name"] == "Dupont Jean"
        assert pool["members"][0]["form_id"] is None

    def test_add_member_no_name_no_form(self, admin_client):
        pool_id = self._make_pool(admin_client)
        r = admin_client.post(f"/api/pools/{pool_id}/members", json={})
        assert r.status_code == 400

    def test_delete_member(self, admin_client):
        pool_id = self._make_pool(admin_client)
        admin_client.post(f"/api/pools/{pool_id}/members", json={"beneficiary_name": "Martin Paul"})
        member_id = admin_client.get(f"/api/pools/{pool_id}").get_json()["members"][0]["id"]
        r = admin_client.delete(f"/api/pools/{pool_id}/members/{member_id}")
        assert r.status_code == 200
        assert admin_client.get(f"/api/pools/{pool_id}").get_json()["members"] == []

    def test_pools_for_form_empty(self, admin_client):
        r = admin_client.get("/api/pools/for-form/nonexistent")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_cascade_delete_pool(self, admin_client):
        """Supprimer un pool efface items et membres."""
        pool_id = self._make_pool(admin_client)
        admin_client.post(f"/api/pools/{pool_id}/items",
            json={"resource_type": "ordinateur", "label": "PC"})
        admin_client.post(f"/api/pools/{pool_id}/members",
            json={"beneficiary_name": "Test"})
        admin_client.delete(f"/api/pools/{pool_id}")
        assert admin_client.get(f"/api/pools/{pool_id}").status_code == 404
