"""Test navigateur du Parc sur une COPIE de la base de prod : « A verifier » (lignes sans identifiant, doublons) et fusion.
    python tests/browser/check_parc.py [--merge]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

if __name__ == "__main__":
    do_merge = "--merge" in sys.argv
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=1366, height=1000)
        driver.get(inst.url("/parc.html"))
        time.sleep(3)
        print("titre :", driver.title)
        print("erreurs console :", inst.console_errors(driver) or "aucune")
        panel = driver.find_element(By.ID, "parcCheck")
        print("section « À vérifier » visible :", panel.is_displayed(), "| compteur :", driver.find_element(By.ID, "parcCheckCount").text)
        rows = driver.find_elements(By.CSS_SELECTOR, "#parcCheckBody table tbody tr")
        print("lignes sans identifiant affichées :", len(rows))
        groups = driver.find_elements(By.CSS_SELECTOR, "#parcCheckBody article")
        for g in groups:
            print("doublon probable :", " | ".join(x.text.replace("\n", " ") for x in g.find_elements(By.TAG_NAME, "li")))
        print("unités listées :", driver.find_element(By.ID, "parcTotal").text, "| section stocks visible :", driver.find_element(By.ID, "parcStock").is_displayed())
        print("import du parc visible :", driver.find_element(By.ID, "parcImport").is_displayed())
        driver.save_screenshot(str(Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path(inst.dir) / "parc.png"))
        if do_merge and groups:
            keep = groups[0].find_elements(By.CSS_SELECTOR, "[data-check-keep]")[0]
            driver.execute_script('arguments[0].scrollIntoView({block: "center"});', keep)
            time.sleep(0.4)
            driver.execute_script('arguments[0].click();', keep)
            time.sleep(1)
            driver.save_screenshot(str(Path(inst.dir) / "confirm.png"))
            buttons = [b for b in driver.find_elements(By.CSS_SELECTOR, "button") if b.is_displayed() and b.text.strip() == "Fusionner"]
            print("bouton de confirmation trouve :", bool(buttons))
            if buttons:
                driver.execute_script('arguments[0].click();', buttons[0])
                time.sleep(2.5)
                print("groupes de doublons apres fusion :", len(driver.find_elements(By.CSS_SELECTOR, "#parcCheckBody article")))
                print("unités listées après fusion :", driver.find_element(By.ID, "parcTotal").text)
                print("erreurs console :", inst.console_errors(driver) or "aucune")
