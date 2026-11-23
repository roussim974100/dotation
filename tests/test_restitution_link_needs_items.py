"""3.73.2 : pas de lien de signature de restitution tant que l'etat du materiel (Phase 2) n'est pas enregistre :
le signataire verrait un recapitulatif vide. Base temporaire (tests/conftest.py)."""
import json
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_db

H = {"X-CSRF-Token": "jeton"}
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = user
        flask_session["csrf_token"] = "jeton"
    return client


def set_restitution(form_id, restitution):
    with get_db() as connection:
        row = connection.execute("SELECT payload_json FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
        payload = json.loads(row["payload_json"])
        payload["restitution"] = restitution
        connection.execute("UPDATE dotation_forms SET payload_json = ? WHERE id = ?", (json.dumps(payload), form_id))


def test_lien_refuse_sans_etat_du_materiel_puis_accepte():
    client = client_for()
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "SANSITEMS", "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": []}, "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}
    created = client.post("/api/forms", json=body, headers=H)
    form_id = created.get_json()["summary"]["id"]

    set_restitution(form_id, {"returnedAt": "2026-09-28", "items": {}})
    refused = client.post(f"/api/forms/{form_id}/restitution-signature-link", json={}, headers=H)
    assert refused.status_code == 400
    assert refused.get_json()["error"] == "restitution_items_missing"
    assert "état du matériel" in refused.get_json()["message"]

    set_restitution(form_id, {"returnedAt": "2026-09-28", "items": {"ordinateur": {"state": "conforme"}}})
    accepted = client.post(f"/api/forms/{form_id}/restitution-signature-link", json={}, headers=H)
    assert accepted.status_code == 201, accepted.get_data(as_text=True)
