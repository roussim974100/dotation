"""Tests des liens de signature : creation, consultation, soumission, revocation."""


_MINIMAL = {"beneficiaire": {"nom": "Dupont", "prenom": "Jean"}}


def _create(client, payload=None):
    r = client.post("/api/forms", json=payload or _MINIMAL)
    assert r.status_code == 201
    return r.get_json()["summary"]["id"]


def _extract_token_from_url(url):
    """Extrait le token depuis l'URL du lien (ex: /signature/<token>)."""
    return url.rstrip("/").split("/")[-1]


def _prepare_restitution(client, form_id):
    """Prepare la restitution pour pouvoir generer un lien de signature."""
    client.patch(
        f"/api/forms/{form_id}/restitution",
        json={
            "returnedAt": "2026-04-01T10:00:00Z",
            "reason": "depart",
            "notes": "RAS",
            "items": {},
        },
    )


class TestSignatureLinkCRUD:
    def test_create_signature_link(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.post(
            f"/api/forms/{form_id}/signature-link",
            json={"validityDays": 7},
        )
        assert r.status_code == 201
        link = r.get_json()["link"]
        assert link["status"] == "active"
        assert link["url"]  # URL contient le token

    def test_get_signature_link(self, admin_client):
        form_id = _create(admin_client)
        admin_client.post(f"/api/forms/{form_id}/signature-link", json={})
        r = admin_client.get(f"/api/forms/{form_id}/signature-link")
        assert r.status_code == 200

    def test_create_link_invalid_validity(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.post(
            f"/api/forms/{form_id}/signature-link",
            json={"validityDays": 0},
        )
        assert r.status_code == 400

    def test_revoke_signature_link(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.post(f"/api/forms/{form_id}/signature-link", json={})
        link_id = r.get_json()["link"]["id"]
        r = admin_client.delete(f"/api/signature-links/{link_id}")
        assert r.status_code == 200
        assert r.get_json()["link"]["status"] == "revoked"

    def test_revoke_inexistant(self, admin_client):
        r = admin_client.delete("/api/signature-links/inexistant-id")
        assert r.status_code == 404

    def test_requires_auth(self, client):
        r = client.post("/api/forms/some-id/signature-link", json={})
        assert r.status_code == 401


class TestSignaturePublicFlow:
    def _create_link(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.post(f"/api/forms/{form_id}/signature-link", json={})
        url = r.get_json()["link"]["url"]
        token = _extract_token_from_url(url)
        return form_id, token

    def test_get_token_returns_form_data(self, admin_client, client):
        _, token = self._create_link(admin_client)
        r = client.get(f"/api/signature/{token}")
        assert r.status_code == 200

    def test_get_token_invalid(self, client):
        r = client.get("/api/signature/invalid-token")
        assert r.status_code == 404

    def test_submit_signature(self, admin_client, client):
        _, token = self._create_link(admin_client)
        r = client.post(
            f"/api/signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,iVBOR...",
                "rgpdAccepted": True,
            },
        )
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_submit_without_signature_rejected(self, admin_client, client):
        _, token = self._create_link(admin_client)
        r = client.post(
            f"/api/signature/{token}/submit",
            json={"rgpdAccepted": True},
        )
        assert r.status_code == 400

    def test_submit_without_rgpd_rejected(self, admin_client, client):
        _, token = self._create_link(admin_client)
        r = client.post(
            f"/api/signature/{token}/submit",
            json={"signatureDataUrl": "data:image/png;base64,abc"},
        )
        assert r.status_code == 400

    def test_token_used_twice_rejected(self, admin_client, client):
        _, token = self._create_link(admin_client)
        client.post(
            f"/api/signature/{token}/submit",
            json={"signatureDataUrl": "data:image/png;base64,abc", "rgpdAccepted": True},
        )
        r = client.post(
            f"/api/signature/{token}/submit",
            json={"signatureDataUrl": "data:image/png;base64,abc", "rgpdAccepted": True},
        )
        assert r.status_code == 410


class TestRestitutionSignatureLink:
    def test_create_restitution_link(self, admin_client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        r = admin_client.post(
            f"/api/forms/{form_id}/restitution-signature-link",
            json={"validityDays": 7},
        )
        assert r.status_code == 201
        assert r.get_json()["link"]["status"] == "active"

    def test_create_restitution_link_without_preparation_rejected(self, admin_client):
        """Un lien de restitution sans restitution preparee est refuse."""
        form_id = _create(admin_client)
        r = admin_client.post(
            f"/api/forms/{form_id}/restitution-signature-link",
            json={"validityDays": 7},
        )
        assert r.status_code == 400

    def test_get_restitution_link(self, admin_client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        admin_client.post(f"/api/forms/{form_id}/restitution-signature-link", json={})
        r = admin_client.get(f"/api/forms/{form_id}/restitution-signature-link")
        assert r.status_code == 200

    def test_submit_restitution_signature(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        r = admin_client.post(f"/api/forms/{form_id}/restitution-signature-link", json={})
        url = r.get_json()["link"]["url"]
        token = _extract_token_from_url(url)
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,abc",
                "signataireDecision": "confirmed",
            },
        )
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_restitution_with_reservation_needs_comment(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        r = admin_client.post(f"/api/forms/{form_id}/restitution-signature-link", json={})
        url = r.get_json()["link"]["url"]
        token = _extract_token_from_url(url)
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,abc",
                "signataireDecision": "with_reservation",
            },
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "reservation_comment_required"
