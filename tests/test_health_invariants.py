"""Invariants de stock et de parc du contrôle de santé (comptages)."""
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import json
from models.health import stock_and_unit_invariants, unsynced_unit_assignments


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE resource_catalog (code TEXT);
        CREATE TABLE resource_stock_movements (resource_code TEXT, variant TEXT, quantity INTEGER);
        CREATE TABLE resource_units (resource_code TEXT, identifier TEXT);
        CREATE TABLE dotation_items (form_id TEXT, item_key TEXT, assigned INTEGER);
        INSERT INTO resource_catalog VALUES ('veste');
    """)
    return c


def test_base_saine_aucun_probleme():
    c = _db()
    c.execute("INSERT INTO resource_stock_movements VALUES ('veste', 'M', 10)")
    c.execute("INSERT INTO resource_units VALUES ('veste', 'ABC')")
    assert set(stock_and_unit_invariants(c).values()) == {0}


def test_invariants_violes_sont_comptes():
    c = _db()
    c.executemany("INSERT INTO resource_stock_movements VALUES (?, ?, ?)", [("veste", "M", -3), ("veste", "L", 4), ("fantome", "", 1)])
    c.executemany("INSERT INTO resource_units VALUES (?, ?)", [("veste", "  "), ("fantome", "X1")])
    c.executemany("INSERT INTO dotation_items VALUES (?, ?, ?)", [("f1", "veste", 1), ("f1", "veste", 1), ("f2", "veste", 1)])
    assert stock_and_unit_invariants(c) == {"stockNegativeBalances": 1, "stockMovementsUnknownResource": 1, "unitsWithoutIdentifier": 1,
                                            "unitsUnknownResource": 1, "duplicateItemLines": 1, "retraitsNonRepercutes": 0,
                                            "unsyncedUnitAssignments": 0}


def test_tables_absentes_base_ancienne_ne_levent_pas_d_erreur():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    assert set(stock_and_unit_invariants(c).values()) == {0}


def test_retrait_non_repercute_au_parc_est_compte():
    """3.64.0 : un objet encore « attribue » a un dossier dont la ligne correspondante est rendue."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE resource_units (resource_code TEXT, identifier TEXT, status TEXT, holder_form_id TEXT);
        CREATE TABLE dotation_items (form_id TEXT, item_key TEXT, assigned INTEGER, returned INTEGER);
        INSERT INTO resource_units VALUES ('pc', 'SN-1', 'assigned', 'f1');   -- rendu au dossier, mais parc inchange : a signaler
        INSERT INTO resource_units VALUES ('pc', 'SN-2', 'in_stock', 'f1');   -- deja remis en stock : sain
        INSERT INTO resource_units VALUES ('pc', 'SN-3', 'assigned', 'f2');   -- toujours detenu, ligne non rendue : sain
        INSERT INTO dotation_items VALUES ('f1', 'pc', 1, 1);
        INSERT INTO dotation_items VALUES ('f2', 'pc', 1, 0);
    """)
    assert stock_and_unit_invariants(c)["retraitsNonRepercutes"] == 1


_UNIT_SCHEMA = json.dumps([{"key": "numeroSerie", "label": "N° de série", "required": True, "identifier": True}])


def _db_with_catalog():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE resource_catalog (code TEXT, category TEXT, tracking_mode TEXT, field_schema_json TEXT);
        CREATE TABLE resource_units (resource_code TEXT, identifier TEXT, status TEXT, holder_form_id TEXT);
        CREATE TABLE dotation_items (form_id TEXT, item_key TEXT, assigned INTEGER, details_json TEXT);
    """)
    c.execute("INSERT INTO resource_catalog VALUES ('ordinateur', 'materiel', NULL, ?)", (_UNIT_SCHEMA,))
    return c


def test_echec_silencieux_de_synchronisation_du_parc_est_detecte():
    """22/11/2026 : angle mort signale par l'audit de perennite - sync_units_for_form peut echouer en silence
    (persist_form avale l'exception) et laisser un objet "attribue" au dossier sans unite de parc correspondante."""
    c = _db_with_catalog()
    c.execute(
        "INSERT INTO dotation_items VALUES ('f1', 'ordinateur', 1, ?)",
        (json.dumps({"fields": {"numeroSerie": "SN-404"}}),),
    )
    # Aucune ligne resource_units pour ('ordinateur', holder_form_id='f1') : la synchronisation n'a jamais eu lieu.
    assert unsynced_unit_assignments(c) == 1
    assert stock_and_unit_invariants(c)["unsyncedUnitAssignments"] == 1


def test_objet_correctement_synchronise_n_est_pas_signale():
    c = _db_with_catalog()
    c.execute(
        "INSERT INTO dotation_items VALUES ('f1', 'ordinateur', 1, ?)",
        (json.dumps({"fields": {"numeroSerie": "SN-1"}}),),
    )
    c.execute("INSERT INTO resource_units VALUES ('ordinateur', 'sn-1', 'assigned', 'f1')")
    assert unsynced_unit_assignments(c) == 0


def test_objet_sans_numero_de_serie_saisi_n_est_pas_un_echec():
    """Sans identifiant saisi, sync_units_for_form ne tente rien non plus (rien a suivre) : pas un echec a signaler."""
    c = _db_with_catalog()
    c.execute(
        "INSERT INTO dotation_items VALUES ('f1', 'ordinateur', 1, ?)",
        (json.dumps({"fields": {}}),),
    )
    assert unsynced_unit_assignments(c) == 0
