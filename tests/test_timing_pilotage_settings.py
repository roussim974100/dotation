"""Tests pour le seuil de pilotage configurable (timing_warning_days)."""
import sys
from pathlib import Path
from datetime import date, timedelta

backend_path = str(Path(__file__).parent.parent / 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.workflow import summarize_assignment_progress
from models.settings import build_public_settings_payload, DEFAULT_APP_SETTINGS


def _payload_with_start_in(days_from_today):
    start_at = (date.today() + timedelta(days=days_from_today)).isoformat()
    return {
        "materiel": {"badge": {"selected": True}},
        "meta": {"startAt": start_at},
    }


def test_default_threshold_matches_previous_hardcoded_behavior():
    """Sans warning_days explicite, le seuil par defaut reste 3 jours (comportement historique)."""
    assert summarize_assignment_progress(_payload_with_start_in(3))["timingStatus"] == "warning"
    assert summarize_assignment_progress(_payload_with_start_in(4))["timingStatus"] == "ok"


def test_explicit_warning_days_moves_the_threshold():
    """Un seuil personnalise (5 jours) deplace bien la bascule warning/ok."""
    result_at_5 = summarize_assignment_progress(_payload_with_start_in(5), warning_days=5)
    result_at_6 = summarize_assignment_progress(_payload_with_start_in(6), warning_days=5)
    assert result_at_5["timingStatus"] == "warning"
    assert result_at_5["timingLabel"] == "En danger"
    assert result_at_6["timingStatus"] == "ok"
    assert result_at_6["timingLabel"] == "Dans les temps"


def test_late_status_unaffected_by_warning_days():
    """Un dossier avec une date depassee reste 'late' quel que soit le seuil."""
    result = summarize_assignment_progress(_payload_with_start_in(-1), warning_days=10)
    assert result["timingStatus"] == "late"


def test_public_settings_payload_exposes_default_timing_warning_days():
    payload = build_public_settings_payload(dict(DEFAULT_APP_SETTINGS))
    assert payload["timingWarningDays"] == 3


def test_public_settings_payload_exposes_custom_timing_warning_days():
    settings = dict(DEFAULT_APP_SETTINGS)
    settings["timing_warning_days"] = "7"
    payload = build_public_settings_payload(settings)
    assert payload["timingWarningDays"] == 7
