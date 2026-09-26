"""3.65.0 : interface d'ajustement d'un dossier actif, dans un vrai navigateur : bouton dans la liste et sur la fiche, fenetre
(retirer / ajouter / service / signature manuscrite reelle), refus affiches, signature a distance puis recueillie, historique sur
la fiche, « Mise a jour » retire du selecteur de creation mais dossiers existants ouvrables. Instance isolee, base vierge.
    python tests/browser/check_adjustment_ui.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver import ActionChains  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

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


def draw_signature(driver, canvas_id):
    canvas = driver.find_element(By.ID, canvas_id)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", canvas)
    time.sleep(0.3)
    actions = ActionChains(driver)
    actions.move_to_element_with_offset(canvas, 40, 40).click_and_hold().move_by_offset(60, 20).move_by_offset(40, -30).move_by_offset(30, 25).release()
    actions.perform()


def modal_open(driver):
    return js(driver, "const m = document.getElementById('adjustmentModal'); return Boolean(m && !m.classList.contains('d-none'))")


def open_menu_and_click(driver, action):
    return js(driver, """const b = document.querySelector('[data-action="%s"]'); if (!b) return false; b.click(); return true""" % action)


with Instance() as inst:
    driver = inst.driver(width=1366, height=1000)
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    for code, label in (("poste_ui", "Poste UI"), ("casque_ui", "Casque UI")):
        api(driver, "POST", "/api/admin/resources", {
            "code": code, "label": label, "description": "", "category": "materiel", "issuer_service": "DSI", "requires_return": True,
            "has_assignment_date": False, "has_assignment_condition": False, "has_assignment_notes": False, "display_order": 990, "is_active": True,
            "field_schema": [{"key": "marque", "label": "Marque", "type": "text", "required": True}]})
    catalog = {r["code"]: r for r in api(driver, "GET", "/api/admin/resources")["json"]}
    poste = catalog["poste_ui"]
    created = api(driver, "POST", "/api/forms", {
        "dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "AJUSTUI", "prenom": "Test", "qualite": "agent", "service": "DRH"},
        "resources": {"additional": [{"id": poste["id"], "code": "poste_ui", "label": "Poste UI", "category": "materiel", "requiresReturn": True,
                                      "selected": True, "fieldSchema": poste.get("field_schema") or [], "fields": {"marque": "Dell"}, "details": "",
                                      "assignedAt": "2026-09-01T09:00:00"}]},
        "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}})
    form_id = (created["json"].get("summary") or {}).get("id")
    check("dossier actif créé", created["status"] in (200, 201) and form_id, str(created)[:200])

    # ── Liste : bouton, fenêtre, refus affiché ──
    driver.get(inst.url("/assignments-completed.html"))
    check("la liste affiche le dossier", wait_for(lambda: "AJUSTUI" in js(driver, "return document.body.innerText").upper()))
    check("le bouton « Ajuster » est proposé dans le menu du dossier", js(driver, "return Boolean(document.querySelector('[data-action=\"openAdjustment\"]'))"))
    open_menu_and_click(driver, "openAdjustment")
    check("la fenêtre d'ajustement s'ouvre", wait_for(lambda: modal_open(driver)))
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("un ajustement vide est refusé avec un message", wait_for(lambda: "Rien à ajuster" in js(driver, "return document.getElementById('adjustmentError').textContent")))

    js(driver, "document.querySelector('[data-adj-withdraw=\"poste_ui\"]').click()")
    js(driver, "const s = document.getElementById('adjAddResource'); s.value = [...s.options].find(o => o.text.startsWith('Casque UI')).value; s.dispatchEvent(new Event('change'))")
    check("le bloc de la ressource ajoutée apparaît avec son champ obligatoire", wait_for(lambda: js(driver, "return Boolean(document.querySelector('[data-adj-addition] [data-adj-field=\"marque\"]'))")))
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("un champ obligatoire vide est refusé", wait_for(lambda: "Marque" in js(driver, "return document.getElementById('adjustmentError').textContent")),
          js(driver, "return document.getElementById('adjustmentError').textContent"))
    js(driver, "document.querySelector('[data-adj-addition] [data-adj-field=\"marque\"]').value = 'Jabra'")
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("sans signature dessinée, le mode présentiel est refusé", wait_for(lambda: "obligatoire" in js(driver, "return document.getElementById('adjustmentError').textContent")),
          js(driver, "return document.getElementById('adjustmentError').textContent"))
    js(driver, "document.getElementById('adjSig_mode_impossible').click()")
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("« signature impossible » sans motif est refusée", wait_for(lambda: "impossible" in js(driver, "return document.getElementById('adjustmentError').textContent").lower()),
          js(driver, "return document.getElementById('adjustmentError').textContent"))
    js(driver, "document.getElementById('adjSig_reason').value = 'absent'")
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("« signature impossible » sans nom de responsable est refusée", wait_for(lambda: "responsable" in js(driver, "return document.getElementById('adjustmentError').textContent").lower()))
    js(driver, "document.getElementById('adjSig_mode_presentiel').click()")
    time.sleep(0.5)
    draw_signature(driver, "adjSig_canvas")
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("l'ajustement est enregistré et la fenêtre se ferme", wait_for(lambda: not modal_open(driver)))

    stored = api(driver, "GET", f"/api/forms/{form_id}")["json"]
    data = stored["data"]
    events = data.get("ajustements") or []
    check("un événement signé est enregistré", len(events) == 1 and events[0]["status"] == "signed", str(events)[:300])
    check("la signature dessinée est bien une image", (events[0]["signature"].get("signatureDataUrl") or "").startswith("data:image/png") if events else False)
    check("retrait et ajout sont enregistrés", data["restitution"]["items"]["poste_ui"]["state"] == "conforme"
          and {r["code"] for r in data["resources"]["additional"]} == {"poste_ui", "casque_ui"})
    check("le dossier reste actif", stored["summary"]["status"] == "active")

    # ── Mode « à distance » puis signature recueillie ──
    time.sleep(1)
    open_menu_and_click(driver, "openAdjustment")
    check("la fenêtre se rouvre avec l'historique", wait_for(lambda: modal_open(driver) and "historique des ajustements" in js(driver, "return document.getElementById('adjustmentModal').innerText").lower()))
    js(driver, "document.querySelector('[data-adj-withdraw=\"casque_ui\"]').click()")
    js(driver, "document.getElementById('adjSig_mode_distance').click()")
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("l'ajustement à distance est enregistré « en attente »", wait_for(lambda: not modal_open(driver)))
    pending = [e for e in api(driver, "GET", f"/api/forms/{form_id}")["json"]["data"]["ajustements"] if e["status"] == "pending_signature"]
    check("un ajustement est en attente de signature", len(pending) == 1)
    driver.get(inst.url("/assignments-completed.html"))
    check("le menu propose de signer l'ajustement en attente", wait_for(lambda: js(driver, "return Boolean(document.querySelector('[data-action=\"openAdjustmentSignature\"]'))")))
    open_menu_and_click(driver, "openAdjustmentSignature")
    check("la fenêtre de signature s'ouvre", wait_for(lambda: modal_open(driver) and js(driver, "return Boolean(document.getElementById('adjSign_canvas'))")))
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("sans signature, la demande est refusée", wait_for(lambda: "signature" in js(driver, "return document.getElementById('adjustmentError').textContent").lower()))
    draw_signature(driver, "adjSign_canvas")
    js(driver, "document.getElementById('adjustmentSubmit').click()")
    check("la signature est recueillie", wait_for(lambda: not modal_open(driver)))
    statuses = [e["status"] for e in api(driver, "GET", f"/api/forms/{form_id}")["json"]["data"]["ajustements"]]
    check("les deux ajustements sont signés", statuses == ["signed", "signed"], str(statuses))

    # ── Fiche : bouton, historique ──
    driver.get(inst.url(f"/form.html?id={form_id}"))
    time.sleep(3.5)
    labels = js(driver, "return [...document.querySelectorAll('.action-bar__buttons [data-locked-action]')].map(b => b.textContent.trim())")
    check("la fiche propose « Ajuster »", "Ajuster" in labels, str(labels))
    check("la fiche affiche l'historique des ajustements", "historique des ajustements" in js(driver, "return document.getElementById('ajustementsHistory').innerText").lower())

    # ── Sélecteur de création ──
    driver.get(inst.url("/form.html"))
    time.sleep(3)
    options = js(driver, "return [...document.querySelectorAll('#dossier_type option')].map(o => o.value)")
    check("« Mise à jour de ressources » n'est plus proposé à la création", "mise_a_jour" not in options and "arrivee" in options, str(options))
    legacy = api(driver, "POST", "/api/forms", {"dossier": {"type": "mise_a_jour", "sourceFormId": form_id}, "beneficiaire": {"nom": "AJUSTUI", "prenom": "Test", "qualite": "agent"},
                                                "resources": {"additional": []}, "retraits": {"items": {}}, "workflow": {"status": "draft"}, "meta": {}})
    legacy_id = (legacy["json"].get("summary") or {}).get("id")
    driver.get(inst.url(f"/form.html?id={legacy_id}"))
    time.sleep(3.5)
    check("un dossier « mise à jour » existant reste ouvrable avec son type",
          js(driver, "return document.getElementById('dossier_type').value") == "mise_a_jour")

    # ── Droit : sans forms.adjust, aucun bouton ──
    driver.get(inst.url("/assignments-completed.html"))
    wait_for(lambda: "AJUSTUI" in js(driver, "return document.body.innerText").upper())
    js(driver, "sessionInfo = {...sessionInfo, permissions: sessionInfo.permissions.filter(p => p !== '*' && p !== 'forms.adjust').concat(['forms.read_list', 'forms.read_detail'])}; void renderDraftList();")
    time.sleep(2)
    check("sans le droit d'ajuster, le bouton disparaît", not js(driver, "return Boolean(document.querySelector('[data-action=\"openAdjustment\"]'))"))

    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:400])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
