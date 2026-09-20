"""Éditeur de champs de ressource (types liste / e-mail avec domaine, alias, aide à la saisie conservés à l'aller-retour),
ressource hors catalogue conservée à l'enregistrement d'un dossier, et refus d'enregistrer une version périmée (deux onglets).
Instance isolée, base vierge.
    python tests/browser/check_editor_and_lock.py
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


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    driver.get(inst.url("/admin-ressources.html"))
    time.sleep(2.5)
    fields = [{"key": "numero_serie", "label": "N° de série", "type": "text", "aliases": ["serial"], "placeholder": "SN-0000", "identifier": True, "required": True},
              {"key": "zones", "label": "Zones", "type": "list", "role": "variant"},
              {"key": "mail", "label": "E-mail", "type": "email_with_domain"}]
    out = driver.execute_script("""renderResourceFieldSchema(arguments[0]);
        const types = [...document.querySelectorAll('.resource-field-type')].map(s => [...s.options].map(o => o.value));
        return {collected: collectResourceFieldSchema(), types};""", fields)
    got = {f["key"]: f for f in out["collected"]}
    check("le sélecteur de type propose « liste » et « e-mail avec domaine »", all("list" in t and "email_with_domain" in t for t in out["types"]), str(out["types"][:1]))
    check("type liste conservé (ne repasse pas en « Texte »)", got.get("zones", {}).get("type") == "list")
    check("rôle du champ conservé à l'aller-retour de l'éditeur", got.get("zones", {}).get("role") == "variant" and got.get("numero_serie", {}).get("role") in ("", None), str(got.get("zones")))
    check("type e-mail avec domaine conservé", got.get("mail", {}).get("type") == "email_with_domain")
    check("alias conservés à l'aller-retour de l'éditeur", got.get("numero_serie", {}).get("aliases") == ["serial"], str(got.get("numero_serie")))
    check("aide à la saisie conservée", got.get("numero_serie", {}).get("placeholder") == "SN-0000")
    check("champ identifiant et obligatoire conservés", got.get("numero_serie", {}).get("identifier") is True and got["numero_serie"].get("required") is True)

    created = api(driver, "POST", "/api/admin/resources", {"code": "res_hors", "label": "Ressource à désactiver", "category": "materiel", "issuer_service": "DSI", "requires_return": True,
                                                            "display_order": 960, "is_active": True, "tracking_mode": "unit",
                                                            "field_schema": [{"key": "numero_serie", "label": "N° de série", "type": "text", "identifier": True, "required": True}]})
    rid = next((r["id"] for r in api(driver, "GET", "/api/admin/resources")["json"] if r["code"] == "res_hors"), None)
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "HORS", "prenom": "Catalogue", "qualite": "agent"},
            "resources": {"additional": [{"id": rid, "code": "res_hors", "label": "Ressource à désactiver", "category": "materiel", "requiresReturn": True, "selected": True,
                                          "fields": {"numero_serie": "SN-HORS-1"}, "details": ""}]}, "workflow": {"status": "draft"}, "meta": {}}
    fid = ((api(driver, "POST", "/api/forms", body)["json"] or {}).get("summary") or {}).get("id")
    row = next(r for r in api(driver, "GET", "/api/admin/resources")["json"] if r["code"] == "res_hors")
    api(driver, "PUT", f"/api/admin/resources/{rid}", dict(row, is_active=False))

    driver.get(inst.url(f"/form.html?id={fid}"))
    time.sleep(3.5)
    kept = driver.execute_script("return JSON.stringify(getAdditionalResourcesData().filter(r => r.code === 'res_hors').map(r => r.fields))")
    check("ressource désactivée : ses valeurs sont conservées à l'enregistrement du dossier", "SN-HORS-1" in kept, kept)

    # deux onglets : la version chargée devient périmée quand un autre enregistrement passe
    stale = driver.execute_script("return document.getElementById('dotationForm') ? document.getElementById('dotationForm').dataset.baseSavedAt : (document.querySelector('form') || {dataset: {}}).dataset.baseSavedAt")
    check("la version chargée est mémorisée par la page", bool(stale), str(stale))
    loaded = api(driver, "GET", f"/api/forms/{fid}")["json"]["data"]
    other = json.loads(json.dumps(loaded))
    other["meta"]["baseSavedAt"] = loaded["meta"]["savedAt"]
    other["beneficiaire"]["fonction"] = "Autre onglet"
    check("autre onglet : enregistrement accepté", api(driver, "PUT", f"/api/forms/{fid}", other)["status"] == 200)
    mine = json.loads(json.dumps(loaded))
    mine["meta"]["baseSavedAt"] = loaded["meta"]["savedAt"]
    mine["beneficiaire"]["fonction"] = "Mon onglet périmé"
    res = api(driver, "PUT", f"/api/forms/{fid}", mine)
    check("version périmée : refus 409 form_conflict", res["status"] == 409 and (res["json"] or {}).get("error") == "form_conflict", str(res))
    check("la modification de l'autre onglet n'est pas écrasée", api(driver, "GET", f"/api/forms/{fid}")["json"]["data"]["beneficiaire"]["fonction"] == "Autre onglet")
    # enregistrement réel par le bouton de la page (sans autre modification concurrente) : jamais refusé à tort
    fresh = api(driver, "POST", "/api/forms", {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "BOUTON", "prenom": "Test", "qualite": "agent", "fonction": "Avant"},
                                                "resources": {"additional": []}, "workflow": {"status": "draft"}, "meta": {}})
    fresh_id = ((fresh["json"] or {}).get("summary") or {}).get("id")
    driver.get(inst.url(f"/form.html?id={fresh_id}"))
    time.sleep(3.5)
    driver.execute_script("const f = document.getElementById('fonction'); if (f) { f.value = 'Apres le bouton'; f.dispatchEvent(new Event('input', {bubbles: true})); } document.getElementById('saveDraftBtn').click();")
    saved_ok = False
    for _ in range(30):
        time.sleep(0.5)
        try:
            saved_ok = api(driver, "GET", f"/api/forms/{fresh_id}")["json"]["data"]["beneficiaire"].get("fonction") == "Apres le bouton"
        except Exception:
            saved_ok = False
        if saved_ok:
            break
    check("bouton Enregistrer : la modification est bien enregistrée (pas de faux conflit)", saved_ok)
    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "api/debug/logs" not in e and "409" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:200])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
