"""3.67.4 : une page déjà ouverte est renvoyée à la connexion dès que sa session est révoquée ailleurs (mot de passe changé,
compte désactivé), sans attendre un rechargement manuel : au retour sur l'onglet, ou dès qu'une requête reçoit un 401.
Instance isolée, base vierge ; la révocation est faite directement dans la base de l'instance.
    python tests/browser/check_session_terminee_ailleurs.py
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def wait_for(condition, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.25)
    return False


def revoke(inst, how):
    """Ce que ferait un autre navigateur : changer le mot de passe de admin, ou désactiver le compte."""
    import bcrypt
    users = sqlite3.connect(os.path.join(inst.dir, "users.db"))
    if how == "password":
        users.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (bcrypt.hashpw(b"Autre-Mot-2-Passe!", bcrypt.gensalt()).decode(),))
    else:
        users.execute("UPDATE users SET is_active = 0, status = 'disabled' WHERE username = 'admin'")
    users.commit()
    users.close()


def on_login_page(driver):
    return "/login" in driver.current_url


for scenario in ("password", "disabled"):
    with Instance() as inst:
        driver = inst.driver()
        driver.get(inst.url("/index.html"))
        check(f"[{scenario}] page ouverte avec une session valide", wait_for(lambda: driver.find_elements("id", "userMenu")) and not on_login_page(driver))
        revoke(inst, scenario)
        time.sleep(1)
        check(f"[{scenario}] sans action, la page reste affichée (aucune requête n'est partie)", not on_login_page(driver))
        driver.execute_script("window.dispatchEvent(new Event('focus'))")  # retour sur l'onglet
        check(f"[{scenario}] au retour sur l'onglet, renvoi vers la connexion", wait_for(lambda: on_login_page(driver)), driver.current_url)
        if scenario == "password":
            message = wait_for(lambda: "plus valide" in driver.find_element("tag name", "body").text)
            check("message clair sur la page de connexion", message, driver.find_element("tag name", "body").text[:200])

with Instance() as inst:
    driver = inst.driver()
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "userMenu"))
    revoke(inst, "password")
    driver.execute_script("fetch('/api/forms', {credentials: 'same-origin'})")  # n'importe quelle action de la page
    check("une requête qui reçoit un 401 renvoie vers la connexion", wait_for(lambda: on_login_page(driver)), driver.current_url)

with Instance() as inst:
    driver = inst.driver()
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "userMenu"))
    time.sleep(1)
    driver.execute_script("window.dispatchEvent(new Event('focus'))")
    time.sleep(1.5)
    check("session valide : un contrôle ne déconnecte pas", not on_login_page(driver))

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
