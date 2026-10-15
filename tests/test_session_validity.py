"""Sessions : une session ouverte ne doit pas survivre au changement de mot de passe, a la desactivation ou a la
suppression du compte, ni depasser sa duree de vie (trouve le 06/10 : session admin/admin encore active apres changement
du mot de passe). Base temporaire (tests/conftest.py)."""
import time

import bcrypt
import pytest

from app import app
from auth import create_user, delete_user, get_user_record, update_user
from database import get_users_db

H = {"X-CSRF-Token": "jeton"}
OLD_PW = "Ancien-Mot-2-Passe!"
NEW_PW = "Nouveau-Mot-2-Passe!"


def make_hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@pytest.fixture(autouse=True)
def sans_limiteur_de_connexion(monkeypatch):
    """Ces tests ouvrent beaucoup de sessions depuis la meme adresse : le limiteur (10 / 10 min) les bloquerait."""
    monkeypatch.setattr("routes.pages._is_login_rate_limited", lambda key: False)


@pytest.fixture
def compte():
    """Compte administrateur jetable (nom unique par test)."""
    name = f"sess_{time.time_ns()}"
    assert create_user(name, make_hash(OLD_PW), ["admin"])
    yield name
    delete_user(name)


def ouvrir_session(compte, password=OLD_PW):
    """Vraie connexion par /login : la session porte l'empreinte du mot de passe."""
    client = app.test_client()
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
    resp = client.post("/login", data={"username": compte, "password": password, "csrf_token": "jeton"})
    assert resp.status_code == 302 and "error" not in resp.headers["Location"], resp.headers["Location"]
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
    assert client.get("/api/session").status_code == 200
    return client


def est_refusee(client):
    return client.get("/api/session").status_code == 401


def test_session_active_apres_connexion(compte):
    assert ouvrir_session(compte).get("/api/session").get_json()["username"] == compte


def test_changement_de_mot_de_passe_par_un_admin_ferme_les_autres_sessions(compte):
    session_a = ouvrir_session(compte)
    assert update_user(compte, password_hash=make_hash(NEW_PW))
    assert est_refusee(session_a)


def test_changement_de_son_propre_mot_de_passe_ferme_les_autres_sessions_mais_garde_la_courante(compte):
    session_a = ouvrir_session(compte)  # l'« ancienne » session, celle de l'intrus
    session_b = ouvrir_session(compte)  # la personne qui change son mot de passe
    resp = session_b.post("/api/me/password", json={"current_password": OLD_PW, "new_password": NEW_PW}, headers=H)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert session_b.get("/api/session").status_code == 200  # pas deconnectee
    assert est_refusee(session_a)  # l'ancienne session ne marche plus
    # et la nouvelle connexion fonctionne avec le nouveau mot de passe
    assert ouvrir_session(compte, NEW_PW).get("/api/session").status_code == 200


def test_desactivation_du_compte_ferme_la_session(compte):
    session_a = ouvrir_session(compte)
    assert update_user(compte, is_active=0, status="disabled")
    assert est_refusee(session_a)


def test_suppression_du_compte_ferme_la_session(compte):
    session_a = ouvrir_session(compte)
    assert delete_user(compte)
    assert est_refusee(session_a)


def test_session_refusee_ne_peut_plus_ecrire(compte):
    """Pas seulement la lecture : une mutation avec un jeton CSRF valide est refusee aussi."""
    session_a = ouvrir_session(compte)
    update_user(compte, password_hash=make_hash(NEW_PW))
    resp = session_a.post("/api/me/password", json={"current_password": OLD_PW, "new_password": "Autre-Mot-2-Passe!"}, headers=H)
    assert resp.status_code == 401


def test_session_trop_ancienne_refusee(compte):
    client = ouvrir_session(compte)
    with client.session_transaction() as s:
        s["login_at"] = int(time.time()) - 13 * 3600
    assert est_refusee(client)


def test_session_inactive_refusee(compte):
    client = ouvrir_session(compte)
    with client.session_transaction() as s:
        s["last_seen"] = int(time.time()) - 2 * 3600
    assert est_refusee(client)


def test_cookie_anterieur_au_controle_refuse(compte):
    """Un cookie emis avant ce correctif (ni empreinte ni dates) doit forcer une nouvelle connexion."""
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = compte
        s["login_at"] = None  # present mais invalide : le client de test n'ajoute rien
    assert est_refusee(client)


def test_connexion_remplace_la_session_precedente(compte):
    """Pas de fixation de session : ce qui etait dans la session avant la connexion disparait."""
    client = app.test_client()
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
        s["intrus"] = "x"
    client.post("/login", data={"username": compte, "password": OLD_PW, "csrf_token": "jeton"})
    with client.session_transaction() as s:
        assert "intrus" not in s and s["user"] == compte


def test_activite_normale_ne_deconnecte_pas(compte):
    client = ouvrir_session(compte)
    for _ in range(3):
        assert client.get("/api/session").status_code == 200


def test_un_controle_du_navigateur_ne_prolonge_pas_la_session(compte):
    """ui.js contrôle la session toutes les minutes (X-Session-Check) : cela ne doit pas repousser l'inactivité."""
    client = ouvrir_session(compte)
    ancien = int(time.time()) - 600
    with client.session_transaction() as s:
        s["last_seen"] = ancien
    assert client.get("/api/session", headers={"X-Session-Check": "1"}).status_code == 200
    with client.session_transaction() as s:
        assert s["last_seen"] == ancien  # inchangé
    assert client.get("/api/session").status_code == 200  # une vraie requête, elle, compte
    with client.session_transaction() as s:
        assert s["last_seen"] > ancien


def test_un_onglet_laisse_ouvert_tombe_en_inactivite_malgre_les_controles(compte):
    client = ouvrir_session(compte)
    with client.session_transaction() as s:
        s["last_seen"] = int(time.time()) - 2 * 3600
    assert client.get("/api/session", headers={"X-Session-Check": "1"}).status_code == 401
