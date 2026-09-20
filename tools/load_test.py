"""Test de charge sur une base SYNTHÉTIQUE (jamais de vraie donnée) : construit N dossiers, mesure le démarrage et les principaux endpoints.
    python tools/load_test.py 3000"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
out = Path(tempfile.mkdtemp(prefix="aquai_charge_"))
pack = {"resources": [{"code": "pc_charge", "category": "materiel", "trackingMode": "unit", "requiresReturn": True,
                       "fields": [{"id": "fld_1", "key": "numero_de_serie", "type": "text", "required": True, "identifier": True},
                                  {"id": "fld_2", "key": "marque", "type": "text"}, {"id": "fld_3", "key": "modele", "type": "text"}]}],
        "usage": {"formsByStatus": {"draft": N // 2, "active": N - N // 2}, "formsPerResource": {"pc_charge": N}}}
(out / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
env = dict(os.environ, PYTHONIOENCODING="utf-8")
t = time.time()
r = subprocess.run([sys.executable, str(ROOT / "tools/build_skeleton.py"), str(out / "pack.json"), str(out / "data"), "--max-forms", str(N)], cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8")
print("construction:", round(time.time() - t, 1), "s", r.stdout.strip()[-120:], r.stderr.strip()[-200:])

# demarrage a froid sur cette grosse base
code = "import time; t=time.time(); import app; print('demarrage_s', round(time.time()-t,2))"
e2 = dict(env, APP_DATA_DIR=str(out / "data"), APP_UPDATE_CHECK="0", APP_HEALTH_INTERVAL_HOURS="0")
r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT / "backend"), env=e2, capture_output=True, text=True, encoding="utf-8")
print(r.stdout.strip(), r.stderr.strip()[-200:])

# endpoints
code = r'''
import time, json, sys
sys.path.insert(0, ".")
import app as m
c = m.app.test_client()
with c.session_transaction() as s:
    s["user"] = "admin"; s["csrf_token"] = "j"
for path in ["/api/forms", "/api/admin/dashboard-stats", "/api/stock", "/api/units", "/api/units/stats", "/api/admin/health", "/api/admin/diagnostic", "/api/forms/export", "/api/admin/logs", "/api/reference/resources"]:
    t = time.time(); r = c.get(path); dt = time.time() - t
    print(f"{path:32} {r.status_code} {dt*1000:8.0f} ms {len(r.data)//1024:6d} Ko")
'''
r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT / "backend"), env=e2, capture_output=True, text=True, encoding="utf-8")
print(r.stdout, r.stderr[-400:])
print("dossier:", out)
