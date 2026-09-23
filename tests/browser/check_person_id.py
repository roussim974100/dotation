"""3.61.0 : le formulaire « Mise à jour de ressources » transmet l'identité de la personne du dossier source (pas de
nouvelle fiche « personne » créée à chaque mise à jour). Instance isolée, base vierge.
    python tests/browser/check_person_id.py
"""
import json
import sys
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


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "PERSONID", "prenom": "Source", "qualite": "agent"},
            "resources": {"additional": []},
            "validation": {"signatureDataUrl": "data:image/png;base64,x", "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}
    created = api(driver, "POST", "/api/forms", body)
    src_id = (created["json"].get("summary") or {}).get("id")
    check("dossier source créé", created["status"] in (200, 201), str(created)[:200])
    src_data = api(driver, "GET", f"/api/forms/{src_id}")["json"].get("data", {})
    src_person_id = src_data.get("meta", {}).get("personId")
    check("le dossier source a un identifiant de personne", bool(src_person_id), str(src_data.get("meta")))

    driver.get(inst.url("/form.html"))
    time.sleep(3)
    driver.execute_script("document.getElementById('dossier_type').value = 'mise_a_jour'; document.getElementById('dossier_type').dispatchEvent(new Event('change', {bubbles: true}));")
    time.sleep(0.5)
    search = driver.find_element("id", "retraitsSourceSearch")
    search.send_keys("PERSONID")
    check("un résultat de recherche apparaît", wait_for(lambda: driver.execute_script("return document.querySelectorAll('.retrait-form-option').length") > 0))
    driver.execute_script("document.querySelector('.retrait-form-option').click()")
    check("l'identité de la personne est transmise au champ caché", wait_for(lambda: driver.execute_script("return document.getElementById('retraitsSourcePersonId').value") == src_person_id),
          driver.execute_script("return document.getElementById('retraitsSourcePersonId').value"))

    driver.execute_script("document.getElementById('nom').value = 'PERSONID'; document.getElementById('prenom').value = 'Source';")
    form_data = driver.execute_script("return getFormData({toDataUrl: () => ''}).meta")
    check("getFormData() inclut le bon personId", form_data.get("personId") == src_person_id, str(form_data))

    saved = api(driver, "POST", "/api/forms", {"dossier": {"type": "mise_a_jour", "sourceFormId": src_id},
                                                "beneficiaire": {"nom": "PERSONID", "prenom": "Source", "qualite": "agent"},
                                                "resources": {"additional": []}, "retraits": {"items": {}},
                                                "workflow": {"status": "draft"}, "meta": {"personId": src_person_id}})
    maj_id = (saved["json"].get("summary") or {}).get("id")
    maj_person_id = api(driver, "GET", f"/api/forms/{maj_id}")["json"].get("data", {}).get("meta", {}).get("personId")
    check("le nouveau dossier partage la même personne que la source", maj_person_id == src_person_id, f"{maj_person_id} != {src_person_id}")

    # Bouton « Changer » : réinitialise l'identité transmise
    driver.get(inst.url("/form.html"))
    time.sleep(2.5)
    driver.execute_script("document.getElementById('dossier_type').value = 'mise_a_jour'; document.getElementById('dossier_type').dispatchEvent(new Event('change', {bubbles: true}));")
    time.sleep(0.5)
    driver.find_element("id", "retraitsSourceSearch").send_keys("PERSONID")
    wait_for(lambda: driver.execute_script("return document.querySelectorAll('.retrait-form-option').length") > 0)
    driver.execute_script("document.querySelector('.retrait-form-option').click()")
    wait_for(lambda: driver.execute_script("return document.getElementById('retraitsSourcePersonId').value") == src_person_id)
    driver.execute_script("document.getElementById('retraitsSourceClear').click()")
    check("« Changer » réinitialise l'identité transmise", driver.execute_script("return document.getElementById('retraitsSourcePersonId').value") == "")

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "api/debug/logs" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:200])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
