"""Archive de sauvegarde multi-bases : creation, chiffrement, diagnostic, restauration."""
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import backup


def _make_db(path, statements):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    for statement in statements:
        conn.execute(statement)
    conn.commit()
    conn.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    dotation = str(tmp_path / "dotation.db")
    users = str(tmp_path / "users.db")
    _make_db(dotation, [
        "CREATE TABLE dotation_forms (id TEXT)", "CREATE TABLE dotation_items (id TEXT)",
        "CREATE TABLE resource_catalog (id TEXT)", "CREATE TABLE service_catalog (id TEXT)",
        "CREATE TABLE app_settings (setting_key TEXT, setting_value TEXT)", "CREATE TABLE app_logs (id TEXT)",
        "INSERT INTO dotation_forms VALUES ('f1')", "INSERT INTO dotation_forms VALUES ('f2')",
    ])
    _make_db(users, [
        "CREATE TABLE users (username TEXT)", "CREATE TABLE groups (key TEXT)", "CREATE TABLE user_groups (u TEXT)",
        "INSERT INTO users VALUES ('alice')",
    ])
    specs = [dict(db) for db in backup.DATABASES]
    specs[0]["path"], specs[1]["path"] = dotation, users
    monkeypatch.setattr(backup, "DATABASES", specs)
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path / "db_backups"))
    return {"dotation": dotation, "users": users}


def _count(path, table):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_plain_archive_contains_every_database_and_diagnoses_ok(env):
    blob, manifest = backup.create_archive()
    assert [d["key"] for d in manifest["databases"]] == ["dotation", "users"]
    assert not backup.is_encrypted(blob)
    report = backup.diagnose_archive(blob)
    assert report["level"] == "ok"
    assert {d["key"]: d["stats"] for d in report["databases"]} == {"dotation": {"dossiers": 2}, "users": {"comptes": 1}}


def test_restore_replaces_data_and_keeps_safety_copies(env):
    blob, _ = backup.create_archive()
    conn = sqlite3.connect(env["dotation"])
    conn.execute("DELETE FROM dotation_forms")
    conn.commit()
    conn.close()
    assert _count(env["dotation"], "dotation_forms") == 0

    result = backup.restore_archive(blob)

    assert sorted(result["restored"]) == ["dotation", "users"]
    assert _count(env["dotation"], "dotation_forms") == 2
    assert len(result["safety_copies"]) == 2
    assert len(backup.list_safety_copies()) == 2


def test_restore_can_target_a_single_database(env):
    blob, _ = backup.create_archive()
    conn = sqlite3.connect(env["users"])
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    result = backup.restore_archive(blob, keys=["users"])
    assert result["restored"] == ["users"]
    assert _count(env["users"], "users") == 1


def test_encrypted_archive_needs_the_right_password(env):
    blob, manifest = backup.create_archive(password="motdepasse-solide")
    assert backup.is_encrypted(blob) and manifest["encrypted"] is True
    assert b"dotation_forms" not in blob  # rien de lisible

    with pytest.raises(backup.BackupError) as missing:
        backup.diagnose_archive(blob)
    assert missing.value.code == "password_required"

    with pytest.raises(backup.BackupError) as wrong:
        backup.diagnose_archive(blob, "autre-mot-de-passe")
    assert wrong.value.code == "wrong_password"

    assert backup.diagnose_archive(blob, "motdepasse-solide")["level"] == "ok"


def test_tampered_encrypted_archive_is_rejected(env):
    blob, _ = backup.create_archive(password="motdepasse-solide")
    tampered = bytearray(blob)
    tampered[-5] ^= 0xFF
    with pytest.raises(backup.BackupError) as error:
        backup.open_archive(bytes(tampered), "motdepasse-solide")
    assert error.value.code == "wrong_password"


def test_short_password_is_refused(env):
    with pytest.raises(backup.BackupError) as error:
        backup.create_archive(password="court")
    assert error.value.code == "password_too_short"


def test_garbage_is_not_an_archive(env):
    with pytest.raises(backup.BackupError) as error:
        backup.open_archive(b"ceci n'est pas une archive")
    assert error.value.code == "invalid_archive"


def test_archive_with_broken_database_is_refused_before_any_write(env, tmp_path):
    blob, _ = backup.create_archive()
    # Remplace la base "users" par une base sans table users : l'archive doit etre refusee.
    broken = str(tmp_path / "broken.db")
    _make_db(broken, ["CREATE TABLE autre (x TEXT)"])
    specs = [dict(db) for db in backup.DATABASES]
    specs[1]["path"] = broken
    backup.DATABASES[:] = specs
    bad_blob, _ = backup.create_archive()
    with pytest.raises(backup.BackupError) as error:
        backup.restore_archive(bad_blob)
    assert error.value.code == "diagnose_failed"
    assert backup.list_safety_copies() == []


def test_oversized_database_entry_is_refused(env, monkeypatch):
    blob, _ = backup.create_archive()
    monkeypatch.setattr(backup, "MAX_DATABASE_BYTES", 10)
    with pytest.raises(backup.BackupError) as error:
        backup.open_archive(blob)
    assert error.value.code == "file_too_large"
