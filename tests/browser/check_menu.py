"""Le menu du compte est IDENTIQUE sur toutes les pages (mêmes entrées, même ordre) pour un administrateur.
    python tests/browser/check_menu.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

PAGES = ["index.html", "assignments-completed.html", "restitutions-pending.html", "form.html", "parc.html", "admin.html", "admin-comptes.html",
         "admin-ressources.html", "admin-db.html", "admin-personnalisation.html", "logs.html", "trash.html", "help.html", "account.html",
         "executive-dashboard.html"]
EXPECTED = ["Administration", "Synthèse", "Parc matériel", "Base de données", "Mon profil", "Mode sombre", "Changer le mot de passe", "Aide générale", "Déconnexion"]

JS = """
const items = [...document.querySelectorAll('#userMenu .user-menu__panel .user-menu__item')].filter(e => e.offsetParent !== null || e.closest('#userMenu'))
  .map(e => e.textContent.trim().replace(/^☾ |^☀ /, '').replace(/^Mode (clair|sombre)$/, 'Mode sombre'));
return JSON.stringify(items);
"""

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


if __name__ == "__main__":
    import json
    with Instance() as inst:
        driver = inst.driver(width=1366, height=900)
        for page in PAGES:
            driver.get(inst.url("/" + page))
            time.sleep(1.8)
            try:
                items = json.loads(driver.execute_script(JS))
            except Exception as error:
                items = [f"erreur : {error}"]
            check(f"{page} : menu du compte complet et dans l'ordre", items == EXPECTED, str(items))
    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
