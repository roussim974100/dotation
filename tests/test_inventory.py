"""Materiel restitue reutilisable : unites disponibles d'une ressource."""
import json
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.inventory import compute_available_units, resolve_identifier_key


def _row(serial, condition, when, item_id, legacy=False, **extra):
    fields = {"numeroSerie": serial, "marque": "Lenovo", "modele": "X1", **extra}
    details = fields if legacy else {"selected": True, "fields": fields}
    return {"details_json": json.dumps(details), "return_condition": condition, "returned_at": "2026-05-01", "sort_key": when, "item_id": item_id}


def test_identifier_key_is_resolved_from_the_catalog():
    assert resolve_identifier_key([{"key": "marque"}, {"key": "numeroSerie"}]) == "numeroSerie"
    assert resolve_identifier_key([{"key": "numero"}]) == "numero"
    assert resolve_identifier_key([{"key": "immatriculation"}, {"key": "modele"}]) == "immatriculation"
    assert resolve_identifier_key([{"key": "description"}]) is None
    assert resolve_identifier_key([]) is None


def test_explicit_identifier_flag_wins():
    schema = [{"key": "numeroSerie"}, {"key": "nomPoste", "identifier": True}]
    assert resolve_identifier_key(schema) == "nomPoste"


def test_returned_unit_is_available():
    units = compute_available_units([_row("SN1", "conforme", "2026-05-01", 1)], "numeroSerie")
    assert [(u["identifier"], u["status"]) for u in units] == [("SN1", "ok")]
    assert units[0]["fields"]["marque"] == "Lenovo"


def test_unit_reassigned_later_is_not_available():
    rows = [_row("SN1", "conforme", "2026-05-01", 1), _row("SN1", "pending", "2026-06-01", 2)]
    assert compute_available_units(rows, "numeroSerie") == []


def test_unit_returned_again_after_reassignment_is_available_again():
    rows = [_row("SN1", "conforme", "2026-05-01", 1), _row("SN1", "pending", "2026-06-01", 2), _row("SN1", "bon", "2026-07-01", 3)]
    assert [u["identifier"] for u in compute_available_units(rows, "numeroSerie")] == ["SN1"]


def test_degraded_unit_is_offered_with_a_warning_status():
    units = compute_available_units([_row("SN2", "degrade", "2026-05-01", 1)], "numeroSerie")
    assert units[0]["status"] == "degraded"


def test_lost_or_pending_units_are_excluded():
    rows = [_row("SN3", "non_restitue", "2026-05-01", 1), _row("SN4", "pending", "2026-05-01", 2)]
    assert compute_available_units(rows, "numeroSerie") == []


def test_identifier_matching_ignores_case_and_spacing():
    rows = [_row("sn 1", "conforme", "2026-05-01", 1), _row("  SN   1 ", "pending", "2026-06-01", 2)]
    assert compute_available_units(rows, "numeroSerie") == []


def test_rows_without_identifier_are_ignored_and_legacy_format_is_read():
    rows = [_row("", "conforme", "2026-05-01", 1), _row("SN9", "conforme", "2026-05-02", 2, legacy=True)]
    assert [u["identifier"] for u in compute_available_units(rows, "numeroSerie")] == ["SN9"]


def test_most_recently_returned_first():
    a = _row("A", "conforme", "2026-05-01", 1); a["returned_at"] = "2026-05-01"
    b = _row("B", "conforme", "2026-05-02", 2); b["returned_at"] = "2026-05-09"
    assert [u["identifier"] for u in compute_available_units([a, b], "numeroSerie")] == ["B", "A"]


def test_only_fields_defined_by_the_resource_are_returned():
    row = _row("SN5", "conforme", "2026-05-01", 1, legacy=True, assignedAt="2025-11-15", conditionAttribution="neuf", selected=True)
    units = compute_available_units([row], "numeroSerie", {"numeroSerie", "marque", "modele"})
    assert set(units[0]["fields"]) == {"numeroSerie", "marque", "modele"}
