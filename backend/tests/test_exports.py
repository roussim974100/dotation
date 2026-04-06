"""Tests des exports : PDF attribution, PDF restitution, Excel, UNC CSV."""


_MINIMAL = {"beneficiaire": {"nom": "Dupont", "prenom": "Jean"}}
_WITH_UNC = {
    **_MINIMAL,
    "unc_acces": [
        {"chemin": "\\\\SRV\\partage", "acces": "lecture", "statut": "demande", "commentaire": ""},
    ],
}


def _create(client, payload=None):
    r = client.post("/api/forms", json=payload or _MINIMAL)
    assert r.status_code == 201
    return r.get_json()["summary"]["id"]


class TestPDFExport:
    def test_pdf_attribution(self, admin_client):
        form_id = _create(admin_client)
        r = admin_client.get(f"/api/forms/{form_id}/pdf")
        assert r.status_code == 200
        assert r.content_type == "application/pdf"
        assert r.data[:5] == b"%PDF-"

    def test_pdf_attribution_inexistant(self, admin_client):
        r = admin_client.get("/api/forms/inexistant-id/pdf")
        assert r.status_code == 404

    def test_pdf_restitution(self, admin_client):
        form_id = _create(admin_client)
        # Preparer la restitution avant export PDF
        admin_client.patch(
            f"/api/forms/{form_id}/restitution",
            json={"returnedAt": "2026-04-01T10:00:00Z", "reason": "depart", "notes": "RAS", "items": {}},
        )
        r = admin_client.get(f"/api/forms/{form_id}/restitution-pdf")
        assert r.status_code == 200
        assert r.content_type == "application/pdf"
        assert r.data[:5] == b"%PDF-"

    def test_pdf_restitution_not_ready(self, admin_client):
        """PDF restitution sans donnees de restitution → 400."""
        form_id = _create(admin_client)
        r = admin_client.get(f"/api/forms/{form_id}/restitution-pdf")
        assert r.status_code == 400

    def test_pdf_requires_auth(self, client):
        r = client.get("/api/forms/some-id/pdf")
        assert r.status_code == 401

    def test_pdf_batch(self, admin_client):
        id1 = _create(admin_client)
        id2 = _create(admin_client, {"beneficiaire": {"nom": "Martin", "prenom": "Alice"}})
        r = admin_client.post(
            "/api/forms/export-pdf-batch",
            json={"ids": [id1, id2]},
        )
        assert r.status_code == 200
        assert "zip" in r.content_type

    def test_restitution_pdf_batch(self, admin_client):
        id1 = _create(admin_client)
        admin_client.patch(
            f"/api/forms/{id1}/restitution",
            json={"returnedAt": "2026-04-01T10:00:00Z", "reason": "depart", "notes": "RAS", "items": {}},
        )
        r = admin_client.post(
            "/api/forms/export-restitution-pdf-batch",
            json={"ids": [id1]},
        )
        assert r.status_code == 200
        assert "zip" in r.content_type


class TestExcelExport:
    def test_export_excel(self, admin_client):
        _create(admin_client)
        r = admin_client.get("/api/forms/export")
        assert r.status_code == 200
        # Excel XML format
        assert "excel" in r.content_type or "xml" in r.content_type or "spreadsheet" in r.content_type

    def test_export_excel_empty(self, admin_client):
        r = admin_client.get("/api/forms/export")
        assert r.status_code == 200

    def test_export_requires_auth(self, client):
        r = client.get("/api/forms/export")
        assert r.status_code == 401


class TestUNCExport:
    def test_export_unc_csv(self, admin_client):
        _create(admin_client, _WITH_UNC)
        r = admin_client.get("/api/forms/export-unc")
        assert r.status_code == 200

    def test_export_unc_empty(self, admin_client):
        r = admin_client.get("/api/forms/export-unc")
        assert r.status_code == 200

    def test_export_unc_requires_auth(self, client):
        r = client.get("/api/forms/export-unc")
        assert r.status_code == 401
