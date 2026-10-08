"""Blocage d'une ADRESSE IP après 10 échecs de connexion, pendant 15 minutes : seuls les échecs comptent, le compte visé n'est jamais bloqué
(personne ne peut empêcher un collègue de se connecter), une autre adresse n'est pas touchée, le blocage ne se prolonge pas tout seul et
rien de ce qui est tapé n'est conservé. Base temporaire (tests/conftest.py)."""
import itertools
import time

import bcrypt
import pytest

import auth
import rate_store
from app import app
from auth import create_user, delete_user, update_user
from database import get_db

BON = "Mot-2-Passe-Adresse1!"
MAX = 10
_compteur = itertools.count(1)


def nouvelle_adresse():
    ip = f"198.51.100.{next(_compteur)}"
    nettoyer(ip)
    return ip


def nettoyer(ip):
    rate_store.clear("login_fail_ip", ip)
    rate_store.clear("login_ip_block", ip)


@pytest.fixture(autouse=True)
def seuil_par_defaut(monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_IP_MAX_FAILURES", MAX)
    monkeypatch.setattr(auth, "LOGIN_IP_BLOCK_SECONDS", 15 * 60)


@pytest.fixture
def compte():
    name = f"adresse_{time.time_ns()}"
    assert create_user(name, bcrypt.hashpw(BON.encode(), bcrypt.gensalt()).decode(), ["lecture"])
    yield name
    delete_user(name)


def tenter(ip, username, password, csrf=True):
    client = app.test_client()
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
    data = {"username": username, "password": password}
    if csrf:
        data["csrf_token"] = "jeton"
    resp = client.post("/login", data=data, environ_overrides={"REMOTE_ADDR": ip})
    return resp.headers["Location"]


def echouer(ip, username, fois):
    for _ in range(fois):
        assert tenter(ip, username, "mauvais") == "/login?error=invalid"


def reussi(destination):
    return not destination.startswith("/login?error=")


def test_dix_echecs_bloquent_l_adresse_meme_avec_le_bon_mot_de_passe(compte):
    ip = nouvelle_adresse()
    echouer(ip, compte, MAX)
    assert tenter(ip, compte, BON) == "/login?error=rate_limited"


def test_neuf_echecs_ne_bloquent_pas(compte):
    ip = nouvelle_adresse()
    echouer(ip, compte, MAX - 1)
    assert reussi(tenter(ip, compte, BON))


def test_le_compte_n_est_jamais_bloque_une_autre_adresse_se_connecte(compte):
    """Le point central : un intrus bloque SON adresse, pas le compte de sa victime."""
    intrus, collegue = nouvelle_adresse(), nouvelle_adresse()
    echouer(intrus, compte, MAX)
    assert tenter(intrus, compte, BON) == "/login?error=rate_limited"
    assert reussi(tenter(collegue, compte, BON))  # le vrai titulaire, depuis son poste, se connecte normalement


def test_les_connexions_reussies_ne_comptent_pas(compte):
    ip = nouvelle_adresse()
    for _ in range(MAX + 5):
        assert reussi(tenter(ip, compte, BON))  # un poste partagé ou un kiosque n'est jamais pénalisé


def test_une_connexion_reussie_ne_remet_pas_les_echecs_a_zero(compte):
    """Sinon quelqu'un qui possède un compte valide pourrait deviner sur d'autres comptes en se reconnectant entre deux essais."""
    ip = nouvelle_adresse()
    echouer(ip, compte, MAX - 1)
    assert reussi(tenter(ip, compte, BON))
    assert tenter(ip, compte, "mauvais") == "/login?error=invalid"  # 10e échec
    assert tenter(ip, compte, BON) == "/login?error=rate_limited"


def test_les_identifiants_inconnus_comptent_pareil():
    ip = nouvelle_adresse()
    echouer(ip, f"inexistant_{time.time_ns()}", MAX)
    assert tenter(ip, "n_importe_qui", "peu importe") == "/login?error=rate_limited"


def test_une_requete_sans_jeton_csrf_compte_comme_un_echec():
    ip = nouvelle_adresse()
    for _ in range(MAX):
        assert tenter(ip, "x", "y", csrf=False) == "/login?error=invalid"
    assert tenter(ip, "x", "y", csrf=False) == "/login?error=rate_limited"


def test_un_compte_desactive_qui_insiste_est_compte(compte):
    ip = nouvelle_adresse()
    update_user(compte, is_active=0, status="disabled")
    for _ in range(MAX):
        assert tenter(ip, compte, BON) == "/login?error=disabled"
    assert tenter(ip, compte, BON) == "/login?error=rate_limited"


def test_le_blocage_dure_quinze_minutes_et_ne_se_prolonge_pas(compte):
    ip = nouvelle_adresse()
    echouer(ip, compte, MAX)
    for _ in range(5):  # on insiste pendant le blocage
        assert tenter(ip, compte, "mauvais") == "/login?error=rate_limited"
    assert rate_store.count("login_ip_block", ip, auth.LOGIN_IP_BLOCK_SECONDS) == 1  # un seul début de blocage : insister ne le repousse pas
    assert auth._is_login_rate_limited(ip) is True
    avant_la_fin = time.time() + 15 * 60 - 30
    apres_la_fin = time.time() + 15 * 60 + 30
    assert rate_store.count("login_ip_block", ip, auth.LOGIN_IP_BLOCK_SECONDS, now=avant_la_fin) == 1
    assert rate_store.count("login_ip_block", ip, auth.LOGIN_IP_BLOCK_SECONDS, now=apres_la_fin) == 0  # libérée


def test_apres_le_blocage_on_repart_de_zero(compte):
    ip = nouvelle_adresse()
    echouer(ip, compte, MAX)
    assert rate_store.count("login_fail_ip", ip, auth.LOGIN_IP_BLOCK_SECONDS) == 0  # le compteur d'échecs a été remis à zéro au blocage


def test_la_duree_par_defaut_est_de_quinze_minutes():
    import importlib
    import os
    source = open(auth.__file__, encoding="utf-8").read()
    assert 'os.environ.get("APP_LOGIN_IP_BLOCK_MINUTES", "15")' in source
    assert 'os.environ.get("APP_LOGIN_IP_MAX_FAILURES", "10")' in source
    importlib.invalidate_caches()
    assert os is not None


def test_desactivable_par_la_configuration(monkeypatch, compte):
    monkeypatch.setattr(auth, "LOGIN_IP_MAX_FAILURES", 0)
    ip = nouvelle_adresse()
    echouer(ip, compte, 25)
    assert reussi(tenter(ip, compte, BON))


def test_le_blocage_est_journalise_sans_identifiant_ni_mot_de_passe(compte):
    ip = nouvelle_adresse()
    echouer(ip, compte, MAX)
    with get_db() as connection:
        row = connection.execute("SELECT target_id, details_json FROM app_logs WHERE action_type = 'login_ip_blocked' AND target_id = ?", (ip,)).fetchone()
    assert row is not None and ip in row[1]
    assert compte not in str(tuple(row)) and BON not in str(tuple(row)) and "mauvais" not in str(tuple(row))


def test_l_adresse_vient_du_serveur_pas_d_un_en_tete_falsifiable(compte):
    """Forger X-Forwarded-For ne permet ni d'échapper au blocage ni de bloquer l'adresse de quelqu'un d'autre."""
    ip = "8.8.4.4"  # une adresse PUBLIQUE : l'application ne fait confiance à X-Forwarded-For que d'un proxy privé (les plages de documentation 198.51.100.x comptent comme privées)
    nettoyer(ip)
    try:
        echouer(ip, compte, MAX)
        client = app.test_client()
        with client.session_transaction() as s:
            s["csrf_token"] = "jeton"
        resp = client.post("/login", data={"username": compte, "password": BON, "csrf_token": "jeton"},
                           headers={"X-Forwarded-For": "203.0.113.77"}, environ_overrides={"REMOTE_ADDR": ip})
        assert resp.headers["Location"] == "/login?error=rate_limited"  # l'en-tête forgé ne change rien
    finally:
        nettoyer(ip)


def test_une_adresse_n_en_bloque_pas_une_autre(compte):
    a, b = nouvelle_adresse(), nouvelle_adresse()
    echouer(a, compte, MAX)
    assert auth._is_login_rate_limited(a) is True and auth._is_login_rate_limited(b) is False
    echouer(b, compte, MAX - 1)
    assert auth._is_login_rate_limited(b) is False
