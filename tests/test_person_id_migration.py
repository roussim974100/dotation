"""Migration 5 : colonne person_id sur dotation_forms, retrouvee depuis payload_json.meta.personId deja connu (jamais
devinee), idempotente, tolerante a un schema minimal (base tres ancienne)."""
import json
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from migrations import _m_person_id_column


def test_backfill_depuis_le_payload_deja_connu():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("CREATE TABLE dotation_forms (id TEXT, payload_json TEXT)")
    connection.execute("INSERT INTO dotation_forms VALUES ('f1', ?)", (json.dumps({"meta": {"personId": "person_abc"}}),))
    connection.execute("INSERT INTO dotation_forms VALUES ('f2', ?)", (json.dumps({"meta": {}}),))  # jamais enregistre normalement : rien a retrouver
    connection.execute("INSERT INTO dotation_forms VALUES ('f3', 'pas du json valide')")  # dossier abime : ignore, jamais bloquant
    _m_person_id_column(connection)
    rows = {r["id"]: r["person_id"] for r in connection.execute("SELECT id, person_id FROM dotation_forms")}
    assert rows == {"f1": "person_abc", "f2": None, "f3": None}
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_dotation_forms_person" in names


def test_idempotente_ne_touche_pas_une_valeur_deja_posee():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("CREATE TABLE dotation_forms (id TEXT, payload_json TEXT, person_id TEXT)")
    connection.execute("INSERT INTO dotation_forms VALUES ('f1', ?, 'deja_pose')", (json.dumps({"meta": {"personId": "autre_valeur"}}),))
    _m_person_id_column(connection)
    assert connection.execute("SELECT person_id FROM dotation_forms WHERE id = 'f1'").fetchone()[0] == "deja_pose"


def test_schema_minimal_sans_payload_json_ne_leve_pas():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("CREATE TABLE dotation_forms (id TEXT)")
    connection.execute("INSERT INTO dotation_forms VALUES ('f1')")
    _m_person_id_column(connection)  # ne doit pas lever, meme sans colonne payload_json
    columns = {r[1] for r in connection.execute("PRAGMA table_info(dotation_forms)").fetchall()}
    assert "person_id" in columns
