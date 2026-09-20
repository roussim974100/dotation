"""Sauvegarde planifiee : echeance, conservation, sante, execution, verrou."""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import backup
import backup_schedule as sched
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
    monkeypatch.setattr(sched, "LOCK_PATH", str(tmp_path / "db_backups" / ".lock"))
    monkeypatch.setattr(sched, "PASSWORD_FILE", str(tmp_path / ".pw"))
    monkeypatch.delenv("AQUAI_BACKUP_PASSWORD", raising=False)
    share = tmp_path / "partage"
    share.mkdir()
    targets.save_destinations([{"label": "NAS", "protocol": "smb", "path": str(share)}])
    return {"share": share, "tmp": tmp_path}


def _cfg(**schedule):
    config = targets.load_config()
    config["schedule"].update({"enabled": True, "frequency": "daily", "time": "02:00", **schedule})
    return config


def _log_run(when, ok=True, trigger="scheduled", error=None):
    os.makedirs(os.path.dirname(targets.HISTORY_PATH), exist_ok=True)
    entry = {"ts": when.astimezone(timezone.utc).isoformat(), "kind": "run", "trigger": trigger, "ok": ok, "error": error}
    with open(targets.HISTORY_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


NOW = datetime(2026, 9, 16, 10, 0)  # un mercredi


def test_latest_slot_daily_and_weekly():
    assert sched.latest_slot({"frequency": "daily", "time": "02:00"}, NOW) == datetime(2026, 9, 16, 2, 0)
    assert sched.latest_slot({"frequency": "daily", "time": "23:30"}, NOW) == datetime(2026, 9, 15, 23, 30)
    monday = {"frequency": "weekly", "time": "02:00", "weekday": 1}
    assert sched.latest_slot(monday, NOW) == datetime(2026, 9, 14, 2, 0)
    assert sched.latest_slot(monday, datetime(2026, 9, 14, 1, 0)) == datetime(2026, 9, 7, 2, 0)


def test_not_due_when_disabled_and_due_when_never_run(env):
    assert sched.is_due(_cfg(enabled=False), NOW) is False
    assert sched.is_due(_cfg(), NOW) is True


def test_due_only_once_per_slot_after_success(env):
    _log_run(datetime(2026, 9, 16, 2, 5))
    assert sched.is_due(_cfg(), NOW) is False
    assert sched.is_due(_cfg(), datetime(2026, 9, 17, 2, 1)) is True  # nouveau creneau


def test_failed_run_is_retried_after_delay_up_to_the_limit(env):
    _log_run(datetime(2026, 9, 16, 2, 5), ok=False, error="x")
    assert sched.is_due(_cfg(), datetime(2026, 9, 16, 2, 30)) is False  # trop tot
    assert sched.is_due(_cfg(), datetime(2026, 9, 16, 3, 10)) is True
    _log_run(datetime(2026, 9, 16, 3, 10), ok=False, error="x")
    _log_run(datetime(2026, 9, 16, 4, 15), ok=False, error="x")
    assert sched.is_due(_cfg(), datetime(2026, 9, 16, 9, 0)) is False  # 3 tentatives atteintes


def test_manual_runs_do_not_count_for_the_schedule(env):
    _log_run(datetime(2026, 9, 16, 2, 5), trigger="manual")
    assert sched.is_due(_cfg(), NOW) is True


def test_health_levels(env):
    assert sched.health(_cfg(enabled=False), NOW)["level"] == "info"
    assert sched.health(_cfg(), NOW)["level"] == "warning"  # aucune execution
    _log_run(datetime(2026, 9, 16, 2, 5), ok=False, error="partage absent")
    assert sched.health(_cfg(), NOW)["level"] == "error"
    _log_run(datetime(2026, 9, 16, 3, 0))
    assert sched.health(_cfg(), NOW)["level"] == "ok"
    assert sched.health(_cfg(), NOW + timedelta(days=5))["level"] == "error"  # plus rien depuis 2 jours


def test_run_without_password_fails_and_is_logged(env):
    summary = sched.run_scheduled()
    assert summary["ok"] is False and "introuvable" in summary["errors"][0]
    assert list(env["share"].iterdir()) == []
    assert sched.read_runs()[0]["ok"] is False


def test_run_with_server_password_sends_an_encrypted_archive(env, monkeypatch):
    monkeypatch.setenv("AQUAI_BACKUP_PASSWORD", "mot-de-passe-serveur")
    summary = sched.run_scheduled()
    assert summary["ok"] is True and summary["sent"] == 1
    archive = next(env["share"].iterdir())
    assert backup.is_encrypted(archive.read_bytes())
    assert backup.diagnose_archive(archive.read_bytes(), "mot-de-passe-serveur")["level"] == "ok"
    assert sched.read_runs()[0]["ok"] is True


def test_password_file_is_used_when_no_env_var(env):
    sched.write_password_file("mot-de-passe-fichier")
    assert sched.read_password(targets.load_config()) == ("mot-de-passe-fichier", "file")
    sched.clear_password_file()
    assert sched.read_password(targets.load_config()) == (None, None)


def test_unencrypted_run_needs_explicit_permission(env):
    config = targets.load_config()
    config["allow_unencrypted"] = True
    targets.save_config(config)
    assert sched.run_scheduled()["ok"] is True
    assert not backup.is_encrypted(next(env["share"].iterdir()).read_bytes())


def test_retention_purges_old_archives_but_keeps_the_minimum(env):
    destination = targets.load_config()["destinations"][0]
    now = datetime.now()
    for age_days in (60, 50, 40, 5, 1):
        stamp = (now - timedelta(days=age_days)).strftime("%Y%m%d_%H%M%S")
        path = env["share"] / f"aquai_sauvegarde_{stamp}.aqbak"
        path.write_bytes(b"x")
        past = time.time() - age_days * 86400
        os.utime(path, (past, past))
    (env["share"] / "important.txt").write_text("ne pas toucher")

    deleted = sched.apply_retention(destination, {"keep_days": 30, "keep_min": 4}, now)
    assert len(deleted) == 1  # seule la plus ancienne depasse 30 jours au-dela des 4 a garder
    assert (env["share"] / "important.txt").exists()
    deleted_all = sched.apply_retention(destination, {"keep_days": 30, "keep_min": 1}, now)
    assert len(deleted_all) == 2 and len(list(env["share"].glob("*.aqbak"))) == 2


def test_only_one_run_at_a_time(env):
    with sched.run_lock():
        with pytest.raises(sched.ScheduleError) as error:
            with sched.run_lock():
                pass
    assert error.value.code == "already_running"
    with sched.run_lock():  # verrou libere ensuite
        pass


@pytest.mark.parametrize("payload, code", [
    ({"schedule": {"frequency": "hourly"}}, "bad_frequency"),
    ({"schedule": {"time": "25:00"}}, "bad_time"),
    ({"schedule": {"frequency": "weekly", "weekday": 9}}, "bad_weekday"),
    ({"retention": {"keep_days": 0}}, "bad_retention"),
    ({"password_source": {"env_var": "pas valide"}}, "bad_env_var"),
])
def test_settings_are_validated(env, payload, code):
    with pytest.raises(sched.ScheduleError) as error:
        sched.validate_settings(payload, targets.load_config())
    assert error.value.code == code
