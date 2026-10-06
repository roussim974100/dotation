"""3.67.2 : la fenetre d'ajustement ("Gerer les ressources") propose desormais de reprendre un materiel deja
restitue et en stock, comme la creation de dossier - avant, il fallait ressaisir le numero de serie a la main
(signale par l'utilisateur : un PC restitue n'etait jamais suggere). Instance isolee, base vierge.
    python tests/browser/check_adjustment_reuse_stock.py
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


def wait_for(fn, tries=40):
    for _ in range(tries):
        time.sleep(0.4)
        try:
            if fn():
                return True
        except Exception:
            pass
    return False


def js(driver, script, *args):
    return driver.execute_script(script, *args)


with Instance() as inst:
    driver = inst.driver(width=1400, height=1000)
    driver.get(inst.url("/index.html"))
    time.sleep(2)

    # Ressource suivie par numero de serie (identifier: true).
    created_resource = api(driver, "POST", "/api/admin/resources", {
        "code": "ordi_reuse", "label": "Ordinateur reprise", "description": "", "category": "materiel",
        "issuer_service": "DSI", "requires_return": True, "has_assignment_date": False,
        "has_assignment_condition": False, "has_assignment_notes": False, "display_order": 990, "is_active": True,
        "field_schema": [
            {"key": "numeroSerie", "label": "N° de série", "type": "text", "required": True, "identifier": True},
            {"key": "marque", "label": "Marque", "type": "text", "required": True},
        ]})
    catalog = {r["code"]: r for r in api(driver, "GET", "/api/admin/resources")["json"]}
    resource_ref = catalog["ordi_reuse"]
    check("ressource « Ordinateur reprise » créée avec un identifiant", bool(resource_ref.get("id")))

    # Dossier 1 : detient l'ordinateur SN-TEST-001, puis le restitue via un ajustement (etat conforme).
    first = api(driver, "POST", "/api/forms", {
        "dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "TORAMAN", "prenom": "Alicia", "qualite": "agent", "service": "DRH"},
        "resources": {"additional": [{"id": resource_ref["id"], "code": "ordi_reuse", "label": "Ordinateur reprise",
                                      "category": "materiel", "requiresReturn": True, "selected": True,
                                      "fieldSchema": resource_ref.get("field_schema") or [],
                                      "fields": {"numeroSerie": "SN-TEST-001", "marque": "HP"}, "details": "",
                                      "assignedAt": "2026-09-01T09:00:00"}]},
        "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}})
    first_id = (first["json"].get("summary") or {}).get("id")
    check("dossier 1 (Toraman) créé avec SN-TEST-001", bool(first_id))

    withdrawal = api(driver, "PATCH", f"/api/forms/{first_id}/ajustement", {
        "retraits": [{"key": "ordi_reuse", "state": "conforme"}],
        "signature": {"mode": "presentiel", "signatureDataUrl": PNG},
    })
    check("SN-TEST-001 restitué via un ajustement (état conforme)", withdrawal["status"] == 200, str(withdrawal)[:200])

    # Dossier 2 : une autre personne, active, sans cet ordinateur - c'est elle qui doit pouvoir le reprendre.
    second = api(driver, "POST", "/api/forms", {
        "dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "GUERRIERO", "prenom": "Lilou", "qualite": "agent", "service": "DRH"},
        "resources": {"additional": [{"id": 1, "code": "badge", "label": "Badge", "category": "materiel", "requiresReturn": True,
                                      "selected": True, "fields": {"marque": "X"}, "details": "", "assignedAt": "2026-09-01T09:00:00"}]},
        "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}})
    second_id = (second["json"].get("summary") or {}).get("id")
    check("dossier 2 (Guerriero) créé", bool(second_id))

    driver.get(inst.url("/assignments-completed.html"))
    check("la liste affiche Lilou", wait_for(lambda: "GUERRIERO" in js(driver, "return document.body.innerText").upper()))
    js(driver, """
        const row = [...document.querySelectorAll('tr.draft-row')].find(r => r.innerText.includes('GUERRIERO'));
        row.querySelector('[data-action="openAdjustment"]').click();
    """)
    check("la fenêtre d'ajustement s'ouvre", wait_for(lambda: js(
        driver, "const m = document.getElementById('adjustmentModal'); return Boolean(m && !m.classList.contains('d-none'))")))

    js(driver, """
        const s = document.getElementById('adjAddResource');
        s.value = [...s.options].find(o => o.text.startsWith('Ordinateur reprise')).value;
        s.dispatchEvent(new Event('change'));
    """)
    check("le bouton « Reprendre un matériel déjà restitué » apparaît", wait_for(lambda: js(
        driver, "return Boolean(document.querySelector('[data-adj-addition] [data-adj-reuse]'))")))

    js(driver, "document.querySelector('[data-adj-addition] [data-adj-reuse]').click()")
    check("la fenêtre de reprise s'ouvre", wait_for(lambda: js(
        driver, "const m = document.getElementById('adjustmentReuseModal'); return Boolean(m && !m.classList.contains('d-none'))")))
    list_text = js(driver, "return document.getElementById('adjReuseList')?.innerText || ''")
    check("SN-TEST-001 est proposé dans la liste", "SN-TEST-001" in list_text, list_text[:200])

    js(driver, "document.querySelector('[data-adj-reuse-index]').click()")
    filled = js(driver, "return document.querySelector('[data-adj-addition] [data-adj-field=\"numeroSerie\"]')?.value || ''")
    check("le champ « N° de série » est rempli automatiquement (SN-TEST-001)", filled == "SN-TEST-001", filled)
    marque = js(driver, "return document.querySelector('[data-adj-addition] [data-adj-field=\"marque\"]')?.value || ''")
    check("le champ « Marque » est aussi repris (HP)", marque == "HP", marque)

    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:400])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
