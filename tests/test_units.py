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
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, status TEXT, dossier_type TEXT, nom TEXT, prenom TEXT, service TEXT,
            assigned_at TEXT, returned_at TEXT, updated_at TEXT);
        CREATE TABLE dotation_items (id INTEGER PRIMARY KEY AUTOINCREMENT, form_id TEXT, item_key TEXT, assigned INTEGER,
            returned_at TEXT, return_condition TEXT, details_json TEXT);
        CREATE TABLE resource_catalog (code TEXT, label TEXT, category TEXT, tracking_mode TEXT, field_schema_json TEXT);
    """)
    conn.execute("INSERT INTO resource_catalog VALUES ('ordinateur','Ordinateur','materiel','unit',?)", (json.dumps(SCHEMA),))
    conn.execute("INSERT INTO resource_catalog VALUES ('veste','Veste','materiel','none','[]')")
    ensure_units_schema(conn)
    return conn


def add_form(db, form_id, status="active", assigned="2026-01-10", updated="2026-01-10", nom="DUPONT", prenom="Anne", service="DSI", dossier_type="arrivee"):
    db.execute("INSERT INTO dotation_forms (id,status,dossier_type,nom,prenom,service,assigned_at,returned_at,updated_at) VALUES (?,?,?,?,?,?,?,NULL,?)",
               (form_id, status, dossier_type, nom, prenom, service, assigned, updated))


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


def test_draft_dossier_reserves_the_object_without_assigning_it(db):
    add_form(db, "F1", status="draft"); add_item(db, "F1", "SN1")
    assert sync_units_for_form(db, "F1") == 1
    assert unit(db)["status"] == "reserved" and unit(db)["holder_form_id"] == "F1"
    assert events(db) == [("reserved", None)]


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
    db.execute("INSERT INTO resource_catalog VALUES ('telephone','Téléphone','materiel','unit',?)", (json.dumps(SCHEMA),))
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


# --- reservation, transferts, regularisation ------------------------------------------------

from models.units import available_units_for_resource, find_holder_unit, release_stale_reservations


def test_signing_the_draft_turns_the_reservation_into_an_assignment(db):
    add_form(db, "F1", status="draft"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    db.execute("UPDATE dotation_forms SET status='active', assigned_at='2026-02-01T10:00:00+00:00', updated_at='2026-02-01T10:00:00+00:00'")
    sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "assigned" and unit(db)["holder_form_id"] == "F1"
    assert events(db) == [("reserved", None), ("assigned", None)]


def test_two_drafts_on_the_same_object_are_reported_as_a_double_reservation(db):
    add_form(db, "F1", status="draft", updated="2026-06-01T08:00:00+00:00"); add_item(db, "F1", "SN1")
    add_form(db, "F2", status="draft", updated="2026-06-02T08:00:00+00:00", nom="MARTIN"); add_item(db, "F2", "SN1")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert events(db) == [("reserved", None), ("reserved", "double_reservation")]


def test_reserving_an_assigned_object_is_flagged_and_does_not_change_its_state(db):
    add_form(db, "F1", assigned="2026-01-10"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    add_form(db, "F2", status="draft", updated="2026-06-02T08:00:00+00:00"); add_item(db, "F2", "SN1"); sync_units_for_form(db, "F2")
    assert events(db)[-1] == ("reserved", "reserved_while_assigned") and unit(db)["status"] == "assigned"


def test_removing_the_object_from_the_draft_releases_the_reservation(db):
    add_form(db, "F1", status="draft"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    db.execute("DELETE FROM dotation_items WHERE form_id='F1'")
    sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "in_stock" and unit(db)["holder_form_id"] is None
    assert [e[0] for e in events(db)] == ["reserved", "reservation_released"]


def test_cancelled_draft_releases_and_deleted_draft_releases(db):
    add_form(db, "F1", status="draft"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    db.execute("UPDATE dotation_forms SET status='cancelled', updated_at='2026-07-01'")
    sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "in_stock"
    add_form(db, "F2", status="draft"); add_item(db, "F2", "SN2"); sync_units_for_form(db, "F2")
    assert release_units_for_form(db, "F2") == 1 and unit(db, "SN2")["status"] == "in_stock"


def test_stale_reservations_expire_after_30_days_of_inactivity(db):
    from datetime import datetime, timezone
    add_form(db, "F1", status="draft", updated="2026-05-01T08:00:00+00:00"); add_item(db, "F1", "SN1")
    add_form(db, "F2", status="draft", updated="2026-06-25T08:00:00+00:00"); add_item(db, "F2", "SN2")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert release_stale_reservations(db, 30, datetime(2026, 7, 1, tzinfo=timezone.utc)) == 1
    assert unit(db, "SN1")["status"] == "in_stock" and unit(db, "SN2")["status"] == "reserved"
    assert release_stale_reservations(db, 30, datetime(2026, 7, 1, tzinfo=timezone.utc)) == 0  # idempotent


def test_transfer_changes_the_holder_without_a_return(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    detail = act(db, "SN1", "transfer", "Mobilité interne", holder_label="MARTIN Paul · RH")
    assert detail["status"] == "assigned" and detail["holder_label"] == "MARTIN Paul · RH"
    assert detail["events"][-1]["event_type"] == "transferred"
    with pytest.raises(UnitActionError) as missing:
        act(db, "SN1", "transfer")
    assert missing.value.code == "holder_required"


def test_regularisation_dossier_marks_the_origin(db):
    add_form(db, "F1", status="partial_return", dossier_type="sortie"); add_item(db, "F1", "SN1", "conforme", "2026-03-01")
    sync_units_for_form(db, "F1")
    assert unit(db)["origin"] == "regularisation" and unit(db)["status"] == "in_stock"


def test_available_units_exclude_reserved_and_assigned_objects(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "conforme", "2026-03-01"); add_item(db, "F1", "SN2", "degrade", "2026-03-02")
    add_form(db, "F2", status="draft"); add_item(db, "F2", "SN3")
    add_form(db, "F3"); add_item(db, "F3", "SN4")
    for form in ("F1", "F2", "F3"):
        sync_units_for_form(db, form)
    assert [(u["identifier"], u["status"]) for u in available_units_for_resource(db, "ordinateur")] == [("SN2", "degraded"), ("SN1", "ok")]


def test_holder_lookup_reports_assigned_and_reserved_objects_of_other_dossiers(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    add_form(db, "F2", status="draft", nom="MARTIN", service="RH"); add_item(db, "F2", "SN2"); sync_units_for_form(db, "F2")
    assert find_holder_unit(db, "ordinateur", " sn1 ", "F9")["status"] == "assigned"
    assert find_holder_unit(db, "ordinateur", "SN1", "F1") is None  # c'est ce dossier lui-meme
    held = find_holder_unit(db, "ordinateur", "SN2", None)
    assert held["status"] == "reserved" and held["service"] == "RH"
    assert find_holder_unit(db, "ordinateur", "INCONNU", None) is None


def test_deleting_one_of_two_reserving_drafts_keeps_the_object_reserved(db):
    add_form(db, "F1", status="draft", updated="2026-06-01T08:00:00+00:00"); add_item(db, "F1", "SN1")
    add_form(db, "F2", status="draft", updated="2026-06-02T08:00:00+00:00", nom="MARTIN"); add_item(db, "F2", "SN1")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert release_units_for_form(db, "F2") == 1
    assert unit(db)["status"] == "reserved" and unit(db)["holder_form_id"] == "F1"
    assert release_units_for_form(db, "F1") == 1
    assert unit(db)["status"] == "in_stock" and unit(db)["holder_form_id"] is None


def test_removing_then_re_adding_the_object_in_a_draft_reserves_it_again(db):
    add_form(db, "F1", status="draft"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    db.execute("DELETE FROM dotation_items WHERE form_id='F1'"); sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "in_stock"
    add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    assert unit(db)["status"] == "reserved"
    assert [e[0] for e in events(db)] == ["reserved", "reservation_released", "reserved"]


def test_repeated_saves_of_competing_drafts_do_not_spam_the_journal(db):
    add_form(db, "F1", status="draft", updated="2026-06-01T08:00:00+00:00"); add_item(db, "F1", "SN1")
    add_form(db, "F2", status="draft", updated="2026-06-02T08:00:00+00:00", nom="MARTIN"); add_item(db, "F2", "SN1")
    for _ in range(3):
        sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    assert [e[0] for e in events(db)] == ["reserved", "reserved"]


def test_deleting_a_draft_that_only_reserved_never_touches_the_actual_holder(db):
    add_form(db, "F1", assigned="2026-01-10"); add_item(db, "F1", "SN1"); sync_units_for_form(db, "F1")
    add_form(db, "F2", status="draft", updated="2026-06-02T08:00:00+00:00"); add_item(db, "F2", "SN1"); sync_units_for_form(db, "F2")
    release_units_for_form(db, "F2")
    assert unit(db)["status"] == "assigned" and unit(db)["holder_form_id"] == "F1"


def test_a_degraded_object_keeps_its_condition_after_a_reservation_is_lifted(db):
    add_form(db, "F1"); add_item(db, "F1", "SN1", "degrade", "2026-03-01"); sync_units_for_form(db, "F1")
    add_form(db, "F2", status="draft", updated="2026-06-02T08:00:00+00:00"); add_item(db, "F2", "SN1"); sync_units_for_form(db, "F2")
    assert unit(db)["status"] == "reserved"
    release_units_for_form(db, "F2")
    assert unit(db)["status"] == "degraded"


# --- etape 5 : RGPD, import CSV, indicateurs ------------------------------------------------

from datetime import datetime, timezone

from models.units_extra import ANONYMIZED_LABEL, anonymize_old_holders, compute_indicators, import_units


def test_old_holders_are_anonymized_but_events_and_current_holders_are_kept(db):
    add_form(db, "F1", assigned="2018-01-10T10:00:00+00:00", updated="2018-03-01"); add_item(db, "F1", "SN1", "conforme", "2018-03-01")
    add_form(db, "F2", assigned="2026-01-10T10:00:00+00:00", updated="2026-01-10", nom="MARTIN"); add_item(db, "F2", "SN2")
    sync_units_for_form(db, "F1"); sync_units_for_form(db, "F2")
    changed = anonymize_old_holders(db, 5, datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert changed == 2  # les deux evenements de F1 (attribution et retour)
    detail = get_unit(db, unit(db)["id"])
    assert [e["event_type"] for e in detail["events"]] == ["assigned", "returned"]
    assert all(e["holder_label"] == ANONYMIZED_LABEL for e in detail["events"])
    assert get_unit(db, unit(db, "SN2")["id"])["events"][0]["holder_label"] == "MARTIN Anne · DSI"  # recent
    assert anonymize_old_holders(db, 5, datetime(2026, 9, 19, tzinfo=timezone.utc)) == 0  # idempotent


def test_a_currently_held_object_is_never_anonymized_even_if_old(db):
    add_form(db, "F1", assigned="2018-01-10T10:00:00+00:00", updated="2018-01-10"); add_item(db, "F1", "SN1")
    sync_units_for_form(db, "F1")
    assert anonymize_old_holders(db, 5, datetime(2026, 9, 19, tzinfo=timezone.utc)) == 0
    assert unit(db)["holder_label"] == "DUPONT Anne · DSI"


CSV = ("Ressource;Identifiant;Etat;Marque\n"
       "Ordinateur;SN-A1;en stock;Lenovo\n"
       "ordinateur;SN-A2;Dégradé;Dell\n"
       "Ordinateur;SN-A1;en stock;Doublon\n"
       "Ordinateur;;en stock;Vide\n"
       "Imprimante;SN-Z;en stock;X\n"
       "Ordinateur;SN-A3;cassé;X\n")


def test_csv_import_dry_run_reports_without_writing(db):
    db.execute("UPDATE resource_catalog SET code='ordinateur' WHERE code='ordinateur'")
    db.execute("INSERT INTO resource_catalog VALUES ('imprimante','Imprimante','materiel','none','[]')")
    report = import_units(db, CSV, "gestionnaire", dry_run=True)
    assert (report["rows"], report["created"]) == (6, 2) and len(report["errors"]) == 4
    assert {e["line"] for e in report["errors"]} == {4, 5, 6, 7}
    assert db.execute("SELECT COUNT(*) FROM resource_units").fetchone()[0] == 0


def test_csv_import_creates_units_with_the_requested_state_and_skips_existing_ones(db):
    add_form(db, "F1"); add_item(db, "F1", "SN-A2"); sync_units_for_form(db, "F1")  # SN-A2 existe deja
    report = import_units(db, CSV.replace("SN-A3;cassé", "SN-A3;perdu"), "gestionnaire", dry_run=False)
    assert report["created"] == 2 and report["skipped"] == 1  # SN-A1 et SN-A3 ; SN-A2 deja connu
    assert unit(db, "SN-A1")["status"] == "in_stock" and json.loads(unit(db, "SN-A1")["fields_json"]) == {"numeroSerie": "SN-A1", "marque": "Lenovo"}
    assert unit(db, "SN-A3")["status"] == "lost" and unit(db, "SN-A3")["origin"] == "import"
    assert all(e[1] is None for e in events(db, "SN-A3"))  # un import n'est pas une anomalie
    assert import_units(db, CSV.replace("SN-A3;cassé", "SN-A3;perdu"), "g", dry_run=False)["created"] == 0  # idempotent


def test_csv_import_reads_comma_separated_files_and_field_labels(db):
    text = "ressource,N° de série,statut\nOrdinateur,SN-B1,réformé\n"
    assert import_units(db, text, "g", dry_run=False)["created"] == 1
    assert unit(db, "SN-B1")["status"] == "retired"


def test_indicators(db):
    add_form(db, "F1", assigned="2026-01-01T00:00:00+00:00"); add_item(db, "F1", "SN1", "conforme", "2026-01-11")
    add_form(db, "F2", assigned="2026-02-01T00:00:00+00:00"); add_item(db, "F2", "SN2", "degrade", "2026-02-21")
    add_form(db, "F3", assigned="2024-01-01T00:00:00+00:00"); add_item(db, "F3", "SN3")  # detenu depuis > 1 an
    for form in ("F1", "F2", "F3"):
        sync_units_for_form(db, form)
    stats = compute_indicators(db, now=datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert stats["units"] == 3 and stats["by_status"] == {"in_stock": 1, "degraded": 1, "assigned": 1}
    assert stats["avg_hold_days"] == 15.0 and stats["damage_rate"] == 50.0
    assert stats["long_held"] == 1 and stats["assignments_per_unit"] == 1.0 and stats["anomalies"] == 0
    assert compute_indicators(db, "telephone")["units"] == 0
