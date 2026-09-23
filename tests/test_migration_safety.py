"""Une migration en echec est annulee proprement (aucune modification partielle), consignee, retentee plus tard ; l'application continue ;
les index de performance sont crees (idempotent)."""
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import migrations


def _db(tmp_path):
    connection = sqlite3.connect(tmp_path / "t.db")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE dotation_forms (id TEXT, status TEXT, updated_at TEXT, dossier_id TEXT, source_form_id TEXT);
        CREATE TABLE dotation_items (form_id TEXT, item_key TEXT);
        CREATE TABLE resource_catalog (id TEXT, code TEXT, field_schema_json TEXT);
        CREATE TABLE marqueur (valeur TEXT);
    """)
    return connection


def test_migration_en_echec_est_annulee_sans_effet_partiel_et_n_arrete_pas_l_application(tmp_path, monkeypatch, capsys):
    def cassee(connection):
        connection.execute("INSERT INTO marqueur VALUES ('ECRITURE-PARTIELLE')")
        raise RuntimeError("panne au milieu")

    def apres(connection):
        connection.execute("INSERT INTO marqueur VALUES ('NE-DOIT-PAS-S-APPLIQUER')")

    monkeypatch.setattr(migrations, "MIGRATIONS", [(1, "ok", lambda c: None), (2, "cassee", cassee), (3, "apres", apres)])
    connection = _db(tmp_path)
    assert migrations.run_pending_migrations(connection) == [1]  # la 1 passe, la 2 echoue, la 3 n'est pas tentee
    assert connection.execute("SELECT COUNT(*) FROM marqueur").fetchone()[0] == 0  # rien d'ecrit par la migration en echec
    assert [r[0] for r in connection.execute("SELECT version FROM schema_migrations")] == [1]
    # retentee au prochain demarrage, une fois le probleme corrige
    monkeypatch.setattr(migrations, "MIGRATIONS", [(1, "ok", lambda c: None), (2, "corrigee", lambda c: None), (3, "apres", lambda c: None)])
    assert migrations.run_pending_migrations(connection) == [2, 3]


def test_index_de_performance_crees_et_idempotents(tmp_path):
    connection = _db(tmp_path)
    migrations._m_indexes(connection)
    migrations._m_indexes(connection)
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_dotation_items_form_key", "idx_dotation_forms_status_updated", "idx_dotation_forms_dossier"} <= names
