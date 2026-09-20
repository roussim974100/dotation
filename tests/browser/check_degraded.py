"""Parc : un materiel restitue « degrade » doit apparaitre dans la liste (filtre « Degrade »).
Regression : un ecran saisi avec l'ancien nom de champ « numeroSerie » n'etait pas repris dans le parc.
    python tests/browser/check_degraded.py [numero_de_serie]      (copie de la base de developpement, jamais l'originale)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import Select  # noqa: E402

if __name__ == "__main__":
    serial = sys.argv[1] if len(sys.argv) > 1 else "1215240131726"
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=1366, height=1000)
        driver.get(inst.url("/parc.html"))
        time.sleep(3)
        print("objets listés (tous états) :", driver.find_element(By.ID, "parcTotal").text)
        Select(driver.find_element(By.ID, "parcStatus")).select_by_value("degraded")
        time.sleep(1.5)
        rows = driver.find_elements(By.CSS_SELECTOR, "#parcBody tr")
        print("filtre « Dégradé » :", len(rows), "ligne(s)")
        found = False
        for row in rows:
            text = row.text.replace("\n", " | ")
            print("   ", text[:140])
            found = found or serial in text
        print("=> le matériel %s est %s dans la liste" % (serial, "VISIBLE" if found else "ABSENT"))
        print("erreurs console :", inst.console_errors(driver) or "aucune")
        sys.exit(0 if found else 1)
