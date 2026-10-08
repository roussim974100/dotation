"""(DÉSACTIVÉ PAR DÉFAUT depuis le 08/10/2026 : ces tests l'activent explicitement ; voir `test_desactive_par_defaut`.)
Verrouillage temporaire PAR COMPTE : 5 échecs en 15 minutes bloquent les tentatives sur ce compte (même avec le bon mot de passe,
même depuis une autre adresse), une connexion réussie remet à zéro, les identifiants inconnus se comportent pareil (aucune
énumération), et rien de ce qui est tapé dans le champ identifiant n'est conservé en clair. Base temporaire (tests/conftest.py)."""
import hashlib
import time

import bcrypt
import pytest

import auth
import rate_store
from app import app
from auth import create_user, delete_user
from database import get_db, get_users_db

BON = "Mot-2-Passe-Verrou1!"


ACCOUNT_MAX_FAILURES = 5


@pytest.fixture(autouse=True)
def verrouillage_actif_sans_limite_par_adresse(monkeypatch):
    """On teste le verrouillage par COMPTE, activé ici (il ne l'est pas par défaut) ; la limite par adresse IP (10 / 10 min) ne doit pas s'en mêler."""
    monkeypatch.setattr(auth, "ACCOUNT_MAX_FAILURES", ACCOUNT_MAX_FAILURES)
    monkeypatch.setattr("routes.pages._is_login_rate_limited", lambda key: False)


@pytest.fixture
def compte():
    name = f"verrou_{time.time_ns()}"
    assert create_user(name, bcrypt.hashpw(BON.encode(), bcrypt.gensalt()).decode(), ["lecture"])
    auth.clear_account_failures(name)
    yield name
    auth.clear_account_failures(name)
    delete_user(name)


def tenter(username, password, ip="10.0.0.1"):
    client = app.test_client()
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
    resp = client.post("/login", data={"username": username, "password": password, "csrf_token": "jeton"},
                       environ_overrides={"REMOTE_ADDR": ip})
    return resp.headers["Location"]


def echouer(username, fois, ip="10.0.0.1"):
    for _ in range(fois):
        assert tenter(username, "mauvais", ip) == "/login?error=invalid"


def test_cinq_echecs_bloquent_meme_avec_le_bon_mot_de_passe(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES)
    assert tenter(compte, BON) == "/login?error=account_locked"


def test_le_blocage_suit_le_compte_pas_l_adresse(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES, ip="10.0.0.1")
    assert tenter(compte, BON, ip="203.0.113.9") == "/login?error=account_locked"  # un attaquant réparti sur plusieurs adresses est arrêté aussi


def test_quatre_echecs_ne_bloquent_pas(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES - 1)
    assert not tenter(compte, BON).startswith("/login?error=")


def test_une_connexion_reussie_remet_les_echecs_a_zero(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES - 1)
    assert not tenter(compte, BON).startswith("/login?error=")
    echouer(compte, ACCOUNT_MAX_FAILURES - 1)  # 4 + 4 : sans remise à zéro on dépasserait la limite
    assert not tenter(compte, BON).startswith("/login?error=")


def test_un_compte_inconnu_est_traite_comme_un_compte_connu():
    """Même comportement, même message : impossible de deviner quels comptes existent."""
    inconnu = f"inexistant_{time.time_ns()}"
    auth.clear_account_failures(inconnu)
    try:
        echouer(inconnu, ACCOUNT_MAX_FAILURES)
        assert tenter(inconnu, "peu importe") == "/login?error=account_locked"
    finally:
        auth.clear_account_failures(inconnu)


def test_la_casse_et_les_espaces_ne_contournent_pas_le_blocage(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES)
    assert tenter(f"  {compte.upper()} ", BON) == "/login?error=account_locked"


def test_un_autre_compte_n_est_pas_touche(compte):
    autre = f"autre_{time.time_ns()}"
    assert create_user(autre, bcrypt.hashpw(BON.encode(), bcrypt.gensalt()).decode(), ["lecture"])
    try:
        echouer(compte, ACCOUNT_MAX_FAILURES)
        assert not tenter(autre, BON).startswith("/login?error=")
    finally:
        delete_user(autre)


def test_le_blocage_expire_avec_les_echecs(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES)
    assert auth.is_account_locked(compte) is True
    futur = time.time() + auth.ACCOUNT_WINDOW_SECONDS + 5
    assert rate_store.count("login_fail_account", auth._account_key(compte), auth.ACCOUNT_WINDOW_SECONDS, now=futur) == 0


def test_la_cle_est_un_hachage_jamais_l_identifiant_tape(compte):
    echouer(compte, 1)
    cle = hashlib.sha256(compte.lower().encode()).hexdigest()[:24]
    with get_users_db() as users:
        cles = {row[0] for row in users.execute("SELECT key FROM rate_limit_hits WHERE scope = 'login_fail_account'")}
    assert cle in cles and compte not in cles


def test_la_tentative_bloquee_est_journalisee_sans_l_identifiant_en_clair(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES)
    tenter(compte, BON)
    with get_db() as connection:
        row = connection.execute("SELECT target_id, details_json FROM app_logs WHERE action_type = 'login_blocked' ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert BON not in str(tuple(row))  # jamais le mot de passe


def test_la_connexion_normale_n_est_pas_ralentie_ni_comptee(compte):
    for _ in range(ACCOUNT_MAX_FAILURES + 3):
        assert not tenter(compte, BON).startswith("/login?error=")  # des connexions réussies ne comptent jamais
    assert auth.is_account_locked(compte) is False


def test_les_comptes_en_attente_ou_desactives_ne_declenchent_pas_le_compteur(compte):
    """Seul l'échec de mot de passe compte : un compte désactivé qui réessaie n'est pas « deviné »."""
    from auth import update_user
    update_user(compte, is_active=0, status="disabled")
    for _ in range(ACCOUNT_MAX_FAILURES + 2):
        assert tenter(compte, BON) == "/login?error=disabled"
    assert auth.is_account_locked(compte) is False


def test_compteur_lecture_seule_et_remise_a_zero():
    cle = f"test_{time.time_ns()}"
    assert rate_store.count("scope_test", cle, 60) == 0
    rate_store.hit("scope_test", cle, 10 ** 9, 60)
    rate_store.hit("scope_test", cle, 10 ** 9, 60)
    assert rate_store.count("scope_test", cle, 60) == 2
    assert rate_store.count("scope_test", cle, 60) == 2  # lire ne compte pas
    rate_store.clear("scope_test", cle)
    assert rate_store.count("scope_test", cle, 60) == 0


# ---- administration : voir et lever un blocage ---------------------------------------------------------------------------------

H = {"X-CSRF-Token": "jeton"}


def admin_client():
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = "admin"
        s["csrf_token"] = "jeton"
    return client


def test_la_liste_des_comptes_signale_un_compte_bloque(compte):
    admin = admin_client()
    listed = {u["username"]: u for u in admin.get("/api/admin/users").get_json()}
    assert listed[compte]["login_locked"] is False
    echouer(compte, ACCOUNT_MAX_FAILURES)
    listed = {u["username"]: u for u in admin_client().get("/api/admin/users").get_json()}
    assert listed[compte]["login_locked"] is True


def test_un_administrateur_leve_le_blocage(compte):
    echouer(compte, ACCOUNT_MAX_FAILURES)
    assert tenter(compte, BON) == "/login?error=account_locked"
    resp = admin_client().post(f"/api/admin/users/{compte}/unlock", json={}, headers=H)
    assert resp.status_code == 200 and resp.get_json() == {"unlocked": True, "was_locked": True}
    assert not tenter(compte, BON).startswith("/login?error=")
    with get_db() as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_logs WHERE action_type = 'login_unblocked' AND target_id = ?", (compte,)).fetchone()[0] == 1


def test_debloquer_exige_le_droit_et_un_compte_existant(compte):
    other = app.test_client()
    with other.session_transaction() as s:
        s["user"] = compte  # compte du groupe « lecture » : pas le droit de gérer les comptes
        s["csrf_token"] = "jeton"
    assert other.post(f"/api/admin/users/{compte}/unlock", json={}, headers=H).status_code == 403
    assert admin_client().post("/api/admin/users/inexistant_xyz/unlock", json={}, headers=H).status_code == 404
    assert app.test_client().post(f"/api/admin/users/{compte}/unlock", json={}, headers=H).status_code == 401


def test_desactive_par_defaut(monkeypatch, compte):
    """Décision du propriétaire : pas de verrouillage tant qu'on ne l'active pas (APP_LOGIN_ACCOUNT_MAX_FAILURES)."""
    monkeypatch.setattr(auth, "ACCOUNT_MAX_FAILURES", 0)
    assert auth.account_lock_enabled() is False
    echouer(compte, 20)  # bien au-delà de n'importe quelle limite
    assert auth.is_account_locked(compte) is False
    assert not tenter(compte, BON).startswith("/login?error=")  # le bon mot de passe passe toujours
    listed = {u["username"]: u for u in admin_client().get("/api/admin/users").get_json()}
    assert listed[compte]["login_locked"] is False


def test_la_valeur_par_defaut_du_module_est_zero():
    """Sans la variable d'environnement, le module est configuré « désactivé » (le fixture ci-dessus l'active pour les autres tests)."""
    import importlib
    import os
    saved = os.environ.pop("APP_LOGIN_ACCOUNT_MAX_FAILURES", None)
    try:
        source = open(auth.__file__, encoding="utf-8").read()
        assert 'os.environ.get("APP_LOGIN_ACCOUNT_MAX_FAILURES", "0")' in source
    finally:
        if saved is not None:
            os.environ["APP_LOGIN_ACCOUNT_MAX_FAILURES"] = saved
        importlib.invalidate_caches()
