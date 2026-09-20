"""Test navigateur des STOCKS par quantite sur une base VIERGE (instance isolee) :
creation d'une ressource « quantite », reception, seuil, ajustement, historique, import d'inventaire CSV.
    python tests/browser/check_stock.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def click(driver, css):
    element = driver.find_element(By.CSS_SELECTOR, css)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    driver.execute_script("arguments[0].click();", element)
    time.sleep(0.6)


def fill(driver, element_id, value):
    element = driver.find_element(By.ID, element_id)
    element.clear()
    element.send_keys(value)


def stock_text(driver):
    return driver.find_element(By.ID, "parcStockBody").text


def open_dialog(driver, kind, code):
    click(driver, f'[data-stock-kind="{kind}"][data-stock-code="{code}"]')


def submit_dialog(driver):
    click(driver, "[data-stock-submit]")
    time.sleep(1.2)


if __name__ == "__main__":
    with Instance() as inst:
        driver = inst.driver(width=1366, height=1000)
        driver.get(inst.url("/parc.html"))
        time.sleep(2)
        check("section Stocks masquee tant qu'aucune ressource « quantité » n'existe", not driver.find_element(By.ID, "parcStock").is_displayed())

        payload = {
            "code": "polo", "label": "Polo", "description": "", "category": "materiel", "issuer_service": "Ressources humaines",
            "requires_return": True, "has_assignment_date": True, "has_assignment_condition": True, "has_assignment_notes": True,
            "display_order": 10, "is_active": True, "tracking_mode": "quantity",
            "field_schema": [{"key": "quantite", "label": "Quantité", "type": "number", "required": True},
                             {"key": "taille", "label": "Taille", "type": "text", "required": False}],
        }
        created = driver.execute_script(
            "return fetch('/api/admin/resources', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRF-Token':'jeton-navigateur'}, body: arguments[0]}).then(r => r.status)",
            json.dumps(payload))
        check("ressource « Polo » (suivi par quantité) créée", created in (200, 201), created)

        driver.get(inst.url("/parc.html"))
        time.sleep(2.5)
        check("section Stocks visible", driver.find_element(By.ID, "parcStock").is_displayed())
        check("la carte « Polo » est affichée avec 0 en stock", "Polo" in stock_text(driver) and "0 en stock" in stock_text(driver), stock_text(driver)[:120])

        # Reception : 10 en taille M
        open_dialog(driver, "receipt", "polo")
        fill(driver, "stockVariant", "M")
        fill(driver, "stockQuantity", "10")
        submit_dialog(driver)
        check("réception de 10 (taille M)", "10 en stock" in stock_text(driver) and "M" in stock_text(driver), stock_text(driver)[:160])

        # Seuil 5
        click(driver, '[data-stock-threshold="polo"]')
        fill(driver, "stockThreshold", "5")
        submit_dialog(driver)
        check("seuil d'alerte enregistré", "seuil d'alerte 5" in stock_text(driver), stock_text(driver)[:200])
        check("pas d'alerte tant que le stock est au-dessus du seuil", "Stock bas" not in stock_text(driver))

        # Ajustement sans note : refuse ; puis -6 avec note -> stock bas
        open_dialog(driver, "adjustment", "polo")
        fill(driver, "stockVariant", "M")
        fill(driver, "stockQuantity", "-6")
        click(driver, "[data-stock-submit]")
        error = driver.find_element(By.ID, "stockError")
        check("ajustement sans note refusé avec un message", error.is_displayed() and "note" in error.text.lower(), error.text)
        fill(driver, "stockNote", "casse constatée à l'inventaire")
        submit_dialog(driver)
        check("après l'ajustement de -6 : 4 en stock et alerte « Stock bas »", "4 en stock" in stock_text(driver) and "Stock bas" in stock_text(driver), stock_text(driver)[:200])

        # Historique
        click(driver, '[data-stock-history="polo"]')
        time.sleep(1)
        rows = driver.find_elements(By.CSS_SELECTOR, "#stockModalBody tbody tr")
        check("historique : 2 mouvements (réception, ajustement)", len(rows) == 2, len(rows))
        click(driver, '[data-stock-close="true"].btn')

        # Import d'inventaire CSV
        csv_file = Path(tempfile.mkdtemp()) / "inventaire.csv"
        csv_file.write_text("ressource;taille;quantite;note\nPolo;M;9;inventaire annuel\nPolo;L;3;\n", encoding="utf-8")
        driver.execute_script("document.getElementById('stockImport').open = true;")
        driver.find_element(By.ID, "stockImportFile").send_keys(str(csv_file))
        click(driver, "#stockImportCheck")
        time.sleep(1.2)
        result = driver.find_element(By.ID, "stockImportResult").text
        check("analyse à blanc : 2 lignes à ajuster", "2 à ajuster" in result and "0 erreur" in result, result)
        check("l'analyse n'a rien modifié (toujours 4 en stock)", "4 en stock" in stock_text(driver))
        click(driver, "#stockImportRun")
        time.sleep(1)
        confirm = [b for b in driver.find_elements(By.CSS_SELECTOR, "button") if b.is_displayed() and b.text.strip() == "Importer"]
        if confirm:
            driver.execute_script("arguments[0].click();", confirm[-1])
        time.sleep(2)
        check("après l'import : 12 en stock (M=9, L=3)", "12 en stock" in stock_text(driver), stock_text(driver)[:200])

        # Reimport du meme fichier : idempotent
        driver.find_element(By.ID, "stockImportFile").send_keys(str(csv_file))
        click(driver, "#stockImportCheck")
        time.sleep(1.2)
        result = driver.find_element(By.ID, "stockImportResult").text
        check("réimport du même fichier : 0 à ajuster, 2 déjà à jour", "0 à ajuster" in result and "2 déjà à jour" in result, result)

        errors = inst.console_errors(driver)
        check("aucune erreur dans la console du navigateur", not errors, errors[:2])
        driver.save_screenshot(str(Path(inst.dir) / "stock.png"))
        print("\n%d/%d vérifications réussies" % (sum(results), len(results)))
        sys.exit(0 if all(results) else 1)
