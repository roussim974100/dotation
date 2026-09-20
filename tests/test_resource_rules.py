"""Coherence d'une ressource du catalogue (mode de suivi, champ identifiant)."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.resource_rules import blocking_issues, catalog_quality_report, effective_tracking_mode, validate_resource

SERIAL = {"key": "numeroSerie", "label": "N° de série", "required": True}


def _res(**over):
    base = {"code": "pc", "label": "PC", "category": "materiel", "requires_return": True, "has_assignment_condition": True,
            "issuer_service": "DSI", "tracking_mode": "unit", "field_schema": [dict(SERIAL)]}
    base.update(over)
    return base


def _codes(issues):
    return {i["code"] for i in issues}


def test_well_configured_unit_resource_has_no_issue():
    assert validate_resource(_res()) == []


def test_unit_without_identifier_is_blocking_when_mode_is_explicit():
    issues = validate_resource(_res(field_schema=[{"key": "marque", "label": "Marque"}]))
    assert "no_identifier" in _codes(blocking_issues(issues))


def test_same_problem_is_only_a_warning_for_legacy_automatic_mode():
    issues = validate_resource(_res(tracking_mode="", field_schema=[{"key": "numeroSerie", "label": "N", "required": False}]))
    assert not blocking_issues(issues)
    assert "identifier_optional" in _codes(issues)


def test_identifier_must_be_required_and_visible():
    optional = validate_resource(_res(field_schema=[{**SERIAL, "required": False}]))
    hidden = validate_resource(_res(field_schema=[{**SERIAL, "hidden": True}]))
    assert "identifier_optional" in _codes(blocking_issues(optional))
    assert "identifier_hidden" in _codes(blocking_issues(hidden))


def test_unit_tracking_requires_material_category():
    assert "unit_needs_material" in _codes(blocking_issues(validate_resource(_res(category="immateriel"))))


def test_only_one_explicit_identifier_and_no_duplicate_keys():
    two = validate_resource(_res(field_schema=[{**SERIAL, "identifier": True}, {"key": "nomPoste", "label": "Poste", "identifier": True, "required": True}]))
    dup = validate_resource(_res(field_schema=[dict(SERIAL), dict(SERIAL)]))
    assert "several_identifiers" in _codes(blocking_issues(two))
    assert "duplicate_field" in _codes(blocking_issues(dup))


def test_recommendations_are_warnings():
    issues = validate_resource(_res(has_assignment_condition=False, requires_return=False, issuer_service=""))
    assert {"no_condition", "unit_not_returnable", "no_issuer"} <= _codes(issues)
    assert not blocking_issues(issues)


def test_no_tracking_and_access_modes_need_no_identifier():
    assert not blocking_issues(validate_resource(_res(tracking_mode="none", field_schema=[])))
    access = validate_resource(_res(tracking_mode="access", category="immateriel", requires_return=False, field_schema=[]))
    assert not blocking_issues(access)


def test_effective_mode_is_derived_for_legacy_resources():
    assert effective_tracking_mode("", "materiel", [dict(SERIAL)]) == "unit"
    assert effective_tracking_mode("", "materiel", []) == "none"
    assert effective_tracking_mode("", "immateriel", []) == "access"
    assert effective_tracking_mode("none", "materiel", [dict(SERIAL)]) == "none"


def test_quality_report_lists_only_resources_with_problems():
    good = {**_res(), "id": "1"}
    bad = {**_res(field_schema=[]), "id": "2", "code": "scanner", "label": "Scanner"}
    report = catalog_quality_report([good, bad])
    assert [r["code"] for r in report] == ["scanner"]
    assert report[0]["issues"][0]["code"] == "no_identifier"
