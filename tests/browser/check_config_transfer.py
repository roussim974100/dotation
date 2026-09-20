"""Export / import du paramétrage (Administration > Base de données) : aperçu sans écriture, application additive, rejeu sans effet,
fichier invalide refusé. Instance isolée, base vierge.
    python tests/browser/check_config_transfer.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
CSRF = "jeton-navigateur"


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


def resource_codes(driver):
    return {r["code"] for r in api(driver, "GET", "/api/admin/resources")["json"]}


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    driver.get(inst.url("/admin-db.html"))
    time.sleep(2.5)
    exported = api(driver, "GET", "/api/admin/config-export")
    check("l'export est servi", exported["status"] == 200 and exported["json"]["format"] == "aquai-config")
    config = exported["json"]
    config["resources"].append({"code": "importee_ui", "label": "Ressource importée", "category": "materiel", "requires_return": True, "tracking_mode": "none",
                                "field_schema": [{"key": "ref", "label": "Référence", "type": "text"}]})
    config["services"].append({"label": "Service importé", "is_active": True})
    path = Path(tempfile.gettempdir()) / "aquai_config_test.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    driver.find_element("id", "configImportFile").send_keys(str(path))
    driver.execute_script("document.getElementById('configPreviewBtn').click()")
    check("aperçu : la nouvelle ressource est annoncée", wait_for(lambda: "importee_ui" in driver.find_element("id", "configImportResult").text))
    check("aperçu : rien n'est écrit", "importee_ui" not in resource_codes(driver))
    check("bouton « Appliquer l'import » affiché", driver.execute_script("return !document.getElementById('configApplyBtn').classList.contains('d-none')"))
    driver.execute_script("document.getElementById('configApplyBtn').click()")
    check("application : la ressource est créée", wait_for(lambda: "importee_ui" in resource_codes(driver)))
    services = {s["label"] for s in api(driver, "GET", "/api/admin/services")["json"]}
    check("application : le service est créé", "Service importé" in services, str(list(services))[:120])

    driver.execute_script("document.getElementById('configPreviewBtn').click()")
    check("rejeu : « rien à importer »", wait_for(lambda: "Rien à importer" in driver.find_element("id", "configImportResult").text))

    path.write_text(json.dumps({"format": "autre"}), encoding="utf-8")
    driver.get(inst.url("/admin-db.html"))
    time.sleep(2)
    driver.find_element("id", "configImportFile").send_keys(str(path))
    driver.execute_script("document.getElementById('configPreviewBtn').click()")
    check("fichier invalide refusé avec un message", wait_for(lambda: "non reconnu" in driver.find_element("id", "configImportResult").text))
    path.unlink(missing_ok=True)
    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "api/debug/logs" not in e and "400" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:200])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
