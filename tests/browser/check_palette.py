"""Palette Ctrl+K : pages et actions atteignables au clavier (en plus des dossiers), liens profonds, aucune action exécutée.
    python tests/browser/check_palette.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.common.action_chains import ActionChains  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def open_palette(driver):
    ActionChains(driver).key_down(Keys.CONTROL).send_keys("k").key_up(Keys.CONTROL).perform()
    time.sleep(0.8)


def rows(driver):
    return [e.text.split("\n")[0] for e in driver.find_elements(By.CSS_SELECTOR, "#globalSearchResults .global-search__result")]


def type_query(driver, text):
    box = driver.find_element(By.ID, "globalSearchInput")
    box.clear()
    box.send_keys(text)
    time.sleep(1.2)


if __name__ == "__main__":
    with Instance() as inst:
        driver = inst.driver(width=1366, height=900)
        driver.get(inst.url("/index.html"))
        time.sleep(2)
        open_palette(driver)
        check("Ctrl+K ouvre la palette", driver.find_element(By.ID, "globalSearchModal").is_displayed())
        default = rows(driver)
        check("sans saisie : raccourcis proposés (Nouvelle attribution, Administration, sauvegarde…)", "Nouvelle attribution" in default and "Administration" in default and "Sauvegarder maintenant" in default, str(default))

        type_query(driver, "sauveg")
        found = rows(driver)
        check("« sauveg » propose « Sauvegarder maintenant » en premier", found[:1] == ["Sauvegarder maintenant"], str(found))
        check("recherche insensible aux accents (« synthese » → Synthèse)", (type_query(driver, "synthese"), "Synthèse" in rows(driver))[1], str(rows(driver)))
        type_query(driver, "logo")
        check("mot-clé « logo » → Personnalisation", "Personnalisation" in rows(driver), str(rows(driver)))
        type_query(driver, "zzzz-inexistant")
        check("aucune commande pour un mot inconnu", not [r for r in rows(driver) if r in ("Journal", "Parc matériel")], str(rows(driver)))

        type_query(driver, "restaurer")
        driver.find_element(By.ID, "globalSearchInput").send_keys(Keys.ENTER)
        time.sleep(2)
        check("Entrée ouvre la page cible sans rien exécuter (admin-db.html#db-restore)", driver.current_url.endswith("admin-db.html#db-restore"), driver.current_url)

        driver.get(inst.url("/admin-ressources.html"))
        time.sleep(2)
        open_palette(driver)
        type_query(driver, "ajouter une ressource")
        driver.find_element(By.ID, "globalSearchInput").send_keys(Keys.ENTER)
        time.sleep(2.5)
        check("« Ajouter une ressource » ouvre l'assistant de création (lien profond #new)", driver.find_element(By.ID, "resourceWizardModal").is_displayed())
        errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
        check("aucune erreur JavaScript", not errors, str(errors)[:200])
    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
