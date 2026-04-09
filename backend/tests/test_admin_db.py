"""Tests pour les routes admin DB : export, diagnose, import.
Les routes sont protégées par la permission db.manage (wildcard admin seulement).
"""

import io
import sqlite3
import tempfile
import os


def _make_valid_db_bytes():
    """Crée un fichier SQLite minimal valide en mémoire."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    with open(path, "rb") as fh:
        data = fh.read()
    os.unlink(path)
    return data


class TestDbExport:
    def test_requires_auth(self, client):
        r = client.get("/api/admin/db/export")
        assert r.status_code == 401

    def test_requires_db_manage_permission(self, redac_client):
        r = redac_client.get("/api/admin/db/export")
        assert r.status_code == 403

    def test_returns_binary(self, admin_client):
        r = admin_client.get("/api/admin/db/export")
        assert r.status_code == 200
        assert r.content_type == "application/octet-stream"
        # Un fichier SQLite valide commence par ce magic bytes
        assert r.data[:16] == b"SQLite format 3\x00"

    def test_filename_in_header(self, admin_client):
        r = admin_client.get("/api/admin/db/export")
        disposition = r.headers.get("Content-Disposition", "")
        assert "aquai_db_" in disposition
        assert ".db" in disposition


class TestDbDiagnose:
    def test_requires_auth(self, client):
        data = _make_valid_db_bytes()
        r = client.post(
            "/api/admin/db/diagnose",
            data={"file": (io.BytesIO(data), "test.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 401

    def test_requires_db_manage_permission(self, redac_client):
        data = _make_valid_db_bytes()
        r = redac_client.post(
            "/api/admin/db/diagnose",
            data={"file": (io.BytesIO(data), "test.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 403

    def test_missing_file_returns_400(self, admin_client):
        r = admin_client.post("/api/admin/db/diagnose", data={}, content_type="multipart/form-data")
        assert r.status_code == 400
        assert r.get_json()["error"] == "no_file"

    def test_valid_db_returns_report(self, admin_client):
        data = _make_valid_db_bytes()
        r = admin_client.post(
            "/api/admin/db/diagnose",
            data={"file": (io.BytesIO(data), "test.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        report = r.get_json()
        assert "level" in report

    def test_corrupt_file_returns_error_level(self, admin_client):
        corrupt = b"this is not a sqlite file at all!!"
        r = admin_client.post(
            "/api/admin/db/diagnose",
            data={"file": (io.BytesIO(corrupt), "corrupt.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        report = r.get_json()
        assert report["level"] == "error"

    def test_too_large_file_rejected(self, admin_client):
        # 201 MB dépasse la limite (200 MB)
        big = b"X" * (201 * 1024 * 1024)
        r = admin_client.post(
            "/api/admin/db/diagnose",
            data={"file": (io.BytesIO(big), "big.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "file_too_large"


class TestDbImport:
    def test_requires_auth(self, client):
        data = _make_valid_db_bytes()
        r = client.post(
            "/api/admin/db/import",
            data={"file": (io.BytesIO(data), "import.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 401

    def test_requires_db_manage_permission(self, redac_client):
        data = _make_valid_db_bytes()
        r = redac_client.post(
            "/api/admin/db/import",
            data={"file": (io.BytesIO(data), "import.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 403

    def test_missing_file_returns_400(self, admin_client):
        r = admin_client.post("/api/admin/db/import", data={}, content_type="multipart/form-data")
        assert r.status_code == 400

    def test_corrupt_file_rejected(self, admin_client):
        corrupt = b"not a sqlite db"
        r = admin_client.post(
            "/api/admin/db/import",
            data={"file": (io.BytesIO(corrupt), "bad.db")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 422
        assert r.get_json()["error"] == "diagnose_failed"
