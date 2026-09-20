"""Test navigateur de bout en bout : nouvelle version detectee, bouton, mot de passe, progression, fin.
Un faux « GitHub » (serveur HTTP local) annonce une version plus recente ; un faux « root » (thread) joue le role de l'unite systemd :
il consomme request.json et ecrit status.json, exactement comme le fera deploy.sh. Aucun vrai serveur ni aucun vrai depot n'est touche.
    python tests/browser/check_update.py
"""
import http.server
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


class FakeGithub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'const APP_BUILD_VERSION = "9.9.9-dev";\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def fake_root(update_dir, done):
    """Joue l'unite systemd : consomme la demande, ecrit la progression, puis « reussit »."""
    request = Path(update_dir) / "request.json"
    status = Path(update_dir) / "status.json"
    while not done.is_set():
        if request.exists():
            request.unlink()
            for step, message in (("1/4", "Sauvegarde des bases"), ("2/4", "Récupération du code"), ("3/4", "Dépendances Python"), ("4/4", "Redémarrage")):
                status.write_text(json.dumps({"state": "running", "step": step, "message": message, "from": "3.48.0-dev", "to": "9.9.9-dev"}), encoding="utf-8")
                time.sleep(4.5)  # plus long que l'intervalle de relecture de la page (3 s)
            status.write_text(json.dumps({"state": "ok", "message": "Application redémarrée et vérifiée.", "from": "3.48.0-dev", "to": "9.9.9-dev",
                                          "finished_at": time.time()}), encoding="utf-8")
        time.sleep(0.3)


def text(driver, element_id):
    return driver.find_element(By.ID, element_id).text


def click(driver, css):
    element = driver.find_element(By.CSS_SELECTOR, css)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    driver.execute_script("arguments[0].click();", element)
    time.sleep(0.5)


if __name__ == "__main__":
    github = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeGithub)
    threading.Thread(target=github.serve_forever, daemon=True).start()
    unit = Path(tempfile.mkdtemp()) / "dotation-update.path"
    unit.write_text("[Path]")
    env = {"APP_UPDATE_CHECK_URL": f"http://127.0.0.1:{github.server_address[1]}/branding.js", "APP_ALLOW_WEB_UPDATE": "1",
           "APP_UPDATE_UNIT_PATH": str(unit)}
    with Instance(env=env) as inst:
        update_dir = Path(inst.dir) / "update"
        update_dir.mkdir(exist_ok=True)
        done = threading.Event()
        threading.Thread(target=fake_root, args=(update_dir, done), daemon=True).start()
        driver = inst.driver(width=1366, height=1000)
        driver.get(inst.url("/admin.html"))
        time.sleep(3)
        info = text(driver, "updateInfo")
        check("la version installée est affichée", "Version installée" in info, info)
        banner = driver.find_element(By.ID, "updateBanner")
        check("le bandeau « nouvelle version » apparaît (9.9.9-dev)", banner.is_displayed() and "9.9.9-dev" in banner.text, banner.text[:120])
        check("le bouton « Mettre à jour maintenant » est proposé (mise à jour web activée)", "Mettre à jour maintenant" in banner.text)
        check("le lien vers les notes de version est présent", "Notes de version" in banner.text)

        click(driver, "[data-update-start]")
        check("la fenêtre de confirmation s'ouvre", driver.find_element(By.ID, "updateModal").is_displayed())
        modal_text = text(driver, "updateModalText")
        check("elle annonce la sauvegarde et le retour arrière automatique", "sauvegarde" in modal_text.lower() and "rétablie automatiquement" in modal_text, modal_text)

        driver.find_element(By.ID, "updatePassword").send_keys("mauvais-mot-de-passe")
        click(driver, "#updateConfirm")
        time.sleep(1)
        err = driver.find_element(By.ID, "updateError")
        check("mauvais mot de passe : refusé avec un message", err.is_displayed() and "incorrect" in err.text.lower(), err.text)
        check("aucune demande n'a été déposée", not (update_dir / "request.json").exists())

        driver.find_element(By.ID, "updatePassword").clear()
        driver.find_element(By.ID, "updatePassword").send_keys("admin")  # compte admin par defaut d'une base vierge
        click(driver, "#updateConfirm")
        time.sleep(1.2)
        banner = driver.find_element(By.ID, "updateBanner")
        check("la fenêtre se ferme et la progression s'affiche", not driver.find_element(By.ID, "updateModal").is_displayed() and "Mise à jour en cours" in banner.text, banner.text[:100])
        seen_steps = set()
        for _ in range(40):
            time.sleep(1)
            current = driver.find_element(By.ID, "updateBanner").text
            for step in ("Sauvegarde des bases", "Récupération du code", "Dépendances Python", "Redémarrage"):
                if step in current:
                    seen_steps.add(step)
            if "Mise à jour terminée" in current:
                break
        check("les étapes du script sont suivies en direct (au moins 3 sur 4)", len(seen_steps) >= 3, sorted(seen_steps))
        final = driver.find_element(By.ID, "updateBanner").text
        check("la fin est annoncée : « Mise à jour terminée »", "Mise à jour terminée" in final, final[:100])
        check("le résultat de la mise à jour ne cache PAS l'annonce de la nouvelle version (les deux bandeaux sont visibles)",
              "Mise à jour terminée" in final and "Nouvelle version 9.9.9-dev disponible" in final, final[:160])
        check("la ligne d'information annonce la version disponible", "9.9.9-dev disponible" in text(driver, "updateInfo"), text(driver, "updateInfo"))
        # le 403 du mauvais mot de passe est PROVOQUE par le test : Chrome le journalise comme une erreur de chargement
        errors = [e for e in inst.console_errors(driver) if not ("/api/admin/update/start" in e and "403" in e)]
        check("aucune erreur dans la console du navigateur", not errors, [e[:160] for e in errors[:3]])
        driver.save_screenshot(str(Path(inst.dir) / "update.png"))
        done.set()
    github.shutdown()
    print("\n%d/%d vérifications réussies" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)
