"""Tests du flux public de signature de restitution (GET/POST /api/restitution-signature/<token>)."""


_MINIMAL = {"beneficiaire": {"nom": "Martin", "prenom": "Alice"}}


def _create(client, payload=None):
    r = client.post("/api/forms", json=payload or _MINIMAL)
    assert r.status_code == 201
    return r.get_json()["summary"]["id"]


def _prepare_restitution(client, form_id):
    client.patch(
        f"/api/forms/{form_id}/restitution",
        json={
            "returnedAt": "2026-04-01T10:00:00Z",
            "reason": "depart",
            "notes": "",
            "items": {},
        },
    )


def _create_restitution_link(admin_client, form_id):
    r = admin_client.post(f"/api/forms/{form_id}/restitution-signature-link", json={})
    assert r.status_code == 201
    url = r.get_json()["link"]["url"]
    return url.rstrip("/").split("/")[-1]


class TestRestitutionSignaturePublicFlow:
    def test_get_restitution_token(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        token = _create_restitution_link(admin_client, form_id)
        r = client.get(f"/api/restitution-signature/{token}")
        assert r.status_code == 200
        data = r.get_json()
        assert "beneficiaire" in data or "form" in data or "dossier" in data

    def test_get_restitution_token_invalid(self, client):
        r = client.get("/api/restitution-signature/invalid-token")
        assert r.status_code == 404

    def test_submit_restitution_confirmed(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        token = _create_restitution_link(admin_client, form_id)
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,iVBOR",
                "signataireDecision": "confirmed",
            },
        )
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_submit_restitution_with_reservation_and_comment(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        token = _create_restitution_link(admin_client, form_id)
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,iVBOR",
                "signataireDecision": "with_reservation",
                "signataireComment": "Clavier manquant",
            },
        )
        assert r.status_code == 200

    def test_submit_without_signature_rejected(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        token = _create_restitution_link(admin_client, form_id)
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={"signataireDecision": "confirmed"},
        )
        assert r.status_code == 400

    def test_submit_invalid_decision_rejected(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        token = _create_restitution_link(admin_client, form_id)
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,abc",
                "signataireDecision": "invalid_choice",
            },
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "invalid_decision"

    def test_token_used_twice_rejected(self, admin_client, client):
        form_id = _create(admin_client)
        _prepare_restitution(admin_client, form_id)
        token = _create_restitution_link(admin_client, form_id)
        client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,abc",
                "signataireDecision": "confirmed",
            },
        )
        r = client.post(
            f"/api/restitution-signature/{token}/submit",
            json={
                "signatureDataUrl": "data:image/png;base64,abc",
                "signataireDecision": "confirmed",
            },
        )
        assert r.status_code == 410
