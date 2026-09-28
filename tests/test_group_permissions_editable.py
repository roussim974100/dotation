"""Tableau dynamique des autorisations (admin > groupes) : toute permission devient modifiable via
PUT /api/admin/groups/<key> (avant, seul unc.view_all l'etait), avec un garde-fou empechant un admin de se
retirer lui-meme users.manage/db.manage s'il n'a pas d'autre groupe qui le porte. Base temporaire (tests/conftest.py)."""
import json
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_users_db

H = {"X-CSRF-Token": "jeton"}


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = user
        flask_session["csrf_token"] = "jeton"
    return client


def group_permissions(key):
    with get_users_db() as connection:
        row = connection.execute("SELECT permissions_json FROM groups WHERE key = ?", (key,)).fetchone()
        return json.loads(row["permissions_json"] or "[]")


def test_any_permission_is_now_toggleable():
    client = client_for("admin")
    assert "forms.adjust" not in group_permissions("user")

    resp = client.put("/api/admin/groups/user", json={"forms.adjust": True}, headers=H)
    assert resp.status_code == 200
    assert "forms.adjust" in group_permissions("user")

    resp = client.put("/api/admin/groups/user", json={"forms.adjust": False}, headers=H)
    assert resp.status_code == 200
    assert "forms.adjust" not in group_permissions("user")
    print("[PASS] une permission hors unc.view_all est desormais basculable via l'API")


def test_self_lockout_guard_blocks_removing_own_users_manage():
    client = client_for("admin")
    assert "users.manage" in group_permissions("admin")

    resp = client.put("/api/admin/groups/admin", json={"users.manage": False}, headers=H)
    assert resp.status_code == 409
    assert resp.get_json().get("error") == "self_lockout"
    assert "users.manage" in group_permissions("admin"), "le droit ne doit pas avoir ete retire"
    print("[PASS] impossible de se retirer soi-meme users.manage sans autre groupe de secours")


def test_self_lockout_guard_does_not_block_other_groups():
    client = client_for("admin")
    # "administration" porte aussi users.manage par defaut, mais l'acteur ("admin") n'appartient pas a ce
    # groupe : le retirer d'un groupe auquel il n'appartient pas ne doit jamais etre bloque.
    assert "users.manage" in group_permissions("administration")

    resp = client.put("/api/admin/groups/administration", json={"users.manage": False}, headers=H)
    assert resp.status_code == 200
    assert "users.manage" not in group_permissions("administration")
    print("[PASS] le garde-fou ne bloque pas le retrait sur un groupe auquel l'acteur n'appartient pas")


def test_group_permissions_change_is_audited():
    client = client_for("admin")
    client.put("/api/admin/groups/user", json={"forms.export": True}, headers=H)
    from database import get_db
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM app_logs WHERE action_type = 'group_permissions_updated' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None, "le changement de permissions doit etre journalise"
    print("[PASS] un changement de permission de groupe est journalise")
