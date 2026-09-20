"""Script de deploiement (setup/deploy-common.sh) : succes, RETOUR ARRIERE AUTOMATIQUE, verrou, suivi de progression.

Le script tourne pour de vrai (bash) dans un environnement de test : depot git temporaire (origine + copie de travail), faux
`systemctl`, `curl`, `journalctl` et `pip`, faux service. Aucune commande systeme reelle n'est lancee. Ignore si bash est absent.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash indisponible")


def posix(path):
    return str(path).replace("\\", "/")


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")


def git(repo, *args):
    result = run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args], cwd=posix(repo))
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


STUBS = {
    # « service » simule par un fichier d'etat : bon si le code n'a pas le fichier BAD, casse sinon.
    "systemctl": r'''#!/bin/bash
echo "$*" >> "$STUB_LOG"
case "$1" in
  restart|start)
    if [ -f "$APP_DIR/BAD" ]; then echo bad > "$STUB_STATE"; "$PYEXE" -c "
import sqlite3, os
c = sqlite3.connect(os.path.join(os.environ['DATA_DIR'], 'dotation.db')); c.execute('CREATE TABLE IF NOT EXISTS migrated_bad (x)'); c.commit()"
    else echo good > "$STUB_STATE"; fi ;;
  stop) echo stopped > "$STUB_STATE" ;;
esac
exit 0
''',
    "curl": '#!/bin/bash\n[ "$(cat "$STUB_STATE" 2>/dev/null)" = "good" ]\n',
    "journalctl": "#!/bin/bash\necho 'journal de test : erreur simulee'\n",
}


@pytest.fixture
def env(tmp_path):
    base = tmp_path
    origin, work, other = base / "origin.git", base / "work", base / "other"
    data, venv, bins = base / "data", base / "venv" / "bin", base / "bin"
    for folder in (data, venv, bins):
        folder.mkdir(parents=True)

    git(base, "init", "-q", "--bare", "-b", "prod", posix(origin))
    git(base, "clone", "-q", posix(origin), posix(work))
    git(work, "checkout", "-q", "-b", "prod")
    (work / "backend").mkdir()
    (work / "frontend" / "js").mkdir(parents=True)
    (work / "backend" / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (work / "frontend" / "js" / "branding.js").write_text('const APP_BUILD_VERSION = "1.0.0";\n', encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "v1")
    git(work, "push", "-q", "origin", "prod")
    v1 = git(work, "rev-parse", "HEAD")

    # faux venv (gunicorn factice, python reel, pip pilotable)
    gunicorn = venv / "gunicorn"
    gunicorn.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (venv / "python").write_text(f'#!/bin/bash\nexec "{posix(sys.executable)}" "$@"\n', encoding="utf-8")
    (venv / "pip").write_text('#!/bin/bash\n[ -f "$APP_DIR/PIPFAIL" ] && exit 1\nexit 0\n', encoding="utf-8")
    for stub, body in STUBS.items():
        (bins / stub).write_text(body, encoding="utf-8")
    for path in (*venv.iterdir(), *bins.iterdir()):
        path.chmod(0o755)

    unit = base / "dotation-test.service"
    unit.write_text(f"[Service]\nEnvironment=\"APP_DATA_DIR={posix(data)}\"\nExecStart={posix(gunicorn)} -w 1 -b 127.0.0.1:5999 app:app\n", encoding="utf-8")

    for name in ("dotation.db", "users.db"):
        connection = sqlite3.connect(str(data / name))
        connection.execute("CREATE TABLE t (v)")
        connection.execute("INSERT INTO t VALUES ('avant')")
        connection.commit()
        connection.close()

    state = base / "state"
    state.write_text("good", encoding="utf-8")

    environment = dict(
        os.environ, DEPLOY_TEST="1", DEPLOY_SLEEP="0", DEPLOY_HEALTH_TRIES="3", DEPLOY_UNIT_PATH=posix(unit),
        DEPLOY_BRANCH="prod", DEPLOY_SCRIPT="deploy.sh", APP_DIR=posix(work), SERVICE="dotation-test",
        STUB_LOG=posix(base / "stub.log"), STUB_STATE=posix(state), PYEXE=posix(sys.executable), DATA_DIR=posix(data),
        PATH=posix(bins) + os.pathsep + os.environ["PATH"],
    )

    def publish(version, extra_files=()):
        """Publie une nouvelle version sur l'origine (depuis un second clone)."""
        if not other.exists():
            git(base, "clone", "-q", "-b", "prod", posix(origin), posix(other))
        (other / "frontend" / "js" / "branding.js").write_text(f'const APP_BUILD_VERSION = "{version}";\n', encoding="utf-8")
        for name in extra_files:
            (other / name).write_text("x", encoding="utf-8")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", f"v{version}")
        git(other, "push", "-q", "origin", "prod")

    def deploy(*args):
        result = run([BASH, "-c", 'set -euo pipefail; f="$1"; shift; source "$f" "$@"', "_", posix(ROOT / "setup" / "deploy-common.sh"), *args],
                     cwd=posix(work), env=environment)
        time.sleep(0.3)  # laisse « tee » finir d'ecrire update.log
        return result

    def status():
        path = data / "update" / "status.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def db_tables(name="dotation.db"):
        connection = sqlite3.connect(str(data / name))
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        connection.close()
        return tables

    class Env:
        pass

    e = Env()
    e.work, e.data, e.v1, e.publish, e.deploy, e.status, e.db_tables, e.state = work, data, v1, publish, deploy, status, db_tables, state
    e.head = lambda: git(work, "rev-parse", "HEAD")
    e.env = environment
    return e


def test_a_good_update_succeeds_and_leaves_a_trace(env):
    env.publish("2.0.0")
    result = env.deploy()
    assert result.returncode == 0, result.stdout + result.stderr
    assert env.head() != env.v1
    status = env.status()
    assert status["state"] == "ok" and status["from"] == "1.0.0" and status["to"] == "2.0.0" and status["finished_at"] > status["started_at"]
    backups = list((env.work / "backend" / "db_backups").glob("avant_maj_*"))
    assert backups and (backups[0] / "dotation.db").exists() and (backups[0] / "users.db").exists()
    assert not (env.data / "update" / "lock.d").exists()  # verrou libere
    assert "Sauvegarde des bases" in (env.data / "update" / "update.log").read_text(encoding="utf-8")


def test_an_unhealthy_new_version_is_rolled_back_code_and_databases(env):
    env.publish("2.0.0", extra_files=["BAD"])  # le nouveau code « ne demarre pas » et a deja migre la base
    result = env.deploy()
    assert result.returncode == 1
    assert env.head() == env.v1, "le code doit revenir a la version precedente"
    assert "migrated_bad" not in env.db_tables(), "la base doit etre restauree (migration annulee)"
    connection = sqlite3.connect(str(env.data / "dotation.db"))
    assert connection.execute("SELECT v FROM t").fetchone()[0] == "avant"
    connection.close()
    assert env.state.read_text(encoding="utf-8").strip() == "good", "l'ancienne version doit repondre de nouveau"
    status = env.status()
    assert status["state"] == "rolled_back" and "1.0.0" in status["message"]
    assert "RETOUR ARRIÈRE" in (env.data / "update" / "update.log").read_text(encoding="utf-8")


def test_no_rollback_option_keeps_the_broken_state_for_diagnosis(env):
    env.publish("2.0.0", extra_files=["BAD"])
    result = env.deploy("--no-rollback")
    assert result.returncode == 1
    assert env.head() != env.v1 and "migrated_bad" in env.db_tables()
    assert env.status()["state"] == "failed" and "no-rollback" in env.status()["message"]


def test_a_dependency_failure_rolls_the_code_back_without_touching_the_databases(env):
    env.publish("2.0.0", extra_files=["PIPFAIL"])
    result = env.deploy()
    assert result.returncode == 1
    assert env.head() == env.v1 and env.status()["state"] == "rolled_back"
    assert "avant_maj" in " ".join(p.name for p in (env.work / "backend" / "db_backups").iterdir())
    restarts = (env.data.parent / "stub.log").read_text(encoding="utf-8").count("restart")
    assert restarts == 0, "le service n'a jamais du redemarrer sur du code dont les dependances n'ont pas pu etre installees"


def test_uncommitted_local_changes_are_refused_unless_forced(env):
    env.publish("2.0.0")
    (env.work / "frontend" / "js" / "branding.js").write_text('const APP_BUILD_VERSION = "1.0.0-modif";\n', encoding="utf-8")
    result = env.deploy()
    assert result.returncode == 1 and env.head() == env.v1
    assert env.status()["state"] == "failed" and "modifi" in env.status()["message"]
    assert env.deploy("--force").returncode == 0 and env.head() != env.v1


def test_a_running_deployment_blocks_a_second_one_and_a_dead_lock_is_recovered(env):
    env.publish("2.0.0")
    lock = env.data / "update" / "lock.d"
    lock.mkdir(parents=True)
    alive = subprocess.Popen([BASH, "-c", "echo $$; exec sleep 30"], stdout=subprocess.PIPE, text=True)
    try:
        (lock / "pid").write_text(alive.stdout.readline().strip(), encoding="utf-8")
        blocked = env.deploy()
        assert blocked.returncode == 1 and "déjà en cours" in (blocked.stdout + blocked.stderr)
        assert env.head() == env.v1
    finally:
        alive.kill()
    (lock / "pid").write_text("999999", encoding="utf-8")  # processus mort : le verrou est repris
    assert env.deploy().returncode == 0 and env.head() != env.v1


def test_the_pending_request_file_is_consumed_and_unknown_options_refused(env):
    env.publish("2.0.0")
    request = env.data / "update" / "request.json"
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text("{}", encoding="utf-8")
    assert env.deploy("--from-web").returncode == 0
    assert not request.exists()  # sinon l'unite de surveillance relancerait le script en boucle
    bad = env.deploy("--nimporte-quoi")
    assert bad.returncode == 2
