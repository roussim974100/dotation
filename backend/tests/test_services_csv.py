"""Tests de l'import CSV des services (POST /api/admin/services/import-csv)."""

import io


def _csv_file(content, filename="services.csv"):
    return (io.BytesIO(content.encode("utf-8")), filename)


class TestImportServicesCsv:
    def test_import_append(self, admin_client):
        data = {"file": _csv_file("label\nService A\nService B\n")}
        r = admin_client.post(
            "/api/admin/services/import-csv",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["imported"] == 2
        assert body["skipped"] == 0

    def test_import_skips_duplicates(self, admin_client):
        csv = _csv_file("label\nService X\n")
        admin_client.post("/api/admin/services/import-csv", data={"file": csv}, content_type="multipart/form-data")
        csv2 = _csv_file("label\nService X\nService Y\n")
        r = admin_client.post("/api/admin/services/import-csv", data={"file": csv2}, content_type="multipart/form-data")
        body = r.get_json()
        assert body["imported"] == 1
        assert body["skipped"] == 1

    def test_import_no_file(self, admin_client):
        r = admin_client.post("/api/admin/services/import-csv", data={}, content_type="multipart/form-data")
        assert r.status_code == 400
        assert r.get_json()["error"] == "no_file"

    def test_import_missing_label_column(self, admin_client):
        data = {"file": _csv_file("nom\nFoo\n")}
        r = admin_client.post("/api/admin/services/import-csv", data=data, content_type="multipart/form-data")
        assert r.status_code == 400
        assert r.get_json()["error"] == "missing_label_column"

    def test_import_semicolon_delimiter(self, admin_client):
        data = {"file": _csv_file("label;is_active\nService Semi;1\n")}
        r = admin_client.post("/api/admin/services/import-csv", data=data, content_type="multipart/form-data")
        assert r.status_code == 200
        assert r.get_json()["imported"] == 1

    def test_import_replace_mode(self, admin_client):
        csv1 = _csv_file("label\nOld Service\n")
        admin_client.post("/api/admin/services/import-csv", data={"file": csv1}, content_type="multipart/form-data")
        csv2 = _csv_file("label\nNew Service\n")
        r = admin_client.post(
            "/api/admin/services/import-csv",
            data={"file": csv2, "mode": "replace"},
            content_type="multipart/form-data",
        )
        assert r.status_code == 200

    def test_import_requires_auth(self, client):
        data = {"file": _csv_file("label\nTest\n")}
        r = client.post("/api/admin/services/import-csv", data=data, content_type="multipart/form-data")
        assert r.status_code == 401

    def test_import_requires_permission(self, redac_client):
        data = {"file": _csv_file("label\nTest\n")}
        r = redac_client.post("/api/admin/services/import-csv", data=data, content_type="multipart/form-data")
        assert r.status_code == 403
