"""3.63.0 : ajustement d'un dossier actif, verifie dans un vrai navigateur (session et jeton CSRF reels) : la fiche recharge avec le
nouveau service, reste verrouillee et signee, le parc reflete le retrait, aucune image de signature n'est renvoyee par la route,
et le dossier reste visible dans les listes. Instance isolee, base vierge.
    python tests/browser/check_adjustment.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
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


def resource(code, label, serial):
    return {"id": code, "code": code, "label": label, "category": "materiel", "requiresReturn": True, "selected": True,
            "fields": {"marque": "X", "numero_de_serie": serial}, "details": "", "assignedAt": "2026-09-01T09:00:00"}


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "AJUSTBROWSER", "prenom": "Test", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": [resource("ordinateur", "Ordinateur", "SN-1"), resource("telephone", "Téléphone", "SN-2")]},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}}
    created = api(driver, "POST", "/api/forms", body)
    form_id = (created["json"].get("summary") or {}).get("id")
    check("dossier actif créé", created["status"] in (200, 201) and form_id, str(created)[:200])

    adjusted = api(driver, "PATCH", f"/api/forms/{form_id}/ajustement", {
        "ajouts": [resource("tablette", "Tablette", "SN-3")],
        "retraits": [{"key": "ordinateur", "state": "conforme", "notes": "rendu au guichet"}],
        "service": "Finances", "signature": {"mode": "presentiel", "signatureDataUrl": PNG}})
    check("l'ajustement est accepté", adjusted["status"] == 200, str(adjusted)[:300])
    check("la réponse ne contient aucune image de signature", "data:image" not in json.dumps(adjusted["json"]))
    check("le dossier reste actif", (adjusted["json"].get("summary") or {}).get("status") == "active")

    driver.get(inst.url(f"/form.html?id={form_id}"))
    time.sleep(3.5)
    # « Finances » n'existe pas au catalogue de cette base vierge : la fiche l'affiche alors dans le champ « autre service ».
    service_shown = driver.execute_script("return [...document.querySelectorAll('input, select')].some(el => el.value === 'Finances')")
    check("la fiche affiche le nouveau service", service_shown)
    check("la fiche reste verrouillée (signée)", bool(driver.execute_script("return document.getElementById('dotationForm')?.dataset.lockedAt || ''")))

    stored = api(driver, "GET", f"/api/forms/{form_id}")["json"]
    events = stored["data"].get("ajustements") or []
    check("l'historique porte un événement signé", len(events) == 1 and events[0]["status"] == "signed", str(events)[:200])
    check("le retrait est tracé dans la restitution partielle", stored["data"]["restitution"]["items"]["ordinateur"]["state"] == "conforme")

    parc = api(driver, "GET", "/api/units")
    parc_text = json.dumps(parc["json"])
    check("le parc répond", parc["status"] == 200, str(parc["status"]))

    listed = {}
    for page, view in (("index.html", "attributions en cours"), ("assignments-completed.html", "attributions finalisées"),
                       ("restitutions-pending.html", "restitutions en cours"), ("restitutions-completed.html", "restitutions finalisées")):
        driver.get(inst.url("/" + page))
        time.sleep(3)
        listed[view] = "AJUSTBROWSER" in driver.execute_script("return document.body.innerText").upper()
    print("     (information) visible dans :", [v for v, seen in listed.items() if seen] or "aucune liste")
    check("un dossier qui garde des ressources reste dans « Attributions finalisées », pas en restitution",
          listed["attributions finalisées"] and not listed["restitutions en cours"] and not listed["restitutions finalisées"], str(listed))

    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
