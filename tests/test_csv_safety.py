"""Exports CSV : les cellules qui ressemblent a des formules sont neutralisees (Excel les executerait sinon)."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from routes.forms import csv_cell
from utils import csv_safe


def test_formules_neutralisees():
    for start in ("=", "+", "-", "@"):
        assert csv_safe(f"{start}CMD()").startswith("'")
    assert csv_safe("Service normal") == "Service normal"
    assert csv_safe(None) == ""


def test_cellule_csv_guillemets_et_separateur():
    assert csv_cell("a;b") == '"a;b"'
    assert csv_cell('dit "oui"') == '"dit ""oui"""'
    assert csv_cell("=1+1") == "'=1+1"
