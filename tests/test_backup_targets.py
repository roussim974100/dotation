"""Destinations de sauvegarde : validation, test, envoi, historique."""
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import backup
import backup_targets as targets


def _make_db(path, statements):
    conn = sqlite3.connect(path)
    for statement in statements:
        conn.execute(statement)
    conn.commit()
    conn.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    dotation, users = str(tmp_path / "dotation.db"), str(tmp_path / "users.db")
    _make_db(dotation, [
        "CREATE TABLE dotation_forms (id TEXT)", "CREATE TABLE dotation_items (id TEXT)",
        "CREATE TABLE resource_catalog (id TEXT)", "CREATE TABLE service_catalog (id TEXT)",
        "CREATE TABLE app_settings (setting_key TEXT, setting_value TEXT)", "CREATE TABLE app_logs (id TEXT)",
    ])
    _make_db(users, ["CREATE TABLE users (username TEXT)", "CREATE TABLE groups (key TEXT)", "CREATE TABLE user_groups (u TEXT)", "INSERT INTO users VALUES ('a')"])
    specs = [dict(db) for db in backup.DATABASES]
    specs[0]["path"], specs[1]["path"] = dotation, users
    monkeypatch.setattr(backup, "DATABASES", specs)
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path / "db_backups"))
    monkeypatch.setattr(targets, "CONFIG_PATH", str(tmp_path / "backup_config.json"))
    monkeypatch.setattr(targets, "HISTORY_PATH", str(tmp_path / "db_backups" / "history.jsonl"))
    share = tmp_path / "partage"
    share.mkdir()
    return {"share": str(share), "tmp": tmp_path}


def _dest(env, **extra):
    return {"label": "NAS", "protocol": "smb", "path": env["share"], **extra}


def test_destination_requires_label_and_absolute_path(env):
    with pytest.raises(targets.TargetError) as no_label:
        targets.validate_destination({"path": env["share"]})
    assert no_label.value.code == "label_required"
    with pytest.raises(targets.TargetError) as relative:
        targets.validate_destination({"label": "x", "path": "sauvegardes/relatif"})
    assert relative.value.code == "path_not_absolute"


def test_destination_inside_the_application_is_forbidden():
    with pytest.raises(targets.TargetError) as error:
        targets.validate_destination({"label": "x", "path": targets.FRONTEND_DIR})
    assert error.value.code == "path_forbidden"
    with pytest.raises(targets.TargetError):
        targets.validate_destination({"label": "x", "path": targets.BASE_DIR})


def test_destinations_are_saved_with_unique_ids_and_no_credentials(env):
    saved = targets.save_destinations([_dest(env), _dest(env, label="Copie")])
    assert len({d["id"] for d in saved}) == 2
    assert [d["protocol"] for d in saved] == ["smb", "smb"]
    # Seuls ces champs sont conserves : jamais d'identifiant ni de mot de passe de partage.
    assert all(set(d) == {"id", "label", "protocol", "path", "enabled"} for d in saved)
    assert targets.load_config()["destinations"] == saved


def test_unknown_protocol_falls_back_to_local(env):
    assert targets.validate_destination(_dest(env, protocol="ftp"))["protocol"] == "local"


def test_destination_test_detects_unreachable_and_reports_free_space(env):
    ok = targets.test_destination({"path": env["share"]})
    assert ok["ok"] is True and ok["free_bytes"] > 0
    with pytest.raises(targets.TargetError) as error:
        targets.test_destination({"path": str(env["tmp"] / "absent")})
    assert error.value.code == "path_unreachable"


def test_send_writes_a_readable_archive_and_logs_success(env):
    destination = targets.save_destinations([_dest(env)])[0]
    entry = targets.run_send(destination, "motdepasse-solide", trigger="manual")
    files = list(Path(env["share"]).iterdir())
    assert [f.name for f in files] == [entry["filename"]]  # aucun .part restant
    manifest, contents = backup.open_archive(files[0].read_bytes(), "motdepasse-solide")
    assert set(contents) == {"dotation", "users"}
    history = targets.read_history()
    assert history[0]["ok"] is True and history[0]["encrypted"] is True and history[0]["trigger"] == "manual"
    assert "motdepasse" not in str(history)


def test_send_to_unreachable_destination_logs_the_failure(env):
    destination = {"id": "dest_x", "label": "Absent", "protocol": "smb", "path": str(env["tmp"] / "absent")}
    with pytest.raises(targets.TargetError):
        targets.run_send(destination, None, trigger="manual")
    last = targets.read_history()[0]
    assert last["ok"] is False and last["code"] == "path_unreachable"


def test_send_never_overwrites_an_existing_archive(env):
    destination = _dest(env)
    (Path(env["share"]) / "aquai_sauvegarde_20260101_000000.zip").write_bytes(b"ancien")
    with pytest.raises(targets.TargetError) as error:
        targets.send_archive(destination, b"nouveau", "aquai_sauvegarde_20260101_000000.zip")
    assert error.value.code == "already_exists"
    assert (Path(env["share"]) / "aquai_sauvegarde_20260101_000000.zip").read_bytes() == b"ancien"


def test_send_refuses_unsafe_file_names(env):
    with pytest.raises(targets.TargetError) as error:
        targets.send_archive(_dest(env), b"x", "../evasion.zip")
    assert error.value.code == "bad_filename"
