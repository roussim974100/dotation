"""3.66.1 : un « personId » stable est expose dans le resume de chaque dossier (row_to_summary), pour que le
navigateur puisse regrouper les dossiers d'une meme personne dans les tableaux de bord (une ligne par personne,
historique deplie) sans jamais fusionner les dossiers eux-memes. Reprendre le personId du dossier source (comme
deja fait pour une "mise a jour") est ce qui permet a "Nouvelle attribution pour cette personne" de lier le nouveau
dossier a la MEME personne plutot que d'en recreer une."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app

H = {"X-CSRF-Token": "jeton"}
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = user
        flask_session["csrf_token"] = "jeton"
    return client


def create_signed_dossier(client, nom, prenom="Test", person_id=""):
    body = {
        "dossier": {"type": "arrivee"},
        "beneficiaire": {"nom": nom, "prenom": prenom, "qualite": "agent", "service": "DRH"},
        "resources": {"additional": [{"id": 1, "code": "badge", "label": "Badge", "category": "materiel",
                                       "selected": True, "fields": {}, "details": ""}]},
        "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
        "workflow": {"status": "active"},
        "meta": {"personId": person_id} if person_id else {},
    }
    created = client.post("/api/forms", json=body, headers=H)
    assert created.status_code in (200, 201), created.get_data(as_text=True)[:300]
    return created.get_json()["summary"]


def test_personid_expose_dans_le_resume_du_dossier():
    client = client_for()
    summary = create_signed_dossier(client, "GROUPETEST")
    assert summary.get("personId"), "personId doit etre expose dans le resume, pas seulement en base"


def test_reattribution_avec_personid_repris_partage_la_meme_personne():
    client = client_for()
    first = create_signed_dossier(client, "GUERRIERO", "Lilou")
    person_id = first["personId"]
    assert person_id

    # "Nouvelle attribution pour cette personne" : le navigateur reprend meta.personId du dossier source
    # (prefillIdentityFromForm -> #retraitsSourcePersonId), exactement comme simule ici.
    second = create_signed_dossier(client, "GUERRIERO", "Lilou", person_id=person_id)

    assert second["personId"] == person_id, "les deux dossiers de Lilou doivent partager le meme personId"
    assert second["id"] != first["id"], "ce sont bien deux dossiers distincts (historique conserve)"

    listing = client.get("/api/forms").get_json()
    ids_for_person = {row["id"] for row in listing if row.get("personId") == person_id}
    assert ids_for_person == {first["id"], second["id"]}, "la liste doit permettre de retrouver les 2 dossiers par personId"


def test_sans_personid_repris_deux_dossiers_du_meme_nom_restent_distincts():
    # Garde-fou : sans reprise explicite du personId (dossier cree "a la main", sans passer par
    # "Nouvelle attribution pour cette personne"), on ne devine jamais qu'il s'agit de la meme personne.
    client = client_for()
    first = create_signed_dossier(client, "HOMONYME", "Jean")
    second = create_signed_dossier(client, "HOMONYME", "Jean")
    assert first["personId"] != second["personId"]
