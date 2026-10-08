"""3.73.0 : après « Enregistrer en attente » d'une restitution en signature « à distance par lien », la fenêtre de fin propose d'afficher
tout de suite le QR code (la personne est souvent encore devant l'agent). Vérifie dans un vrai navigateur : la proposition n'existe QUE pour
la signature à distance ; le QR s'affiche (lien du serveur, SVG sur fond blanc), la redirection n'a lieu qu'À LA FERMETURE du QR ; « Plus
tard » (et un clic hors de la fenêtre) redirige sans effet ; signature impossible = pas de QR ; échec de création du lien = on reste sur la page.
Instance isolée, base vierge.
    python tests/browser/check_restitution_qr_attente.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

results = []
CSRF = "jeton-navigateur"
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def api(driver, method, path, body=None):
    script = ("const [m,p,b]=arguments;return fetch(p,{method:m,credentials:'same-origin',headers:{'Content-Type':'application/json',"
              f"'X-CSRF-Token':'{CSRF}'}},body:b?JSON.stringify(b):undefined}}).then(async r=>{{let j=null;try{{j=await r.json()}}catch(e){{}};return JSON.stringify({{status:r.status,json:j}})}})")
    return json.loads(driver.execute_script(script, method, path, body))


def wait_for(fn, tries=40):
    for _ in range(tries):
        time.sleep(0.4)
        try:
            if fn():
                return True
        except Exception:
            pass
    return False


def js(driver, script, *args):
    return driver.execute_script(script, *args)


def workflow_visible(driver):
    return js(driver, "const d = document.getElementById('workflowDialog'); return Boolean(d && !d.classList.contains('is-hidden'))")


def qr_open(driver):
    return js(driver, "const m = document.getElementById('signatureQrModal'); return Boolean(m && !m.classList.contains('d-none'))")


def dossier_actif(driver, nom):
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": "Test", "qualite": "agent"}, "resources": {"additional": []},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}}
    created = api(driver, "POST", "/api/forms", body)
    return (created["json"].get("summary") or {}).get("id")


def phase2(driver, inst, form_id):
    """Phase 1 enregistrée et validée par l'API de l'écran (dates), puis ouverture de l'écran de la Phase 2."""
    driver.get(inst.url(f"/restitution-phase1.html?id={form_id}"))
    time.sleep(2.5)
    js(driver, "document.getElementById('p1_returned_at').value = new Date().toISOString().slice(0, 10);")
    js(driver, "document.getElementById('savePhase1Btn').click()")
    time.sleep(2)
    js(driver, "document.getElementById('validatePhase1Btn').click()")
    wait_for(lambda: workflow_visible(driver))
    js(driver, "document.getElementById('workflowDialogSecondaryBtn').click()")  # « Plus tard » : pas d'e-mail
    wait_for(lambda: "restitution.html" in driver.current_url and "phase1" not in driver.current_url)
    time.sleep(2.5)


def choisir_signature(driver, valeur, motif=""):
    js(driver, "document.querySelector('input[name=\"restitution_signature_status\"][value=\"%s\"]').click()" % valeur)
    if motif:
        js(driver, "const t = document.getElementById('restitution_signature_reason'); t.value = arguments[0]; t.dispatchEvent(new Event('input', {bubbles: true}));", motif)


def enregistrer_en_attente(driver):
    js(driver, "document.getElementById('saveRestitutionPendingBtn').click()")
    return wait_for(lambda: "enregistrée en attente" in js(driver, "return document.getElementById('workflowDialogTitle').textContent") and workflow_visible(driver))


def dialogue(driver):
    return js(driver, "return {title: document.getElementById('workflowDialogTitle').textContent, text: document.getElementById('workflowDialogText').textContent,"
                      " confirm: document.getElementById('workflowDialogConfirmBtn').textContent.trim(),"
                      " secondary: (b => b && !b.classList.contains('d-none') && getComputedStyle(b).display !== 'none' ? b.textContent.trim() : '')(document.getElementById('workflowDialogSecondaryBtn'))}")


with Instance() as inst:
    driver = inst.driver(width=1366, height=1000)
    driver.get(inst.url("/index.html"))
    time.sleep(2)

    # ── 1. signature à distance : le QR code est proposé, affiché, et la redirection attend sa fermeture ──
    form_id = dossier_actif(driver, "QRATTENTE")
    check("dossier actif créé", bool(form_id))
    phase2(driver, inst, form_id)
    check("écran de la Phase 2 ouvert", "restitution.html" in driver.current_url and "phase1" not in driver.current_url, driver.current_url)
    choisir_signature(driver, "deferred")
    check("fin d'enregistrement en attente affichée", enregistrer_en_attente(driver))
    d = dialogue(driver)
    check("la fenêtre propose « Afficher le QR code » et « Plus tard »", d["confirm"] == "Afficher le QR code" and d["secondary"] == "Plus tard", str(d))
    check("elle explique qu'on peut signer maintenant avec un téléphone", "QR code" in d["text"] and "téléphone" in d["text"], d["text"])
    js(driver, "document.getElementById('workflowDialogConfirmBtn').click()")
    check("le QR code s'affiche", wait_for(lambda: qr_open(driver)))
    check("la page n'est PAS quittée tant que le QR est ouvert", "restitution.html" in driver.current_url and "pending" not in driver.current_url, driver.current_url)
    check("le QR est un SVG sur fond blanc", js(driver, "const b = document.querySelector('[data-signature-qr-image]'); return Boolean(b && b.querySelector('svg') && getComputedStyle(b).backgroundColor === 'rgb(255, 255, 255)')"))
    link = api(driver, "GET", f"/api/forms/{form_id}/restitution-signature-link")["json"]["link"]
    shown = js(driver, "return document.querySelector('#signatureQrModal a[href]').href")
    check("le lien affiché est celui de la signature de la RESTITUTION", shown == inst.url(link["url"]) and "restitution-signature" in shown, f"{shown} / {link}")
    check("le titre dit « Signature de la restitution »", "Signature de la restitution" in js(driver, "return document.getElementById('signatureQrTitle').textContent"))
    js(driver, "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
    check("à la fermeture du QR, on retourne à la liste des restitutions en cours", wait_for(lambda: "restitutions-pending.html" in driver.current_url), driver.current_url)

    # ── 2. « Plus tard » : retour à la liste, aucun QR ──
    driver.get(inst.url(f"/restitution.html?id={form_id}"))
    time.sleep(3)
    choisir_signature(driver, "deferred")
    check("(2) fin d'enregistrement affichée", enregistrer_en_attente(driver))
    js(driver, "document.getElementById('workflowDialogSecondaryBtn').click()")
    check("« Plus tard » : retour à la liste sans QR code", wait_for(lambda: "restitutions-pending.html" in driver.current_url) and not qr_open(driver), driver.current_url)

    # ── 3. signature impossible : aucun QR proposé ──
    driver.get(inst.url(f"/restitution.html?id={form_id}"))
    time.sleep(3)
    choisir_signature(driver, "impossible", "Agent parti sans signer")
    check("(3) fin d'enregistrement affichée", enregistrer_en_attente(driver))
    d = dialogue(driver)
    check("signature impossible : un simple « OK », pas de QR code", d["confirm"] == "OK" and not d["secondary"] and "QR" not in d["text"], str(d))
    js(driver, "document.getElementById('workflowDialogConfirmBtn').click()")
    check("(3) retour à la liste", wait_for(lambda: "restitutions-pending.html" in driver.current_url), driver.current_url)

    # ── 4. un clic hors de la fenêtre = « Plus tard » : jamais de QR déclenché par erreur ──
    driver.get(inst.url(f"/restitution.html?id={form_id}"))
    time.sleep(3)
    choisir_signature(driver, "deferred")
    check("(4) fin d'enregistrement affichée", enregistrer_en_attente(driver))
    js(driver, "const b = document.querySelector('#workflowDialog .workflow-dialog__backdrop, #workflowDialog [data-workflow-backdrop]'); if (b) b.click(); else document.getElementById('workflowDialog').click();")
    check("clic hors de la fenêtre : on repart sans afficher le QR", wait_for(lambda: "restitutions-pending.html" in driver.current_url) and not qr_open(driver), driver.current_url)

    # ── 5. échec de création du lien : on reste sur la page, avec un message ──
    driver.get(inst.url(f"/restitution.html?id={form_id}"))
    time.sleep(3)
    choisir_signature(driver, "deferred")
    check("(5) fin d'enregistrement affichée", enregistrer_en_attente(driver))
    js(driver, "window.ensureRestitutionSignatureLink = async () => { throw new Error('Lien indisponible pour le test'); };")
    js(driver, "document.getElementById('workflowDialogConfirmBtn').click()")
    time.sleep(1)
    toasts = js(driver, "return [...document.querySelectorAll('.toast')].map(t => t.textContent)")
    check("échec du lien : on reste sur l'écran (pas de redirection) et le QR n'est pas ouvert", "restitution.html" in driver.current_url and "pending" not in driver.current_url and not qr_open(driver), driver.current_url)
    check("le message d'erreur est affiché (alerte en erreur)", any("Lien indisponible" in t for t in toasts), str(toasts))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "Lien indisponible" not in e]
    check("aucune erreur JavaScript inattendue", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
