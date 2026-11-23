"""3.67.2 : la fenetre "Attribution partielle" (askWorkflowDialog, frontend/js/ui.js) n'avait aucune limite de
hauteur ni defilement interne - avec beaucoup de ressources incompletes, le bouton OK (tout en bas du panneau)
sortait de l'ecran et devenait inatteignable (signale par l'utilisateur, capture d'ecran a l'appui). Instance
isolee, base vierge.
    python tests/browser/check_workflow_dialog_scroll.py
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


def js(driver, script, *args):
    return driver.execute_script(script, *args)


with Instance() as inst:
    # Petite fenetre : garantit le depassement meme si la liste etait raisonnablement courte.
    driver = inst.driver(width=900, height=500)
    driver.get(inst.url("/form.html"))
    time.sleep(2)

    # Une trentaine d'erreurs, comme un dossier avec beaucoup de ressources incompletes.
    items = [f"Ressource {i} : champ manquant" for i in range(30)]
    js(driver, """
        const [title, text, items] = arguments;
        window.__dialogDone = false;
        showSaveInfoDialog(title, text, items).then(() => { window.__dialogDone = true; });
    """, "Attribution partielle", "Certaines ressources cochées ne sont pas complètement renseignées.", items)

    check("la fenêtre s'affiche", js(driver, """
        const el = document.getElementById('workflowDialog');
        return Boolean(el && !el.classList.contains('is-hidden'));
    """))

    # Ressource pas encore renseignee = information, pas un blocage : "Erreur" etait inutilement alarmant
    # pour un dossier qui "reste modifiable" (voir le sous-titre de la fenetre).
    state_text = js(driver, "return document.querySelector('#workflowDialogSteps .workflow-dialog__state')?.textContent || ''")
    check("le libellé est rassurant (« À compléter », pas « Erreur »)", state_text.strip() == "À compléter", state_text)

    check("la liste des erreurs déborde (donc nécessite un défilement interne)", js(driver, """
        const list = document.getElementById('workflowDialogSteps');
        return list.scrollHeight > list.clientHeight;
    """))

    viewport = js(driver, "return window.innerHeight")
    button_rect = js(driver, """
        const btn = document.getElementById('workflowDialogConfirmBtn');
        const r = btn.getBoundingClientRect();
        return {top: r.top, bottom: r.bottom};
    """)
    check("le bouton OK est entièrement visible dans la fenêtre (pas hors écran)",
          button_rect["top"] >= 0 and button_rect["bottom"] <= viewport,
          f"bouton top={button_rect['top']:.0f} bottom={button_rect['bottom']:.0f} vs fenêtre={viewport}")

    js(driver, "document.getElementById('workflowDialogConfirmBtn').click()")
    done = False
    for _ in range(20):
        time.sleep(0.2)
        if js(driver, "return window.__dialogDone === true"):
            done = True
            break
    check("cliquer OK résout bien la fenêtre (le dossier reste modifiable)", done)
    check("la fenêtre se referme après OK", js(driver, """
        const el = document.getElementById('workflowDialog');
        return Boolean(el && el.classList.contains('is-hidden'));
    """))

    errors = [e for e in inst.console_errors(driver) if "/api/debug/" not in e]
    check("aucune erreur console", not errors, str(errors)[:400])

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
