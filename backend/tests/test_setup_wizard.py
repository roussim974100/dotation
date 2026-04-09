"""Tests pour le setup wizard et le conflict-check beneficiary_types."""

import json


def _seed_form_with_type(app, beneficiary_type):
    """Insère directement un dossier avec un type de bénéficiaire."""
    import uuid
    import database
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO dotation_forms"
            " (id, dossier_type, title, status, beneficiary_type, nom, prenom, payload_json, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "arrivee", "Test", "draft", beneficiary_type,
             "Test", "Seed", json.dumps({}), now, now),
        )


class TestSetupStatus:
    def test_requires_auth(self, client):
        r = client.get("/api/setup/status")
        assert r.status_code == 401

    def test_returns_status_not_completed_by_default(self, admin_client):
        r = admin_client.get("/api/setup/status")
        assert r.status_code == 200
        data = r.get_json()
        assert "setupCompleted" in data
        assert data["setupCompleted"] is False

    def test_returns_org_context(self, admin_client):
        r = admin_client.get("/api/setup/status")
        data = r.get_json()
        assert "orgContext" in data
        assert "beneficiaryTypes" in data


class TestSetupComplete:
    def test_requires_auth(self, client):
        r = client.post("/api/setup/complete", json={})
        assert r.status_code == 401

    def test_requires_users_manage_permission(self, redac_client):
        r = redac_client.post("/api/setup/complete", json={})
        assert r.status_code == 403

    def test_marks_setup_as_completed(self, admin_client):
        r = admin_client.post("/api/setup/complete", json={
            "org_name": "Mairie Test",
            "org_context": "public_collectivite",
        })
        assert r.status_code == 200
        status = admin_client.get("/api/setup/status").get_json()
        assert status["setupCompleted"] is True

    def test_saves_org_name(self, admin_client):
        admin_client.post("/api/setup/complete", json={"org_name": "Commune de Test"})
        settings = admin_client.get("/api/admin/settings").get_json()
        assert settings["raw"]["org_name"] == "Commune de Test"

    def test_saves_beneficiary_types(self, admin_client):
        admin_client.post("/api/setup/complete", json={
            "beneficiary_types": "salarie:Salarié,stagiaire:Stagiaire",
        })
        settings = admin_client.get("/api/admin/settings").get_json()
        assert settings["raw"]["beneficiary_types"] == "salarie:Salarié,stagiaire:Stagiaire"


class TestConflictCheck:
    def test_requires_auth(self, client):
        r = client.get("/api/admin/settings/conflict-check?beneficiary_types=agent:Agent")
        assert r.status_code == 401

    def test_requires_users_manage(self, redac_client):
        r = redac_client.get("/api/admin/settings/conflict-check?beneficiary_types=agent:Agent")
        assert r.status_code == 403

    def test_no_conflict_when_db_empty(self, admin_client):
        r = admin_client.get("/api/admin/settings/conflict-check?beneficiary_types=agent:Agent,elu:Élu")
        assert r.status_code == 200
        data = r.get_json()
        assert data["hasConflicts"] is False
        assert data["totalAffected"] == 0

    def test_detects_conflict(self, admin_client, app):
        _seed_form_with_type(app, "agent")
        r = admin_client.get("/api/admin/settings/conflict-check?beneficiary_types=salarie:Salarié")
        assert r.status_code == 200
        data = r.get_json()
        assert data["hasConflicts"] is True
        assert data["totalAffected"] == 1
        assert any(c["type"] == "agent" for c in data["conflicts"])

    def test_no_conflict_when_type_preserved(self, admin_client, app):
        _seed_form_with_type(app, "agent")
        r = admin_client.get("/api/admin/settings/conflict-check?beneficiary_types=agent:Agent,elu:Élu")
        assert r.status_code == 200
        data = r.get_json()
        assert data["hasConflicts"] is False

    def test_counts_multiple_affected(self, admin_client, app):
        _seed_form_with_type(app, "agent")
        _seed_form_with_type(app, "agent")
        _seed_form_with_type(app, "elu")
        r = admin_client.get("/api/admin/settings/conflict-check?beneficiary_types=salarie:Salarié")
        data = r.get_json()
        assert data["totalAffected"] == 3
