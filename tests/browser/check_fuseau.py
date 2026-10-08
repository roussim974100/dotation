"""Fuseau horaire de l'organisation (Administration > Personnalisation) : champ où l'on peut TAPER (nom IANA ou lieu en français) et choisir
parmi des suggestions ; Europe/Paris par défaut ; aperçu de l'heure locale et du prochain changement d'heure (heure d'été / d'hiver) ;
détection par le navigateur ; refus clair d'un fuseau inconnu ; TOUS les fuseaux proposés acceptés par le serveur. Instance isolée.
    python tests/browser/check_fuseau.py
"""
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

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


def reglage(driver):
    return driver.execute_script("return fetch('/api/admin/settings', {credentials:'same-origin', cache:'no-store'}).then(r => r.json()).then(j => j.raw.timezone)")


def api_put(driver, timezone):
    return driver.execute_async_script(
        """const [tz, done] = arguments;
           fetch('/api/admin/settings', {method: 'PUT', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': 'jeton-navigateur'},
                                         body: JSON.stringify({timezone: tz})}).then(r => r.json().then(j => done({status: r.status, json: j})));""", timezone)


def taper(driver, texte, quitter=True):
    """Vraie saisie au clavier dans le champ ; `quitter` = sortir du champ (déclenche la résolution « Réunion » -> « Indian/Reunion »)."""
    champ = driver.find_element("id", "brandingTimezone")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", champ)  # la barre du bas peut masquer le champ
    driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", champ)
    champ.send_keys(texte)
    if quitter:
        champ.send_keys("")  # Tab : sortie du champ -> événement change


with Instance() as inst:
    driver = inst.driver()
    driver.get(inst.url("/admin-personnalisation.html"))
    champ = lambda: driver.find_element("id", "brandingTimezone")  # noqa: E731
    valeur = lambda: champ().get_attribute("value")  # noqa: E731
    preview = lambda: driver.find_element("id", "brandingTimezonePreview").text  # noqa: E731

    check("c'est un champ où l'on peut écrire, avec des suggestions", wait_for(lambda: champ().tag_name == "input" and champ().get_attribute("list") == "brandingTimezoneList"))
    check("la valeur par défaut est Europe/Paris", wait_for(lambda: valeur() == "Europe/Paris"), valeur())
    check("un aperçu donne l'heure actuelle et dit si l'heure d'été est en vigueur", wait_for(lambda: "Il est actuellement" in preview() and "changement d'heure" in preview()), preview())

    suggestions = driver.execute_script("return Array.from(document.querySelectorAll('#brandingTimezoneList option')).map(o => [o.value, o.label])")
    check("la liste propose plus de 300 fuseaux", len(suggestions) > 300, str(len(suggestions)))
    check("les cas courants viennent d'abord, avec un nom lisible et le décalage",
          suggestions[0][0] == "Europe/Paris" and "France métropolitaine" in suggestions[0][1] and any(v == "Indian/Reunion" and "La Réunion" in label and "UTC+4" in label for v, label in suggestions),
          str(suggestions[:2]))
    refuses = []
    for nom, _ in suggestions:
        try:
            ZoneInfo(nom)
        except Exception:
            refuses.append(nom)
    check(f"les {len(suggestions)} fuseaux proposés sont tous connus du serveur", not refuses, str(refuses[:10]))

    # ---- on peut écrire ----------------------------------------------------------------------------------------------------
    taper(driver, "Indian/Reunion")
    check("on peut taper un nom de fuseau : l'aperçu suit (La Réunion : UTC+4)", wait_for(lambda: "UTC+4" in preview() and "pas de changement d'heure" in preview()), preview())
    taper(driver, "Réunion")
    check("on peut taper un lieu en français : « Réunion » devient Indian/Reunion", wait_for(lambda: valeur() == "Indian/Reunion"), valeur())
    taper(driver, "belgique")
    check("sans accents ni majuscules : « belgique » devient Europe/Brussels", wait_for(lambda: valeur() == "Europe/Brussels"), valeur())
    taper(driver, "Europe/Zurich")
    check("un nom exact est gardé tel quel", wait_for(lambda: valeur() == "Europe/Zurich"), valeur())
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", champ())
    time.sleep(1.2)
    driver.save_screenshot(str(CAPTURES / "fuseau.png"))

    taper(driver, "Nulle part")
    check("un texte inconnu est signalé tout de suite", wait_for(lambda: "Fuseau inconnu" in preview()), preview())
    check("le champ est marqué invalide (accessibilité)", champ().get_attribute("aria-invalid") == "true")

    # ---- heure d'été / heure d'hiver : calculées sur des dates FIXES (le test ne dépend pas de la saison où il tourne) -----------------
    def changement(zone, date):
        return driver.execute_script("const i = timezoneChangeInfo(arguments[0], new Date(arguments[1]));"
                                     "return {dst: i.isDst, observes: i.observesDst, offset: i.offsetNow, next: i.nextChange && i.nextChange.toISOString().slice(0, 10), nextOffset: i.nextOffset};",
                                     zone, date)

    ete = changement("Europe/Paris", "2026-10-08T10:00:00Z")
    check("Paris en octobre : heure d'été (UTC+2), retour à l'heure d'hiver le 25 octobre", ete["dst"] and ete["offset"] == 120 and ete["next"] == "2026-10-25" and ete["nextOffset"] == 60, str(ete))
    hiver = changement("Europe/Paris", "2026-01-10T10:00:00Z")
    check("Paris en janvier : heure d'hiver (UTC+1), passage à l'heure d'été le 29 mars", not hiver["dst"] and hiver["offset"] == 60 and hiver["next"] == "2026-03-29" and hiver["nextOffset"] == 120, str(hiver))
    sud = changement("Australia/Sydney", "2026-01-10T10:00:00Z")
    check("hémisphère sud : janvier est l'heure d'été (UTC+11), retour le 5 avril", sud["dst"] and sud["offset"] == 660 and sud["next"] == "2026-04-05", str(sud))
    reunion = changement("Indian/Reunion", "2026-10-08T10:00:00Z")
    check("La Réunion : aucun changement d'heure", not reunion["observes"] and reunion["next"] is None and reunion["offset"] == 240, str(reunion))
    inde = changement("Asia/Kolkata", "2026-10-08T10:00:00Z")
    check("décalage à la demi-heure géré (Inde : UTC+5:30)", inde["offset"] == 330, str(inde))
    texte = driver.execute_script("return describeTimezoneChange('Europe/Paris', new Date('2026-10-08T10:00:00Z'))")
    check("le texte dit l'heure d'été et le prochain changement", "Heure d'été en vigueur" in texte and "25 octobre 2026" in texte and "heure d'hiver (UTC+1)" in texte, texte)

    # ---- détection par le navigateur ---------------------------------------------------------------------------------------
    navigateur = driver.execute_script("return Intl.DateTimeFormat().resolvedOptions().timeZone")
    driver.execute_script("document.getElementById('brandingTimezoneDetect').click()")
    check("« Utiliser le fuseau de ce navigateur » remplit le champ", wait_for(lambda: valeur() == navigateur), f"{valeur()} / {navigateur}")

    # ---- un fuseau inconnu : refusé à l'enregistrement, avec la raison --------------------------------------------------------------
    taper(driver, "Nulle part")
    driver.execute_script("document.getElementById('saveBrandingBtn').click()")
    check("l'enregistrement d'un fuseau inconnu est refusé avec un message clair",
          wait_for(lambda: "Fuseau horaire inconnu" in driver.find_element("tag name", "body").text), driver.find_element("tag name", "body").text[-300:])
    check("le réglage n'a pas changé", reglage(driver) == "Europe/Paris", str(reglage(driver)))

    # ---- un fuseau tapé est enregistré, même absent de la liste proposée -----------------------------------------------------------
    driver.get(inst.url("/admin-personnalisation.html"))
    wait_for(lambda: valeur() == "Europe/Paris")
    taper(driver, "Réunion")
    driver.execute_script("document.getElementById('saveBrandingBtn').click()")
    check("un lieu tapé (« Réunion ») est enregistré sous son nom de fuseau", wait_for(lambda: reglage(driver) == "Indian/Reunion"), str(reglage(driver)))
    driver.get(inst.url("/admin-personnalisation.html"))
    check("il est restitué à la réouverture", wait_for(lambda: valeur() == "Indian/Reunion"), valeur())

    noms = {nom for nom, _ in suggestions}
    absent = next((z for z in ("America/Montreal", "Asia/Calcutta", "US/Eastern", "Europe/Belfast") if z not in noms), None)
    if absent:
        taper(driver, absent)
        driver.execute_script("document.getElementById('saveBrandingBtn').click()")
        check(f"un fuseau valide absent de la liste proposée se tape et s'enregistre ({absent})", wait_for(lambda: reglage(driver) == absent), str(reglage(driver)))
    refus = api_put(driver, "Nulle/Part")
    check("le serveur refuse toujours un nom inconnu (API)", refus["status"] == 400 and "Fuseau horaire inconnu" in str(refus["json"]), str(refus))

    errors = [e for e in inst.console_errors(driver) if "favicon" not in e and "400" not in e]
    check("aucune erreur JavaScript", not errors, str(errors)[:300])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
