"""Test navigateur de l'ASSISTANT D'ORGANISATION sur une base VIERGE (instance isolee) :
parcours des 5 etapes, suggestions, apercu, confirmation, application, idempotence, pas de scroll horizontal.
    python tests/browser/check_org_wizard.py
"""
import sys
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
    time.sleep(0.5)


def body(driver):
    return driver.find_element(By.ID, "orgWzBody").text


if __name__ == "__main__":
    with Instance() as inst:
        driver = inst.driver(width=1366, height=1000)
        driver.get(inst.url("/admin.html"))
        time.sleep(2)
        checklist = driver.find_element(By.ID, "startupChecklist")
        check("portail admin : checklist de démarrage visible sur une base neuve", checklist.is_displayed() and "Configuration" in checklist.text, checklist.text[:120])
        check("... avec un lien vers l'assistant", bool(checklist.find_elements(By.CSS_SELECTOR, 'a[href="admin-personnalisation.html?wizard=1"]')))
        driver.get(inst.url("/admin-personnalisation.html?wizard=1"))
        time.sleep(2)
        check("?wizard=1 ouvre l'assistant directement", driver.find_element(By.ID, "orgWizardModal").is_displayed())
        driver.get(inst.url("/admin-personnalisation.html"))
        time.sleep(2)
        click(driver, "[data-open-org-wizard]")
        time.sleep(1)
        modal = driver.find_element(By.ID, "orgWizardModal")
        check("l'assistant s'ouvre", modal.is_displayed())
        check("5 étapes affichées", len(driver.find_elements(By.CSS_SELECTOR, "#orgWzProgress li")) == 5)
        check("5 types d'organisation proposés, dont « Autre »", len(driver.find_elements(By.NAME, "orgWzContext")) == 5 and "Autre" in body(driver))

        click(driver, 'input[name="orgWzContext"][value="association"]')
        driver.find_element(By.ID, "orgWzName").send_keys("Association Test")
        click(driver, "#orgWzNext")
        check("étape 2 : types de l'association pré-remplis", driver.find_element(By.CSS_SELECTOR, '[data-type-row="1"] [data-type-field="value"]').get_attribute("value") == "benevole")
        click(driver, "#orgWzAddType")
        row = driver.find_elements(By.CSS_SELECTOR, "[data-type-row]")[-1]
        row.find_element(By.CSS_SELECTOR, '[data-type-field="value"]').send_keys("member")
        row.find_element(By.CSS_SELECTOR, '[data-type-field="label"]').send_keys("会员")
        click(driver, "#orgWzNext")

        check("étape 3 : ressources natives listées", len(driver.find_elements(By.CSS_SELECTOR, "[data-resource-toggle]")) >= 10)
        click(driver, "#orgWzApplyPack")
        check("les suggestions décochent le véhicule pour une association", not driver.find_element(By.CSS_SELECTOR, '[data-resource-toggle="vehicule"]').is_selected())
        check("... et gardent l'ordinateur", driver.find_element(By.CSS_SELECTOR, '[data-resource-toggle="ordinateur"]').is_selected())
        click(driver, '[data-template="stock_vetement"]')
        click(driver, "#orgWzAddCustom")
        driver.find_element(By.CSS_SELECTOR, '[data-custom-field="label"]').send_keys("Instrument de musique")
        click(driver, "#orgWzNext")

        check("étape 4 : réglages", "Conservation" in body(driver))
        click(driver, "#orgWzNext")
        time.sleep(1)
        text = body(driver)
        check("étape 5 : aperçu des changements", "org_context" in text and "Instrument de musique" in text and "Masquer" in text, text[:200])
        check("« Appliquer » désactivé tant que non confirmé", driver.find_element(By.ID, "orgWzApply").get_attribute("disabled") is not None)
        check("pas de scroll horizontal dans l'assistant", driver.execute_script("return document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        click(driver, "#orgWzConfirm")
        check("« Appliquer » actif après confirmation", driver.find_element(By.ID, "orgWzApply").get_attribute("disabled") is None)
        click(driver, "#orgWzApply")
        time.sleep(1.5)
        check("configuration appliquée", "Configuration appliquée" in body(driver), body(driver)[:200])

        # Rejouer : plus aucun changement.
        click(driver, "#orgWzClose")
        time.sleep(2)
        click(driver, "[data-open-org-wizard]")
        time.sleep(1)
        check("rouvert : le type d'organisation appliqué est présélectionné", driver.find_element(By.CSS_SELECTOR, 'input[name="orgWzContext"][value="association"]').is_selected())
        for _ in range(4):
            click(driver, "#orgWzNext")
        time.sleep(1)
        check("rejouer sans rien changer : aucun changement à appliquer", "Aucun changement" in body(driver) and driver.find_element(By.ID, "orgWzApply").get_attribute("disabled") is not None, body(driver)[:200])
        errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
        check("aucune erreur JavaScript", not errors, str(errors)[:200])

    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
