"""(Désactivé par défaut depuis le 08/10/2026 ; activé ici par APP_LOGIN_ACCOUNT_MAX_FAILURES.)
Verrouillage temporaire par compte : la personne bloquée voit un message clair sur la page de connexion ; l'administrateur voit
« Connexion bloquée » dans la liste des comptes et la lève (« Débloquer la connexion ») ; la personne se connecte ensuite.
Instance isolée, base vierge ; les échecs sont posés directement dans le compteur de l'instance.
    python tests/browser/check_login_lock.py
"""
import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcrypt  # noqa: E402
from browser_harness import Instance  # noqa: E402

results = []
BON = "Mot-2-Passe-Bloque1!"


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def wait_for(condition, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if condition():
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def se_connecter(driver, inst, username, password):
    driver.delete_all_cookies()
    driver.get(inst.url("/login"))
    wait_for(lambda: driver.find_elements("id", "username"))
    time.sleep(1)
    driver.find_element("id", "username").send_keys(username)
    driver.find_element("id", "password").send_keys(password)
    driver.find_element("css selector", "form button[type=submit]").click()
    time.sleep(2)


with Instance(env={"APP_LOGIN_ACCOUNT_MAX_FAILURES": "5"}) as inst:  # désactivé par défaut : on l'active pour cette instance
    users = sqlite3.connect(os.path.join(inst.dir, "users.db"))
    users.execute("INSERT INTO users (username, password_hash, is_active, status, created_at, updated_at) VALUES ('bloque_e2e', ?, 1, 'active', 'x', 'x')",
                  (bcrypt.hashpw(BON.encode(), bcrypt.gensalt()).decode(),))
    users.execute("INSERT INTO user_groups (username, group_key) VALUES ('bloque_e2e', 'lecture')")
    users.execute("CREATE TABLE IF NOT EXISTS rate_limit_hits (scope TEXT NOT NULL, key TEXT NOT NULL, ts REAL NOT NULL)")
    key = hashlib.sha256(b"bloque_e2e").hexdigest()[:24]
    for _ in range(5):
        users.execute("INSERT INTO rate_limit_hits (scope, key, ts) VALUES ('login_fail_account', ?, ?)", (key, time.time()))
    users.commit()
    users.close()

    admin = inst.driver()
    visitor = inst.driver(with_session=False)

    # ---- la personne bloquée --------------------------------------------------------------------------------------------
    se_connecter(visitor, inst, "bloque_e2e", BON)
    check("même avec le bon mot de passe, la connexion est refusée", "/login" in visitor.current_url and "account_locked" in visitor.current_url, visitor.current_url)
    check("le message dit pourquoi et quoi faire", wait_for(lambda: "Trop d'échecs" in visitor.find_element("tag name", "body").text), visitor.find_element("tag name", "body").text[:300])

    # ---- l'administrateur ------------------------------------------------------------------------------------------------
    admin.get(inst.url("/admin-comptes.html"))
    row = lambda: next(r for r in admin.find_elements("css selector", "#userTableBody tr") if "bloque_e2e" in r.text)  # noqa: E731
    check("la liste signale « Connexion bloquée »", wait_for(lambda: "Connexion bloquée" in row().text), row().text if admin.find_elements("css selector", "#userTableBody tr") else "")
    admin.execute_script("arguments[0].scrollIntoView({block: 'center'})", row())
    menu = row().find_element("css selector", "details.draft-actions__menu summary")
    admin.execute_script("arguments[0].click()", menu)
    unlock = wait_for(lambda: row().find_elements("css selector", "[data-admin-action='unlockUser']"))
    check("l'action « Débloquer la connexion » est proposée", unlock)
    admin.execute_script("arguments[0].click()", row().find_element("css selector", "[data-admin-action='unlockUser']"))
    check("après déblocage, le marquage disparaît", wait_for(lambda: "Connexion bloquée" not in row().text))

    # ---- la personne se connecte ----------------------------------------------------------------------------------------
    se_connecter(visitor, inst, "bloque_e2e", BON)
    check("la personne peut se connecter", "/login" not in visitor.current_url, visitor.current_url)

    errors = [e for e in inst.console_errors(admin) if "favicon" not in e]
    check("aucune erreur JavaScript (administrateur)", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
