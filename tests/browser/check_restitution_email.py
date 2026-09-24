"""E-mails de restitution depuis les écrans de restitution (24/09/2026) : proposition d'e-mail à la validation de la
Phase 1, boutons « Télécharger le PDF » / « Envoyer par e-mail » en Phase 2, envoi proposé après l'enregistrement.
Instance isolée, base vierge.
    python tests/browser/check_restitution_email.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
CSRF = "jeton-navigateur"
# saveBlob est une déclaration globale de storage.js : la remplacer capte les fichiers .eml/.pdf sans téléchargement réel.
CAPTURE_DOWNLOADS = "window.__saved = []; window.saveBlob = (blob, name) => window.__saved.push(name);"


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def api(driver, method, path, body=None):
    script = ("const [m,p,b]=arguments;return fetch(p,{method:m,credentials:'same-origin',headers:{'Content-Type':'application/json',"
              f"'X-CSRF-Token':'{CSRF}'}},body:b?JSON.stringify(b):undefined}}).then(async r=>{{let j=null;try{{j=await r.json()}}catch(e){{}};return JSON.stringify({{status:r.status,json:j}})}})")
    return json.loads(driver.execute_script(script, method, path, body))


def wait_for(fn, tries=30):
    for _ in range(tries):
        time.sleep(0.4)
        try:
            if fn():
                return True
        except Exception:
            pass
    return False


def dialog_visible(driver):
    return driver.execute_script("const d = document.getElementById('workflowDialog'); return Boolean(d && !d.classList.contains('is-hidden'));")


def saved(driver):
    return driver.execute_script("return window.__saved || []")


with Instance() as inst:
    driver = inst.driver(width=1366, height=900)
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "RESTIMAIL", "prenom": "Test", "qualite": "agent", "email": "test@example.org"},
            "resources": {"additional": []},
            "validation": {"signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}
    created = api(driver, "POST", "/api/forms", body)
    form_id = (created["json"].get("summary") or {}).get("id")
    check("dossier actif créé", created["status"] in (200, 201) and form_id, str(created)[:200])

    # Fiche d'attribution : l'e-mail avec PDF fonctionnait mal hors des listes (chargeur d'export absent de form.html)
    driver.get(inst.url(f"/form.html?id={form_id}"))
    time.sleep(3)
    driver.execute_script(CAPTURE_DOWNLOADS + f"void prepareDraftPdfEmail('{form_id}');")
    check("fiche : l'e-mail avec le PDF du dossier est préparé", wait_for(lambda: any(n.startswith("dossier_pdf_email") for n in saved(driver))), str(saved(driver)))

    # Phase 1 : validation → proposition d'e-mail d'information
    driver.get(inst.url(f"/restitution-phase1.html?id={form_id}"))
    time.sleep(2.5)
    check("Phase 1 non validée : pas de bouton d'e-mail", driver.execute_script("return document.querySelectorAll('[data-restitution-action]').length") == 0)
    driver.execute_script(CAPTURE_DOWNLOADS)
    driver.execute_script("document.getElementById('p1_returned_at').value = new Date().toISOString().slice(0, 10);")
    driver.execute_script("document.getElementById('validatePhase1Btn').click()")
    check("la validation propose d'informer la personne", wait_for(lambda: dialog_visible(driver)
          and "informer" in driver.execute_script("return document.getElementById('workflowDialogText').textContent")))
    driver.execute_script("document.getElementById('workflowDialogConfirmBtn').click()")
    check("un e-mail d'information est préparé", wait_for(lambda: any(n.startswith("information_restitution") and n.endswith(".eml") for n in saved(driver))), str(saved(driver)))
    check("redirection vers la Phase 2", wait_for(lambda: "restitution.html" in driver.current_url and "phase1" not in driver.current_url), driver.current_url)

    # Phase 2 : boutons dans la barre du bas
    time.sleep(2.5)
    driver.execute_script(CAPTURE_DOWNLOADS)
    labels = driver.execute_script("return [...document.querySelectorAll('[data-restitution-action]')].map(b => b.textContent)")
    check("Phase 2 : boutons PDF et e-mail présents", labels == ["Télécharger le PDF", "Envoyer par e-mail"], str(labels))
    driver.execute_script("[...document.querySelectorAll('[data-restitution-action]')].find(b => b.textContent === 'Envoyer par e-mail').click()")
    check("le bouton prépare l'e-mail avec le PDF de restitution", wait_for(lambda: any(n.startswith("restitution_pdf_email") for n in saved(driver))), str(saved(driver)))

    # Enregistrement final : l'envoi est proposé ; un clic hors du dialogue ne l'envoie pas
    driver.execute_script(CAPTURE_DOWNLOADS)
    driver.execute_script("document.querySelector('input[name=\"restitution_signature_status\"][value=\"deferred\"]').click()")
    driver.execute_script("window.playCompletionCelebration = async () => {}; document.getElementById('saveRestitutionBtn').click()")
    check("après enregistrement, l'envoi par e-mail est proposé", wait_for(lambda: dialog_visible(driver)
          and driver.execute_script("return document.getElementById('workflowDialogConfirmBtn').textContent") == "Envoyer par e-mail"))
    driver.execute_script("document.querySelector(\"[data-workflow-close='backdrop']\").click()")
    check("un clic hors du dialogue n'envoie rien et ramène à la liste", wait_for(lambda: "restitutions-pending" in driver.current_url) and not saved(driver), f"{driver.current_url} {saved(driver)}")

    # /api/debug/report-lock : sonde de débogage de la fiche, refusée hors APP_DEBUG_ENDPOINTS (sans rapport ici).
    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
