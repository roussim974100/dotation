"""22/11 : blocage (plus seulement avertissement) d'un numéro de série déjà attribué à un autre dossier actif
(persist_form, code resource_already_held) + toast « Annuler » après suppression d'un dossier
(DELETE /api/forms/<id> renvoie trash_id, POST /api/forms/trash/<id>/restore)."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app

H = {"X-CSRF-Token": "jeton"}


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = user
        flask_session["csrf_token"] = "jeton"
    return client


def ordinateur(serial="SN-DUP-1"):
    return {"id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel", "requiresReturn": True,
            "selected": True, "fieldSchema": [{"key": "numeroSerie", "label": "N° de série"}],
            "fields": {"numeroSerie": serial}, "details": ""}


def create_dossier(client, nom, serial="SN-DUP-1", status="active"):
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": [ordinateur(serial)]}, "workflow": {"status": status}, "meta": {}}
    return client.post("/api/forms", json=body, headers=H)


def test_un_meme_numero_de_serie_bloque_un_second_dossier_actif():
    client = client_for()
    first = create_dossier(client, "PREMIER")
    assert first.status_code == 201, first.get_data(as_text=True)[:300]

    second = create_dossier(client, "SECOND")
    assert second.status_code == 409, second.get_data(as_text=True)[:300]
    assert second.get_json()["error"] == "resource_already_held"


def test_reenregistrer_le_meme_dossier_n_est_pas_bloque_par_sa_propre_unite():
    client = client_for()
    created = create_dossier(client, "MEME_DOSSIER", serial="SN-DUP-2")
    form_id = created.get_json()["summary"]["id"]
    payload = client.get(f"/api/forms/{form_id}").get_json()["data"]
    payload["beneficiaire"]["fonction"] = "Agent technique"  # modification anodine
    updated = client.put(f"/api/forms/{form_id}", json=payload, headers=H)
    assert updated.status_code == 200, updated.get_data(as_text=True)[:300]


def test_suppression_d_un_dossier_renvoie_un_identifiant_de_corbeille_et_se_restaure():
    client = client_for()
    created = create_dossier(client, "A_SUPPRIMER", serial="SN-DUP-9")
    form_id = created.get_json()["summary"]["id"]

    deleted = client.delete(f"/api/forms/{form_id}", headers=H)
    assert deleted.status_code == 200
    trash_id = deleted.get_json()["trash_id"]
    assert trash_id

    assert client.get(f"/api/forms/{form_id}").status_code == 404

    restored = client.post(f"/api/forms/trash/{trash_id}/restore", headers=H)
    assert restored.status_code == 200, restored.get_data(as_text=True)[:300]
    assert client.get(f"/api/forms/{form_id}").status_code == 200

    # Le dossier restauré n'est plus dans la corbeille : une seconde tentative échoue.
    again = client.post(f"/api/forms/trash/{trash_id}/restore", headers=H)
    assert again.status_code == 404
