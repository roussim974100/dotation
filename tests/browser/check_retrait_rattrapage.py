"""3.64.0 : le « Contrôle général de la base » (Administration > Base de données) signale un retrait « mise a jour » non
repercute au parc (etat herite du bug corrige en 3.60.1), puis n'en signale plus une fois la migration 7 rejouee.
Instance isolee, base vierge ; l'etat herite est recree directement dans la base de l'instance.
    python tests/browser/check_retrait_rattrapage.py
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
from browser_harness import Instance  # noqa: E402

results = []
CSRF = "jeton-navigateur"
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def api(driver, method, path, body=None):
    script = ("const [m,p,b]=arguments;return fetch(p,{method:m,credentials:'same-origin',headers:{'Content-Type':'application/json',"
              f"'X-CSRF-Token':'{CSRF}'}},body:b?JSON.stringify(b):undefined}}).then(async r=>{{let j=null;try{{j=await r.json()}}catch(e){{}};return JSON.stringify({{status:r.status,json:j}})}})")
    return json.loads(driver.execute_script(script, method, path, body))


def wait_for(fn, tries=30):
    for _ in range(tries):
        time.sleep(0.4)
        try:
            if fn():
                return True
        except Exception:
            pass
    return False


def run_health_from_the_page(driver):
    driver.get(inst.url("/admin-db.html"))
    time.sleep(2.5)
    driver.execute_script("document.getElementById('dbHealthBtn').click()")
    time.sleep(2.5)
    return driver.execute_script("return document.body.innerText")


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    api(driver, "POST", "/api/admin/resources", {
        "code": "poste_rattrapage", "label": "Poste rattrapage", "description": "", "category": "materiel", "issuer_service": "DSI",
        "requires_return": True, "has_assignment_date": False, "has_assignment_condition": False, "has_assignment_notes": False,
        "display_order": 990, "is_active": True, "tracking_mode": "unit",
        "field_schema": [{"key": "numero_de_serie", "label": "N° de série", "type": "text", "required": True, "identifier": True}]})
    catalog = next((r for r in (api(driver, "GET", "/api/admin/resources")["json"] or []) if r.get("code") == "poste_rattrapage"), {})
    schema = catalog.get("field_schema") or catalog.get("fieldSchema") or []
    source = api(driver, "POST", "/api/forms", {
        "dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "RATTRAPAGE", "prenom": "Source", "qualite": "agent"},
        "resources": {"additional": [{"id": catalog.get("id"), "code": "poste_rattrapage", "label": "Poste rattrapage", "category": "materiel",
                                      "requiresReturn": True, "hasAssignmentDate": False, "selected": True, "fieldSchema": schema,
                                      "fields": {"numero_de_serie": "SN-RATTRAPAGE"}, "details": ""}]},
        "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}})
    source_id = (source["json"].get("summary") or {}).get("id")
    check("dossier source actif créé", source["status"] in (200, 201) and source_id, str(source)[:200])
    api(driver, "POST", "/api/forms", {
        "dossier": {"type": "mise_a_jour", "sourceFormId": source_id}, "beneficiaire": {"nom": "RATTRAPAGE", "prenom": "Source", "qualite": "agent"},
        "resources": {"additional": []}, "retraits": {"items": {"poste_rattrapage": {"selected": True, "etat": "Bon", "notes": "rendu"}}},
        "workflow": {"status": "draft"}, "meta": {}})

    text = run_health_from_the_page(driver)
    check("état sain : aucun retrait non répercuté signalé", "retrait non répercuté" not in text, text[-300:])

    # État hérité du bug 3.60.1 : le dossier dit « rendu » mais le parc garde l'objet attribué.
    database = sqlite3.connect(str(Path(inst.dir) / "dotation.db"), timeout=10)
    database.execute("UPDATE resource_units SET status = 'assigned', holder_form_id = ? WHERE resource_code = 'poste_rattrapage'", (source_id,))
    database.commit()
    database.close()
    text = run_health_from_the_page(driver)
    check("le contrôle signale le retrait non répercuté", "retrait non répercuté" in text, text[-400:])

    # Migration 7 rejouée sur l'instance (même code que celle du démarrage).
    import subprocess
    code = ("import sys; sys.path.insert(0, r'%s'); import sqlite3, os; from migrations import _m_resync_retrait_sources; "
            "c = sqlite3.connect(os.path.join(os.environ['APP_DATA_DIR'], 'dotation.db')); c.row_factory = sqlite3.Row; "
            "_m_resync_retrait_sources(c); c.commit()" % (Path(__file__).parent.parent.parent / "backend"))
    import os
    env = dict(os.environ, APP_DATA_DIR=inst.dir, APP_CUSTOM_BRANDING_DIR=os.path.join(inst.dir, "branding"), PYTHONIOENCODING="utf-8")
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, encoding="utf-8")
    check("la migration de rattrapage s'exécute sans erreur", done.returncode == 0, done.stderr[-300:])
    text = run_health_from_the_page(driver)
    check("après rattrapage, plus rien n'est signalé", "retrait non répercuté" not in text, text[-300:])
    units = api(driver, "GET", "/api/units?resource=poste_rattrapage")["json"].get("units", [])
    check("l'objet est redevenu disponible dans le parc", [u["status"] for u in units if u.get("identifier") == "SN-RATTRAPAGE"] == ["in_stock"], str(units)[:200])

    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
