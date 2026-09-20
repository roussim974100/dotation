"""Roles de champs (identifiant / quantite / variante) : explicites, uniques, derives des anciens drapeaux, figes par migration."""
import json
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from migrations import _m_field_roles
from models.workflow import normalize_resource_field_schema


def test_role_explicite_conserve_avec_drapeaux_derives():
    out = normalize_resource_field_schema([{"label": "Combien", "key": "qte_en_stock", "role": "quantity"}, {"label": "Pointure", "role": "variant"}])
    assert [(f["key"], f["role"], f["quantity"], f["variant"], f["identifier"]) for f in out] == [("qte_en_stock", "quantity", True, False, False), ("pointure", "variant", False, True, False)]


def test_anciens_drapeaux_deviennent_des_roles():
    out = normalize_resource_field_schema([{"label": "N° série", "identifier": True}, {"label": "Nb", "quantity": True}])
    assert [f["role"] for f in out] == ["identifier", "quantity"]


def test_un_seul_champ_par_role():
    out = normalize_resource_field_schema([{"label": "A", "role": "quantity"}, {"label": "B", "role": "quantity"}])
    assert [f["role"] for f in out] == ["quantity", ""] and out[1]["quantity"] is False


def test_role_inconnu_ignore():
    assert normalize_resource_field_schema([{"label": "A", "role": "n_importe_quoi"}])[0]["role"] == ""


def test_migration_fige_les_roles_actuellement_deduits_des_noms():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE resource_catalog (id TEXT, code TEXT, category TEXT, tracking_mode TEXT, field_schema_json TEXT)")
    db.execute("INSERT INTO resource_catalog VALUES ('1','veste','materiel','quantity',?)", (json.dumps([{"key": "quantite", "label": "Q"}, {"key": "taille", "label": "T"}, {"key": "couleur", "label": "C"}]),))
    db.execute("INSERT INTO resource_catalog VALUES ('2','pc','materiel','unit',?)", (json.dumps([{"key": "numero_de_serie", "label": "N"}]),))
    db.execute("INSERT INTO resource_catalog VALUES ('3','cassee','materiel','quantity','null')")
    _m_field_roles(db)
    veste = json.loads(db.execute("SELECT field_schema_json FROM resource_catalog WHERE code='veste'").fetchone()[0])
    pc = json.loads(db.execute("SELECT field_schema_json FROM resource_catalog WHERE code='pc'").fetchone()[0])
    assert [f.get("role", "") for f in veste] == ["quantity", "variant", ""]
    assert pc[0]["role"] == "identifier"
    _m_field_roles(db)  # idempotent
    assert json.loads(db.execute("SELECT field_schema_json FROM resource_catalog WHERE code='veste'").fetchone()[0]) == veste
