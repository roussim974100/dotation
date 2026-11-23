"""3.70 (lot 2) : un titulaire de service voit les ressources à fournir pour un dossier actif, les marque « Fait » (elles
disparaissent), puis la restitution du dossier fait apparaître la ressource à fermer. Session d'un compte ordinaire (groupe
« lecture »), instance isolée, base vierge ; dossiers et service créés directement dans la base de l'instance.
    python tests/browser/check_service_tasks.py
"""
import os
import sqlite3
import sys
import tempfile
import time
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
    db.execute("INSERT INTO dotation_forms (id, title, status, nom, prenom, payload_json, created_at, updated_at) VALUES ('form_e2e', 'Dossier', 'active', 'MARTIN', 'Claire', '{}', '2026-10-01T09:00:00', '2026-10-01T09:00:00')")
    for code, label, category in (("compte_ad", "Compte AD", "immateriel"), ("pc_portable", "PC portable", "materiel")):
        db.execute("INSERT INTO dotation_items (form_id, item_key, category, label, assigned, returned) VALUES ('form_e2e', ?, ?, ?, 1, 0)", (code, category, label))
    db.commit()
    db.close()


def set_status(inst, status):
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    db.execute("UPDATE dotation_forms SET status = ? WHERE id = 'form_e2e'", (status,))
    db.commit()
    db.close()


def badge(driver):
    return int(driver.find_element("id", "notificationBell").get_attribute("data-count") or 0)


def open_list(driver):
    driver.find_element("id", "notificationBell").click()
    wait_for(lambda: driver.find_elements("css selector", "[data-notification-run]"))
    driver.find_element("css selector", "[data-notification-run]").click()
    return wait_for(lambda: driver.find_elements("id", "serviceTasksModal"))


with Instance(user="elsa_e2e", env={"APP_NOTIFICATIONS_CACHE_SECONDS": "1"}) as inst:  # des changements faits directement en base ne passent pas par persist_form
    seed(inst)
    driver = inst.driver()

    # ---- à fournir ------------------------------------------------------------------------------------------------
    driver.get(inst.url("/index.html"))
    check("la cloche est affichée pour un compte ordinaire", wait_for(lambda: driver.find_elements("id", "notificationBell")))
    check("une tâche à traiter", wait_for(lambda: badge(driver) == 1), str(badge(driver)))
    driver.find_element("id", "notificationBell").click()
    wait_for(lambda: driver.find_elements("id", "notificationPanel"))
    check("« 2 ressources à fournir »", wait_for(lambda: "2 ressources à fournir" in driver.find_element("id", "notificationPanel").text), driver.find_element("id", "notificationPanel").text[:200])
    driver.find_element("css selector", "[data-notification-run]").click()
    check("la liste s'ouvre", wait_for(lambda: driver.find_elements("id", "serviceTasksModal")))
    text = driver.find_element("id", "serviceTasksModal").text
    check("la personne, la ressource et le service sont affichés", "MARTIN Claire" in text and "Compte AD" in text and "PC portable" in text and "DSI e2e" in text, text[:300])
    links = [a.get_attribute("href") for a in driver.find_elements("link text", "Ouvrir le dossier")]
    check("lien vers le dossier (le groupe « lecture » peut le lire)", len(links) == 2 and all(h.endswith("form.html?id=form_e2e") for h in links), str(links))
    driver.save_screenshot(str(CAPTURES / "notif_lot2_liste.png"))

    driver.find_elements("css selector", "#serviceTasksModal [data-done]")[0].click()
    check("une ligne disparaît après « Fait »", wait_for(lambda: len(driver.find_elements("css selector", "#serviceTasksModal tbody tr")) == 1))
    driver.find_elements("css selector", "#serviceTasksModal [data-done]")[0].click()
    check("la fenêtre se ferme quand il ne reste rien", wait_for(lambda: not driver.find_elements("id", "serviceTasksModal")))
    check("le compteur tombe à zéro", wait_for(lambda: badge(driver) == 0), str(badge(driver)))
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    rows = db.execute("SELECT kind, item_key, done_by FROM service_task_done WHERE done_by IS NOT NULL ORDER BY item_key").fetchall()
    db.close()
    check("qui a fait quoi est enregistré", rows == [("provision", "compte_ad", "elsa_e2e"), ("provision", "pc_portable", "elsa_e2e")], str(rows))

    # ---- à fermer ---------------------------------------------------------------------------------------------------
    set_status(inst, "partial_return")
    time.sleep(1.5)  # le cache des tâches est de 1 s dans cette instance de test
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "notificationBell"))
    check("la restitution crée une tâche à fermer", wait_for(lambda: badge(driver) == 1), str(badge(driver)))
    check("la liste s'ouvre", open_list(driver))
    text = driver.find_element("id", "serviceTasksModal").text
    check("seul le compte est à fermer (le matériel est suivi par la restitution)", "Compte AD" in text and "PC portable" not in text, text[:300])
    driver.find_element("css selector", "#serviceTasksModal [data-done]").click()
    check("après « Fait », plus rien à faire", wait_for(lambda: badge(driver) == 0 and not driver.find_elements("id", "serviceTasksModal")))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "403" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
