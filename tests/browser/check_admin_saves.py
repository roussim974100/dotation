"""Autres formulaires d'administration : chaque champ, modifié SEUL, est bien enregistré (comme pour Personnalisation).
Modale de modification d'un compte (e-mail, prénom, nom, service, gestion base de données, actif), modale d'un service (nom, actif)
et page « Mon profil » (e-mail, prénom, nom). Instance isolée, base vierge.
    python tests/browser/check_admin_saves.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.common.exceptions import NoAlertPresentException  # noqa: E402

results = []
CSRF = "jeton-navigateur"


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def api(driver, method, path, body=None):
    script = ("const [m,p,b]=arguments;return fetch(p,{method:m,credentials:'same-origin',headers:{'Content-Type':'application/json',"
              f"'X-CSRF-Token':'{CSRF}'}},body:b?JSON.stringify(b):undefined}}).then(async r=>{{let j=null;try{{j=await r.json()}}catch(e){{}};return JSON.stringify({{status:r.status,json:j}})}})")
    return json.loads(driver.execute_script(script, method, path, body))


def accept_alerts(driver):
    for _ in range(3):
        try:
            driver.switch_to.alert.accept()
            time.sleep(0.3)
        except NoAlertPresentException:
            return


def set_field(driver, element_id, value):
    driver.execute_script(
        """const el = document.getElementById(arguments[0]);
           if (el.type === 'checkbox') { el.checked = arguments[1]; } else { el.value = arguments[1]; }
           el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true}));""", element_id, value)


def wait_for(fn, tries=25):
    for _ in range(tries):
        time.sleep(0.4)
        try:
            if fn():
                return True
        except Exception:
            pass
    return False


def user(driver):
    return next((u for u in api(driver, "GET", "/api/admin/users")["json"] if u["username"] == "testuser"), {})


if __name__ == "__main__":
    with Instance() as inst:
        driver = inst.driver(width=1366, height=900)
        driver.get(inst.url("/parc.html"))
        time.sleep(1)
        service = api(driver, "POST", "/api/admin/services", {"label": "Service Test", "is_active": True})
        created = api(driver, "POST", "/api/admin/users", {"username": "testuser", "password": "Motdepasse-Test-2026!", "groups": ["user"], "is_active": True})
        check("préparation : service et compte de test créés", service["status"] in (200, 201) and created["status"] in (200, 201), f"{service['status']} / {created['status']}")

        # --- modale de modification d'un compte -----------------------------------------------------------------------------
        for element_id, key, value in [("modalAdminEmail", "email", "test@exemple.fr"), ("modalAdminFirstName", "first_name", "Paul"), ("modalAdminLastName", "last_name", "Durand"),
                                       ("modalAdminService", "service", "Service Test"), ("modalAdminDbManage", "db_manage", True), ("modalAdminActive", "status", False)]:
            driver.get(inst.url("/admin-comptes.html"))
            time.sleep(2.2)
            driver.execute_script("document.querySelector('[data-admin-action=\"populateUserForm\"][data-username=\"testuser\"]').click()")
            time.sleep(0.8)
            set_field(driver, element_id, value)
            driver.execute_script("document.getElementById('modalSaveUserBtn').click()")
            accept_alerts(driver)
            expected = {"status": "disabled"}.get(key, value) if key == "status" else value
            ok = wait_for(lambda: (user(driver).get(key) in (expected, bool(expected)) if isinstance(expected, bool) else user(driver).get(key) == expected))
            check(f"compte : {element_id} modifié SEUL → enregistré ({key})", ok, f"{key}={user(driver).get(key)!r}")

        # --- modale d'un service ---------------------------------------------------------------------------------------------
        services = api(driver, "GET", "/api/admin/services")["json"]
        service_id = next((s["id"] for s in services if s.get("label") == "Service Test"), None)
        for element_id, key, value in [("modalServiceLabel", "label", "Service Test 2"), ("modalServiceActive", "is_active", False)]:
            driver.get(inst.url("/admin-services.html"))
            time.sleep(2.2)
            driver.execute_script("document.querySelector('[data-admin-action=\"populateServiceForm\"][data-id=\"%s\"]').click()" % service_id)
            time.sleep(0.8)
            set_field(driver, element_id, value)
            driver.execute_script("document.getElementById('modalSaveServiceBtn').click()")
            accept_alerts(driver)
            def current():
                return next((s for s in api(driver, "GET", "/api/admin/services")["json"] if s["id"] == service_id), {}).get(key)
            ok = wait_for(lambda: (current() == value) or (isinstance(value, bool) and bool(current()) == value))
            check(f"service : {element_id} modifié SEUL → enregistré ({key})", ok, f"{key}={current()!r}")

        # --- Mon profil ------------------------------------------------------------------------------------------------------
        for element_id, key, value in [("acc_email", "email", "admin@exemple.fr"), ("acc_first_name", "first_name", "Samir"), ("acc_last_name", "last_name", "Test")]:
            driver.get(inst.url("/account.html"))
            time.sleep(2)
            set_field(driver, element_id, value)
            driver.execute_script("document.getElementById('accountSaveBtn').click()")
            time.sleep(0.6)
            if key in ("first_name", "last_name"):  # nom et prénom : confirmation obligatoire (ils ne seront plus modifiables par la personne)
                driver.execute_script("[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Enregistrer définitivement')?.click()")
            accept_alerts(driver)
            ok = wait_for(lambda: api(driver, "GET", "/api/account")["json"].get(key) == value)
            check(f"profil : {element_id} modifié SEUL → enregistré ({key})", ok, f"{key}={api(driver, 'GET', '/api/account')['json'].get(key)!r}")

        errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
        check("aucune erreur JavaScript", not errors, str(errors)[:200])
    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
