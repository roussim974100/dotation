"""Installateur de la mise a jour depuis le navigateur (setup/install-web-update.sh) : unites generees, droits, activation, retrait.
Execute pour de vrai (bash) dans un faux dossier systemd avec de faux `systemctl` et `chown`. Ignore si bash est absent."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash indisponible")


def posix(path):
    return str(path).replace("\\", "/")


@pytest.fixture
def setup(tmp_path):
    units, bins, data, app = tmp_path / "systemd", tmp_path / "bin", tmp_path / "data", tmp_path / "app"
    for folder in (units, bins, data, app / "setup" / "systemd"):
        folder.mkdir(parents=True)
    for name in ("dotation-update.path", "dotation-update.service"):
        shutil.copy(ROOT / "setup" / "systemd" / name, app / "setup" / "systemd" / name)
    (app / "deploy.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (app / "deploy-dev.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (units / "dotation.service").write_text(
        f'[Service]\nUser=www-data\nGroup=www-data\nEnvironment="APP_DATA_DIR={posix(data)}"\nExecStart=/x/gunicorn -b 127.0.0.1:5000 app:app\n', encoding="utf-8")
    for stub in ("systemctl", "chown"):
        (bins / stub).write_text(f'#!/bin/bash\necho "{stub} $*" >> "$STUB_LOG"\nexit 0\n', encoding="utf-8")
        (bins / stub).chmod(0o755)
    subprocess.run(["git", "init", "-q", "-b", "prod", posix(app)], check=True)
    subprocess.run(["git", "-C", posix(app), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, DEPLOY_TEST="1", APP_DIR=posix(app), INSTALL_UNIT_DIR=posix(units), STUB_LOG=posix(tmp_path / "stub.log"),
               HOME=posix(home), PATH=posix(bins) + os.pathsep + os.environ["PATH"])

    def run(*args, extra_env=None):
        return subprocess.run([BASH, posix(ROOT / "setup" / "install-web-update.sh"), *args], capture_output=True, text=True, encoding="utf-8",
                              env={**env, **(extra_env or {})})

    class S:
        pass

    s = S()
    s.run, s.units, s.data, s.app, s.log = run, units, data, app, tmp_path / "stub.log"
    return s


def test_install_writes_the_units_the_dropin_and_activates_the_watcher(setup):
    result = setup.run("--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    path_unit = (setup.units / "dotation-update.path").read_text(encoding="utf-8")
    service_unit = (setup.units / "dotation-update.service").read_text(encoding="utf-8")
    assert f"PathExists={posix(setup.data)}/update/request.json" in path_unit and "@DATA_DIR@" not in path_unit
    assert f"ExecStart=/bin/bash {posix(setup.app)}/deploy.sh --from-web" in service_unit  # branche prod -> deploy.sh
    assert "Type=oneshot" in service_unit and "@APP_DIR@" not in service_unit and "@DEPLOY_SCRIPT@" not in service_unit
    dropin = (setup.units / "dotation.service.d" / "web-update.conf").read_text(encoding="utf-8")
    assert 'APP_ALLOW_WEB_UPDATE=1' in dropin
    assert (setup.data / "update").is_dir()
    calls = setup.log.read_text(encoding="utf-8")
    assert f"chown www-data:www-data {posix(setup.data)}/update" in calls  # l'application (utilisateur du service) peut y deposer la demande
    assert "enable --now dotation-update.path" in calls and "daemon-reload" in calls and "restart dotation" in calls


def test_the_dev_branch_installs_the_dev_script(setup):
    subprocess.run(["git", "-C", posix(setup.app), "checkout", "-q", "-b", "dev"], check=True)
    assert setup.run("--yes").returncode == 0
    assert "deploy-dev.sh --from-web" in (setup.units / "dotation-update.service").read_text(encoding="utf-8")


def test_without_confirmation_the_service_is_not_restarted(setup):
    result = subprocess.run([BASH, posix(ROOT / "setup" / "install-web-update.sh")], input="n\n", capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "DEPLOY_TEST": "1", "APP_DIR": posix(setup.app), "INSTALL_UNIT_DIR": posix(setup.units),
                                 "STUB_LOG": posix(setup.log), "HOME": posix(setup.app.parent / "home"),
                                 "PATH": posix(setup.app.parent / "bin") + os.pathsep + os.environ["PATH"]})
    assert result.returncode == 0 and "restart dotation" not in setup.log.read_text(encoding="utf-8")
    assert "pense a redemarrer" in result.stdout


def test_uninstall_removes_everything_it_installed(setup):
    setup.run("--yes")
    result = setup.run("--uninstall", "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("dotation-update.path", "dotation-update.service"):
        assert not (setup.units / name).exists()
    assert not (setup.units / "dotation.service.d").exists()
    assert "disable --now dotation-update.path" in setup.log.read_text(encoding="utf-8")


def test_it_refuses_to_run_without_root_and_without_the_service(setup):
    refused = setup.run("--yes", extra_env={"DEPLOY_TEST": "0"})
    if os.geteuid() != 0 if hasattr(os, "geteuid") else True:
        assert refused.returncode == 1 and "root" in refused.stderr
    (setup.units / "dotation.service").unlink()
    missing = setup.run("--yes")
    assert missing.returncode == 1 and "introuvable" in missing.stderr


def test_unknown_options_are_refused(setup):
    assert setup.run("--nimporte-quoi").returncode == 2
