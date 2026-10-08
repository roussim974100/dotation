"""Fuseau horaire de l'organisation (Administration > Personnalisation) : valeur par défaut Europe/Paris, aperçu de l'heure locale,
détection par le navigateur, refus d'un fuseau inconnu avec un message clair, enregistrement d'un fuseau valide.
Instance isolée, base vierge.
    python tests/browser/check_fuseau.py
"""
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


def wait_for(condition, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if condition():
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def saisir(driver, valeur):
    driver.execute_script("""const el = document.getElementById('brandingTimezone'); el.value = arguments[0];
        el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true}));""", valeur)


def reglage(driver):
    return driver.execute_script("return fetch('/api/admin/settings', {credentials:'same-origin', cache:'no-store'}).then(r => r.json()).then(j => j.raw.timezone)")


with Instance() as inst:
    driver = inst.driver()
    driver.get(inst.url("/admin-personnalisation.html"))
    field = lambda: driver.find_element("id", "brandingTimezone")  # noqa: E731
    preview = lambda: driver.find_element("id", "brandingTimezonePreview").text  # noqa: E731
    check("la valeur par défaut est Europe/Paris", wait_for(lambda: field().get_attribute("value") == "Europe/Paris"), field().get_attribute("value"))
    check("un aperçu donne l'heure actuelle dans ce fuseau", wait_for(lambda: "Il est actuellement" in preview()), preview())
    check("la liste propose des fuseaux", driver.execute_script("return document.querySelectorAll('#brandingTimezoneList option').length") > 20)

    saisir(driver, "Indian/Reunion")
    check("l'aperçu suit la saisie (La Réunion : UTC+4)", wait_for(lambda: "UTC+4" in preview()), preview())
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", field())
    time.sleep(1.2)  # laisse finir le défilement
    driver.save_screenshot(str(CAPTURES / "fuseau.png"))
    saisir(driver, "Nulle/Part")
    check("un fuseau inconnu est signalé dans l'aperçu", wait_for(lambda: "Fuseau inconnu" in preview()), preview())

    # ---- détection ------------------------------------------------------------------------------------------------------
    navigateur = driver.execute_script("return Intl.DateTimeFormat().resolvedOptions().timeZone")
    driver.execute_script("document.getElementById('brandingTimezoneDetect').click()")
    check("« Utiliser le fuseau de ce navigateur » remplit le champ", wait_for(lambda: field().get_attribute("value") == navigateur), f"{field().get_attribute('value')} / {navigateur}")

    # ---- un fuseau inconnu est refusé par le serveur, avec un message clair ----------------------------------------------
    saisir(driver, "Nulle/Part")
    driver.execute_script("document.getElementById('saveBrandingBtn').click()")
    check("l'enregistrement d'un fuseau inconnu est refusé avec un message clair",
          wait_for(lambda: "Fuseau horaire inconnu" in driver.find_element("tag name", "body").text), driver.find_element("tag name", "body").text[-300:])
    check("le réglage n'a pas changé", reglage(driver) == "Europe/Paris", str(reglage(driver)))

    # ---- un fuseau valide est enregistré -----------------------------------------------------------------------------------
    driver.get(inst.url("/admin-personnalisation.html"))
    wait_for(lambda: field().get_attribute("value") == "Europe/Paris")
    saisir(driver, "Indian/Reunion")
    driver.execute_script("document.getElementById('saveBrandingBtn').click()")
    check("un fuseau valide est enregistré", wait_for(lambda: reglage(driver) == "Indian/Reunion"), str(reglage(driver)))
    driver.get(inst.url("/admin-personnalisation.html"))
    check("il est restitué à la réouverture", wait_for(lambda: field().get_attribute("value") == "Indian/Reunion"), field().get_attribute("value"))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "400" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
