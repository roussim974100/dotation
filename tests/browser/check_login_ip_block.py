"""Blocage d'une adresse IP après 10 échecs de connexion (15 minutes) : au 11e essai, même avec le bon mot de passe, la personne voit un
message clair ; le COMPTE n'est pas touché (la liste des comptes ne montre aucun blocage) ; la connexion redevient possible à la fin du
blocage (simulée en vidant le compteur). Instance isolée, base vierge.
    python tests/browser/check_login_ip_block.py
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcrypt  # noqa: E402
from browser_harness import Instance  # noqa: E402

results = []
BON = "Mot-2-Passe-Adresse1!"


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


def echecs_en_rafale(driver, inst, username, nombre):
    """`nombre` mots de passe faux, envoyés comme le ferait la page de connexion (jeton CSRF de la session)."""
    driver.delete_all_cookies()
    driver.get(inst.url("/login"))
    wait_for(lambda: driver.find_elements("id", "username"))
    time.sleep(1)
    return driver.execute_async_script(
        """const [username, nombre, done] = arguments;
           (async () => {
             const token = (await (await fetch('/api/csrf-token', {credentials: 'same-origin'})).json()).token;
             const sorties = [];
             for (let i = 0; i < nombre; i++) {
               const body = new URLSearchParams({username, password: 'mauvais', csrf_token: token});
               const r = await fetch('/login', {method: 'POST', body, redirect: 'manual', credentials: 'same-origin'});
               sorties.push(r.type);
             }
             done(sorties.length);
           })();""", username, nombre)


with Instance() as inst:
    users = sqlite3.connect(os.path.join(inst.dir, "users.db"))
    users.execute("INSERT INTO users (username, password_hash, is_active, status, created_at, updated_at) VALUES ('cible_e2e', ?, 1, 'active', 'x', 'x')",
                  (bcrypt.hashpw(BON.encode(), bcrypt.gensalt()).decode(),))
    users.execute("INSERT INTO user_groups (username, group_key) VALUES ('cible_e2e', 'lecture')")
    users.commit()
    users.close()

    admin = inst.driver()
    visitor = inst.driver(with_session=False)

    # ---- avant le seuil : rien n'est bloqué -------------------------------------------------------------------------------
    check("9 échecs envoyés", echecs_en_rafale(visitor, inst, "cible_e2e", 9) == 9)
    se_connecter(visitor, inst, "cible_e2e", BON)
    check("avec 9 échecs, le bon mot de passe passe encore", "/login" not in visitor.current_url, visitor.current_url)

    # ---- 10 échecs : l'adresse est bloquée ---------------------------------------------------------------------------------
    check("10 échecs envoyés", echecs_en_rafale(visitor, inst, "cible_e2e", 10) == 10)
    se_connecter(visitor, inst, "cible_e2e", BON)
    check("au 11e essai, même avec le bon mot de passe, la connexion est refusée", "rate_limited" in visitor.current_url, visitor.current_url)
    check("le message dit pourquoi et combien de temps", wait_for(lambda: "15 minutes" in visitor.find_element("tag name", "body").text and "cette adresse" in visitor.find_element("tag name", "body").text),
          visitor.find_element("tag name", "body").text[:300])

    # ---- le compte n'est pas touché --------------------------------------------------------------------------------------
    admin.get(inst.url("/admin-comptes.html"))
    row = lambda: next(r for r in admin.find_elements("css selector", "#userTableBody tr") if "cible_e2e" in r.text)  # noqa: E731
    check("la liste des comptes ne montre aucun blocage pour ce compte", wait_for(lambda: "cible_e2e" in row().text) and "bloqu" not in row().text.lower(), row().text if admin.find_elements("css selector", "#userTableBody tr") else "")
    check("aucune action « Débloquer » n'existe plus", not admin.find_elements("css selector", "[data-admin-action='unlockUser']"))

    # ---- fin du blocage ------------------------------------------------------------------------------------------------
    db = sqlite3.connect(os.path.join(inst.dir, "users.db"))
    db.execute("DELETE FROM rate_limit_hits WHERE scope IN ('login_ip_block', 'login_fail_ip')")  # = les 15 minutes sont écoulées
    db.commit()
    db.close()
    se_connecter(visitor, inst, "cible_e2e", BON)
    check("une fois le blocage terminé, la connexion refonctionne", "/login" not in visitor.current_url, visitor.current_url)

    errors = [e for e in inst.console_errors(admin) if "favicon" not in e]
    check("aucune erreur JavaScript (administrateur)", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
