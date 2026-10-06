"""3.68 (lot 1) : la cloche affiche les ressources sans service référent aux administrateurs ; le panneau s'ouvre au clavier et
se ferme avec Échap ; la fenêtre de choix rattache les ressources (suggestion pré-remplie, l'administrateur valide) ; les
titulaires d'un service se choisissent dans Admin > Services. Instance isolée, base vierge.
    python tests/browser/check_notifications.py
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


def seed_legacy_resources(inst):
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    db.execute("INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at) VALUES ('svc_dsi_e2e', 'Direction Phoenix et moyens', 1, 0, 'x', 'x')")
    for index, legacy in enumerate(("Phoenix", "Phoenix", "Ancien service inconnu")):
        db.execute("INSERT INTO resource_catalog (id, code, label, category, issuer_service, created_at, updated_at) VALUES (?,?,?,?,?, 'x', 'x')",
                   (f"res_e2e_{index}", f"e2e_{index}", f"Ressource E2E {index}", "materiel", legacy))
    db.commit()
    db.close()


def badge_count(driver):
    bell = driver.find_element("id", "notificationBell")
    return int(bell.get_attribute("data-count") or 0)


with Instance() as inst:
    driver = inst.driver()
    seed_legacy_resources(inst)

    # ---- la cloche ------------------------------------------------------------------------------------------------
    driver.get(inst.url("/index.html"))
    check("la cloche est affichée", wait_for(lambda: driver.find_elements("id", "notificationBell")))
    check("le compteur annonce une tâche", wait_for(lambda: badge_count(driver) >= 1), str(driver.find_element("id", "notificationBell").get_attribute("aria-label")))
    check("libellé accessible avec le nombre", "à traiter" in (driver.find_element("id", "notificationBell").get_attribute("aria-label") or ""))

    driver.find_element("id", "notificationBell").click()
    check("le panneau s'ouvre", wait_for(lambda: driver.find_elements("id", "notificationPanel")))
    check("la tâche est décrite", wait_for(lambda: "sans service référent" in driver.find_element("id", "notificationPanel").text), driver.find_element("id", "notificationPanel").text[:200])
    check("aria-expanded passe à vrai", driver.find_element("id", "notificationBell").get_attribute("aria-expanded") == "true")
    driver.save_screenshot(str(CAPTURES / "notif_panneau.png"))
    driver.find_element("css selector", "body").send_keys("")  # Échap
    check("Échap ferme le panneau", wait_for(lambda: not driver.find_elements("id", "notificationPanel")))
    check("le focus revient à la cloche", driver.switch_to.active_element.get_attribute("id") == "notificationBell")

    # ---- le choix de l'administrateur ----------------------------------------------------------------------------------
    driver.find_element("id", "notificationBell").click()
    wait_for(lambda: driver.find_elements("css selector", "[data-notification-run]"))
    driver.find_element("css selector", "[data-notification-run]").click()
    check("la fenêtre de choix s'ouvre", wait_for(lambda: driver.find_elements("id", "assignServicesModal")))
    selects = driver.find_elements("css selector", "#assignServicesModal select")
    check("un choix par ancien nom (regroupement)", len(selects) >= 2, str(len(selects)))
    suggested = [s.get_attribute("value") for s in selects]
    check("« Phoenix » est pré-rempli avec le seul service qui le contient (suggestion)", "svc_dsi_e2e" in suggested, str(suggested))
    check("rien n'est deviné pour un nom inconnu", "" in suggested, str(suggested))
    driver.save_screenshot(str(CAPTURES / "notif_choix.png"))

    # on valide la suggestion et on choisit un service pour le dernier groupe
    from selenium.webdriver.support.ui import Select
    for select in selects:
        if not select.get_attribute("value"):
            Select(select).select_by_value("svc_dsi_e2e")
    driver.find_element("id", "assignServicesSubmit").click()
    check("la fenêtre se ferme après validation", wait_for(lambda: not driver.find_elements("id", "assignServicesModal")))
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    rows = dict(db.execute("SELECT id, issuer_service FROM resource_catalog WHERE id LIKE 'res_e2e_%'").fetchall())
    db.close()
    check("les ressources sont rattachées au service choisi", set(rows.values()) == {"Direction Phoenix et moyens"}, str(rows))

    # ---- il ne reste rien à faire -------------------------------------------------------------------------------------
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "notificationBell"))
    driver.find_element("id", "notificationBell").click()
    # les ressources du catalogue d'origine peuvent aussi avoir un ancien nom : on vide ce qui reste
    wait_for(lambda: driver.find_elements("id", "notificationPanel"))
    if driver.find_elements("css selector", "[data-notification-run]"):
        driver.find_element("css selector", "[data-notification-run]").click()
        wait_for(lambda: driver.find_elements("id", "assignServicesModal"))
        for select in driver.find_elements("css selector", "#assignServicesModal select"):
            if not select.get_attribute("value"):
                Select(select).select_by_value("svc_dsi_e2e")
        driver.find_element("id", "assignServicesSubmit").click()
        wait_for(lambda: not driver.find_elements("id", "assignServicesModal"))
    check("plus aucune tâche : compteur à zéro", wait_for(lambda: badge_count(driver) == 0), str(badge_count(driver)))
    check("compteur masqué quand il n'y a rien", driver.find_element("css selector", ".notification-bell__count").get_attribute("hidden") is not None)

    # ---- titulaires d'un service ---------------------------------------------------------------------------------------
    driver.get(inst.url("/admin-services.html"))
    wait_for(lambda: driver.find_elements("css selector", "[data-admin-action='populateServiceForm']"))
    check("colonne « Titulaires » dans la liste", "titulaires" in driver.find_element("css selector", "#serviceTableBody").find_element("xpath", "./ancestor::table").text.lower())
    target = next(b for b in driver.find_elements("css selector", "[data-admin-action='populateServiceForm']"))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click()", target)
    check("la fenêtre du service propose les comptes", wait_for(lambda: driver.find_elements("css selector", "#modalServiceReferents input[type=checkbox]")))
    driver.save_screenshot(str(CAPTURES / "notif_titulaires.png"))
    box = driver.find_element("css selector", "#modalServiceReferents input[value='admin']")
    if not box.is_selected():
        driver.execute_script("arguments[0].click()", box)
    driver.find_element("id", "modalSaveServiceBtn").click()
    check("l'enregistrement ferme la fenêtre", wait_for(lambda: "d-none" in driver.find_element("id", "serviceEditModal").get_attribute("class")))
    check("le titulaire apparaît dans la liste", wait_for(lambda: "admin" in driver.find_element("id", "serviceTableBody").text))
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    count = db.execute("SELECT COUNT(*) FROM service_referents WHERE username = 'admin'").fetchone()[0]
    db.close()
    check("titulaire enregistré en base", count == 1, str(count))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
