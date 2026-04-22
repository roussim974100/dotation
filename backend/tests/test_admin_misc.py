"""Tests des endpoints admin non couverts : unc-stats, logo-upload, logs, csv-template."""

import io
import struct
import zlib


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_FORM = {"beneficiaire": {"nom": "Durand", "prenom": "Marie"}}
_UNC_FORM = {
    **_MINIMAL_FORM,
    "unc_acces": [
        {"chemin": "\\\\SRV\\share", "acces": "lecture", "statut": "demande", "commentaire": ""},
        {"chemin": "\\\\SRV\\data", "acces": "lecture_ecriture", "statut": "provisionne", "commentaire": ""},
    ],
}


def _create(client, payload=None):
    r = client.post("/api/forms", json=payload or _MINIMAL_FORM)
    assert r.status_code == 201
    return r.get_json()["summary"]["id"]


def _minimal_png() -> bytes:
    """Génère un PNG 1×1 pixel valide en mémoire."""
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat_data = zlib.compress(b"\x00\xFF\xFF\xFF")
    idat = chunk(b"IDAT", idat_data)
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


# ---------------------------------------------------------------------------
# GET /api/admin/unc-stats
# ---------------------------------------------------------------------------

class TestUncStats:
    def test_empty_db(self, admin_client):
        r = admin_client.get("/api/admin/unc-stats")
        assert r.status_code == 200
        data = r.get_json()
        assert data["agents"] == 0
        assert data["counts"]["demande"] == 0
        assert data["detail"] == []

    def test_with_unc_entries(self, admin_client):
        _create(admin_client, _UNC_FORM)
        r = admin_client.get("/api/admin/unc-stats")
        assert r.status_code == 200
        data = r.get_json()
        assert data["agents"] == 1
        assert data["counts"]["demande"] == 1
        assert data["counts"]["provisionne"] == 1
        assert len(data["detail"]) == 2

    def test_requires_auth(self, client):
        r = client.get("/api/admin/unc-stats")
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        r = redac_client.get("/api/admin/unc-stats")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/settings/logo-upload
# ---------------------------------------------------------------------------

class TestLogoUpload:
    def test_upload_valid_png(self, admin_client, tmp_path, monkeypatch):
        import routes.admin as admin_module
        monkeypatch.setattr(admin_module, "CUSTOM_BRANDING_DIR", str(tmp_path))
        png = _minimal_png()
        data = {"logo": (io.BytesIO(png), "logo.png")}
        r = admin_client.post(
            "/api/admin/settings/logo-upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 201
        assert r.get_json()["uploaded"] is True

    def test_missing_file(self, admin_client):
        r = admin_client.post("/api/admin/settings/logo-upload", data={}, content_type="multipart/form-data")
        assert r.status_code == 400
        assert r.get_json()["error"] == "logo_required"

    def test_wrong_extension(self, admin_client):
        data = {"logo": (io.BytesIO(b"GIF89a"), "logo.gif")}
        r = admin_client.post(
            "/api/admin/settings/logo-upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "invalid_logo_type"

    def test_invalid_png_magic(self, admin_client):
        # Extension .png mais contenu non-PNG
        data = {"logo": (io.BytesIO(b"\x00" * 100), "logo.png")}
        r = admin_client.post(
            "/api/admin/settings/logo-upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "invalid_logo_type"

    def test_requires_auth(self, client):
        r = client.post("/api/admin/settings/logo-upload", data={}, content_type="multipart/form-data")
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        data = {"logo": (io.BytesIO(b"x"), "logo.png")}
        r = redac_client.post(
            "/api/admin/settings/logo-upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/logs
# ---------------------------------------------------------------------------

class TestAdminLogs:
    def test_empty_returns_paginated(self, admin_client):
        r = admin_client.get("/api/admin/logs")
        assert r.status_code == 200
        data = r.get_json()
        assert "items" in data and "total" in data and "limit" in data and "offset" in data
        assert isinstance(data["items"], list)

    def test_logs_after_login(self, admin_client):
        r = admin_client.get("/api/admin/logs")
        assert r.status_code == 200
        data = r.get_json()
        items = data["items"]
        assert data["total"] >= 1
        assert all("actor" in l and "action_type" in l for l in items)

    def test_search_filter(self, admin_client):
        r = admin_client.get("/api/admin/logs?q=login")
        assert r.status_code == 200
        items = r.get_json()["items"]
        for log in items:
            fields = [
                log.get("actor", ""), log.get("scope", ""), log.get("action_type", ""),
                log.get("action_label", ""), log.get("target_type", ""), log.get("target_id", ""),
            ]
            assert any("login" in str(f).lower() for f in fields)

    def test_limit_param(self, admin_client):
        r = admin_client.get("/api/admin/logs?limit=1")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["items"]) <= 1
        assert "total" in data

    def test_offset_param(self, admin_client):
        r_all = admin_client.get("/api/admin/logs?limit=100&offset=0")
        r_offset = admin_client.get("/api/admin/logs?limit=100&offset=1")
        assert r_all.status_code == 200
        assert r_offset.status_code == 200
        all_items = r_all.get_json()["items"]
        offset_items = r_offset.get_json()["items"]
        if len(all_items) > 1:
            assert offset_items[0]["id"] == all_items[1]["id"]

    def test_requires_auth(self, client):
        r = client.get("/api/admin/logs")
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        r = redac_client.get("/api/admin/logs")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/services/csv-template
# ---------------------------------------------------------------------------

class TestServicesCsvTemplate:
    def test_returns_csv(self, admin_client):
        r = admin_client.get("/api/admin/services/csv-template")
        assert r.status_code == 200
        assert "text/csv" in r.content_type

    def test_has_header_row(self, admin_client):
        r = admin_client.get("/api/admin/services/csv-template")
        text = r.data.decode("utf-8")
        first_line = text.strip().splitlines()[0]
        assert "label" in first_line
        assert "is_active" in first_line

    def test_has_example_rows(self, admin_client):
        r = admin_client.get("/api/admin/services/csv-template")
        lines = r.data.decode("utf-8").strip().splitlines()
        assert len(lines) >= 2  # header + au moins une ligne exemple

    def test_requires_auth(self, client):
        r = client.get("/api/admin/services/csv-template")
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        r = redac_client.get("/api/admin/services/csv-template")
        assert r.status_code == 403
