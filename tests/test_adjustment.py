"""3.63.0 : ajustement d'un dossier actif (PATCH /api/forms/<id>/ajustement) : ajouter / retirer des ressources et changer le
service en une transaction, une signature par geste (presentiel, a distance, impossible + signataire de substitution), dossier
qui reste actif et verrouille, permission dediee, verrou optimiste. Base temporaire (tests/conftest.py)."""
import copy
import json
import sys
from pathlib import Path

import bcrypt
import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_db
from models.adjustment import apply_adjustment, held_resource_keys
from utils import AppError

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


def telephone():
    return {"id": 2, "code": "telephone", "label": "Téléphone", "category": "materiel", "requiresReturn": True,
            "selected": True, "fields": {"marque": "Y"}, "details": "", "assignedAt": "2026-09-01T09:00:00"}


def create_active_dossier(client, nom="AJUSTEMENT", resources=None):
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": resources or [ordinateur(), telephone()]},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}
    created = client.post("/api/forms", json=body, headers=H)
    assert created.status_code in (200, 201), created.get_data(as_text=True)[:300]
    form_id = created.get_json()["summary"]["id"]
    assert client.get(f"/api/forms/{form_id}").get_json()["summary"]["status"] == "active"
    return form_id


def presentiel():
    return {"mode": "presentiel", "signatureDataUrl": PNG}


def patch(client, form_id, body):
    return client.patch(f"/api/forms/{form_id}/ajustement", json=body, headers=H)


def dossier(client, form_id):
    return client.get(f"/api/forms/{form_id}").get_json()


def test_ajout_retrait_et_service_en_une_transaction_le_dossier_reste_actif_et_verrouille():
    client = client_for()
    form_id = create_active_dossier(client)
    response = patch(client, form_id, {
        "ajouts": [{"id": 3, "code": "tablette", "label": "Tablette", "category": "materiel", "fields": {"marque": "Z"}}],
        "retraits": [{"key": "ordinateur", "state": "degrade", "notes": "écran fissuré"}],
        "service": "Finances", "signature": presentiel()})
    assert response.status_code == 200, response.get_data(as_text=True)
    event = response.get_json()["ajustement"]
    assert event["status"] == "signed" and "data:image" not in response.get_data(as_text=True)  # jamais l'image de la signature
    assert response.get_json()["summary"]["status"] == "active"
    data = dossier(client, form_id)["data"]
    assert data["workflow"]["status"] == "active" and data["meta"]["lockedAt"]
    assert data["beneficiaire"]["service"] == "Finances"
    assert {r["code"] for r in data["resources"]["additional"]} == {"ordinateur", "telephone", "tablette"}
    assert data["restitution"]["items"]["ordinateur"]["state"] == "degrade"
    assert "telephone" not in data["restitution"]["items"]  # le reste du dossier n'est pas touché
    assert len(data["ajustements"]) == 1 and data["ajustements"][0]["service"] == {"from": "DRH", "to": "Finances"}
    assert data["ajustements"][0]["retraits"][0]["label"] == "Ordinateur"
    with get_db() as connection:
        rows = {r["item_key"]: r["returned"] for r in connection.execute("SELECT item_key, returned FROM dotation_items WHERE form_id = ?", (form_id,))}
    assert rows["ordinateur"] == 1 and rows["telephone"] == 0 and rows["tablette"] == 0  # projection resynchronisée


def test_service_seul_change_la_fiche_de_la_personne():
    client = client_for()
    form_id = create_active_dossier(client, nom="SERVICESEUL")
    assert patch(client, form_id, {"service": "Voirie", "signature": presentiel()}).status_code == 200
    with get_db() as connection:
        service = connection.execute("SELECT p.service FROM persons p JOIN onboarding_dossiers d ON d.person_id = p.id "
                                     "JOIN dotation_forms f ON f.dossier_id = d.id WHERE f.id = ?", (form_id,)).fetchone()[0]
    assert service == "Voirie"


@pytest.mark.parametrize("body, code, status", [
    ({"signature": presentiel()}, "empty_adjustment", 400),
    ({"service": "X"}, "signature_mode_required", 400),
    ({"service": "X", "signature": {"mode": "presentiel"}}, "signature_required", 400),
    ({"retraits": [{"key": "inexistant"}], "signature": presentiel()}, "not_held", 409),
    ({"ajouts": [{"code": "ordinateur", "label": "Ordinateur"}], "signature": presentiel()}, "already_held", 409),
    ({"ajouts": [{"label": "Sans code"}], "signature": presentiel()}, "invalid_addition", 400),
    ({"retraits": [{"key": "ordinateur", "state": "cassé"}], "signature": presentiel()}, "invalid_state", 400),
    ({"service": "X", "signature": {"mode": "impossible", "substitute": {"name": "Chef", "quality": "DGS"}}}, "signature_reason_required", 400),
    ({"service": "X", "signature": {"mode": "impossible", "reason": "absent"}}, "substitute_required", 400),
])
def test_refus_et_rien_n_est_enregistre(body, code, status):
    client = client_for()
    form_id = create_active_dossier(client, nom="REFUS" + code.upper())
    before = dossier(client, form_id)["data"]
    response = patch(client, form_id, body)
    assert (response.status_code, response.get_json()["error"]) == (status, code)
    after = dossier(client, form_id)["data"]
    assert after.get("ajustements") in (None, []) and after["beneficiaire"]["service"] == before["beneficiaire"]["service"]


def test_ressource_ajoutee_incomplete_refusee_sans_deverrouiller_le_dossier():
    client = client_for()
    form_id = create_active_dossier(client, nom="INCOMPLET")
    incomplete = {"id": 9, "code": "badge", "label": "Badge", "category": "materiel", "fields": {},
                  "fieldSchema": [{"id": "fld_n", "key": "numero", "label": "N°", "type": "text", "required": True}]}
    response = patch(client, form_id, {"ajouts": [incomplete], "signature": presentiel()})
    assert response.status_code == 400 and response.get_json()["error"] == "resource_incomplete"
    assert dossier(client, form_id)["summary"]["status"] == "active"


def test_dossier_non_actif_refuse():
    client = client_for()
    created = client.post("/api/forms", json={"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "BROUILLON", "prenom": "T", "qualite": "agent"},
                                              "resources": {"additional": []}, "workflow": {"status": "draft"}, "meta": {}}, headers=H)
    response = patch(client, created.get_json()["summary"]["id"], {"service": "X", "signature": presentiel()})
    assert (response.status_code, response.get_json()["error"]) == (409, "not_adjustable")


def test_signature_a_distance_puis_recueillie_et_signature_impossible_avec_substitut():
    client = client_for()
    form_id = create_active_dossier(client, nom="DISTANCE")
    event = patch(client, form_id, {"service": "Archives", "signature": {"mode": "distance"}}).get_json()["ajustement"]
    assert event["status"] == "pending_signature"
    url = f"/api/forms/{form_id}/ajustement/{event['id']}/signature"
    assert client.post(url, json={"mode": "distance"}, headers=H).status_code == 400  # rien à recueillir
    signed = client.post(url, json=presentiel(), headers=H)
    assert signed.status_code == 200 and signed.get_json()["ajustement"]["status"] == "signed"
    assert client.post(url, json=presentiel(), headers=H).get_json()["error"] == "already_signed"
    assert client.post(f"/api/forms/{form_id}/ajustement/inconnu/signature", json=presentiel(), headers=H).status_code == 404

    pending = patch(client, form_id, {"service": "Culture", "signature": {"mode": "distance"}}).get_json()["ajustement"]
    substitute = client.post(f"/api/forms/{form_id}/ajustement/{pending['id']}/signature", headers=H,
                             json={"mode": "impossible", "reason": "agent en congé", "substitute": {"name": "M. Durand", "quality": "Responsable de service"}})
    result = substitute.get_json()["ajustement"]
    assert result["status"] == "signed_by_substitute" and result["signature"]["substitute"]["name"] == "M. Durand"
    events = dossier(client, form_id)["data"]["ajustements"]
    assert [e["status"] for e in events] == ["signed", "signed_by_substitute"]


def test_permission_dediee_et_verrou_optimiste():
    from auth import create_user, delete_user
    create_user("sans.ajustement", bcrypt.hashpw(b"MotDePasse-Complexe-1!", bcrypt.gensalt()).decode(), ["lecture"])
    try:
        admin = client_for()
        form_id = create_active_dossier(admin, nom="PERMISSION")
        forbidden = patch(client_for("sans.ajustement"), form_id, {"service": "X", "signature": presentiel()})
        assert forbidden.status_code == 403
    finally:
        delete_user("sans.ajustement")
    stale = patch(admin, form_id, {"service": "X", "signature": presentiel(), "baseSavedAt": "2000-01-01T00:00:00"})
    assert (stale.status_code, stale.get_json()["error"]) == (409, "form_conflict")
    fresh = dossier(admin, form_id)["data"]["meta"]["savedAt"]
    assert patch(admin, form_id, {"service": "X", "signature": presentiel(), "baseSavedAt": fresh}).status_code == 200


def test_anonyme_refuse():
    assert app.test_client().patch("/api/forms/x/ajustement", json={}).status_code in (401, 403)


def test_fonctions_pures():
    payload = {"workflow": {"status": "active"}, "beneficiaire": {"nom": "A", "prenom": "B", "service": "S"},
               "resources": {"additional": [ordinateur()]}}
    assert held_resource_keys(payload) == {"ordinateur"}
    with pytest.raises(AppError) as error:
        apply_adjustment(copy.deepcopy(payload), {"retraits": [{"key": "ordinateur"}, {"key": "ordinateur"}], "signature": presentiel()}, "moi")
    assert error.value.code in ("not_held", "duplicate_gesture")
    _, event = apply_adjustment(copy.deepcopy(payload), {"retraits": [{"key": "ordinateur"}], "signature": {"mode": "distance"}}, "moi", now="2026-09-26T12:00:00")
    assert event["at"] == "2026-09-26T12:00:00" and event["by"] == "moi" and event["status"] == "pending_signature"
