"""Type de bénéficiaire avec drapeau « |mandat » : le formulaire demande le mandat pour ce type (et plus seulement pour « élu »).
Instance isolée, base vierge.
    python tests/browser/check_mandate_type.py
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
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    res = api(driver, "PUT", "/api/admin/settings", {"beneficiary_types": "agent:Agent,elu:Élu(e),conseiller:Conseiller municipal|mandat,stagiaire:Stagiaire"})
    check("types configurés enregistrés", res["status"] == 200, str(res)[:200])
    driver.get(inst.url("/form.html"))
    time.sleep(3.5)
    state = driver.execute_script("""
      const radios = [...document.querySelectorAll('input[name="qualite"]')].map(r => r.value);
      const pick = (v) => { const r = document.querySelector('input[name="qualite"][value="' + v + '"]'); if (r) { r.click(); } };
      const visible = () => { const b = document.getElementById('eluBlock'); return !!b && !b.classList.contains('d-none') && b.offsetParent !== null; };
      const out = {radios, mandate: {conseiller: isMandateType('conseiller'), stagiaire: isMandateType('stagiaire'), elu: isMandateType('elu')}};
      pick('conseiller'); out.blockForConseiller = visible();
      pick('stagiaire'); out.blockForStagiaire = visible();
      pick('elu'); out.blockForElu = visible();
      return out;""")
    check("les types configurés sont proposés dans le formulaire", {"agent", "elu", "conseiller", "stagiaire"} <= set(state["radios"]), str(state["radios"]))
    check("isMandateType suit la configuration", state["mandate"] == {"conseiller": True, "stagiaire": False, "elu": True}, str(state["mandate"]))
    check("bloc mandat affiché pour le type « conseiller » (drapeau |mandat)", state["blockForConseiller"] is True)
    check("bloc mandat masqué pour « stagiaire » (sans drapeau)", state["blockForStagiaire"] is False)
    check("bloc mandat toujours affiché pour « élu »", state["blockForElu"] is True)
    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "api/debug/logs" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:200])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
