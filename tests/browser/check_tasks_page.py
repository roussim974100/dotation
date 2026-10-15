"""3.71 (lot 4) : la page « Mes tâches » liste les tâches de mon service avec leur ancienneté (« En retard » en toutes lettres),
se filtre, permet « Fait » et « Rouvrir » (un Fait enregistré par erreur), et la cloche y renvoie. Session d'un compte ordinaire
(groupe « lecture »), instance isolée, base vierge.
    python tests/browser/check_tasks_page.py
"""
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
CAPTURES = Path(tempfile.gettempdir())


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


def seed(inst):
    users = sqlite3.connect(os.path.join(inst.dir, "users.db"))
    users.execute("INSERT INTO users (username, password_hash, is_active, status, created_at, updated_at) VALUES ('elsa_e2e', 'x', 1, 'active', 'x', 'x')")
    users.execute("INSERT INTO user_groups (username, group_key) VALUES ('elsa_e2e', 'lecture')")
    users.commit()
    users.close()
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    db.execute("INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at) VALUES ('svc_dsi', 'DSI e2e', 1, 0, 'x', 'x')")
    db.execute("INSERT INTO service_referents (service_id, username, created_at) VALUES ('svc_dsi', 'elsa_e2e', 'x')")
    for code, label, category, returns in (("compte_ad", "Compte AD", "immateriel", 0), ("pc_portable", "PC portable", "materiel", 1)):
        db.execute("INSERT INTO resource_catalog (id, code, label, category, issuer_service, requires_return, created_at, updated_at) VALUES (?,?,?,?,?,?, 'x','x')",
                   (f"res_{code}", code, label, category, "DSI e2e", returns))
    recent = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    for form_id, nom, created, items in (("form_recent", "MARTIN", recent, ("compte_ad", "pc_portable")), ("form_ancien", "BERNARD", old, ("compte_ad",))):
        db.execute("INSERT INTO dotation_forms (id, title, status, nom, prenom, payload_json, created_at, updated_at) VALUES (?, 'Dossier', 'active', ?, 'Alex', '{}', ?, ?)",
                   (form_id, nom, created, created))
        for code in items:
            db.execute("INSERT INTO dotation_items (form_id, item_key, category, label, assigned, returned) VALUES (?, ?, 'x', ?, 1, 0)",
                       (form_id, code, "Compte AD" if code == "compte_ad" else "PC portable"))
    db.commit()
    db.close()


def rows(driver, container="tasksContainer"):
    return driver.find_elements("css selector", f"#{container} tbody tr")


with Instance(user="elsa_e2e", env={"APP_NOTIFICATIONS_CACHE_SECONDS": "1"}) as inst:
    seed(inst)
    driver = inst.driver()

    # ---- la cloche renvoie vers la page ----------------------------------------------------------------------------
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "notificationBell"))
    driver.find_element("id", "notificationBell").click()
    wait_for(lambda: driver.find_elements("id", "notificationPanel"))
    panel = lambda: driver.find_element("id", "notificationPanel").text  # noqa: E731
    check("la cloche annonce le retard en toutes lettres", wait_for(lambda: "en retard" in panel()), panel()[:200])
    check("lien « Tout voir » vers Mes tâches", "Tout voir" in panel())
    driver.find_element("link text", "Tout voir dans « Mes tâches »").click()
    check("on arrive sur la page Mes tâches", wait_for(lambda: "tasks.html" in driver.current_url), driver.current_url)

    # ---- la page ---------------------------------------------------------------------------------------------------
    check("trois lignes à fournir", wait_for(lambda: len(rows(driver)) == 3), str(len(rows(driver))))
    body = driver.find_element("id", "tasksContainer").text
    check("« En retard » est écrit (pas seulement une couleur)", "En retard" in body, body[:300])
    check("rien d'escaladé : le dossier de 5 jours n'a pas atteint 7 jours", "Escaladée" not in body)
    driver.save_screenshot(str(CAPTURES / "notif_lot4_page.png"))

    # ---- filtre ----------------------------------------------------------------------------------------------------
    driver.find_element("id", "tasksLateOnly").click()
    check("« Seulement en retard » ne garde qu'une ligne", wait_for(lambda: len(rows(driver)) == 1), str(len(rows(driver))))
    check("c'est la personne du dossier ancien", "BERNARD" in driver.find_element("id", "tasksContainer").text)
    driver.find_element("id", "tasksLateOnly").click()
    check("sans filtre, les trois lignes reviennent", wait_for(lambda: len(rows(driver)) == 3))

    # ---- Fait puis Rouvrir ------------------------------------------------------------------------------------------
    driver.find_element("id", "tasksLateOnly").click()
    wait_for(lambda: len(rows(driver)) == 1)
    driver.find_element("css selector", "#tasksContainer [data-done]").click()
    check("après « Fait », plus de ligne en retard", wait_for(lambda: not rows(driver)))
    driver.find_element("id", "tasksLateOnly").click()
    check("les deux autres lignes restent", wait_for(lambda: len(rows(driver)) == 2), str(len(rows(driver))))
    check("l'historique montre le Fait avec son auteur", wait_for(lambda: "elsa_e2e" in driver.find_element("id", "recentContainer").text), driver.find_element("id", "recentContainer").text[:200])
    driver.save_screenshot(str(CAPTURES / "notif_lot4_historique.png"))
    reopen = driver.find_element("css selector", "#recentContainer [data-reopen]")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click()", reopen)
    check("« Rouvrir » ramène la tâche pour tout le service", wait_for(lambda: len(rows(driver)) == 3), str(len(rows(driver))))
    check("l'historique est vide de nouveau", wait_for(lambda: "Rien de terminé" in driver.find_element("id", "recentContainer").text))

    # ---- menu -------------------------------------------------------------------------------------------------------
    links = driver.find_elements("id", "tasksLink")
    check("« Mes tâches » est dans le menu du compte", len(links) == 1 and links[0].get_attribute("href").endswith("tasks.html"))
    check("le compteur de la cloche est à jour", wait_for(lambda: int(driver.find_element("id", "notificationBell").get_attribute("data-count") or 0) >= 1))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "403" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
