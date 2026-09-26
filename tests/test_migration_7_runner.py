"""3.64.1 : la migration 7 doit s'executer AVEC le lanceur reel (`run_pending_migrations`), pas seulement en appel direct.
Elle appelait `ensure_units_schema`, dont l'`executescript` valide la transaction en cours et detruit le point de sauvegarde
(SAVEPOINT) du lanceur : « no such savepoint: migration » au demarrage sur une base contenant des dossiers « mise a jour »."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_db
from migrations import run_pending_migrations

H = {"X-CSRF-Token": "jeton"}
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _client():
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = "admin"
        flask_session["csrf_token"] = "jeton"
    return client


def test_migration_7_s_execute_dans_le_lanceur_sur_une_base_avec_dossiers_mise_a_jour():
    client = _client()
    source = client.post("/api/forms", headers=H, json={
        "dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "LANCEUR", "prenom": "Sept", "qualite": "agent"},
        "resources": {"additional": [{"id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel", "requiresReturn": True,
                                      "selected": True, "fields": {"marque": "X"}, "details": "", "assignedAt": "2026-09-01T09:00:00"}]},
        "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}})
    source_id = source.get_json()["summary"]["id"]
    client.post("/api/forms", headers=H, json={
        "dossier": {"type": "mise_a_jour", "sourceFormId": source_id}, "beneficiaire": {"nom": "LANCEUR", "prenom": "Sept", "qualite": "agent"},
        "resources": {"additional": []}, "retraits": {"items": {"ordinateur": {"selected": True, "etat": "Bon", "notes": ""}}},
        "workflow": {"status": "draft"}, "meta": {}})

    with get_db() as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 7")
        connection.commit()
    with get_db() as connection:
        applied = run_pending_migrations(connection)  # ne doit ni lever, ni etre annulee
        connection.commit()
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert applied == [7]
    assert 7 in versions
