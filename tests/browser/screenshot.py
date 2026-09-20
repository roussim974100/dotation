"""Capture d'ecran d'une page a une largeur donnee (instance isolee, copie de la base) : screenshot.py <largeur> <page> <fichier.png>"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

if __name__ == "__main__":
    width, page, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=width, height=height)
        driver.get(inst.url(page))
        time.sleep(2.5)
        driver.save_screenshot(out)
        print("capture :", out)
