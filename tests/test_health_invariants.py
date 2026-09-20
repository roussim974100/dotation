"""Invariants de stock et de parc du contrôle de santé (comptages)."""
import sqlite3
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.health import stock_and_unit_invariants


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
                                            "unitsUnknownResource": 1, "duplicateItemLines": 1}


def test_tables_absentes_base_ancienne_ne_levent_pas_d_erreur():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    assert set(stock_and_unit_invariants(c).values()) == {0}
