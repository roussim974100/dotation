"""Suivi par quantite : mouvements de stock, alimentation depuis les dossiers, ajustements, seuil d'alerte."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.resource_rules import TRACKING_MODES, effective_tracking_mode, validate_resource
from models.stock import (
    StockError, add_manual_movement, ensure_stock_schema, list_movements, release_stock_for_form, set_threshold,
    stock_levels, sync_stock_for_form,
)

SCHEMA = [{"key": "quantite", "label": "Quantité", "type": "number"}, {"key": "taille", "label": "Taille"}]


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, status TEXT, dossier_type TEXT, nom TEXT, prenom TEXT, service TEXT,
            assigned_at TEXT, returned_at TEXT, updated_at TEXT);
        CREATE TABLE dotation_items (id INTEGER PRIMARY KEY AUTOINCREMENT, form_id TEXT, item_key TEXT, assigned INTEGER,
            returned_at TEXT, return_condition TEXT, details_json TEXT);
        CREATE TABLE resource_catalog (code TEXT, label TEXT, category TEXT, tracking_mode TEXT, field_schema_json TEXT);
    """)
    conn.execute("INSERT INTO resource_catalog VALUES ('veste','Veste','materiel','quantity',?)", (json.dumps(SCHEMA),))
    conn.execute("INSERT INTO resource_catalog VALUES ('gilet','Gilet','materiel','quantity','[]')")
    conn.execute("INSERT INTO resource_catalog VALUES ('ordinateur','Ordinateur','materiel','unit','[]')")
    ensure_stock_schema(conn)
    return conn


def add_form(db, form_id, status="active", nom="DUPONT", prenom="Anne", service="DSI"):
    db.execute("INSERT INTO dotation_forms VALUES (?,?,?,?,?,?,?,NULL,?)",
               (form_id, status, "arrivee", nom, prenom, service, "2026-01-10", "2026-01-10"))


def add_item(db, form_id, quantity=2, size="M", condition="pending", code="veste", returned_at=None):
    fields = {"quantite": quantity, "taille": size} if code == "veste" else {}
    db.execute("INSERT INTO dotation_items (form_id,item_key,assigned,returned_at,return_condition,details_json) VALUES (?,?,1,?,?,?)",
               (form_id, code, returned_at, condition, json.dumps({"selected": True, "fields": fields})))


def on_hand(db, code="veste", variant=None):
    for level in stock_levels(db):
        if level["resource_code"] == code:
            if variant is None:
                return level["on_hand"]
            return next((v["on_hand"] for v in level["variants"] if v["variant"] == variant), 0)


def test_quantity_is_a_tracking_mode_and_needs_no_identifier():
    assert "quantity" in TRACKING_MODES
    assert effective_tracking_mode("quantity", "materiel", []) == "quantity"
    issues = validate_resource({"tracking_mode": "quantity", "category": "materiel", "field_schema": [], "issuer_service": "RH"})
    assert not [i for i in issues if i["level"] == "error"]
    assert any(i["code"] == "no_quantity_field" for i in issues)
    bad = validate_resource({"tracking_mode": "quantity", "category": "immateriel", "field_schema": [], "issuer_service": "RH"})
    assert any(i["code"] == "quantity_needs_material" and i["level"] == "error" for i in bad)


def test_reception_then_signed_assignment_lowers_the_stock(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M", notes="livraison")
    add_form(db, "F1")
    add_item(db, "F1", quantity=3, size="M")
    sync_stock_for_form(db, "F1")
    assert on_hand(db, "veste", "M") == 7
    level = next(l for l in stock_levels(db) if l["resource_code"] == "veste")
    assert level["held"] == 3


def test_drafts_do_not_move_the_stock(db):
    add_manual_movement(db, "veste", "receipt", 5, variant="M")
    add_form(db, "F1", status="draft")
    add_item(db, "F1", quantity=2)
    assert sync_stock_for_form(db, "F1") == 0
    assert on_hand(db) == 5


def test_sync_is_idempotent(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1")
    add_item(db, "F1", quantity=2)
    sync_stock_for_form(db, "F1")
    assert sync_stock_for_form(db, "F1") == 0
    assert on_hand(db) == 8


def test_quantity_changed_after_signature_is_corrected_once(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1")
    add_item(db, "F1", quantity=2)
    sync_stock_for_form(db, "F1")
    db.execute("UPDATE dotation_items SET details_json = ?", (json.dumps({"selected": True, "fields": {"quantite": 5, "taille": "M"}}),))
    sync_stock_for_form(db, "F1")
    sync_stock_for_form(db, "F1")
    assert on_hand(db) == 5


def test_ready_return_restocks_and_degraded_return_does_not(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1")
    add_item(db, "F1", quantity=2, condition="bon")
    add_form(db, "F2")
    add_item(db, "F2", quantity=3, condition="degrade")
    sync_stock_for_form(db, "F1")
    sync_stock_for_form(db, "F2")
    assert on_hand(db) == 7  # 10 - 2 + 2 - 3 (les 3 degrades ne reviennent pas)


def test_default_quantity_is_one_without_quantity_field(db):
    add_manual_movement(db, "gilet", "receipt", 4)
    add_form(db, "F1")
    add_item(db, "F1", code="gilet")
    sync_stock_for_form(db, "F1")
    assert on_hand(db, "gilet") == 3


def test_deleting_a_form_gives_the_stock_back(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1")
    add_item(db, "F1", quantity=4)
    sync_stock_for_form(db, "F1")
    assert on_hand(db) == 6
    release_stock_for_form(db, "F1")
    release_stock_for_form(db, "F1")
    assert on_hand(db) == 10
    assert len(list_movements(db, "veste")) == 3  # l'historique reste


def test_manual_movements_are_validated(db):
    with pytest.raises(StockError):
        add_manual_movement(db, "ordinateur", "receipt", 1)
    with pytest.raises(StockError):
        add_manual_movement(db, "veste", "receipt", 0)
    with pytest.raises(StockError):
        add_manual_movement(db, "veste", "loss", -2)
    with pytest.raises(StockError) as error:
        add_manual_movement(db, "veste", "adjustment", -1)
    assert error.value.code == "note_required"
    add_manual_movement(db, "veste", "adjustment", -1, notes="inventaire")
    add_manual_movement(db, "veste", "loss", 2, notes="casse")
    assert on_hand(db) == -3


def test_threshold_raises_a_low_stock_alert(db):
    add_manual_movement(db, "veste", "receipt", 6, variant="M")
    assert next(l for l in stock_levels(db) if l["resource_code"] == "veste")["low"] is False
    set_threshold(db, "veste", 5)
    add_manual_movement(db, "veste", "loss", 2, variant="M", notes="perte")
    level = next(l for l in stock_levels(db) if l["resource_code"] == "veste")
    assert level["low"] is True and level["threshold"] == 5
    set_threshold(db, "veste", None)
    assert next(l for l in stock_levels(db) if l["resource_code"] == "veste")["threshold"] is None
    with pytest.raises(StockError):
        set_threshold(db, "veste", -1)


def test_holder_names_are_masked_for_masked_scope(db):
    add_manual_movement(db, "veste", "receipt", 5, variant="M")
    add_form(db, "F1", nom="DUPONT", prenom="Anne")
    add_item(db, "F1", quantity=1)
    sync_stock_for_form(db, "F1")
    holder = next(m for m in list_movements(db, "veste", mask=True) if m["form_id"] == "F1")["holder_label"]
    assert "DUPONT" not in holder and "Anne" not in holder


def test_stock_routes_refuse_anonymous_and_unauthorised_users():
    """Sans session : refus. Session d'un compte inconnu (aucun droit parc.manage) : refus, et rien n'est ecrit."""
    from app import app

    anonymous = app.test_client()
    assert anonymous.get("/api/stock").status_code in (401, 403)
    assert anonymous.get("/api/stock/veste/movements").status_code in (401, 403)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "utilisateur_sans_droits_stock"
        sess["csrf_token"] = "jeton-de-test"
    headers = {"X-CSRF-Token": "jeton-de-test"}
    body = {"kind": "receipt", "quantity": 5}
    assert client.post("/api/stock/veste/movements", json=body, headers=headers).status_code in (401, 403)
    assert client.put("/api/stock/veste/threshold", json={"threshold": 3}, headers=headers).status_code in (401, 403)
    assert client.post("/api/stock/veste/movements", json=body).status_code == 403  # sans jeton CSRF


def test_import_sets_the_counted_stock_and_is_idempotent(db):
    from models.stock import import_stock
    csv_text = "ressource;taille;quantite;note\nveste;M;12;inventaire annuel\nveste;L;5;\ngilet;;7;\n"
    dry = import_stock(db, csv_text, dry_run=True)
    assert (dry["created"], dry["skipped"], dry["errors"]) == (3, 0, []) and on_hand(db) == 0  # a blanc : rien d'ecrit
    real = import_stock(db, csv_text, actor="admin", dry_run=False)
    assert real["created"] == 3 and on_hand(db, "veste", "M") == 12 and on_hand(db, "veste", "L") == 5 and on_hand(db, "gilet") == 7
    again = import_stock(db, csv_text, dry_run=False)
    assert (again["created"], again["skipped"]) == (0, 3) and on_hand(db, "veste", "M") == 12  # 2e import : aucun changement
    # un nouvel inventaire ajuste l'ecart (12 -> 9)
    import_stock(db, "ressource;taille;quantite\nveste;M;9\n", dry_run=False)
    assert on_hand(db, "veste", "M") == 9


def test_import_reports_bad_lines_without_stopping(db):
    from models.stock import import_stock
    text = "ressource,taille,quantite\ninconnue,M,3\nveste,M,abc\nveste,M,-2\nveste,M,4\nveste,M,6\nordinateur,,1\n"
    report = import_stock(db, text, dry_run=False)
    messages = " | ".join(e["message"] for e in report["errors"])
    assert report["created"] == 1 and on_hand(db, "veste", "M") == 4  # seule la 1re ligne valide est prise
    assert "inconnue" in messages and "abc" in messages and "-2" in messages and "Doublon" in messages and "ordinateur" in messages


def touch_all(db):
    """Dossiers de test recents (sinon leur reservation a deja expire : plus de 30 jours sans activite)."""
    from datetime import datetime, timezone
    db.execute("UPDATE dotation_forms SET updated_at = ?", (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),))


def test_drafts_reserve_stock_without_moving_it(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1", status="draft")
    add_item(db, "F1", quantity=3, size="M")
    add_form(db, "F2", status="awaiting_signature")
    add_item(db, "F2", quantity=2, size="M")
    add_form(db, "F3", status="cancelled")
    add_item(db, "F3", quantity=4, size="M")  # un dossier annule ne reserve rien
    touch_all(db)
    level = next(l for l in stock_levels(db) if l["resource_code"] == "veste")
    variant = next(v for v in level["variants"] if v["variant"] == "M")
    assert (variant["on_hand"], variant["reserved"], variant["available"]) == (10, 5, 5)
    assert (level["on_hand"], level["reserved"], level["available"]) == (10, 5, 5)


def test_signature_turns_a_reservation_into_a_real_movement(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1", status="draft")
    add_item(db, "F1", quantity=3)
    touch_all(db)
    assert next(l for l in stock_levels(db) if l["resource_code"] == "veste")["reserved"] == 3
    db.execute("UPDATE dotation_forms SET status = 'active' WHERE id = 'F1'")
    sync_stock_for_form(db, "F1")
    level = next(l for l in stock_levels(db) if l["resource_code"] == "veste")
    assert (level["on_hand"], level["reserved"], level["available"]) == (7, 0, 7)  # plus de reservation, le stock a baisse


def test_a_stale_draft_no_longer_reserves(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    add_form(db, "F1", status="draft")
    add_item(db, "F1", quantity=3)
    db.execute("UPDATE dotation_forms SET updated_at = '2020-01-01T00:00:00' WHERE id = 'F1'")
    level = next(l for l in stock_levels(db) if l["resource_code"] == "veste")
    assert level["reserved"] == 0 and level["available"] == 10


def test_low_stock_alert_uses_the_available_quantity(db):
    add_manual_movement(db, "veste", "receipt", 10, variant="M")
    set_threshold(db, "veste", 5)
    assert next(l for l in stock_levels(db) if l["resource_code"] == "veste")["low"] is False
    add_form(db, "F1", status="draft")
    add_item(db, "F1", quantity=6)
    touch_all(db)  # 10 en stock, 6 reserves -> 4 disponibles : sous le seuil
    assert next(l for l in stock_levels(db) if l["resource_code"] == "veste")["low"] is True
