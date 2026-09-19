"""Parc : transitions, journal d'evenements, alimentation depuis les dossiers, reprise de l'existant."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.units import (
    UnitActionError, apply_manual_action, backfill_units, count_units_by_status, derive_state, ensure_units_schema,
    get_unit, list_units, next_status, release_units_for_form, sync_units_for_form,
)

SCHEMA = [{"key": "numeroSerie", "label": "N° de série", "required": True, "identifier": True}, {"key": "marque", "label": "Marque"}]


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, status TEXT, nom TEXT, prenom TEXT, service TEXT,
            assigned_at TEXT, returned_at TEXT, updated_at TEXT);
        CREATE TABLE dotation_items (id INTEGER PRIMARY KEY AUTOINCREMENT, form_id TEXT, item_key TEXT, assigned INTEGER,
            returned_at TEXT, return_condition TEXT, details_json TEXT);
        CREATE TABLE resource_catalog (code TEXT, category TEXT, tracking_mode TEXT, field_schema_json TEXT);
    """)
    conn.execute("INSERT INTO resource_catalog VALUES ('ordinateur','materiel','unit',?)", (json.dumps(SCHEMA),))
    conn.execute("INSERT INTO resource_catalog VALUES ('veste','materiel','none','[]')")
    ensure_units_schema(conn)
    return conn


def add_form(db, form_id, status="active", assigned="2026-01-10", updated="2026-01-10", nom="DUPONT", prenom="Anne", service="DSI"):
    db.execute("INSERT INTO dotation_forms VALUES (?,?,?,?,?,?,NULL,?)", (form_id, status, nom, prenom, service, assigned, updated))


def add_item(db, form_id, serial, condition="pending", returned_at=None, code="ordinateur", flat=False):
    fields = {"numeroSerie": serial, "marque": "Lenovo"}
    details = fields if flat else {"selected": True, "fields": fields}
    db.execute("INSERT INTO dotation_items (form_id,item_key,assigned,returned_at,return_condition,details_json) VALUES (?,?,1,?,?,?)",
               (form_id, code, returned_at, condition, json.dumps(details)))


def unit(db, serial="SN1"):
    return db.execute("SELECT * FROM resource_units WHERE identifier_norm = ?", (serial.lower(),)).fetchone()


def events(db, serial="SN1"):
    return [(e["event_type"], e["anomaly"]) for e in db.execute(
        "SELECT * FROM resource_unit_events WHERE unit_id = ? ORDER BY occurred_at, seq", (unit(db, serial)["id"],))]


# --- transitions pures ----------------------------------------------------------------------

@pytest.mark.parametrize("current, event, expected", [
    (None, "assigned", ("assigned", None)), ("in_stock", "assigned", ("assigned", None)), ("degraded", "assigned", ("assigned", None)),
    ("assigned", "assigned", ("assigned", "double_attribution")), ("lost", "assigned", ("assigned", "assigned_while_lost")),
    ("assigned", "returned", ("in_stock", None)), ("assigned", "returned_degraded", ("degraded", None)),
    ("assigned", "lost", ("lost", None)), ("in_stock", "lost", ("lost", "lost_without_assignment")),
    ("assigned", "released", ("in_stock", None)), ("degraded", "note", ("degraded", None)),
])
def test_transitions(current, event, expected):
    assert next_status(current, event) == expected


def test_unknown_event_is_rejected():
    with pytest.raises(ValueError):
        next_status("assigned", "explose")


def test_derive_state_folds_events_in_order():
    seq = [{"event_type": "assigned", "form_id": "F1", "holder_label": "A"}, {"event_type": "returned"},
           {"event_type": "assigned", "form_id": "F2", "holder_label": "B"}]
    assert derive_state(seq) == ("assigned", {"form_id": "F2", "label": "B"})
    assert derive_state(seq[:2]) == ("in_stock", None)


# --- alimentation depuis les dossiers ---------------------------------------------------------

def test_signed_dossier_creates_the_unit_and_assigns_it(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1")
    assert sync_units_for_form(db, "F1") == 1
    row = unit(db)
    assert (row["status"], row["holder_form_id"], row["holder_label"], row["resource_code"]) == ("assigned", "F1", "DUPONT Anne · DSI", "ordinateur")
    assert events(db) == [("assigned", None)]


def test_sync_is_idempotent(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F1"); sync_units_for_form(db, "F1")
    assert len(events(db)) == 1
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 1


def test_draft_dossier_does_not_put_the_object_in_the_parc(db):
    add_form(db, "F1", status="draft"); add_item(db, "F1", "SN1")
    assert sync_units_for_form(db, "F1") == 0
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 0


def test_a_return_proves_the_assignment_even_if_the_dossier_status_is_not_effective(db):
    add_form(db, "F1", status="awaiting_signature"); add_item(db, "F1", "SN1", "non_restitue", "2026-03-01")
    sync_units_for_form(db, "F1")
    assert events(db) == [("assigned", None), ("lost", None)]  # pas d'anomalie « perte sans attribution »
    assert unit(db)["status"] == "lost"


def test_return_in_good_condition_puts_the_unit_back_in_stock(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "conforme", "2026-03-01")
    sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "in_stock" and unit(db)["holder_form_id"] is None
    assert [e[0] for e in events(db)] == ["assigned", "returned"]


def test_degraded_and_lost_returns(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "degrade", "2026-03-01")
    add_form(db, "F2"); add_item(db, "F2", "SN2", "non_restitue", "2026-03-01")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert unit(db, "SN1")["status"] == "degraded" and unit(db, "SN2")["status"] == "lost"


def test_return_recorded_later_completes_the_history(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1")
    sync_units_for_form(db, "F1")
    db.execute("UPDATE dotation_items SET return_condition='conforme', returned_at='2026-05-01' WHERE form_id='F1'")
    sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "in_stock" and [e[0] for e in events(db)] == ["assigned", "returned"]


def test_double_attribution_is_recorded_as_an_anomaly(db):
    add_form(db, "F1", assigned="2026-01-10"); add_item(db, "F1", "SN1")
    add_form(db, "F2", assigned="2026-02-10", nom="MARTIN", prenom="Paul"); add_item(db, "F2", "sn1")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 1  # casse ignoree
    assert events(db) == [("assigned", None), ("assigned", "double_attribution")]
    assert unit(db)["holder_form_id"] == "F2"


def test_resources_without_identifier_field_are_ignored(db):
    add_form(db, "F1"); add_item(db, "F1", "X", code="veste")
    assert sync_units_for_form(db, "F1") == 0
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 0


def test_legacy_flat_details_and_empty_identifier(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", flat=True); add_item(db, "F1", "   ")
    sync_units_for_form(db, "F1")
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 1


def test_deleting_a_dossier_releases_its_units_but_keeps_the_history(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1")
    sync_units_for_form(db, "F1")
    assert release_units_for_form(db, "F1") == 1
    assert unit(db)["status"] == "in_stock" and unit(db)["holder_form_id"] is None
    assert [e[0] for e in events(db)] == ["assigned", "released"]
    assert release_units_for_form(db, "F1") == 0  # plus rien a liberer


# --- reprise de l'existant -----------------------------------------------------------------

def test_backfill_builds_units_from_forms_and_marks_orphans_as_unknown(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "conforme", "2026-03-01")
    add_item(db, "GONE", "SN-ORPHAN")  # dossier supprime avant l'historique
    result = backfill_units(db)
    assert result == {"forms": 1, "orphan_units": 1}
    assert unit(db, "SN1")["status"] == "in_stock"
    orphan = unit(db, "SN-ORPHAN")
    assert orphan["status"] == "unknown" and orphan["origin"] == "backfill_orphan"
    assert "vérifier" in db.execute("SELECT notes FROM resource_unit_events WHERE unit_id=?", (orphan["id"],)).fetchone()[0]


def test_backfill_is_idempotent_and_does_not_touch_known_units(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1")
    add_item(db, "GONE", "SN1")  # meme objet, aussi dans un dossier supprime : ne cree rien
    backfill_units(db); backfill_units(db)
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 1
    assert len(events(db)) == 1 and unit(db)["status"] == "assigned"


# --- lecture -----------------------------------------------------------------------------------

def test_unit_history_and_masking(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "conforme", "2026-03-01")
    sync_units_for_form(db, "F1")
    detail = get_unit(db, unit(db)["id"])
    assert [e["event_type"] for e in detail["events"]] == ["assigned", "returned"]
    assert detail["events"][0]["holder_label"] == "DUPONT Anne · DSI"
    masked = get_unit(db, unit(db)["id"], mask=True)
    assert masked["events"][0]["holder_label"] == "—" and masked["holder_label"] is None
    assert get_unit(db, "inconnu") is None


def test_list_filters(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); add_item(db, "F1", "ABC9")
    sync_units_for_form(db, "F1")
    assert len(list_units(db)) == 2
    assert [u["identifier"] for u in list_units(db, query="abc")] == ["ABC9"]
    assert len(list_units(db, status="in_stock")) == 0 and len(list_units(db, status="assigned")) == 2


def test_date_only_return_on_the_assignment_day_sorts_after_the_assignment(db):
    add_form(db, "F1", assigned="2026-09-19T09:30:00.123+00:00", updated="2026-09-19T09:30:00.123+00:00")
    add_item(db, "F1", "SN1", "conforme", "2026-09-19")
    sync_units_for_form(db, "F1")
    assert [e[0] for e in events(db)] == ["assigned", "returned"]
    assert unit(db)["status"] == "in_stock"


def test_return_dated_before_the_assignment_is_clamped_and_annotated(db):
    add_form(db, "F1", assigned="2026-05-01T10:00:00+00:00")
    add_item(db, "F1", "SN1", "conforme", "2026-03-01")
    sync_units_for_form(db, "F1")
    assert [e[0] for e in events(db)] == ["assigned", "returned"]
    note = db.execute("SELECT notes FROM resource_unit_events WHERE event_type='returned'").fetchone()[0]
    assert "antérieure" in note and unit(db)["status"] == "in_stock"


def test_reassignment_after_a_same_day_return_is_not_a_double_attribution(db):
    add_form(db, "F1", assigned="2026-09-19T09:00:00+00:00"); add_item(db, "F1", "SN1", "conforme", "2026-09-19")
    add_form(db, "F2", assigned="2026-09-19T15:00:00+00:00", nom="MARTIN"); add_item(db, "F2", "SN1")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert events(db) == [("assigned", None), ("returned", None), ("assigned", None)]
    assert unit(db)["holder_form_id"] == "F2"


# --- actions manuelles ----------------------------------------------------------------------

def uid(db, serial="SN1"):
    return unit(db, serial)["id"]


def act(db, serial, action, notes="", **params):
    return apply_manual_action(db, uid(db, serial), action, notes, "gestionnaire", params)


def test_new_transitions_for_manual_events():
    assert next_status("lost", "found") == ("in_stock", None)
    assert next_status("in_stock", "retired") == ("retired", None)
    assert next_status("in_stock", "repair_started") == ("maintenance", None)
    assert next_status("maintenance", "repair_done") == ("in_stock", None)
    assert next_status("unknown", "verified") == ("in_stock", None)
    assert next_status("assigned", "correction") == ("assigned", None)


def test_lost_then_found_cycle(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "conforme", "2026-03-01"); sync_units_for_form(db, "F1")
    assert act(db, "SN1", "lost", "Volé en réunion")["status"] == "lost"
    assert act(db, "SN1", "found")["status"] == "in_stock"
    detail = get_unit(db, uid(db))
    assert [e["event_type"] for e in detail["events"]][-2:] == ["lost", "found"]
    assert detail["events"][-2]["actor"] == "gestionnaire" and detail["events"][-2]["notes"] == "Volé en réunion"
    assert all(e["anomaly"] is None for e in detail["events"][-2:])  # action volontaire : jamais une anomalie


def test_actions_are_refused_from_the_wrong_state_or_without_reason(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")  # attribue
    for action in ("found", "repair_start", "repair_done", "verify"):
        with pytest.raises(UnitActionError) as error:
            act(db, "SN1", action)
        assert error.value.code == "invalid_state"
    with pytest.raises(UnitActionError) as reason:
        act(db, "SN1", "lost", "  ")
    assert reason.value.code == "note_required"
    with pytest.raises(UnitActionError) as unknown:
        act(db, "SN1", "explose")
    assert unknown.value.code == "invalid_action"
    with pytest.raises(UnitActionError) as missing:
        apply_manual_action(db, "inconnue", "note", "x")
    assert missing.value.code == "unknown_unit"


def test_repair_and_retirement_cycle(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "degrade", "2026-03-01"); sync_units_for_form(db, "F1")
    assert act(db, "SN1", "repair_start")["status"] == "maintenance"
    assert act(db, "SN1", "repair_done")["status"] == "in_stock"
    assert act(db, "SN1", "retire", "Fin de vie")["status"] == "retired"
    assert unit(db)["holder_form_id"] is None


def test_orphan_unit_can_be_verified(db):
    add_item(db, "GONE", "SN-O"); backfill_units(db)
    assert unit(db, "SN-O")["status"] == "unknown"
    assert act(db, "SN-O", "verify", "Contrôlé sur place")["status"] == "in_stock"


def test_a_note_never_changes_the_state(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    assert act(db, "SN1", "note", "Écran rayé")["status"] == "assigned"


def test_identifier_correction_keeps_history_and_future_syncs_land_on_the_same_unit(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    unit_id = uid(db)
    detail = act(db, "SN1", "correct", new_identifier="SN-0001")
    assert detail["identifier"] == "SN-0001" and detail["events"][-1]["event_type"] == "correction"
    assert "SN1 → SN-0001" in detail["events"][-1]["notes"]
    # Un dossier qui contient encore l'ancienne graphie retombe sur la meme unite (alias), sans doublon
    add_form(db, "F2", assigned="2026-08-01"); add_item(db, "F2", "sn1", "conforme", "2026-08-02"); sync_units_for_form(db, "F2")
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 1
    assert db.execute("SELECT id FROM resource_units").fetchone()[0] == unit_id


def test_identifier_correction_refuses_an_existing_identifier_and_empty_value(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); add_item(db, "F1", "SN2"); sync_units_for_form(db, "F1")
    with pytest.raises(UnitActionError) as clash:
        act(db, "SN1", "correct", new_identifier=" sn2 ")
    assert clash.value.code == "identifier_exists"
    with pytest.raises(UnitActionError) as empty:
        act(db, "SN1", "correct", new_identifier="")
    assert empty.value.code == "identifier_required"


def test_merge_moves_history_and_identifier_to_the_target_without_duplicating_on_resync(db):
    add_form(db, "F1", assigned="2026-01-10"); add_item(db, "F1", "SN1", "conforme", "2026-02-01")
    add_form(db, "F2", assigned="2026-03-10"); add_item(db, "F2", "SN-1")  # meme objet mal saisi
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 2
    target = act(db, "SN1", "merge", target_unit_id=uid(db, "SN-1"))
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 1
    assert [e["event_type"] for e in target["events"]] == ["assigned", "returned", "assigned", "merged"]
    assert target["status"] == "assigned"
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")  # nouvelle synchronisation : aucun doublon
    assert len(get_unit(db, uid(db, "SN-1"))["events"]) == 4


def test_merge_is_refused_across_resources_or_with_itself(db):
    db.execute("INSERT INTO resource_catalog VALUES ('telephone','materiel','unit',?)", (json.dumps(SCHEMA),))
    add_form(db, "F1"); add_item(db, "F1", "SN1"); add_item(db, "F1", "SN1", code="telephone"); sync_units_for_form(db, "F1")
    other = db.execute("SELECT id FROM resource_units WHERE resource_code='telephone'").fetchone()[0]
    with pytest.raises(UnitActionError) as cross:
        act(db, "SN1", "merge", target_unit_id=other)
    assert cross.value.code == "different_resource"
    with pytest.raises(UnitActionError) as same:
        act(db, "SN1", "merge", target_unit_id=uid(db, "SN1"))
    assert same.value.code == "same_unit"


def test_counts_by_status(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); add_item(db, "F1", "SN2", "conforme", "2026-03-01"); sync_units_for_form(db, "F1")
    assert count_units_by_status(db) == {"assigned": 1, "in_stock": 1}
    assert count_units_by_status(db, "telephone") == {}


def test_unit_fields_only_keep_the_resource_fields(db):
    add_form(db, "F1")
    details = {"numeroSerie": "SN1", "marque": "Lenovo", "assignedAt": "2025-11-15T09:00:00+00:00", "conditionAttribution": "neuf", "selected": True}
    db.execute("INSERT INTO dotation_items (form_id,item_key,assigned,return_condition,details_json) VALUES ('F1','ordinateur',1,'pending',?)", (json.dumps(details),))
    sync_units_for_form(db, "F1")
    assert json.loads(unit(db)["fields_json"]) == {"numeroSerie": "SN1", "marque": "Lenovo"}
