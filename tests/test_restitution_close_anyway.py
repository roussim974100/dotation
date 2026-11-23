"""22/11 : « Non restitué » ne doit plus bloquer indéfiniment le dossier si l'opérateur confirme explicitement
qu'il faut clôturer malgré tout (ex. matériel mutualisé qui ne repasse jamais individuellement par le stock).
L'objet garde son état réel (« Non restitué ») ; seul le statut agrégé du dossier passe outre (closeAnyway).
Base temporaire (tests/conftest.py)."""
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


def create_active_dossier(client, nom):
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": []}, "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}
    created = client.post("/api/forms", json=body, headers=H)
    assert created.status_code in (200, 201), created.get_data(as_text=True)[:300]
    return created.get_json()["summary"]["id"]


def mark_phase1_validated(form_id):
    with get_db() as connection:
        row = connection.execute("SELECT payload_json FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
        payload = json.loads(row["payload_json"])
        payload.setdefault("restitution", {})["phase1ValidatedAt"] = "2026-11-20T08:00:00+00:00"
        connection.execute("UPDATE dotation_forms SET payload_json = ? WHERE id = ?", (json.dumps(payload), form_id))


def items(mouse_state="non_restitue"):
    return {
        "ordinateur": {"state": "conforme", "returned": True, "returnedAt": "2026-11-20", "condition": "conforme", "notes": ""},
        "souris": {"state": mouse_state, "returned": mouse_state != "non_restitue", "returnedAt": "", "condition": mouse_state, "notes": ""},
    }


def test_un_objet_non_restitue_bloque_le_dossier_sans_confirmation():
    client = client_for()
    form_id = create_active_dossier(client, "SANS_CONFIRMATION")
    mark_phase1_validated(form_id)

    response = client.patch(f"/api/forms/{form_id}/restitution", json={
        "returnedAt": "2026-11-20", "items": items(), "signatureStatus": "signed", "signatureDataUrl": PNG,
    }, headers=H)
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert response.get_json()["summary"]["status"] == "partial_return"


def test_closeanyway_cloture_le_dossier_sans_changer_l_etat_de_l_objet():
    client = client_for()
    form_id = create_active_dossier(client, "AVEC_CONFIRMATION")
    mark_phase1_validated(form_id)

    response = client.patch(f"/api/forms/{form_id}/restitution", json={
        "returnedAt": "2026-11-20", "items": items(), "signatureStatus": "signed", "signatureDataUrl": PNG,
        "closeAnyway": True,
    }, headers=H)
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert response.get_json()["summary"]["status"] == "returned"

    dossier = client.get(f"/api/forms/{form_id}").get_json()["data"]
    assert dossier["restitution"]["items"]["souris"]["state"] == "non_restitue"  # l'historique reste honnete
    assert dossier["restitution"]["closedDespiteMissingItems"] is True


def test_compute_effective_workflow_status_ne_fait_pas_regresser_un_dossier_clos_malgre_tout():
    """compute_effective_workflow_status (utilise par persist_form pour TOUT enregistrement, pas seulement le
    PATCH restitution) doit lire le drapeau persiste plutot que de recalculer « en cours » a chaque fois que
    l'objet mutualise reste « non restitue » dans les donnees."""
    from models.workflow import compute_effective_workflow_status

    payload = {
        "workflow": {"status": "returned"},
        "restitution": {
            "items": items(), "returnedAt": "2026-11-20", "signatureStatus": "signed", "signatureDataUrl": PNG,
            "closedDespiteMissingItems": True,
        },
    }
    assert compute_effective_workflow_status(payload) == "returned"

    payload["restitution"]["closedDespiteMissingItems"] = False
    assert compute_effective_workflow_status(payload) == "partial_return"


def test_page_de_diagnostic_accessible_connecte():
    client = client_for()
    response = client.get("/restitution-blocage.html")
    assert response.status_code == 200
    assert b"restitution-blocage.js" in response.data


def test_closeanyway_reserve_a_forms_restitution_force_pas_a_forms_restitution_seul():
    """forms.restitution (restitutions normales) ne doit pas suffire a passer outre un objet non restitue :
    c'est un droit sensible, distinct, reserve a l'administrateur par defaut (voir AGENTS.md)."""
    import bcrypt
    from auth import create_user, delete_user

    create_user("sans.force", bcrypt.hashpw(b"MotDePasse-Complexe-1!", bcrypt.gensalt()).decode(), ["gestion"])
    try:
        admin = client_for()
        form_id = create_active_dossier(admin, "DROIT_LIMITE")
        mark_phase1_validated(form_id)
        limited = client_for("sans.force")

        forbidden = limited.patch(f"/api/forms/{form_id}/restitution", json={
            "returnedAt": "2026-11-20", "items": items(), "signatureStatus": "signed", "signatureDataUrl": PNG,
            "closeAnyway": True,
        }, headers=H)
        assert forbidden.status_code == 403
        assert forbidden.get_json()["error"] == "forbidden"

        # La restitution normale (sans closeAnyway) reste autorisee avec forms.restitution seul.
        allowed = limited.patch(f"/api/forms/{form_id}/restitution", json={
            "returnedAt": "2026-11-20", "items": items(), "signatureStatus": "signed", "signatureDataUrl": PNG,
        }, headers=H)
        assert allowed.status_code == 200, allowed.get_data(as_text=True)[:300]
        assert allowed.get_json()["summary"]["status"] == "partial_return"
    finally:
        delete_user("sans.force")
