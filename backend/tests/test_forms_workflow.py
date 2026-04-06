"""Tests workflow des dossiers : update (PUT), reopen, restitution (PATCH)."""


_MINIMAL = {"beneficiaire": {"nom": "Dupont", "prenom": "Jean"}}


def _create(client, payload=None):
    r = client.post("/api/forms", json=payload or _MINIMAL)
    assert r.status_code == 201
    return r.get_json()["summary"]["id"]


class TestUpdateForm:
    def test_update_beneficiaire(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.put(
            f"/api/forms/{form_id}",
            json={
                "meta": {"id": form_id},
                "beneficiaire": {"nom": "Martin", "prenom": "Alice", "service": "DSI"},
            },
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["nom"] == "Martin"

    def test_update_inexistant(self, admin_client):
        r = admin_client.put(
            "/api/forms/inexistant-id",
            json={"beneficiaire": {"nom": "X", "prenom": "Y"}},
        )
        # persist_form with unknown id should create or return error
        # depending on implementation — at minimum it should not 500
        assert r.status_code in (200, 201, 400, 404)

    def test_update_requires_auth(self, client):
        r = client.put("/api/forms/some-id", json=_MINIMAL)
        assert r.status_code == 401

    def test_update_requires_permission(self, redac_client, admin_client):
        form_id = _create(admin_client)
        # redac has forms.edit, so update should work
        r = redac_client.put(
            f"/api/forms/{form_id}",
            json={"meta": {"id": form_id}, "beneficiaire": {"nom": "Modif", "prenom": "Test"}},
        )
        assert r.status_code == 200


class TestReopenForm:
    def _create_draft(self, client):
        """Cree un dossier en statut draft (par defaut)."""
        return _create(client)

    def test_reopen_draft(self, admin_client):
        form_id = self._create_draft(admin_client)
        r = admin_client.post(f"/api/forms/{form_id}/reopen")
        assert r.status_code == 200
        data = r.get_json()
        assert data["meta"]["reopenCount"] == 1

    def test_reopen_increments_count(self, admin_client):
        form_id = self._create_draft(admin_client)
        admin_client.post(f"/api/forms/{form_id}/reopen")
        r = admin_client.post(f"/api/forms/{form_id}/reopen")
        assert r.status_code == 200
        assert r.get_json()["meta"]["reopenCount"] == 2

    def test_reopen_inexistant(self, admin_client):
        r = admin_client.post("/api/forms/inexistant-id/reopen")
        assert r.status_code == 404

    def test_reopen_requires_auth(self, client):
        r = client.post("/api/forms/some-id/reopen")
        assert r.status_code == 401

    def test_reopen_active_dossier_rejected(self, admin_client, client):
        """Un dossier signe (statut 'active') ne peut pas etre rouvert."""
        form_id = _create(admin_client)
        # Creer un lien de signature, le signer pour passer en 'active'
        r = admin_client.post(f"/api/forms/{form_id}/signature-link", json={})
        url = r.get_json()["link"]["url"]
        token = url.rstrip("/").split("/")[-1]
        client.post(
            f"/api/signature/{token}/submit",
            json={"signatureDataUrl": "data:image/png;base64,abc", "rgpdAccepted": True},
        )
        r = admin_client.post(f"/api/forms/{form_id}/reopen")
        assert r.status_code == 400
        assert r.get_json()["error"] == "not_reopenable"


class TestRestitution:
    def test_patch_restitution(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.patch(
            f"/api/forms/{form_id}/restitution",
            json={
                "returnedAt": "2026-04-01T10:00:00Z",
                "reason": "depart",
                "notes": "RAS",
                "items": {},
            },
        )
        assert r.status_code == 200

    def test_restitution_inexistant(self, admin_client):
        r = admin_client.patch(
            "/api/forms/inexistant-id/restitution",
            json={"reason": "test"},
        )
        assert r.status_code == 404

    def test_restitution_requires_auth(self, client):
        r = client.patch("/api/forms/some-id/restitution", json={})
        assert r.status_code == 401

    def test_restitution_requires_permission(self, redac_client, admin_client):
        """redac n'a pas forms.restitution → 403."""
        form_id = _create(admin_client)
        r = redac_client.patch(
            f"/api/forms/{form_id}/restitution",
            json={"reason": "test"},
        )
        assert r.status_code == 403
