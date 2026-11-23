"""PDF et e-mail d'un ajustement : dans l'historique des ajustements de la fiche, « Télécharger le PDF » enregistre un vrai PDF et
« Envoyer par e-mail » prépare un fichier .eml avec ce PDF en pièce jointe. Instance isolée, base vierge ; ajustement créé par l'API.
    python tests/browser/check_adjustment_pdf.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


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


def api(driver, method, path, body=None):
    return driver.execute_async_script(
        """const [method, path, body, done] = arguments;
           fetch(path, {method, credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': 'jeton-navigateur'},
                        body: body ? JSON.stringify(body) : undefined})
             .then(r => r.json().then(j => done({status: r.status, json: j})));""", method, path, body)


with Instance() as inst:
    driver = inst.driver()
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "userMenu"))

    dossier = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "LEFEBVRE", "prenom": "Sam", "qualite": "agent", "service": "DRH"},
               "resources": {"additional": [{"id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel", "requiresReturn": True,
                                             "selected": True, "fields": {"marque": "X"}, "details": "", "assignedAt": "2026-09-01T09:00:00"}]},
               "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}}
    form_id = api(driver, "POST", "/api/forms", dossier)["json"]["summary"]["id"]
    adjusted = api(driver, "PATCH", f"/api/forms/{form_id}/ajustement", {"service": "Finances", "signature": {"mode": "presentiel", "signatureDataUrl": PNG}})
    check("ajustement signé créé par l'API", adjusted["status"] == 200, str(adjusted)[:200])

    driver.get(inst.url(f"/form.html?id={form_id}"))
    history = lambda: driver.find_element("id", "ajustementsHistory")  # noqa: E731
    check("l'historique des ajustements est affiché", wait_for(lambda: "d-none" not in history().get_attribute("class")))
    buttons = lambda: history().find_elements("css selector", "[data-adjustment-pdf]")  # noqa: E731
    check("le bouton « Télécharger le PDF » est visible (export autorisé)", wait_for(lambda: buttons() and buttons()[0].is_displayed()))
    check("le bouton « Envoyer par e-mail » est visible", history().find_element("css selector", "[data-adjustment-email]").is_displayed())

    # saveBlob (storage.js) est une déclaration globale : la remplacer capte les fichiers produits sans téléchargement réel
    driver.execute_script("window.__saved = []; window.saveBlob = (blob, name) => window.__saved.push({name, type: blob.type, size: blob.size, blob});")
    saved = lambda: driver.execute_script("return window.__saved.map(f => ({name: f.name, type: f.type, size: f.size}))")  # noqa: E731
    head = lambda i, n: driver.execute_async_script("const [i, n, done] = arguments; window.__saved[i].blob.slice(0, n).text().then(done);", i, n)  # noqa: E731

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click()", buttons()[0])
    check("« Télécharger le PDF » produit un fichier", wait_for(lambda: len(saved()) == 1), str(saved()))
    if saved():
        file = saved()[0]
        check("c'est un PDF d'ajustement non vide", file["type"] == "application/pdf" and file["size"] > 1500 and "ajustement" in file["name"].lower(), str(file))
        check("il commence bien par %PDF", head(0, 4) == "%PDF")

    driver.execute_script("arguments[0].click()", history().find_element("css selector", "[data-adjustment-email]"))
    check("« Envoyer par e-mail » produit un fichier .eml", wait_for(lambda: len(saved()) == 2), str(saved()))
    if len(saved()) == 2:
        file = saved()[1]
        eml = driver.execute_async_script("const done = arguments[arguments.length - 1]; window.__saved[1].blob.text().then(done);")
        check("c'est un .eml", file["name"].endswith(".eml"), file["name"])
        check("il joint le PDF et parle de la fiche d'ajustement", "application/pdf" in eml and "ajustement" in eml.lower(), eml[:300])

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "report-lock" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
