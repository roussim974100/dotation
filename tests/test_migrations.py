"""Migrations numerotees : appliquees une fois, copie de securite avant, identifiants de champs attribues, idempotence."""
import json
import os
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from migrations import MIGRATIONS, field_id_for, run_pending_migrations


def _base(tmp_path):
    path = tmp_path / "test.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE resource_catalog (id TEXT, code TEXT, field_schema_json TEXT);
        CREATE TABLE dotation_forms (id TEXT);
        INSERT INTO dotation_forms VALUES ('f1');
    """)
    connection.execute("INSERT INTO resource_catalog VALUES ('r1','pc',?)", (json.dumps([{"key": "numero", "label": "N"}, {"key": "marque", "label": "M", "id": "fld_deja"}]),))
    connection.commit()
    return connection, path


def test_migrations_appliquees_une_fois_avec_copie_de_securite(tmp_path):
    connection, path = _base(tmp_path)
    assert run_pending_migrations(connection) == [m[0] for m in MIGRATIONS]
    connection.commit()
    schema = json.loads(connection.execute("SELECT field_schema_json FROM resource_catalog").fetchone()[0])
    assert schema[0]["id"] == field_id_for("pc", "numero") and schema[1]["id"] == "fld_deja"  # un id existant n'est jamais change
    assert connection.execute("PRAGMA user_version").fetchone()[0] == max(m[0] for m in MIGRATIONS)
    backups = list((tmp_path / "db_backups").glob("dotation_avant_migration_*.db"))
    assert len(backups) == 1
    assert run_pending_migrations(connection) == []  # idempotent : rien de plus, pas de nouvelle copie
    assert len(list((tmp_path / "db_backups").glob("*.db"))) == 1


def test_base_vide_pas_de_copie_de_securite(tmp_path):
    path = tmp_path / "vide.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript("CREATE TABLE resource_catalog (id TEXT, code TEXT, field_schema_json TEXT); CREATE TABLE dotation_forms (id TEXT);")
    run_pending_migrations(connection)
    assert not (tmp_path / "db_backups").exists()
