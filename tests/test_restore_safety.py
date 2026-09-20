"""Restauration : base d'une version plus recente refusee, base de comptes vide refusee, remplacement tout-ou-rien."""
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import backup
from migrations import MIGRATIONS


def _dotation_db(path, schema_version=None):
    c = sqlite3.connect(path)
    for table in ("dotation_forms", "dotation_items", "resource_catalog", "service_catalog", "app_settings", "app_logs"):
        c.execute(f"CREATE TABLE {table} (id TEXT)")
    if schema_version is not None:
        c.execute("CREATE TABLE schema_migrations (version INTEGER, name TEXT, applied_at TEXT)")
        c.execute("INSERT INTO schema_migrations VALUES (?, 'x', 'x')", (schema_version,))
    c.commit()
    c.close()


def test_base_d_une_version_plus_recente_est_refusee(tmp_path):
    path = tmp_path / "futur.db"
    _dotation_db(path, max(m[0] for m in MIGRATIONS) + 5)
    report = backup.diagnose_sqlite(str(path), "dotation")
    assert report["level"] == "error" and any("plus récente" in i for i in report["issues"])


def test_base_de_la_version_courante_ou_ancienne_est_acceptee(tmp_path):
    for version in (None, 1, max(m[0] for m in MIGRATIONS)):
        path = tmp_path / f"ok_{version}.db"
        _dotation_db(path, version)
        assert backup.diagnose_sqlite(str(path), "dotation")["level"] != "error", version


def test_base_de_comptes_vide_est_refusee(tmp_path):
    path = tmp_path / "users.db"
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE users (username TEXT); CREATE TABLE groups (key TEXT);")
    c.commit()
    c.close()
    report = backup.diagnose_sqlite(str(path), "users")
    assert report["level"] == "error" and any("Aucun compte" in i for i in report["issues"])


def test_restauration_tout_ou_rien_une_panne_sur_la_seconde_base_remet_la_premiere(tmp_path, monkeypatch):
    dotation, users = tmp_path / "dotation.db", tmp_path / "users.db"
    _dotation_db(dotation)
    u = sqlite3.connect(users)
    u.executescript("CREATE TABLE users (username TEXT); CREATE TABLE groups (key TEXT); CREATE TABLE user_groups (a TEXT);")
    u.execute("INSERT INTO users VALUES ('admin')")
    u.commit()
    u.close()
    c = sqlite3.connect(dotation)
    c.execute("CREATE TABLE etat (v TEXT)")
    c.execute("INSERT INTO etat VALUES ('DANS-L-ARCHIVE')")
    c.commit()
    c.close()
    monkeypatch.setattr(backup, "DATABASES", [dict(db, path=str(dotation if db["key"] == "dotation" else users)) for db in backup.DATABASES])
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path / "db_backups"))
    blob = backup.create_archive()[0] if isinstance(backup.create_archive(), tuple) else backup.create_archive()
    c = sqlite3.connect(dotation)
    c.execute("UPDATE etat SET v = 'ETAT-ACTUEL-A-CONSERVER'")
    c.commit()
    c.close()

    real_restore = backup.restore_sqlite
    calls = {"n": 0}

    def flaky(source, target):
        calls["n"] += 1
        if calls["n"] == 2:  # la seconde base (users) echoue apres que la premiere a ete remplacee
            raise sqlite3.OperationalError("disque plein simule")
        return real_restore(source, target)

    monkeypatch.setattr(backup, "restore_sqlite", flaky)
    try:
        backup.restore_archive(blob)
        raise AssertionError("la restauration aurait du echouer")
    except backup.BackupError as error:
        assert "remises à leur état d'avant" in str(error)
    monkeypatch.setattr(backup, "restore_sqlite", real_restore)
    assert sqlite3.connect(dotation).execute("SELECT v FROM etat").fetchone()[0] == "ETAT-ACTUEL-A-CONSERVER"
