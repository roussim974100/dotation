"""22/11 : blocage (plus seulement avertissement) d'un numéro de série déjà attribué à un autre dossier actif
(persist_form, code resource_already_held) + toast « Annuler » après suppression d'un dossier
(DELETE /api/forms/<id> renvoie trash_id, POST /api/forms/trash/<id>/restore)."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_db

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


def test_reenregistrer_sans_toucher_au_numero_devenu_conflictuel_n_est_pas_bloque():
    """23/11 (constat réel sur une fiche d'arrivée) : un dossier déjà enregistré, dont le matériel a depuis été
    légitimement réattribué à un autre dossier actif, ne doit pas empêcher d'enregistrer une modification qui
    ne touche pas à ce champ (le conflit n'est pas créé par cette sauvegarde). Seule une saisie qui change
    cette valeur reste bloquée si elle crée un nouveau conflit.
    Le conflit préexistant (matériel réattribué depuis que ce dossier a été enregistré) ne peut plus être
    recréé par l'API elle-même (le blocage est désormais systématique) : on simule la donnée historique par
    une écriture directe, comme elle a pu exister avant l'introduction de ce blocage (22/11)."""
    client = client_for()
    nouveau = create_dossier(client, "NOUVEAU", serial="SN-LIBRE", status="draft")
    assert nouveau.status_code == 201, nouveau.get_data(as_text=True)[:300]
    form_id = nouveau.get_json()["summary"]["id"]

    ancien = create_dossier(client, "ANCIEN", serial="SN-STALE-2")
    assert ancien.status_code == 201, ancien.get_data(as_text=True)[:300]

    # Donnée historique simulée : la fiche de NOUVEAU porte encore ce numéro de série, devenu obsolète
    # depuis qu'ANCIEN détient réellement l'unité (écriture directe, hors API, pour reproduire un état
    # antérieur au blocage du 22/11).
    import json as _json
    with get_db() as connection:
        row = connection.execute("SELECT payload_json FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
        stale_payload = _json.loads(row["payload_json"])
        stale_payload["resources"]["additional"][0]["fields"]["numeroSerie"] = "SN-STALE-2"
        connection.execute("UPDATE dotation_forms SET payload_json = ? WHERE id = ?",
                            (_json.dumps(stale_payload, ensure_ascii=False), form_id))

    # NOUVEAU rouvre sa fiche et l'enregistre sans toucher au matériel : pas bloqué.
    payload = client.get(f"/api/forms/{form_id}").get_json()["data"]
    payload["beneficiaire"]["fonction"] = "Agent administratif"
    updated = client.put(f"/api/forms/{form_id}", json=payload, headers=H)
    assert updated.status_code == 200, updated.get_data(as_text=True)[:300]

    # Mais une saisie qui change réellement ce champ vers une autre valeur déjà prise ailleurs reste bloquée.
    payload["resources"]["additional"][0]["fields"]["numeroSerie"] = "SN-STALE-2-AUTRE"
    ancien2 = create_dossier(client, "ANCIEN2", serial="SN-STALE-2-AUTRE")
    assert ancien2.status_code == 201, ancien2.get_data(as_text=True)[:300]
    blocked = client.put(f"/api/forms/{form_id}", json=payload, headers=H)
    assert blocked.status_code == 409, blocked.get_data(as_text=True)[:300]
    assert blocked.get_json()["error"] == "resource_already_held"


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
