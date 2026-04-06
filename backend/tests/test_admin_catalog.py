"""Tests admin catalogues : CRUD services et resources."""


class TestServicesCatalog:
    def test_list_services(self, admin_client):
        r = admin_client.get("/api/admin/services")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_create_service(self, admin_client):
        r = admin_client.post(
            "/api/admin/services",
            json={"label": "Direction Informatique"},
        )
        assert r.status_code == 201

    def test_create_service_duplicate(self, admin_client):
        admin_client.post("/api/admin/services", json={"label": "DSI"})
        r = admin_client.post("/api/admin/services", json={"label": "DSI"})
        assert r.status_code == 409

    def test_create_service_empty_label(self, admin_client):
        r = admin_client.post("/api/admin/services", json={"label": ""})
        assert r.status_code == 400

    def test_update_service(self, admin_client):
        admin_client.post("/api/admin/services", json={"label": "SVC-UPD"})
        services = admin_client.get("/api/admin/services").get_json()
        svc = next(s for s in services if s["label"] == "SVC-UPD")
        r = admin_client.put(
            f"/api/admin/services/{svc['id']}",
            json={"label": "SVC-UPDATED"},
        )
        assert r.status_code == 200

    def test_update_service_not_found(self, admin_client):
        r = admin_client.put(
            "/api/admin/services/inexistant",
            json={"label": "X"},
        )
        assert r.status_code == 404

    def test_delete_service(self, admin_client):
        admin_client.post("/api/admin/services", json={"label": "SVC-DEL"})
        services = admin_client.get("/api/admin/services").get_json()
        svc = next(s for s in services if s["label"] == "SVC-DEL")
        r = admin_client.delete(f"/api/admin/services/{svc['id']}")
        assert r.status_code == 200

    def test_requires_admin(self, redac_client):
        r = redac_client.get("/api/admin/services")
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.get("/api/admin/services")
        assert r.status_code == 401


class TestResourcesCatalog:
    _RESOURCE = {
        "code": "badge_test",
        "label": "Badge de test",
        "category": "acces",
        "is_active": True,
    }

    def test_list_resources(self, admin_client):
        r = admin_client.get("/api/admin/resources")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_create_resource(self, admin_client):
        r = admin_client.post("/api/admin/resources", json=self._RESOURCE)
        assert r.status_code == 201

    def test_create_resource_duplicate_code(self, admin_client):
        admin_client.post("/api/admin/resources", json=self._RESOURCE)
        r = admin_client.post("/api/admin/resources", json=self._RESOURCE)
        assert r.status_code == 409

    def test_create_resource_missing_fields(self, admin_client):
        r = admin_client.post("/api/admin/resources", json={"code": "", "label": ""})
        assert r.status_code == 400

    def test_update_resource(self, admin_client):
        admin_client.post("/api/admin/resources", json=self._RESOURCE)
        resources = admin_client.get("/api/admin/resources").get_json()
        res = next(r for r in resources if r["code"] == "badge_test")
        r = admin_client.put(
            f"/api/admin/resources/{res['id']}",
            json={"label": "Badge modifie"},
        )
        assert r.status_code == 200

    def test_update_resource_not_found(self, admin_client):
        r = admin_client.put(
            "/api/admin/resources/inexistant",
            json={"label": "X"},
        )
        assert r.status_code == 404

    def test_delete_resource(self, admin_client):
        res_payload = {**self._RESOURCE, "code": "badge_del"}
        admin_client.post("/api/admin/resources", json=res_payload)
        resources = admin_client.get("/api/admin/resources").get_json()
        res = next(r for r in resources if r["code"] == "badge_del")
        r = admin_client.delete(f"/api/admin/resources/{res['id']}")
        assert r.status_code == 200

    def test_requires_admin(self, redac_client):
        r = redac_client.get("/api/admin/resources")
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.get("/api/admin/resources")
        assert r.status_code == 401


class TestReferenceCatalogs:
    """Endpoints de reference publics (authentifies, sans permission admin)."""

    def test_reference_resources(self, redac_client):
        r = redac_client.get("/api/reference/resources")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_reference_services(self, redac_client):
        r = redac_client.get("/api/reference/services")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_reference_requires_auth(self, client):
        assert client.get("/api/reference/resources").status_code == 401
        assert client.get("/api/reference/services").status_code == 401
