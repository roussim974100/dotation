"""22/11 : la colonne Progression/Pilotage reflete l'avancement REEL de la restitution (objets rendus), pas la
complétude de la saisie à l'attribution — constat sur un dossier de régularisation affiché à "0/4" alors que
3 objets sur 4 étaient bien rendus (voir CHANGELOG). Nouvel état "mutualisé" pour un objet qui ne repasse jamais
individuellement par le stock (ex. PC de télétravail transféré directement)."""
import sys
from datetime import date, timedelta
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_db
from models.workflow import summarize_restitution_progress

H = {"X-CSRF-Token": "jeton"}
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = user
        flask_session["csrf_token"] = "jeton"
    return client


def resource(code, state=None, requires_return=True):
    item = {"id": code, "code": code, "label": code, "category": "materiel", "selected": True, "requiresReturn": requires_return}
    return item, ({code: state} if state else {})


def _payload(resources_and_states, missionEndAt=None, closed_despite_missing=False):
    additional = []
    items = {}
    for resource_entry, state_entry in resources_and_states:
        additional.append(resource_entry)
        items.update(state_entry)
    restitution = {"items": items}
    if missionEndAt:
        restitution["missionEndAt"] = missionEndAt
    if closed_despite_missing:
        restitution["closedDespiteMissingItems"] = True
    return {"resources": {"additional": additional}, "restitution": restitution}


def test_un_objet_non_restitue_compte_comme_non_resolu_meme_regularisation():
    """Reproduit le cas Camille : 3 objets rendus (conforme), 1 non restitue, aucun champ "fields" rempli
    (regularisation). L'ancien calcul (completude de saisie) aurait dit 0/4 ; le nouveau dit 3/4."""
    payload = _payload([
        resource("ordinateur", {"state": "conforme"}),
        resource("ecran", {"state": "conforme"}),
        resource("autre", {"state": "conforme"}),
        resource("souris", {"state": "non_restitue"}),
    ], missionEndAt="2026-09-01")
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (3, 4)
    assert result["ratio"] == 0.75


def test_perdu_et_autre_comptent_comme_resolus_pas_bloquants():
    payload = _payload([
        resource("badge", {"state": "perdu"}),
        resource("cles", {"state": "autre"}),
    ])
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (2, 2)
    assert result["timingLabel"] == "Restitution terminée"


def test_mutualise_compte_comme_resolu():
    payload = _payload([resource("ordinateur", {"state": "mutualise", "notes": "Transfere a DURAND"})])
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (1, 1)
    assert result["timingStatus"] == "ok"


def test_objet_sans_obligation_de_retour_exclu_du_total():
    payload = _payload([
        resource("email", {"state": "non_restitue"}, requires_return=False),
        resource("ordinateur", {"state": "conforme"}),
    ])
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (1, 1)


def test_ressource_immaterielle_ancien_format_evaluee_via_immateriel_actions():
    """Reproduit le cas Dominique/Alexia : "email" (immateriel, ancien format) compte dans le total (2/3, pas
    2/2 - ce n'est pas une raison de le faire disparaitre), mais sa resolution se lit dans
    restitution.immaterielActions (actionDone), jamais dans restitution.items (toujours "pending" pour elle,
    donc a tort "jamais rendu" si on la traitait comme un objet materiel)."""
    payload = {
        "materiel": {"ordinateur": {"selected": True}, "telephone": {"selected": True}},
        "immateriel": {"email": {"selected": True}},
        "restitution": {"items": {
            "ordinateur": {"state": "degrade"},
            "telephone": {"state": "degrade"},
        }, "immaterielActions": {}},
    }
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (2, 3)  # email jamais traite : non resolu
    assert result["timingLabel"] != "Restitution terminée"

    payload["restitution"]["immaterielActions"] = {"email": {"actionToDo": "desactiver", "actionDone": "desactive"}}
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (3, 3)
    assert result["timingLabel"] == "Restitution terminée"


def test_restitution_en_retard_si_date_depassee_au_dela_du_seuil():
    old_date = (date.today() - timedelta(days=30)).isoformat()
    payload = _payload([resource("ordinateur", {"state": "non_restitue"})], missionEndAt=old_date)
    result = summarize_restitution_progress(payload, warning_days=3)
    assert result["timingStatus"] == "late"
    assert result["timingLabel"] == "Restitution en retard"


def test_restitution_en_cours_si_date_recente():
    recent_date = date.today().isoformat()
    payload = _payload([resource("ordinateur", {"state": "non_restitue"})], missionEndAt=recent_date)
    result = summarize_restitution_progress(payload, warning_days=3)
    assert result["timingStatus"] == "warning"
    assert result["timingLabel"] == "Restitution en cours"


def test_cloture_malgre_tout_affiche_termine_sans_mentir_sur_la_fraction():
    """closedDespiteMissingItems (3.74.1) : la fraction reste honnete (3/4), mais Pilotage ne dit plus
    "en retard" puisqu'il n'y a plus rien a relancer administrativement."""
    payload = _payload([
        resource("ordinateur", {"state": "conforme"}),
        resource("ecran", {"state": "conforme"}),
        resource("autre", {"state": "conforme"}),
        resource("souris", {"state": "non_restitue"}),
    ], missionEndAt="2026-09-01", closed_despite_missing=True)
    result = summarize_restitution_progress(payload)
    assert (result["completed"], result["total"]) == (3, 4)
    assert result["timingStatus"] == "ok"
    assert result["timingLabel"] == "Clôturé malgré du matériel manquant"


def test_aucun_objet_a_restituer():
    result = summarize_restitution_progress({"resources": {"additional": []}, "restitution": {"items": {}}})
    assert (result["completed"], result["total"]) == (0, 0)
    assert result["timingLabel"] == "Aucun objet à restituer"


def _incomplete_resource():
    """Champ requis jamais rempli : complet au sens "restitution" (si rendu), incomplet au sens "attribution"."""
    return {"id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel", "selected": True,
            "fieldSchema": [{"key": "marque", "label": "Marque", "required": True}], "fields": {}}


def test_le_resume_api_utilise_la_completude_d_attribution_hors_phase_de_restitution():
    client = client_for()
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "ACTIF", "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": [_incomplete_resource()]},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}}
    created = client.post("/api/forms", json=body, headers=H)
    assert created.status_code == 201, created.get_data(as_text=True)[:300]
    form_id = created.get_json()["summary"]["id"]

    summary = client.get(f"/api/forms/{form_id}").get_json()["summary"]
    assert summary["status"] == "partial_assignment"  # champ requis manquant : pas encore "active"
    assert (summary["completedResources"], summary["totalResources"]) == (0, 1)


def test_le_resume_api_bascule_sur_la_completude_de_restitution_une_fois_en_cours():
    client = client_for()
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "BASCULE", "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": [_incomplete_resource()]},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}}
    created = client.post("/api/forms", json=body, headers=H)
    form_id = created.get_json()["summary"]["id"]
    with get_db() as connection:
        connection.execute("UPDATE dotation_forms SET payload_json = json_set(payload_json, '$.restitution.phase1ValidatedAt', '2026-11-20T08:00:00+00:00') WHERE id = ?", (form_id,))

    patched = client.patch(f"/api/forms/{form_id}/restitution", json={
        "returnedAt": "2026-11-20",
        "items": {"ordinateur": {"state": "conforme", "returned": True, "returnedAt": "2026-11-20", "condition": "conforme", "notes": ""}},
        "signatureStatus": "signed", "signatureDataUrl": PNG,
    }, headers=H)
    assert patched.status_code == 200, patched.get_data(as_text=True)[:300]

    summary = client.get(f"/api/forms/{form_id}").get_json()["summary"]
    assert summary["status"] == "returned"
    # Le champ "marque" est toujours vide (incomplet au sens attribution) mais l'objet a ete rendu :
    # la restitution doit se dire "terminee", pas "0/1" comme avant ce correctif.
    assert (summary["completedResources"], summary["totalResources"]) == (1, 1)
    assert summary["timingLabel"] == "Restitution terminée"
