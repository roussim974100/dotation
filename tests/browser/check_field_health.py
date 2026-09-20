"""Champs d'anciens dossiers (instance isolée, base vierge) : le formulaire affiche les valeurs saisies sous d'anciens noms,
garde celles sans champ correspondant (bloc « Autres informations enregistrées » + renvoyées à l'enregistrement), et la page
Base de données > Santé des champs analyse puis rattache les valeurs.
    python tests/browser/check_field_health.py
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
    schema = [{"key": "nom_du_poste", "label": "Nom du poste", "type": "text"}, {"key": "marque", "label": "Marque", "type": "text"},
              {"key": "numero_de_serie", "label": "N° de série", "type": "text", "identifier": True, "required": True}, {"key": "adresse_email", "label": "Adresse e-mail", "type": "text"}]
    created = api(driver, "POST", "/api/admin/resources", {"code": "poste_sante", "label": "Poste santé", "description": "", "category": "materiel", "issuer_service": "DSI",
                                                             "requires_return": True, "has_assignment_date": True, "display_order": 950, "is_active": True, "tracking_mode": "unit", "field_schema": schema})
    check("ressource créée", created["status"] in (200, 201), str(created)[:400])
    rid = next((r["id"] for r in api(driver, "GET", "/api/admin/resources")["json"] if r["code"] == "poste_sante"), None)
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "SANTE", "prenom": "Test", "qualite": "agent"},
            "resources": {"additional": [{"id": rid, "code": "poste_sante", "label": "Poste santé", "category": "materiel", "requiresReturn": True, "selected": True,
                                          "fields": {"marque": "HP", "nomPoste": "PC-LEGACY", "numeroSerie": "SN-LEGACY", "adresse": "legacy@exemple.fr", "champInconnuXyz": "VALEUR-SANS-CHAMP"}, "details": ""}]},
            "workflow": {"status": "draft"}, "meta": {}}
    fid = ((api(driver, "POST", "/api/forms", body)["json"] or {}).get("summary") or {}).get("id")
    check("dossier ancien créé", bool(fid))

    driver.get(inst.url(f"/form.html?id={fid}"))
    time.sleep(3.5)
    dom = driver.execute_script("""const o = {}; document.querySelectorAll('.dynamic-resource-field').forEach(e => { if (e.dataset.fieldKey) o[e.dataset.fieldKey] = e.value; });
        return {fields: o, orphans: [...document.querySelectorAll('.dynamic-resource-orphans')].map(e => e.innerText)};""")
    check("nom du poste affiché (ancien nom nomPoste)", dom["fields"].get("nom_du_poste") == "PC-LEGACY", str(dom["fields"]))
    check("numéro de série affiché (ancien nom numeroSerie)", dom["fields"].get("numero_de_serie") == "SN-LEGACY")
    check("e-mail affiché (ancien nom adresse)", dom["fields"].get("adresse_email") == "legacy@exemple.fr")
    check("valeur sans champ : bloc « Autres informations enregistrées » visible", any("VALEUR-SANS-CHAMP" in t and "Autres informations enregistrées" in t for t in dom["orphans"]), str(dom["orphans"]))
    saved = driver.execute_script("return JSON.stringify(getAdditionalResourcesData().find(r => r.code === 'poste_sante').fields)")
    check("à l'enregistrement, la valeur sans champ est conservée", "VALEUR-SANS-CHAMP" in saved and "PC-LEGACY" in saved, saved)

    driver.get(inst.url("/admin-db.html"))
    time.sleep(2.5)
    driver.execute_script("document.getElementById('fieldHealthScanBtn').click()")
    check("analyse : les anciens noms sont listés", wait_for(lambda: "nomPoste" in driver.find_element("id", "fieldHealthResult").text))
    check("bouton de rattachement affiché", driver.execute_script("return !document.getElementById('fieldHealthRepairBtn').classList.contains('d-none')"))
    driver.execute_script("document.getElementById('fieldHealthRepairBtn').click()")
    check("rattachement fait puis plus rien à rattacher", wait_for(lambda: "rattachée" in driver.find_element("id", "fieldHealthResult").text or "Aucune valeur orpheline" in driver.find_element("id", "fieldHealthResult").text))
    driver.execute_script("document.getElementById('fieldHealthScanBtn').click()")
    time.sleep(1.5)
    after = api(driver, "GET", "/api/admin/field-health")["json"]
    check("nomPoste / numeroSerie / adresse ne sont plus orphelins", not any(o["field"] in ("nomPoste", "numeroSerie", "adresse") for o in after["orphans"]), str(after)[:200])
    driver.execute_script("document.getElementById('diagPreviewBtn').click()")
    check("paquet de diagnostic : aperçu affiché avant téléchargement", wait_for(lambda: '"format": "aquai-diagnostic"' in driver.find_element("id", "diagPreview").text))
    preview_text = driver.find_element("id", "diagPreview").text
    check("paquet de diagnostic : aucune donnée de l'ancien dossier (nom, valeurs saisies)", "SANTE" not in preview_text and "SN-LEGACY" not in preview_text and "legacy@exemple.fr" not in preview_text)
    check("paquet de diagnostic : lien de téléchargement présent", driver.execute_script("return document.getElementById('diagDownloadLink').getAttribute('href')") == "/api/admin/diagnostic/download")
    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "api/debug/logs" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:200])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
