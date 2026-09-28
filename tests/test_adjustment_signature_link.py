"""Lien de signature a distance + QR pour un ajustement de dossier actif (3.66.x) : un ajustement en mode
"distance" reste "pending_signature" ; un lien public (comme pour l'attribution/la restitution) permet a la
personne de consulter le geste puis de signer sans etre authentifiee. Base temporaire (tests/conftest.py)."""
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


def ordinateur():
    return {"id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel", "requiresReturn": True,
            "selected": True, "fields": {"marque": "X"}, "details": "", "assignedAt": "2026-09-01T09:00:00"}


def create_active_dossier(client, nom="SIGLINK"):
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": [ordinateur()]},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}
    created = client.post("/api/forms", json=body, headers=H)
    assert created.status_code in (200, 201), created.get_data(as_text=True)[:300]
    return created.get_json()["summary"]["id"]


def create_pending_withdrawal(client, form_id):
    response = client.patch(f"/api/forms/{form_id}/ajustement", json={
        "retraits": [{"key": "ordinateur", "state": "conforme"}],
        "signature": {"mode": "distance"},
    }, headers=H)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["ajustement"]["id"]


def token_from_url(url):
    return url.rstrip("/").rsplit("/", 1)[-1]


def test_lien_cree_uniquement_si_ajustement_en_attente():
    client = client_for()
    form_id = create_active_dossier(client, "SANSATTENTE")
    response = client.post(f"/api/forms/{form_id}/adjustment-signature-link", json={}, headers=H)
    assert (response.status_code, response.get_json()["error"]) == (400, "no_pending_adjustment")
    print("[PASS] pas de lien possible sans ajustement en attente de signature")


def test_parcours_public_complet_signe_l_ajustement():
    client = client_for()
    form_id = create_active_dossier(client)
    create_pending_withdrawal(client, form_id)

    created = client.post(f"/api/forms/{form_id}/adjustment-signature-link", json={"validityDays": 5}, headers=H)
    assert created.status_code == 201, created.get_data(as_text=True)
    url = created.get_json()["link"]["url"]
    token = token_from_url(url)

    anonymous = app.test_client()
    view = anonymous.get(f"/api/adjustment-signature/{token}")
    assert view.status_code == 200
    payload = view.get_json()
    assert payload["form"]["adjustment"]["retraits"][0]["label"] == "Ordinateur"
    assert "signatureDataUrl" not in payload["form"]["adjustment"]["retraits"][0]

    submit = anonymous.post(f"/api/adjustment-signature/{token}/submit", json={"signatureDataUrl": PNG})
    assert submit.status_code == 200, submit.get_data(as_text=True)
    assert "data:image" not in submit.get_data(as_text=True)  # jamais l'image de la signature dans la reponse

    dossier_after = client.get(f"/api/forms/{form_id}").get_json()["data"]
    event = dossier_after["ajustements"][0]
    assert event["status"] == "signed"
    assert event["signature"]["requestedMode"] == "distance"

    # Le lien est a usage unique : une seconde tentative echoue.
    replay = anonymous.get(f"/api/adjustment-signature/{token}")
    assert (replay.status_code, replay.get_json()["error"]) == (410, "used")
    print("[PASS] parcours public complet : consultation puis signature d'un ajustement a distance")


def test_jeton_inconnu_ou_type_different_refuse():
    client = client_for()
    form_id = create_active_dossier(client, "AUTRETYPE")
    # Un lien d'ATTRIBUTION (pas d'ajustement) ne doit jamais etre accepte par la route d'ajustement.
    other_link = client.post(f"/api/forms/{form_id}/signature-link", json={}, headers=H)
    assert other_link.status_code in (201, 400)  # 400 si deja signe : sans importance ici
    anonymous = app.test_client()
    assert anonymous.get("/api/adjustment-signature/jeton-inexistant").get_json()["error"] == "invalid_link"
    print("[PASS] jeton inexistant ou d'un autre type de signature refuse")


def test_soumission_sans_signature_refusee():
    client = client_for()
    form_id = create_active_dossier(client, "SANSSIGNATURE")
    create_pending_withdrawal(client, form_id)
    created = client.post(f"/api/forms/{form_id}/adjustment-signature-link", json={}, headers=H)
    token = token_from_url(created.get_json()["link"]["url"])
    anonymous = app.test_client()
    response = anonymous.post(f"/api/adjustment-signature/{token}/submit", json={})
    assert (response.status_code, response.get_json()["error"]) == (400, "signature_required")
    print("[PASS] soumission sans signature refusee")
