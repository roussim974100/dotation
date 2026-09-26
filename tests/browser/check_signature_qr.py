"""3.66.0 : QR code du lien de signature (personne presente : elle scanne au lieu de recevoir un e-mail). Verifie dans un vrai
navigateur que le QR code est propose dans le menu des dossiers (attribution et restitution) et dans la banniere du lien, qu'il
se DECODE reellement (capture d'ecran lue par OpenCV) vers le bon lien, qu'il reste lisible en mode sombre, et qu'aucune
requete reseau externe n'est necessaire. Instance isolee, base vierge.
    python tests/browser/check_signature_qr.py
Le decodage demande OpenCV (`pip install opencv-python-headless`, outil de verification, hors dependances de l'application) ;
sans lui, seules les verifications d'affichage sont faites.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

try:
    import cv2
    import numpy
except ImportError:  # pragma: no cover - outil facultatif
    cv2 = None

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


def dialog_open(driver):
    return js(driver, "const m = document.getElementById('signatureQrModal'); return Boolean(m && !m.classList.contains('d-none'))")


def decode_qr(driver):
    """Capture du QR affiche puis lecture par OpenCV : ce que verrait l'appareil photo d'un telephone."""
    png = driver.find_element("css selector", "[data-signature-qr-image] svg").screenshot_as_png
    image = cv2.imdecode(numpy.frombuffer(png, numpy.uint8), cv2.IMREAD_COLOR)
    image = cv2.copyMakeBorder(image, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    return text


def click_action(driver, action):
    return js(driver, """const b = document.querySelector('[data-action="%s"]'); if (!b) return false; b.click(); return true""" % action)


def close_dialog(driver):
    js(driver, "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
    return wait_for(lambda: not dialog_open(driver))


with Instance() as inst:
    driver = inst.driver(width=1366, height=1000)
    driver.get(inst.url("/index.html"))
    time.sleep(2)
    draft = api(driver, "POST", "/api/forms", {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "QRATTRIB", "prenom": "Test", "qualite": "agent"},
                                               "resources": {"additional": []}, "workflow": {"status": "draft"}, "meta": {}})
    draft_id = (draft["json"].get("summary") or {}).get("id")
    check("dossier à signer créé", draft["status"] in (200, 201) and draft_id, str(draft)[:200])

    # ── Attribution : menu, fenêtre, décodage ──
    driver.get(inst.url("/index.html"))
    check("la liste affiche le dossier", wait_for(lambda: "QRATTRIB" in js(driver, "return document.body.innerText").upper()))
    check("le menu propose le QR code de signature (attribution)", js(driver, "return Boolean(document.querySelector('[data-action=\"showAssignmentSignatureQr\"]'))"))
    click_action(driver, "showAssignmentSignatureQr")
    check("la fenêtre du QR code s'ouvre", wait_for(lambda: dialog_open(driver)))
    check("le QR code est un SVG sur fond blanc", js(driver, "const box = document.querySelector('[data-signature-qr-image]'); return Boolean(box && box.querySelector('svg') && getComputedStyle(box).backgroundColor === 'rgb(255, 255, 255)')"))
    link = api(driver, "GET", f"/api/forms/{draft_id}/signature-link")["json"]["link"]
    expected = inst.url(link["url"])
    shown = js(driver, "return document.querySelector('#signatureQrModal a[href]').href")
    check("le lien affiché est celui du serveur", shown == expected, f"{shown} != {expected}")
    check("la date d'expiration est indiquée", "valable jusqu" in js(driver, "return document.getElementById('signatureQrModal').innerText"))
    check("l'adresse locale est signalée (un téléphone ne pourrait pas l'ouvrir)", "localhost" in js(driver, "return document.getElementById('signatureQrModal').innerText"))
    if cv2 is not None:
        decoded = decode_qr(driver)
        check("le QR code se décode vers le lien de signature", decoded == expected, f"{decoded!r} != {expected!r}")
    else:
        print("     (OpenCV absent : décodage non vérifié)")
    check("Échap ferme la fenêtre", close_dialog(driver))

    # ── Bannière du lien ──
    js(driver, "persistDashboardSignatureLinkNotice({url: arguments[0], title: 'QRATTRIB Test', kind: 'assignment'}); renderDashboardSignatureLinkNotice();", expected)
    check("la bannière propose « QR code »", wait_for(lambda: js(driver, "return Boolean(document.querySelector('[data-signature-link-qr]'))")))
    js(driver, "document.querySelector('[data-signature-link-qr]').click()")
    check("le bouton de la bannière ouvre le QR code", wait_for(lambda: dialog_open(driver)))
    if cv2 is not None:
        check("… et il se décode vers le même lien", decode_qr(driver) == expected)
    close_dialog(driver)
    js(driver, "persistDashboardSignatureLinkNotice(null); renderDashboardSignatureLinkNotice();")

    # ── Restitution ──
    active = api(driver, "POST", "/api/forms", {
        "dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "QRRESTIT", "prenom": "Test", "qualite": "agent"},
        "resources": {"additional": []}, "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True}, "workflow": {"status": "active"}, "meta": {}})
    active_id = (active["json"].get("summary") or {}).get("id")
    api(driver, "PATCH", f"/api/forms/{active_id}/restitution", {"returnedAt": "2026-09-28", "reason": "fin_de_fonction", "keepPending": True})
    driver.get(inst.url("/restitutions-pending.html"))
    check("la liste des restitutions affiche le dossier", wait_for(lambda: "QRRESTIT" in js(driver, "return document.body.innerText").upper()))
    check("le menu propose le QR code de signature (restitution)", js(driver, "return Boolean(document.querySelector('[data-action=\"showRestitutionSignatureQr\"]'))"))
    click_action(driver, "showRestitutionSignatureQr")
    check("la fenêtre s'ouvre pour la restitution", wait_for(lambda: dialog_open(driver)))
    rlink = api(driver, "GET", f"/api/forms/{active_id}/restitution-signature-link")["json"]["link"]
    rexpected = inst.url(rlink["url"])
    check("le lien de restitution est bien un lien de restitution", "restitution" in rexpected, rexpected)
    if cv2 is not None:
        check("le QR code de restitution se décode", decode_qr(driver) == rexpected)
    close_dialog(driver)

    # ── Mode sombre : le QR reste lisible ──
    js(driver, "localStorage.setItem('userDarkModePreference', 'dark')")
    driver.get(inst.url("/restitutions-pending.html"))
    wait_for(lambda: "QRRESTIT" in js(driver, "return document.body.innerText").upper())
    check("le mode sombre est actif", js(driver, "return document.documentElement.dataset.colorMode") == "dark")
    click_action(driver, "showRestitutionSignatureQr")
    wait_for(lambda: dialog_open(driver))
    if cv2 is not None:
        check("en mode sombre, le QR code se décode toujours", decode_qr(driver) == rexpected)
    close_dialog(driver)

    # ── Autonomie : aucune requête externe pour le QR code ──
    scripts = js(driver, "return [...document.scripts].map(s => s.getAttribute('src')).filter(Boolean)")
    check("le générateur est servi localement (pas de CDN)", "js/vendor/qrcode-generator.js" in scripts and not any("qrcode" in s and s.startswith("http") for s in scripts), str(scripts))
    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
