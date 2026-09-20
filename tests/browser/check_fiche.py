"""Affiche le contenu reel d'une fiche d'objet du Parc (historique de vie) sur une copie de la base de developpement.
    python tests/browser/check_fiche.py [numero_de_serie]"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

if __name__ == "__main__":
    serial = sys.argv[1] if len(sys.argv) > 1 else "1215240131726"
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=1366, height=1100)
        driver.get(inst.url("/parc.html"))
        time.sleep(3)
        driver.find_element(By.ID, "parcSearch").send_keys(serial)
        time.sleep(1.5)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "[data-parc-open]"))
        time.sleep(1.5)
        print(driver.find_element(By.ID, "parcModalBody").text[:1800])
        driver.save_screenshot(str(Path(inst.dir) / "fiche.png"))
        print("\n(capture :", Path(inst.dir) / "fiche.png", ")")
