"""Doublons de personnes : le scan ne regroupe que par identite exacte (nom+prenom+service), la fusion ne
supprime ni ne modifie aucun dossier (seul le rattachement change), et refuse tout ce qu'elle n'est pas sure
de pouvoir faire sans deviner."""
import json
import sqlite3
import sys
from pathlib import Path

import bcrypt
import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from auth import create_user, delete_user
from database import get_db
from models.person_duplicates import merge_persons, scan_person_duplicates

H = {"X-CSRF-Token": "jeton"}


def _uid():
    import time
    return str(time.time_ns())


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = user
        s["csrf_token"] = "jeton"
    return client


@pytest.fixture
def lecture_user():
    name = f"persondup_{_uid()}"
    assert create_user(name, bcrypt.hashpw(b"Mot-2-Passe-Dup1!", bcrypt.gensalt()).decode(), ["lecture"])
    yield name
    delete_user(name)


@pytest.fixture
def two_duplicate_persons():
    p1, p2 = f"p1_{_uid()}", f"p2_{_uid()}"
    with get_db() as c:
        for pid, created in ((p1, "2026-01-01"), (p2, "2026-02-01")):
            c.execute(
                "INSERT INTO persons (id, nom, prenom, qualite, service, is_active, created_at, updated_at) VALUES (?,?,?,?,?,1,?,?)",
                (pid, "Dupont", "Jean", "agent", "DRH", created, created),
            )
    yield p1, p2
    with get_db() as c:
        c.execute("DELETE FROM persons WHERE id IN (?, ?)", (p1, p2))


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE persons (
            id TEXT PRIMARY KEY, nom TEXT, prenom TEXT, qualite TEXT, service TEXT,
            is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE onboarding_dossiers (id TEXT PRIMARY KEY, person_id TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, person_id TEXT, payload_json TEXT);
    """)
    return c


def _person(c, pid, nom, prenom, service, created_at="2026-01-01", is_active=1):
    c.execute(
        "INSERT INTO persons (id, nom, prenom, qualite, service, is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (pid, nom, prenom, "agent", service, is_active, created_at, created_at),
    )


def test_deux_fiches_meme_identite_sont_groupees():
    c = _db()
    _person(c, "p1", "Guerriero", "Lilou", "DRH", created_at="2026-01-01")
    _person(c, "p2", "GUERRIERO", " Lilou ", "drh", created_at="2026-02-01")  # casse/espaces/accents ignores
    _person(c, "p3", "Martin", "Jean", "DRH")
    groups = scan_person_duplicates(c)
    assert len(groups) == 1
    assert [p["id"] for p in groups[0]["persons"]] == ["p1", "p2"]  # la plus ancienne en premier


def test_meme_nom_service_different_n_est_pas_un_doublon():
    c = _db()
    _person(c, "p1", "Martin", "Jean", "DRH")
    _person(c, "p2", "Martin", "Jean", "Communication")
    assert scan_person_duplicates(c) == []


def test_fiche_inactive_n_est_pas_signalee():
    c = _db()
    _person(c, "p1", "Martin", "Jean", "DRH")
    _person(c, "p2", "Martin", "Jean", "DRH", is_active=0)
    assert scan_person_duplicates(c) == []


def test_fusion_repointe_dossiers_et_supprime_la_fiche_source():
    c = _db()
    _person(c, "p1", "Guerriero", "Lilou", "DRH", created_at="2026-01-01")
    _person(c, "p2", "Guerriero", "Lilou", "DRH", created_at="2026-02-01")
    c.execute("INSERT INTO onboarding_dossiers (id, person_id) VALUES ('d1','p2')")
    c.execute("INSERT INTO dotation_forms (id, person_id, payload_json) VALUES ('f1','p2',?)",
              (json.dumps({"meta": {"personId": "p2"}, "beneficiaire": {"nom": "Guerriero"}}),))

    report = merge_persons(c, keep_id="p1", drop_id="p2")

    assert report == {"movedDossiers": 1}
    assert c.execute("SELECT person_id FROM onboarding_dossiers WHERE id = 'd1'").fetchone()[0] == "p1"
    form = c.execute("SELECT person_id, payload_json FROM dotation_forms WHERE id = 'f1'").fetchone()
    assert form["person_id"] == "p1"
    payload = json.loads(form["payload_json"])
    assert payload["meta"]["personId"] == "p1"
    assert payload["beneficiaire"]["nom"] == "Guerriero"  # le reste du dossier n'est pas touche
    assert c.execute("SELECT COUNT(*) FROM persons WHERE id = 'p2'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM persons WHERE id = 'p1'").fetchone()[0] == 1


def test_fusion_refuse_la_meme_fiche():
    c = _db()
    _person(c, "p1", "Guerriero", "Lilou", "DRH")
    with pytest.raises(ValueError, match="same_person"):
        merge_persons(c, "p1", "p1")


def test_fusion_refuse_une_fiche_introuvable():
    c = _db()
    _person(c, "p1", "Guerriero", "Lilou", "DRH")
    with pytest.raises(ValueError, match="person_not_found"):
        merge_persons(c, "p1", "inexistant")


def test_fusion_refuse_des_identites_differentes():
    c = _db()
    _person(c, "p1", "Guerriero", "Lilou", "DRH")
    _person(c, "p2", "Martin", "Jean", "Communication")
    with pytest.raises(ValueError, match="identity_mismatch"):
        merge_persons(c, "p1", "p2")


# ---- routes (droit db.manage, copie de securite) --------------------------------------------------------------

def test_lecture_n_a_pas_le_droit_de_voir_ni_de_fusionner(lecture_user, two_duplicate_persons):
    client = client_for(lecture_user)
    p1, p2 = two_duplicate_persons
    assert client.get("/api/admin/person-duplicates").status_code == 403
    assert client.post("/api/admin/person-duplicates/merge", json={"keepId": p1, "dropId": p2}, headers=H).status_code == 403


def test_admin_peut_scanner_et_fusionner(two_duplicate_persons):
    client = client_for("admin")
    p1, p2 = two_duplicate_persons

    scan = client.get("/api/admin/person-duplicates").get_json()
    group = next(g for g in scan["groups"] if p1 in [p["id"] for p in g["persons"]])
    assert {p["id"] for p in group["persons"]} == {p1, p2}

    resp = client.post("/api/admin/person-duplicates/merge", json={"keepId": p1, "dropId": p2}, headers=H)
    assert resp.status_code == 200
    assert resp.get_json()["movedDossiers"] == 0

    with get_db() as c:
        assert c.execute("SELECT COUNT(*) FROM persons WHERE id = ?", (p2,)).fetchone()[0] == 0

    scan_after = client.get("/api/admin/person-duplicates").get_json()
    assert all(p1 not in [p["id"] for p in g["persons"]] for g in scan_after["groups"])


def test_fusion_invalide_renvoie_400_sans_rien_faire(two_duplicate_persons):
    client = client_for("admin")
    p1, p2 = two_duplicate_persons
    resp = client.post("/api/admin/person-duplicates/merge", json={"keepId": p1, "dropId": p1}, headers=H)
    assert resp.status_code == 400
    with get_db() as c:
        assert c.execute("SELECT COUNT(*) FROM persons WHERE id IN (?, ?)", (p1, p2)).fetchone()[0] == 2
