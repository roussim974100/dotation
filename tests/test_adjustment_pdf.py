"""PDF d'un ajustement (3.72.0) : preuve de ce qui a été ajouté, retiré ou changé et de la signature (présentiel, à distance en
attente, par un responsable). Mêmes droits que les autres PDF (export, jamais pour un profil masqué). Base temporaire."""
import io
import time

import bcrypt
import pytest

from auth import create_user, delete_user
from database import get_users_db
from test_adjustment import PNG, client_for, create_active_dossier, patch, presentiel  # noqa: E402  (tests/ est dans sys.path : conftest)

pypdf = pytest.importorskip("pypdf")


@pytest.fixture(autouse=True)
def sans_limiteur_de_creation(monkeypatch):
    monkeypatch.setattr("auth._is_api_rate_limited", lambda *args, **kwargs: False)


def texte(response):
    reader = pypdf.PdfReader(io.BytesIO(response.data))
    return "\n".join(page.extract_text() for page in reader.pages)


def pdf_url(form_id, event_id):
    return f"/api/forms/{form_id}/pdf/ajustement/{event_id}"


def ajuster(body, nom="PDFAJUST"):
    client = client_for()
    form_id = create_active_dossier(client, nom=nom)
    response = patch(client, form_id, body)
    assert response.status_code == 200, response.get_data(as_text=True)
    return client, form_id, response.get_json()["ajustement"]["id"]


def test_pdf_d_un_ajustement_signe_en_presentiel():
    client, form_id, event_id = ajuster({
        "ajouts": [{"id": 3, "code": "tablette", "label": "Tablette", "category": "materiel", "fields": {"marque": "Z"}}],
        "retraits": [{"key": "ordinateur", "state": "degrade", "notes": "écran fissuré"}],
        "service": "Finances", "signature": presentiel()}, nom="PRESENTIEL")
    response = client.get(pdf_url(form_id, event_id))
    assert response.status_code == 200 and response.mimetype == "application/pdf" and response.data.startswith(b"%PDF")
    assert "ajustement" in response.headers["Content-Disposition"].lower()
    text = texte(response)
    for expected in ("Fiche d'ajustement de dossier", "PRESENTIEL", "Ressources ajoutées", "Tablette", "Ressources retirées", "Ordinateur",
                     "Dégradé", "écran fissuré", "Changement de service", "Finances", "DRH", "Signature recueillie en présentiel"):
        assert expected in text, f"« {expected} » absent du PDF"
    assert "en attente" not in text.lower()


def test_pdf_d_un_ajustement_a_distance_encore_en_attente_le_dit():
    client, form_id, event_id = ajuster({"ajouts": [{"id": 3, "code": "tablette", "label": "Tablette", "category": "materiel", "fields": {"marque": "Z"}}],
                                         "signature": {"mode": "distance"}}, nom="ATTENTE")
    text = texte(client.get(pdf_url(form_id, event_id)))
    assert "en attente de signature" in text.lower() and "pas encore valeur de preuve" in text
    assert "Signature recueillie" not in text


def test_pdf_d_un_ajustement_signe_par_un_responsable():
    client, form_id, event_id = ajuster({"retraits": [{"key": "telephone", "state": "conforme"}],
                                         "signature": {"mode": "impossible", "reason": "Absence prolongée", "substitute": {"name": "Mme Durand", "quality": "DRH"}}},
                                        nom="REMPLACANT")
    text = texte(client.get(pdf_url(form_id, event_id)))
    assert "Signature par un responsable" in text and "Absence prolongée" in text and "Mme Durand" in text and "DRH" in text
    assert "Conforme" in text


def test_un_ajustement_sans_retrait_ni_ajout_dit_aucune_ressource():
    client, form_id, event_id = ajuster({"service": "Voirie", "signature": presentiel()}, nom="SERVICESEUL")
    text = texte(client.get(pdf_url(form_id, event_id)))
    assert "Aucune ressource ajoutée" in text and "Aucune ressource retirée" in text and "Voirie" in text


def test_pdf_introuvable_ou_non_autorise():
    client, form_id, event_id = ajuster({"service": "Voirie", "signature": presentiel()}, nom="DROITS")
    assert client.get(pdf_url(form_id, "ajust_inconnu")).status_code == 404
    assert client.get(pdf_url("dossier_inconnu", event_id)).status_code == 404
    from app import app
    assert app.test_client().get(pdf_url(form_id, event_id)).status_code == 401
    # profil à portée masquée : aucun PDF (comme pour les autres exports), même avec le droit d'export
    name = f"masque_pdf_{time.time_ns()}"
    assert create_user(name, bcrypt.hashpw(b"Mot-2-Passe-Pdf1!", bcrypt.gensalt()).decode(), [])
    with get_users_db() as users:
        users.execute("INSERT OR REPLACE INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) "
                      "VALUES ('masque_pdf','M','','[\"forms.export\",\"forms.read_detail\"]','masked','x','x')")
        users.execute("INSERT INTO user_groups (username, group_key) VALUES (?, 'masque_pdf')", (name,))
    try:
        assert client_for(name).get(pdf_url(form_id, event_id)).status_code == 403
    finally:
        with get_users_db() as users:
            users.execute("DELETE FROM user_groups WHERE group_key = 'masque_pdf'")
            users.execute("DELETE FROM groups WHERE key = 'masque_pdf'")
        delete_user(name)


def test_la_signature_manuscrite_est_dans_le_pdf_pour_qui_peut_l_exporter():
    """Le logo de l'application est aussi une image : on compare avec un ajustement signé par un responsable (pas de signature manuscrite)."""
    def images(body, nom):
        client, form_id, event_id = ajuster(body, nom=nom)
        reader = pypdf.PdfReader(io.BytesIO(client.get(pdf_url(form_id, event_id)).data))
        return sum(len(page.images) for page in reader.pages)

    avec = images({"service": "Voirie", "signature": presentiel()}, "AVECSIGNATURE")
    sans = images({"service": "Voirie", "signature": {"mode": "impossible", "reason": "Absent", "substitute": {"name": "M. Martin", "quality": "RH"}}}, "SANSSIGNATURE")
    assert avec == sans + 1
