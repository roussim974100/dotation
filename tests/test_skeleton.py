"""Base squelette : reconstruite depuis un paquet de diagnostic, sans aucune donnée réelle, et l'application démarre dessus."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

PACK = {
    "format": "aquai-diagnostic",
    "resources": [{"code": "ressource_client", "category": "materiel", "trackingMode": "unit", "active": True, "requiresReturn": True,
                   "fields": [{"id": "fld_aaa", "key": "numero", "type": "text", "required": True, "identifier": True},
                              {"id": "fld_bbb", "key": "couleur", "type": "select"}, {"id": "fld_ccc", "key": "achat", "type": "date"}]}],
    "usage": {"formsByStatus": {"draft": 6, "active": 2}, "formsPerResource": {"ressource_client": 4}, "unreadablePayloads": 2},
}


def test_squelette_reconstruit_ressources_volumes_et_anomalies_puis_demarre(tmp_path):
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(PACK), encoding="utf-8")
    out = tmp_path / "squelette"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "build_skeleton.py"), str(pack_path), str(out)], cwd=str(ROOT), env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert result.returncode == 0, result.stderr[-1000:]

    db = sqlite3.connect(out / "dotation.db")
    schema = json.loads(db.execute("SELECT field_schema_json FROM resource_catalog WHERE code = 'ressource_client'").fetchone()[0])
    assert [f["key"] for f in schema] == ["numero", "couleur", "achat"] and schema[0]["identifier"] is True
    assert db.execute("SELECT COUNT(*) FROM dotation_forms WHERE title != 'ILLISIBLE'").fetchone()[0] == 8
    assert db.execute("SELECT COUNT(*) FROM dotation_forms WHERE title = 'ILLISIBLE'").fetchone()[0] == 2
    names = [r[0] for r in db.execute("SELECT nom FROM dotation_forms WHERE title != 'ILLISIBLE'").fetchall()]
    assert all(n.startswith("PERSONNE-") for n in names)  # uniquement des donnees fictives
    db.close()

    # l'application demarre sur cette base squelette (dont les 2 payloads illisibles)
    started = subprocess.run([sys.executable, "-c", "import app; print('DEMARRE')"], cwd=str(ROOT / "backend"),
                             env=dict(env, APP_DATA_DIR=str(out), APP_UPDATE_CHECK="0", APP_HEALTH_INTERVAL_HOURS="0"), capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert "DEMARRE" in started.stdout, started.stderr[-800:]
