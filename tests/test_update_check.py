"""Detection de nouvelle version et demande de mise a jour depuis le navigateur."""
import sys
import time
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import update_check as uc


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    update_dir = tmp_path / "update"
    monkeypatch.setattr(uc, "UPDATE_DIR", str(update_dir))
    monkeypatch.setattr(uc, "CHECK_FILE", str(update_dir / "check.json"))
    monkeypatch.setattr(uc, "REQUEST_FILE", str(update_dir / "request.json"))
    monkeypatch.setattr(uc, "STATUS_FILE", str(update_dir / "status.json"))
    monkeypatch.setattr(uc, "current_version", lambda: "3.48.0-dev")
    monkeypatch.delenv("APP_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("APP_UPDATE_CHECK_URL", raising=False)
    monkeypatch.delenv("APP_ALLOW_WEB_UPDATE", raising=False)
    return update_dir


def test_version_comparison_and_channel():
    assert uc.is_newer("3.49.0-dev", "3.48.0-dev") and uc.is_newer("3.48.1", "3.48.0-prod") and uc.is_newer("4.0.0", "3.99.9")
    assert not uc.is_newer("3.48.0", "3.48.0-dev") and not uc.is_newer("3.47.9", "3.48.0") and not uc.is_newer(None, "3.48.0")
    assert not uc.is_newer("n'importe quoi", "3.48.0")
    assert uc.channel_for("3.48.0-dev") == "dev" and uc.channel_for("3.18.5-prod") == "prod" and uc.channel_for("") == "prod"
    assert uc.channel_for("3.49.0-preprod") == "preprod" and "/preprod/frontend/js/branding.js" in uc.source_url("3.49.0-preprod")
    assert "/dev/frontend/js/branding.js" in uc.source_url("3.48.0-dev") and "/prod/frontend/js/branding.js" in uc.source_url("3.18.5-prod")


def test_the_real_installed_version_is_readable():
    assert uc.parse_version(uc.current_version()) is not None  # branding.js reel, sans le remplacement du fixture


def test_a_newer_remote_version_is_reported_and_cached(isolated):
    result = uc.refresh(url="https://exemple.invalide/branding.js", fetch=lambda url: "3.50.0-dev")
    assert result["latest"] == "3.50.0-dev" and result["error"] is None
    state = uc.status()
    assert state["available"] is True and state["latest"] == "3.50.0-dev" and state["current"] == "3.48.0-dev"
    assert state["channel"] == "dev" and state["can_update"] is False


def test_same_or_older_remote_version_is_not_an_update(isolated):
    uc.refresh(fetch=lambda url: "3.48.0-dev")
    assert uc.status()["available"] is False


def test_network_failure_is_silent_and_keeps_the_last_known_version(isolated):
    uc.refresh(fetch=lambda url: "3.49.0-dev")

    def broken(url):
        raise OSError("réseau coupé")

    result = uc.refresh(fetch=broken)
    assert result["error"] and result["latest"] == "3.49.0-dev"  # on conserve la derniere version connue
    state = uc.status()
    assert state["error"] and state["available"] is True


def test_the_very_first_check_is_synchronous_so_the_page_shows_the_result(isolated, monkeypatch):
    calls = []

    def fake_refresh(url=None, fetch=None):
        calls.append("sync")
        return {"latest": "3.60.0-dev", "checked_at": time.time(), "error": None}

    monkeypatch.setattr(uc, "refresh", fake_refresh)
    state = uc.status()  # aucun cache : la verification est faite tout de suite
    assert calls == ["sync"] and state["available"] is True and state["latest"] == "3.60.0-dev"


def test_disabled_check_never_touches_the_network(isolated, monkeypatch):
    monkeypatch.setenv("APP_UPDATE_CHECK", "0")
    monkeypatch.setattr(uc, "refresh", lambda *a, **k: pytest.fail("aucune verification attendue"))
    state = uc.status(force=True)
    assert state["enabled"] is False and state["available"] is False and state["latest"] is None


def test_stale_cache_triggers_a_background_refresh_without_blocking(isolated, monkeypatch):
    calls = []
    monkeypatch.setattr(uc, "_refresh_in_background", lambda: calls.append("bg"))
    uc._write_json_atomic(uc.CHECK_FILE, {"latest": "3.49.0-dev", "checked_at": time.time() - 7 * 3600})
    state = uc.status()
    assert calls == ["bg"] and state["latest"] == "3.49.0-dev"  # reponse immediate avec la valeur en cache
    calls.clear()
    uc._write_json_atomic(uc.CHECK_FILE, {"latest": "3.49.0-dev", "checked_at": time.time() - 60})
    uc.status()
    assert calls == []  # cache recent : pas de nouvelle verification


def test_an_invalid_source_address_is_refused():
    with pytest.raises(ValueError):
        uc.fetch_latest_version("file:///etc/passwd")
    with pytest.raises(ValueError):
        uc.fetch_latest_version("ftp://exemple.fr/branding.js")


def test_web_update_is_off_by_default_and_needs_every_condition(isolated, monkeypatch, tmp_path):
    assert uc.can_update() is False
    monkeypatch.setenv("APP_ALLOW_WEB_UPDATE", "1")
    assert uc.can_update() is False  # unite systemd absente
    unit = tmp_path / "dotation-update.path"
    unit.write_text("[Path]")
    monkeypatch.setattr(uc, "PATH_UNIT", str(unit))
    isolated.mkdir(parents=True, exist_ok=True)
    assert uc.can_update() is True
    monkeypatch.setenv("APP_ALLOW_WEB_UPDATE", "0")
    assert uc.can_update() is False  # sans activation explicite : jamais


def test_request_file_is_written_atomically_and_blocks_a_second_run(isolated):
    assert uc.update_in_progress() is False
    uc.request_update("admin", "3.50.0")
    assert uc.update_in_progress() is True
    assert uc._read_json(uc.REQUEST_FILE)["requested_by"] == "admin"
    Path(uc.REQUEST_FILE).unlink()
    uc._write_json_atomic(uc.STATUS_FILE, {"state": "running"})
    assert uc.update_in_progress() is True
    uc._write_json_atomic(uc.STATUS_FILE, {"state": "ok"})
    assert uc.update_in_progress() is False
