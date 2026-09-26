"""3.62.1 : un mot de passe tape par erreur dans le champ « identifiant » n'apparait JAMAIS dans le journal d'administration
(ni dans l'ecran Journaux, ni dans l'API). Un identifiant de compte existant reste visible. Instance isolee, base vierge.
    python tests/browser/check_login_journal.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
SECRET = "Publier@52@26!"


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def failed_login_from_the_login_page(inst, driver, typed_username):
    """Vraie saisie dans le formulaire de connexion, session anonyme."""
    session_cookie = driver.get_cookie("publier_session")
    driver.delete_all_cookies()
    driver.get(inst.url("/login"))
    time.sleep(1.5)
    driver.find_element("id", "username").send_keys(typed_username)
    driver.find_element("id", "password").send_keys("mauvais-mot-de-passe")
    driver.find_element("css selector", "form button[type=submit]").click()
    time.sleep(2)
    driver.delete_all_cookies()
    driver.get(inst.url("/login"))
    driver.add_cookie({"name": "publier_session", "value": session_cookie["value"], "path": "/"})


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    failed_login_from_the_login_page(inst, driver, SECRET)
    failed_login_from_the_login_page(inst, driver, "admin")  # un compte qui existe (celui de l'instance de test)

    driver.get(inst.url("/logs.html"))
    time.sleep(3)
    screen_text = driver.execute_script("return document.body.innerText")
    check("l'ecran Journaux n'affiche pas la valeur saisie", SECRET not in screen_text)

    raw = driver.execute_script("return fetch('/api/admin/logs?limit=200', {credentials: 'same-origin'}).then(r => r.text())")
    check("l'API des journaux ne contient pas la valeur saisie", SECRET not in raw, raw[:200])
    entries = json.loads(raw)
    entries = entries.get("items", entries.get("logs", entries)) if isinstance(entries, dict) else entries
    failed = [e for e in entries if e.get("action_type") == "login_failed"]
    check("les deux echecs sont bien journalises", len(failed) >= 2, str(len(failed)))
    targets = {e.get("target_id") for e in failed}
    check("l'identifiant inconnu est remplace par un libelle neutre", "(identifiant inconnu)" in targets, str(targets))
    check("l'identifiant d'un compte existant reste visible", "admin" in targets, str(targets))
    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
