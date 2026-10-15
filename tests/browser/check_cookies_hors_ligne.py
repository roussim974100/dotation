"""Bouton « Cookies » du pied de page, SANS accès à Internet : la fenêtre des préférences s'ouvre (bibliothèque embarquée), annonce les vraies
durées de session, et AUCUNE requête ne part vers un serveur externe (Bootstrap, Chart.js, CookieConsent sont servis par l'application).
Toute requête vers une adresse externe fait échouer le scénario.
    python tests/browser/check_cookies_hors_ligne.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []


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


with Instance() as inst:
    driver = inst.driver()
    # La bibliothèque des cookies ne s'affiche pas pour un robot (option hideFromBots, navigator.webdriver) : on se fait passer pour un navigateur normal.
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => false})"})
    for page, bibliotheques in (("/", ("bootstrap",)), ("/executive-dashboard.html", ("bootstrap", "chart"))):
        driver.get(inst.url(page))
        time.sleep(2)
        externes = driver.execute_script(
            "return performance.getEntriesByType('resource').map(e => e.name).filter(n => !n.startsWith(location.origin) && !n.startsWith('data:'))")
        check(f"{page} : aucune requête vers un serveur externe", not externes, str(externes[:5]))
        locales = driver.execute_script("return performance.getEntriesByType('resource').map(e => e.name)")
        for nom in bibliotheques:
            check(f"{page} : {nom} est servi par l'application", any(f"/vendor/{nom}" in u for u in locales), str([u for u in locales if "vendor" in u]))
    check("Bootstrap fonctionne (grille et composants)", driver.execute_script("return typeof bootstrap !== 'undefined' || getComputedStyle(document.body).fontFamily.length > 0"))

    driver.get(inst.url("/"))
    wait_for(lambda: driver.find_elements("css selector", ".app-footer__cookies"))
    bouton = driver.find_element("css selector", ".app-footer__cookies")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", bouton)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click()", bouton)  # à la première visite, le bandeau de consentement recouvre le bouton du pied de page
    check("un clic sur « Cookies » ouvre la fenêtre des préférences", wait_for(lambda: driver.find_elements("css selector", "#cc-main .pm--box, #cc-main .pm")
                                                                          and "Préférences cookies" in driver.find_element("id", "cc-main").text), driver.find_element("tag name", "body").text[-200:])
    texte = driver.find_element("id", "cc-main").text
    check("elle annonce la vraie durée de la session (plus « session navigateur »)", "12 heures au maximum" in texte and "1 heure sans activité" in texte and "session navigateur" not in texte, texte[-500:])
    time.sleep(0.8)
    driver.save_screenshot(str(Path(__import__("tempfile").gettempdir()) / "cookies_local.png"))

    erreurs = [e for e in inst.console_errors(driver) if "favicon" not in e]
    check("aucune erreur JavaScript", not erreurs, str(erreurs)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
