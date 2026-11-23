"""3.67.3, lot 3 : le compte `admin` protégé par le mot de passe d'origine (`admin`) doit le changer avant tout autre usage.
Drapeau `must_change_password` posé au seed et rattrapé au démarrage sur les installations existantes ; tant qu'il est levé,
le serveur ne répond qu'au changement de mot de passe. Base temporaire (tests/conftest.py)."""
import sqlite3
import time

import bcrypt
import pytest

from app import app
from auth import create_user, delete_user, get_user_record, update_user
from database import flag_default_credentials, get_users_db

H = {"X-CSRF-Token": "jeton"}
ORIGINE = "Mot-2-Passe-Dorigine!"
NOUVEAU = "Nouveau-Mot-2-Passe!"


def make_hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@pytest.fixture(autouse=True)
def sans_limiteur_de_connexion(monkeypatch):
    monkeypatch.setattr("routes.pages._is_login_rate_limited", lambda key: False)


@pytest.fixture
def compte():
    """Administrateur jetable, marqué « doit changer son mot de passe »."""
    name = f"defaut_{time.time_ns()}"
    assert create_user(name, make_hash(ORIGINE), ["admin"])
    assert update_user(name, must_change_password=1)
    yield name
    delete_user(name)


def ouvrir_session(compte, password):
    client = app.test_client()
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
    resp = client.post("/login", data={"username": compte, "password": password, "csrf_token": "jeton"})
    assert resp.status_code == 302 and "error" not in resp.headers["Location"], resp.headers["Location"]
    with client.session_transaction() as s:
        s["csrf_token"] = "jeton"
    return client, resp.headers["Location"]


def test_la_connexion_ramene_a_l_accueil_et_pas_a_l_assistant(compte):
    _, destination = ouvrir_session(compte, ORIGINE)
    assert destination == "/"


def test_api_session_expose_le_drapeau(compte):
    client, _ = ouvrir_session(compte, ORIGINE)
    assert client.get("/api/session").get_json()["must_change_password"] is True


@pytest.mark.parametrize("route", ["/api/forms", "/api/admin/users", "/api/stock", "/api/logs"])
def test_api_bloquee_tant_que_le_mot_de_passe_n_est_pas_change(compte, route):
    client, _ = ouvrir_session(compte, ORIGINE)
    resp = client.get(route)
    assert resp.status_code == 403 and resp.get_json()["error"] == "password_change_required"


def test_ecriture_bloquee_meme_avec_un_jeton_csrf_valide(compte):
    client, _ = ouvrir_session(compte, ORIGINE)
    resp = client.post("/api/admin/users", json={"username": "intrus_x", "password": NOUVEAU, "groups": ["admin"]}, headers=H)
    assert resp.status_code == 403 and get_user_record("intrus_x") is None


@pytest.mark.parametrize("page", ["/admin.html", "/admin-comptes.html", "/form.html", "/setup.html", "/account.html"])
def test_pages_renvoyees_a_l_accueil(compte, page):
    client, _ = ouvrir_session(compte, ORIGINE)
    resp = client.get(page)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")


@pytest.mark.parametrize("route", ["/", "/api/session", "/api/csrf-token", "/api/settings/public", "/js/ui.js", "/css/style.css"])
def test_ce_qui_reste_accessible(compte, route):
    client, _ = ouvrir_session(compte, ORIGINE)
    assert client.get(route).status_code == 200


def test_le_changement_debloque_le_compte(compte):
    client, _ = ouvrir_session(compte, ORIGINE)
    resp = client.post("/api/me/password", json={"current_password": ORIGINE, "new_password": NOUVEAU}, headers=H)
    assert resp.status_code == 200
    assert get_user_record(compte)["must_change_password"] == 0
    assert client.get("/api/session").get_json()["must_change_password"] is False  # sa session reste ouverte
    assert client.get("/api/admin/users").status_code == 200
    assert client.get("/admin.html").status_code == 200


def test_meme_mot_de_passe_refuse_et_le_compte_reste_bloque(compte):
    client, _ = ouvrir_session(compte, ORIGINE)
    resp = client.post("/api/me/password", json={"current_password": ORIGINE, "new_password": ORIGINE}, headers=H)
    assert resp.status_code == 400 and resp.get_json()["error"] == "password_unchanged"
    assert get_user_record(compte)["must_change_password"] == 1


def test_mot_de_passe_trop_faible_refuse_et_le_compte_reste_bloque(compte):
    client, _ = ouvrir_session(compte, ORIGINE)
    resp = client.post("/api/me/password", json={"current_password": ORIGINE, "new_password": "court"}, headers=H)
    assert resp.status_code == 400
    assert get_user_record(compte)["must_change_password"] == 1
    assert client.get("/api/admin/users").status_code == 403


def test_apres_le_changement_la_connexion_suivante_est_normale(compte):
    client, _ = ouvrir_session(compte, ORIGINE)
    client.post("/api/me/password", json={"current_password": ORIGINE, "new_password": NOUVEAU}, headers=H)
    _, destination = ouvrir_session(compte, NOUVEAU)
    assert destination in ("/", "/setup.html")  # selon que l'assistant d'organisation est terminé
    assert get_user_record(compte)["must_change_password"] == 0


def test_un_administrateur_qui_fixe_le_mot_de_passe_d_un_autre_le_force_a_le_changer():
    """Un administrateur qui réinitialise le mot de passe d'un autre compte le connaît : la personne doit en choisir un nouveau."""
    cible = f"cible_{time.time_ns()}"
    assert create_user(cible, make_hash(ORIGINE), ["lecture"])
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["user"] = "admin"
        s["csrf_token"] = "jeton"
    try:
        assert get_user_record(cible)["must_change_password"] == 0
        resp = admin.put(f"/api/admin/users/{cible}", json={"password": NOUVEAU}, headers=H)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert get_user_record(cible)["must_change_password"] == 1
        client, _ = ouvrir_session(cible, NOUVEAU)  # il peut se connecter... mais rien d'autre qu'un changement de mot de passe
        assert client.get("/api/admin/users").status_code == 403
        done = client.post("/api/me/password", json={"current_password": NOUVEAU, "new_password": "Choisi-Par-Moi-2-Fois!"}, headers=H)
        assert done.status_code == 200 and get_user_record(cible)["must_change_password"] == 0
    finally:
        delete_user(cible)


def test_un_administrateur_qui_change_son_propre_mot_de_passe_n_est_pas_force_de_le_rechanger():
    moi = f"moi_{time.time_ns()}"
    assert create_user(moi, make_hash(ORIGINE), ["admin"])
    try:
        client, _ = ouvrir_session(moi, ORIGINE)
        resp = client.put(f"/api/admin/users/{moi}", json={"password": NOUVEAU}, headers=H)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert get_user_record(moi)["must_change_password"] == 0
        assert client.get("/api/admin/users").status_code == 200  # sa session reste pleinement utilisable
    finally:
        delete_user(moi)


def test_un_compte_cree_par_un_administrateur_doit_changer_son_mot_de_passe():
    nom = f"cree_{time.time_ns()}"
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["user"] = "admin"
        s["csrf_token"] = "jeton"
    try:
        resp = admin.post("/api/admin/users", json={"username": nom, "password": ORIGINE, "groups": ["lecture"]}, headers=H)
        assert resp.status_code == 201, resp.get_data(as_text=True)
        assert get_user_record(nom)["must_change_password"] == 1
        client, destination = ouvrir_session(nom, ORIGINE)
        assert destination == "/"  # la fenêtre de changement s'y ouvre
        assert client.get("/api/forms").status_code == 403
    finally:
        delete_user(nom)


def test_un_compte_ordinaire_n_est_pas_marque():
    nom = f"normal_{time.time_ns()}"
    assert create_user(nom, make_hash("admin"), ["lecture"])  # même avec le mot de passe « admin » : seul le compte admin est visé
    try:
        assert get_user_record(nom)["must_change_password"] == 0
        flag_default_credentials()
        assert get_user_record(nom)["must_change_password"] == 0
    finally:
        delete_user(nom)


def test_rattrapage_au_demarrage_du_compte_admin_au_mot_de_passe_d_origine():
    """Installation existante (colonne à 0, mot de passe `admin`) : le drapeau est posé, une seule fois."""
    avant = get_user_record("admin")
    with get_users_db() as c:
        c.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE username='admin'", (make_hash("admin"),))
        c.commit()
    try:
        assert flag_default_credentials() is True
        assert get_user_record("admin")["must_change_password"] == 1
        assert flag_default_credentials() is False  # idempotent
        # mot de passe déjà changé : rien n'est posé
        with get_users_db() as c:
            c.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE username='admin'", (make_hash(NOUVEAU),))
            c.commit()
        assert flag_default_credentials() is False
        assert get_user_record("admin")["must_change_password"] == 0
    finally:
        with get_users_db() as c:
            c.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE username='admin'", (avant["password_hash"],))
            c.commit()


def test_installation_neuve_cree_admin_marque(tmp_path):
    """Le seed de la première installation pose le drapeau directement (sans attendre un redémarrage)."""
    import app as app_module
    connection = sqlite3.connect(tmp_path / "users.db")
    connection.executescript(
        """
        CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active', service TEXT, db_manage INTEGER NOT NULL DEFAULT 0, email TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '', must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE user_groups (username TEXT, group_key TEXT, PRIMARY KEY (username, group_key));
        """
    )
    app_module.seed_default_admin(connection)
    row = connection.execute("SELECT must_change_password, password_hash FROM users WHERE username='admin'").fetchone()
    assert row[0] == 1 and bcrypt.checkpw(b"admin", row[1].encode())
