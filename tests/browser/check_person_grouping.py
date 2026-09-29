"""3.67.1 : regroupement des dossiers d'une meme personne dans les tableaux de bord (ligne principale + historique
deplie avec le detail de chaque dossier, progression agregee sur la ligne ET au survol Pilotage, panneau qui reste
ouvert apres un nouveau rendu), et reprise d'identite/personId pour "Nouvelle attribution pour cette personne" et
"Changement de service". Instance isolee, base vierge.
    python tests/browser/check_person_grouping.py
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


def resource(code, label):
    return {"id": 1, "code": code, "label": label, "category": "materiel", "requiresReturn": True,
            "selected": True, "fields": {"marque": "X"}, "details": "", "assignedAt": "2026-09-01T09:00:00"}


def create_dossier(driver, resources, person_id="", nom="GUERRIERO", prenom="Lilou", service="DRH"):
    body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": nom, "prenom": prenom, "qualite": "agent", "service": service},
            "resources": {"additional": resources},
            "validation": {"signatureDataUrl": PNG, "rgpdAccepted": True},
            "workflow": {"status": "active"}, "meta": ({"personId": person_id} if person_id else {})}
    created = api(driver, "POST", "/api/forms", body)
    summary = created["json"].get("summary") or {}
    return summary.get("id"), summary.get("personId")


with Instance() as inst:
    driver = inst.driver(width=1400, height=1000)
    driver.get(inst.url("/index.html"))
    time.sleep(2)

    # Dossier A : cree en premier -> son personId sert de reference pour les 2 autres.
    id_a, person_id = create_dossier(driver, [resource("ordinateur", "Ordinateur"), resource("badge", "Badge")])
    check("dossier A créé (2 ressources)", bool(id_a and person_id))

    # Dossier B : reprend le MEME personId (simule "Nouvelle attribution pour cette personne" apres le correctif).
    id_b, _ = create_dossier(driver, [resource("telephone", "Téléphone")], person_id=person_id)
    check("dossier B créé avec le personId repris (1 ressource)", bool(id_b))

    # Dossier C : personId DIFFERENT mais meme identite nom+prenom+service (simule un dossier cree AVANT le
    # correctif de reprise, ou un homonyme dans le meme service - doit quand meme se regrouper par identite).
    id_c, person_id_c = create_dossier(driver, [resource("cles", "Clé")])
    check("dossier C créé avec un personId différent (1 ressource)", bool(id_c) and person_id_c != person_id)

    driver.get(inst.url("/assignments-completed.html"))
    check("la liste affiche Lilou", wait_for(lambda: "GUERRIERO" in js(driver, "return document.body.innerText").upper()))

    count_rows = lambda: js(driver, "return [...document.querySelectorAll('tr.draft-row')].filter(r => r.innerText.includes('GUERRIERO')).length")
    check("une seule ligne visible pour Lilou (pas 3)", wait_for(lambda: count_rows() == 1), str(count_rows()))

    toggle_text = js(driver, "return document.querySelector('[data-person-history-open]')?.textContent.trim() || ''")
    check("le chevron annonce les 2 autres dossiers", "2 autres dossiers" in toggle_text, toggle_text)

    step_labels = js(driver, """
        const row = [...document.querySelectorAll('tr.draft-row')].find(r => r.innerText.includes('GUERRIERO'));
        return [...row.querySelectorAll('.draft-actions__primary .btn-outline-primary')].map(b => b.textContent.trim());
    """)
    check("« Gérer les ressources » et « Restituer » coexistent (2 parcours distincts)",
          "Gérer les ressources" in step_labels and "Restituer" in step_labels, str(step_labels))

    progress = js(driver, """
        const row = [...document.querySelectorAll('tr.draft-row')].find(r => r.innerText.includes('GUERRIERO'));
        return row?.querySelector('.resource-progress__fraction')?.textContent.trim() || '';
    """)
    check("la progression de la ligne est agrégée sur les 3 dossiers (4/4)", progress == "4/4", progress)

    # Deplier l'historique : chaque dossier doit afficher CE QU'IL CONTIENT, pas juste son titre (identique partout).
    js(driver, "document.querySelector('[data-person-history-open]').click()")
    check("l'historique se déplie", wait_for(lambda: js(
        driver, "return !document.querySelector('.person-history-panel')?.classList.contains('d-none')")))
    # Le dossier C (le plus recemment cree) devient la ligne principale (tri par derniere modification) : les 2
    # AUTRES dossiers (A et B) sont ceux attendus dans l'historique deplie.
    history_text = js(driver, "return document.querySelector('.person-history-panel')?.innerText || ''")
    check("l'historique détaille le contenu de chaque dossier (pas le titre générique)",
          "Téléphone" in history_text and "Ordinateur" in history_text, history_text[:200])

    # Le panneau reste ouvert apres un nouveau rendu (simule l'actualisation automatique toutes les 20s).
    js(driver, "void renderDraftList();")
    time.sleep(0.5)
    check("le panneau reste ouvert après un nouveau rendu (actualisation auto)", wait_for(lambda: js(
        driver, "return !document.querySelector('.person-history-panel')?.classList.contains('d-none')")))

    # Survol Pilotage : doit reprendre le total agrege, pas le seul dossier principal.
    js(driver, "document.querySelector('[data-timing-preview-id]').dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}))")
    check("le survol Pilotage affiche le total agrégé sur les 3 dossiers", wait_for(lambda: "cumulé sur 3 dossiers" in js(
        driver, "return document.getElementById('statusHoverCard')?.innerText || ''")))

    # "Nouvelle attribution pour cette personne" reprend l'identite, la date de prise de fonction ET le personId.
    driver.get(inst.url(f"/form.html?prefillFrom={id_a}"))
    check("le nom est repris", wait_for(lambda: js(driver, "return document.getElementById('nom').value") == "GUERRIERO"))
    check("le personId est repris (garantit le regroupement futur)",
          js(driver, "return document.getElementById('retraitsSourcePersonId').value") == person_id)
    check("la date de prise de fonction est reprise (n'est plus vide)",
          js(driver, "return document.getElementById('start_at').value") != "")

    # "Changement de service" propose aussi la reprise d'identite (avant : reserve a "mise a jour" seulement).
    driver.get(inst.url("/form.html"))
    time.sleep(2)
    js(driver, "document.getElementById('dossier_type').value = 'changement_service'; "
               "document.getElementById('dossier_type').dispatchEvent(new Event('change'))")
    check("le sélecteur « Dossier précédent » apparaît pour un changement de service", wait_for(lambda: not js(
        driver, "return document.getElementById('sourceFormPickerBlock').classList.contains('d-none')")))

    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:400])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
