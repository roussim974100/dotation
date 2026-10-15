"""La fiche d'un dossier affiche les tâches des services : ce qui reste à faire et ce qui est fait (par qui, quand) ; rien pour un
dossier sans tâche. Dossiers créés par l'API depuis la page (vraie charge utile), instance isolée, base vierge.
    python tests/browser/check_fiche_taches.py
"""
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
CAPTURES = Path(tempfile.gettempdir())
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def wait_for(condition, timeout=8):
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
    """Appel de l'API depuis la page (session et jeton CSRF du navigateur)."""
    return driver.execute_async_script(
        """const [method, path, body, done] = arguments;
           fetch(path, {method, credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': 'jeton-navigateur'},
                        body: body ? JSON.stringify(body) : undefined})
             .then(r => r.json().then(j => done({status: r.status, json: j})));""", method, path, body)


def dossier(nom, codes):
    resources = [{"id": i + 1, "code": code, "label": f"Libellé {code}", "category": "materiel", "requiresReturn": True, "selected": True,
                  "fields": {}, "details": "Détail de test", "assignedAt": "2026-10-01T09:00:00"} for i, code in enumerate(codes)]
    return {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Alex", "qualite": "agent", "service": "DRH"},
            "resources": {"additional": resources}, "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": {}}


with Instance() as inst:
    db = sqlite3.connect(os.path.join(inst.dir, "dotation.db"))
    db.execute("INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at) VALUES ('svc_dsi', 'DSI e2e', 1, 0, 'x', 'x')")
    db.execute("INSERT INTO service_referents (service_id, username, created_at) VALUES ('svc_dsi', 'admin', 'x')")
    for code, label, returns in (("compte_ad", "Compte AD", 0), ("pc_portable", "PC portable", 1), ("sans_service", "Sans service", 1)):
        db.execute("INSERT INTO resource_catalog (id, code, label, category, issuer_service, requires_return, created_at, updated_at) VALUES (?,?,?,?,?,?, 'x','x')",
                   (f"res_{code}", code, label, "materiel", "DSI e2e" if code != "sans_service" else "", returns))
    db.commit()
    db.close()

    driver = inst.driver()
    driver.get(inst.url("/index.html"))
    wait_for(lambda: driver.find_elements("id", "userMenu"))
    first = api(driver, "POST", "/api/forms", dossier("DUPONT", ["compte_ad", "pc_portable"]))
    form_id = first["json"]["summary"]["id"]
    check("dossier créé par l'API", first["status"] in (200, 201), str(first)[:200])
    done = api(driver, "POST", "/api/service-tasks/done", {"kind": "service_provision", "form_id": form_id, "item_key": "compte_ad"})
    check("« Fait » enregistré pour le compte", done["status"] == 200, str(done)[:200])
    empty = api(driver, "POST", "/api/forms", dossier("MARTIN", ["sans_service"]))["json"]["summary"]["id"]

    # ---- la fiche avec des tâches -------------------------------------------------------------------------------------
    driver.get(inst.url(f"/form.html?id={form_id}"))
    block = lambda: driver.find_element("id", "serviceTasksHistory")  # noqa: E731
    check("le bloc « Tâches des services » apparaît", wait_for(lambda: "d-none" not in block().get_attribute("class")), block().get_attribute("class"))
    text = block().text
    check("ce qui reste à faire est annoncé", "À fournir" in text and "PC portable" in text or "Libellé pc_portable" in text, text[:300])
    check("ce qui est fait dit par qui et quand", "Fourni" in text and "par admin" in text, text[:300])
    check("le service est nommé", "DSI e2e" in text, text[:300])
    check("aucune donnée sur la personne dans ce bloc", "DUPONT" not in text)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", block())
    time.sleep(2)  # laisse disparaître le voile « Chargement de la fiche »
    driver.save_screenshot(str(CAPTURES / "fiche_taches.png"))

    # ---- un dossier sans tâche -----------------------------------------------------------------------------------------
    driver.get(inst.url(f"/form.html?id={empty}"))
    time.sleep(2)
    check("rien n'est affiché pour un dossier sans tâche de service", "d-none" in block().get_attribute("class"))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "report-lock" not in e]  # point de diagnostic désactivé par défaut
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
