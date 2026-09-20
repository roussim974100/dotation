"""Historique de vie du Parc : format de la date d'un evenement (parcWhen dans frontend/js/parc.js), execute avec Node."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node indisponible")


def run_parc_when(values):
    source = (ROOT / "frontend" / "js" / "parc.js").read_text(encoding="utf-8")
    function = re.search(r"function parcWhen\(value\) \{.*?\n\}\n", source, re.S).group(0)
    script = function + "\nconsole.log(JSON.stringify(%s.map(parcWhen)));" % json.dumps(values)
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_time_is_shown_only_when_it_is_known():
    dates = run_parc_when([
        "2026-09-18T12:04",            # saisi avec une heure : affichee
        "2026-09-19T00:00:00",         # date sans heure (enregistree a minuit) : jour seul, jamais « 00:00 »
        "2026-01-10",                  # jour seul
        "2026-09-19T00:00",
    ])
    assert dates[0] == "18/09/2026 · 12:04"
    assert dates[1] == "19/09/2026" and dates[3] == "19/09/2026"
    assert dates[2] == "10/01/2026"


def test_an_unreadable_date_is_announced_instead_of_left_blank():
    assert run_parc_when(["n'importe quoi", ""]) == ["date inconnue", "date inconnue"]


def test_a_timestamp_with_a_timezone_keeps_a_time():
    assert " · " in run_parc_when(["2026-09-19T16:42:05.616658+00:00"])[0]
