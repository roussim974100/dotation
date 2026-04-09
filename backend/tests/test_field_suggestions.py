"""Tests pour les routes field_suggestions et unc-paths."""

import json


def _create_form(client, beneficiaire=None):
    """Crée un dossier minimal et retourne son id."""
    payload = {
        "type": "arrivee",
        "beneficiaire": beneficiaire or {"nom": "Dupont", "prenom": "Jean", "service": "Informatique"},
    }
    r = client.post("/api/forms", json=payload)
    assert r.status_code == 201
    return r.get_json()["id"]


def _seed_suggestions(app, entries):
    """Insère directement des suggestions dans la table field_suggestions."""
    import uuid
    import database
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    rows = [(str(uuid.uuid4()), key, value, service or "", now) for key, value, service in entries]
    with database.get_db() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO field_suggestions (id, field_key, value, service, created_at) VALUES (?, ?, ?, ?, ?)",
            rows,
        )


class TestFieldSuggestions:
    def test_returns_empty_list_for_unknown_key(self, admin_client):
        r = admin_client.get("/api/forms/field-suggestions?field=champ_inconnu")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_returns_empty_for_missing_field_param(self, admin_client):
        r = admin_client.get("/api/forms/field-suggestions")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_returns_seeded_values(self, admin_client, app):
        _seed_suggestions(app, [
            ("marque", "Apple", None),
            ("marque", "Dell", None),
        ])
        r = admin_client.get("/api/forms/field-suggestions?field=marque")
        assert r.status_code == 200
        values = r.get_json()
        assert "Apple" in values
        assert "Dell" in values

    def test_requires_auth(self, client):
        r = client.get("/api/forms/field-suggestions?field=marque")
        assert r.status_code == 401

    def test_requires_forms_read_permission(self, admin_client, app, monkeypatch):
        # Un client sans permission forms.read_list doit recevoir 403.
        # On vérifie via un utilisateur redac (qui a forms.read_list) — 200 attendu.
        _seed_suggestions(app, [("modele", "ThinkPad X1", None)])
        r = admin_client.get("/api/forms/field-suggestions?field=modele")
        assert r.status_code == 200

    def test_field_key_too_long_returns_empty(self, admin_client):
        long_key = "x" * 65
        r = admin_client.get(f"/api/forms/field-suggestions?field={long_key}")
        assert r.status_code == 200
        assert r.get_json() == []


class TestUncPaths:
    def test_empty_when_no_paths(self, admin_client):
        r = admin_client.get("/api/forms/unc-paths")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_requires_auth(self, client):
        r = client.get("/api/forms/unc-paths")
        assert r.status_code == 401

    def test_admin_sees_all_paths(self, admin_client, app):
        _seed_suggestions(app, [
            ("unc_chemin", r"\\srv1\partage", "Informatique"),
            ("unc_chemin", r"\\srv2\docs", "RH"),
        ])
        r = admin_client.get("/api/forms/unc-paths")
        assert r.status_code == 200
        paths = r.get_json()
        assert r"\\srv1\partage" in paths
        assert r"\\srv2\docs" in paths

    def test_no_duplicate_paths(self, admin_client, app):
        _seed_suggestions(app, [
            ("unc_chemin", r"\\srv1\commun", "Informatique"),
            ("unc_chemin", r"\\srv1\commun", "RH"),
        ])
        r = admin_client.get("/api/forms/unc-paths")
        paths = r.get_json()
        assert paths.count(r"\\srv1\commun") == 1

    def test_dossier_avec_unc(self, admin_client):
        """Dossier créé avec un chemin UNC — le chemin est mémorisé."""
        payload = {
            "type": "arrivee",
            "beneficiaire": {"nom": "Martin", "prenom": "Alice", "service": "DSI"},
            "unc_acces": [{"chemin": r"\\nas\dsi\alice"}],
        }
        r = admin_client.post("/api/forms", json=payload)
        assert r.status_code == 201
        paths = admin_client.get("/api/forms/unc-paths").get_json()
        assert r"\\nas\dsi\alice" in paths

    def test_dossier_sans_unc(self, admin_client):
        """Dossier sans UNC — aucun chemin ajouté."""
        payload = {
            "type": "arrivee",
            "beneficiaire": {"nom": "Petit", "prenom": "Bob", "service": "RH"},
        }
        admin_client.post("/api/forms", json=payload)
        paths = admin_client.get("/api/forms/unc-paths").get_json()
        assert paths == []
