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
        assert "excel" in r.content_type or "xml" in r.content_type or "spreadsheet" in r.content_type

    def test_export_excel_empty(self, admin_client):
        r = admin_client.get("/api/forms/export")
        assert r.status_code == 200

    def test_export_requires_auth(self, client):
        r = client.get("/api/forms/export")
        assert r.status_code == 401

    def test_filter_status_active(self, admin_client):
        _create(admin_client)
        r = admin_client.get("/api/forms/export?status=active")
        assert r.status_code == 200
        # aucun dossier actif → ligne header uniquement (pas de bénéficiaire dans le XML)
        assert b"Durand" not in r.data

    def test_filter_status_draft_includes_form(self, admin_client):
        _create(admin_client)
        r = admin_client.get("/api/forms/export?status=draft")
        assert r.status_code == 200
        assert b"Dupont" in r.data

    def test_filter_service(self, admin_client):
        _create(admin_client, {"beneficiaire": {"nom": "Martin", "prenom": "Paul", "service": "DSI"}})
        _create(admin_client, {"beneficiaire": {"nom": "Girard", "prenom": "Sophie", "service": "RH"}})
        r = admin_client.get("/api/forms/export?service=DSI")
        assert r.status_code == 200
        assert b"Martin" in r.data
        assert b"Girard" not in r.data

    def test_filter_service_case_insensitive(self, admin_client):
        _create(admin_client, {"beneficiaire": {"nom": "Leblanc", "prenom": "Anne", "service": "Informatique"}})
        r = admin_client.get("/api/forms/export?service=informatique")
        assert r.status_code == 200
        assert b"Leblanc" in r.data

    def test_filter_date_from_excludes_old(self, admin_client, app):
        import database
        form_id = _create(admin_client)
        with app.app_context():
            with database.get_db() as conn:
                conn.execute(
                    "UPDATE dotation_forms SET updated_at = '2020-01-01T00:00:00' WHERE id = ?",
                    (form_id,),
                )
        r = admin_client.get("/api/forms/export?date_from=2025-01-01")
        assert r.status_code == 200
        assert b"Dupont" not in r.data

    def test_filter_date_to_includes_old(self, admin_client, app):
        import database
        form_id = _create(admin_client)
        with app.app_context():
            with database.get_db() as conn:
                conn.execute(
                    "UPDATE dotation_forms SET updated_at = '2020-06-15T00:00:00' WHERE id = ?",
                    (form_id,),
                )
        r = admin_client.get("/api/forms/export?date_from=2020-01-01&date_to=2020-12-31")
        assert r.status_code == 200
        assert b"Dupont" in r.data

    def test_no_filter_returns_all(self, admin_client):
        _create(admin_client, {"beneficiaire": {"nom": "Moreau", "prenom": "Louis"}})
        _create(admin_client, {"beneficiaire": {"nom": "Bernard", "prenom": "Claire"}})
        r = admin_client.get("/api/forms/export")
        assert r.status_code == 200
        assert b"Moreau" in r.data
        assert b"Bernard" in r.data


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
