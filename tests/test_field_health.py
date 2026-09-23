"""Sante des champs : la reparation ajoute les noms actuels dans le dossier ET dans la copie a plat, sans rien retirer ; idempotente."""
import json
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.field_health import repair_orphan_fields, scan_orphan_fields


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE resource_catalog (code TEXT, label TEXT, field_schema_json TEXT);
        CREATE TABLE dotation_forms (id TEXT, payload_json TEXT);
        CREATE TABLE dotation_items (id INTEGER PRIMARY KEY AUTOINCREMENT, form_id TEXT, item_key TEXT, details_json TEXT);
    """)
    schema = [{"key": "nom_du_poste", "label": "Nom du poste"}, {"key": "numero_de_serie", "label": "N° de série"}]
    c.execute("INSERT INTO resource_catalog VALUES ('pc','PC',?)", (json.dumps(schema),))
    payload = {"resources": {"additional": [{"code": "pc", "fields": {"nomPoste": "PC-1", "numeroSerie": "SN-1"}}]}}
    c.execute("INSERT INTO dotation_forms VALUES ('f1',?)", (json.dumps(payload),))
    c.execute("INSERT INTO dotation_items (form_id, item_key, details_json) VALUES ('f1','pc',?)", (json.dumps({"fields": {"nomPoste": "PC-1", "numeroSerie": "SN-1"}}),))
    return c


def test_scan_puis_reparation_puis_plus_rien_a_reparer():
    c = _db()
    scan = scan_orphan_fields(c)
    assert {(o["field"], o["target"]) for o in scan["orphans"]} == {("nomPoste", "nom_du_poste"), ("numeroSerie", "numero_de_serie")}
    report = repair_orphan_fields(c)
    assert report["repairedFields"] == 2 and report["repairedForms"] == 1
    payload_fields = json.loads(c.execute("SELECT payload_json FROM dotation_forms").fetchone()[0])["resources"]["additional"][0]["fields"]
    item_fields = json.loads(c.execute("SELECT details_json FROM dotation_items").fetchone()[0])["fields"]
    for fields in (payload_fields, item_fields):
        assert fields["nom_du_poste"] == "PC-1" and fields["numero_de_serie"] == "SN-1"
        assert fields["nomPoste"] == "PC-1" and fields["numeroSerie"] == "SN-1"  # rien n'est retire
    assert scan_orphan_fields(c)["orphans"] == []
    assert repair_orphan_fields(c)["repairedFields"] == 0  # idempotent
