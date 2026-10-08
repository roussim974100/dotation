"""Page « Comptes et droits » : groupes expliqués en français simple, tableau « Qui peut faire quoi ? » (cases à cocher, depuis que les droits sont modifiables par groupe), aucun nom technique visible.
    python tests/browser/check_groups.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

results = []


def toggleable_permissions_count():
    """Nombre de droits modifiables, lu dans le code source (sans importer l'application : un import créerait / migrerait la base du développeur)."""
    import ast
    tree = ast.parse((Path(__file__).resolve().parents[2] / "backend" / "routes" / "admin.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "TOGGLEABLE_PERMISSIONS" for t in node.targets):
            return len(getattr(node.value, "keys", None) or node.value.elts)  # dict ou ensemble
    raise RuntimeError("TOGGLEABLE_PERMISSIONS introuvable")


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


if __name__ == "__main__":
    with Instance() as inst:
        driver = inst.driver(width=1366, height=900)
        driver.get(inst.url("/admin-comptes.html"))
        time.sleep(2.5)
        cards = driver.find_elements(By.CSS_SELECTOR, "#groupCards .equipment-item")
        check("les groupes s'affichent en cartes", len(cards) >= 5, str(len(cards)))
        text = driver.find_element(By.ID, "groupCards").text
        check("chaque carte dit ce que le groupe peut faire", text.count("Ce groupe peut") == len(cards), text[:120])
        check("aucun nom technique visible (forms., users., db., unc., parc.)", not any(k in text for k in ("forms.", "users.manage", "db.manage", "unc.view", "parc.manage")), text[:200])
        check("« Lecture » est expliqué avec des mots simples", "sans rien changer" in text)
        matrix = driver.find_element(By.ID, "groupMatrix").text
        check("tableau « Qui peut faire quoi ? » présent", "Qui peut faire quoi" in matrix and "Créer un nouveau dossier" in matrix, matrix[:120])
        rows = driver.find_elements(By.CSS_SELECTOR, "#groupMatrix tbody tr")
        check(f"une ligne par droit ({toggleable_permissions_count()})", len(rows) == toggleable_permissions_count(), str(len(rows)))
        boxes = driver.find_elements(By.CSS_SELECTOR, "#groupMatrix input[type=checkbox]")
        unnamed = [b for b in boxes if not (b.get_attribute("aria-label") or driver.execute_script("return arguments[0].labels && arguments[0].labels.length", b))]
        check("une case à cocher par groupe et par droit, chacune avec un nom accessible", len(boxes) >= len(rows) and not unnamed, f"{len(boxes)} cases, {len(unnamed)} sans nom")
        page = driver.find_element(By.TAG_NAME, "body").text
        check("plus de « Groupes disponibles » ni de jargon « UNC » sans explication", "Groupes disponibles" not in page and "Accès UNC complet" not in page)
        check("pas de scroll horizontal", driver.execute_script("return document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
        check("aucune erreur JavaScript", not errors, str(errors)[:200])
    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
