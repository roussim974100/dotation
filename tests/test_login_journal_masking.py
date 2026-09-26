"""3.62.1 : un echec de connexion ne journalise plus en clair un identifiant qui ne correspond a aucun compte (mot de passe
tape par erreur dans le champ identifiant), et la migration 6 masque les entrees deja enregistrees."""
import json
import sqlite3
import sys
from pathlib import Path

import bcrypt

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import migrations
from migrations import _m_mask_login_failed_identifiers

SECRET_TYPED = "Publier@52@26!"


def _failed_login(client, username):
    with client.session_transaction() as flask_session:
        flask_session["csrf_token"] = "jeton-de-test"
    return client.post("/login", data={"username": username, "password": "x", "csrf_token": "jeton-de-test"},
                       environ_overrides={"REMOTE_ADDR": "203.0.113.%d" % (abs(hash(username)) % 200 + 1)})


def _last_login_failed_rows():
    from database import get_db
    with get_db() as connection:
        return connection.execute("SELECT target_id, target_label, details_json FROM app_logs WHERE action_type = 'login_failed'").fetchall()


def test_identifiant_inconnu_jamais_journalise_en_clair():
    from app import app
    client = app.test_client()
    _failed_login(client, SECRET_TYPED)
    rows = _last_login_failed_rows()
    assert rows, "l'echec de connexion doit rester journalise"
    for row in rows:
        blob = " ".join(str(value) for value in (row["target_id"], row["target_label"], row["details_json"]))
        assert SECRET_TYPED not in blob
    assert any(row["target_id"] == "(identifiant inconnu)" for row in rows)
    assert any(json.loads(row["details_json"]).get("identifiant_tente") == "(identifiant inconnu)" for row in rows)


def test_identifiant_d_un_compte_existant_reste_visible():
    from app import app
    import auth
    hashed = bcrypt.hashpw(b"MotDePasse-Complexe-1!", bcrypt.gensalt()).decode()
    auth.create_user("compte.existant", hashed, [])
    try:
        _failed_login(app.test_client(), "compte.existant")
        rows = [r for r in _last_login_failed_rows() if r["target_id"] == "compte.existant"]
        assert rows and json.loads(rows[0]["details_json"]).get("identifiant_tente") == "compte.existant"
    finally:
        auth.delete_user("compte.existant")


def _log_row(connection, ident, label=None):
    details = {"identifiant_tente": ident, "ip": "10.0.0.1"}
    connection.execute("INSERT INTO app_logs (id, actor, scope, action_type, action_label, target_type, target_id, target_label, details_json, created_at) "
                       "VALUES (?, 'anonymous', 'security', 'login_failed', 'Echec', 'user', ?, ?, ?, '2026-09-24T06:40:01')",
                       (f"log_{connection.execute('SELECT COUNT(*) FROM app_logs').fetchone()[0]}", ident, label, json.dumps(details)))


def _users_db(path, names):
    users = sqlite3.connect(path)
    users.execute("CREATE TABLE users (username TEXT)")
    users.executemany("INSERT INTO users VALUES (?)", [(n,) for n in names])
    users.commit()
    users.close()


def _logs_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE app_logs (id TEXT, actor TEXT, scope TEXT, action_type TEXT, action_label TEXT, target_type TEXT, "
                       "target_id TEXT, target_label TEXT, details_json TEXT, created_at TEXT)")
    return connection


def test_migration_masque_les_entrees_existantes_et_epargne_les_vrais_comptes(tmp_path, monkeypatch):
    import config
    users_path = str(tmp_path / "users.db")
    _users_db(users_path, ["samir"])
    monkeypatch.setattr(config, "DB_USERS_PATH", users_path)
    connection = _logs_db()
    _log_row(connection, SECRET_TYPED, label=SECRET_TYPED)
    _log_row(connection, "samir")
    _log_row(connection, "(vide)")
    _m_mask_login_failed_identifiers(connection)
    rows = {r["id"]: r for r in connection.execute("SELECT * FROM app_logs")}
    secret = rows["log_0"]
    assert SECRET_TYPED not in " ".join(str(v) for v in dict(secret).values())
    assert secret["target_id"] == "(identifiant inconnu)" and secret["target_label"] == "(identifiant inconnu)"
    assert json.loads(secret["details_json"])["ip"] == "10.0.0.1"  # le reste de la trace est conserve
    assert rows["log_1"]["target_id"] == "samir"
    assert rows["log_2"]["target_id"] == "(vide)"


def test_migration_idempotente(tmp_path, monkeypatch):
    import config
    users_path = str(tmp_path / "users.db")
    _users_db(users_path, [])
    monkeypatch.setattr(config, "DB_USERS_PATH", users_path)
    connection = _logs_db()
    _log_row(connection, SECRET_TYPED)
    _m_mask_login_failed_identifiers(connection)
    first = [tuple(r) for r in connection.execute("SELECT * FROM app_logs")]
    _m_mask_login_failed_identifiers(connection)
    assert [tuple(r) for r in connection.execute("SELECT * FROM app_logs")] == first


def test_migration_sans_entree_ne_touche_pas_a_la_base_des_comptes(monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_USERS_PATH", "/chemin/inexistant/users.db")
    _m_mask_login_failed_identifiers(_logs_db())  # aucune entree : ne leve pas


def test_migration_reportee_si_la_base_des_comptes_manque(monkeypatch):
    """Ne jamais masquer 'tout' faute de pouvoir lire les comptes : la migration s'annule (et sera retentee au demarrage)."""
    import config
    import pytest
    monkeypatch.setattr(config, "DB_USERS_PATH", "/chemin/inexistant/users.db")
    connection = _logs_db()
    _log_row(connection, "samir")
    with pytest.raises(RuntimeError):
        _m_mask_login_failed_identifiers(connection)
    assert connection.execute("SELECT target_id FROM app_logs").fetchone()[0] == "samir"


def test_migration_6_enregistree():
    assert (6, "masquer_identifiants_de_connexion", _m_mask_login_failed_identifiers) in migrations.MIGRATIONS
