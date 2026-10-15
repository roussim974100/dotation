"""3.67.3 : le compte `admin` au mot de passe d'origine (`admin`) doit le changer avant tout autre usage.
Vraie connexion dans le formulaire, fenêtre de changement obligatoire (sans Annuler, ni Échap, ni clic à côté), pages
d'administration renvoyées à l'accueil, puis déblocage après le changement. Instance isolée, base vierge ; les valeurs
(`admin`/`admin`) sont celles du seed de l'application de test.
    python tests/browser/check_password_obligatoire.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
NOUVEAU = "Nouveau-Mot-2-Passe!"
CAPTURE_DIR = Path(tempfile.gettempdir())


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def modal_present(driver):
    return bool(driver.find_elements("id", "passwordChangeModal"))


def wait_for(condition, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.25)
    return False


with Instance(keep_default_password_flag=True) as inst:
    driver = inst.driver(with_session=False)
    driver.get(inst.url("/login"))
    time.sleep(1.5)
    driver.find_element("id", "username").send_keys("admin")
    driver.find_element("id", "password").send_keys("admin")
    driver.find_element("css selector", "form button[type=submit]").click()

    check("la connexion mène à l'accueil (pas à l'assistant)", wait_for(lambda: driver.current_url.rstrip("/") == inst.url("/").rstrip("/")), driver.current_url)
    check("la fenêtre de changement de mot de passe s'ouvre d'elle-même", wait_for(lambda: modal_present(driver)))
    driver.save_screenshot(str(CAPTURE_DIR / "password_obligatoire.png"))

    dialog = driver.find_element("css selector", "#passwordChangeModal .password-change-modal__dialog")
    check("titre explicite", "Choisissez votre mot de passe" in dialog.text, dialog.text[:80])
    check("pas de bouton Annuler", not driver.find_elements("id", "pwdCancelBtn"))

    driver.find_element("css selector", "body").send_keys("")  # Échap
    time.sleep(0.5)
    check("Échap ne ferme pas la fenêtre", modal_present(driver))
    driver.execute_script("document.getElementById('passwordChangeModal').click()")  # clic sur le fond
    time.sleep(0.5)
    check("un clic à côté ne ferme pas la fenêtre", modal_present(driver))

    driver.get(inst.url("/admin.html"))
    check("une page d'administration renvoie à l'accueil", wait_for(lambda: "/admin" not in driver.current_url), driver.current_url)
    check("la fenêtre y est de nouveau", wait_for(lambda: modal_present(driver)))

    # Mauvaises saisies : la fenêtre reste, avec un message en français
    driver.find_element("id", "pwdCurrent").send_keys("admin")
    driver.find_element("id", "pwdNew").send_keys("admin")
    driver.find_element("id", "pwdConfirm").send_keys("admin")
    driver.find_element("id", "pwdSubmitBtn").click()
    check("même mot de passe : message clair", wait_for(lambda: "différent" in driver.find_element("id", "pwdFeedback").text), driver.find_element("id", "pwdFeedback").text)
    driver.find_element("id", "pwdNew").clear()
    driver.find_element("id", "pwdConfirm").clear()
    driver.find_element("id", "pwdNew").send_keys("trop-court")
    driver.find_element("id", "pwdConfirm").send_keys("trop-court")
    driver.find_element("id", "pwdSubmitBtn").click()
    check("mot de passe faible : message clair (pas de code technique)", wait_for(lambda: "12 caractères" in driver.find_element("id", "pwdFeedback").text), driver.find_element("id", "pwdFeedback").text)
    check("la fenêtre reste ouverte après un refus", modal_present(driver))

    # Bonne saisie
    driver.find_element("id", "pwdNew").clear()
    driver.find_element("id", "pwdConfirm").clear()
    driver.find_element("id", "pwdNew").send_keys(NOUVEAU)
    driver.find_element("id", "pwdConfirm").send_keys(NOUVEAU)
    driver.find_element("id", "pwdSubmitBtn").click()
    check("la page se recharge sans la fenêtre", wait_for(lambda: not modal_present(driver) and driver.current_url.rstrip("/") == inst.url("/").rstrip("/"), 10))
    time.sleep(1)
    check("plus de fenêtre après rechargement", not modal_present(driver))
    driver.get(inst.url("/admin.html"))
    time.sleep(1)
    check("l'administration est de nouveau accessible", "/admin.html" in driver.current_url, driver.current_url)
    check("aucune fenêtre sur l'administration", not modal_present(driver))
    errors = [e for e in inst.console_errors(driver) if "403" not in e and "/api/me/password" not in e]  # refus provoqués exprès ci-dessus
    check("aucune erreur JavaScript hors refus attendus", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
