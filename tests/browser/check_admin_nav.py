"""Navigation d'administration : même menu latéral groupé sur toutes les sous-pages (journal et corbeille compris), page courante
marquée, fil d'Ariane, ancres propres à la page conservées, pas de scroll horizontal, pas d'erreur JavaScript.
    python tests/browser/check_admin_nav.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

SUBPAGES = {"admin-comptes.html": "Comptes", "admin-services.html": "Services", "admin-ressources.html": "Ressources",
            "admin-ressources-ordre.html": "Ordre des ressources", "admin-personnalisation.html": "Personnalisation",
            "admin-db.html": "Base de données", "logs.html": "Journal", "trash.html": "Corbeille"}
EXPECTED_LINKS = ["Accueil admin", "Comptes", "Services", "Ressources", "Ordre des ressources", "Assistant d'organisation", "Personnalisation",
                  "Base de données", "Parc matériel", "Journal", "Corbeille"]
JS = """
const nav = document.querySelector('.admin-nav');
if (!nav) return JSON.stringify({error: 'pas de menu latéral'});
const links = [...nav.querySelectorAll('a.admin-nav__link:not(.admin-nav__link--local)')].filter(a => !a.hidden).map(a => a.querySelector('span').textContent.trim());
const current = nav.querySelector('[aria-current="page"] span');
const crumbs = [...document.querySelectorAll('.admin-breadcrumb li')].map(li => li.textContent.trim());
const local = [...nav.querySelectorAll('.admin-nav__link--local span')].map(s => s.textContent.trim());
return JSON.stringify({links, current: current && current.textContent.trim(), crumbs, local,
  overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth});
"""
results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


if __name__ == "__main__":
    with Instance() as inst:
        driver = inst.driver(width=1366, height=900)
        for page, label in SUBPAGES.items():
            driver.get(inst.url("/" + page))
            time.sleep(1.8)
            data = json.loads(driver.execute_script(JS))
            check(f"{page} : menu latéral complet et groupé", data.get("links") == EXPECTED_LINKS, str(data)[:250])
            check(f"{page} : page courante « {label} » marquée", data.get("current") == label, str(data.get("current")))
            check(f"{page} : fil d'Ariane Accueil › Administration › {label}", data.get("crumbs") == ["Accueil", "Administration", label], str(data.get("crumbs")))
            check(f"{page} : pas de scroll horizontal", data.get("overflow") is False)
        driver.get(inst.url("/admin-comptes.html"))
        time.sleep(1.8)
        data = json.loads(driver.execute_script(JS))
        check("admin-comptes : les ancres propres à la page sont conservées", data.get("local") == ["Nouveau compte", "Utilisateurs existants", "Les groupes"], str(data.get("local")))
        driver.get(inst.url("/admin-personnalisation.html"))
        time.sleep(1.8)
        visible = driver.execute_script("const b = document.getElementById('saveBrandingBtn').getBoundingClientRect(); return b.top >= 0 && b.bottom <= innerHeight")
        check("Personnalisation : le bouton Enregistrer est visible sans défiler (barre fixée en bas)", visible)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.4)
        visible = driver.execute_script("const b = document.getElementById('saveBrandingBtn').getBoundingClientRect(); return b.top >= 0 && b.bottom <= innerHeight")
        check("... et en bas de page", visible)
        # Mode sombre : les titres et sous-titres du menu latéral restent lisibles (contraste >= 4,5).
        driver.execute_script("localStorage.setItem('userDarkModePreference','dark')")
        driver.refresh()
        time.sleep(2.5)
        worst = driver.execute_script(r"""
          const lum = (c) => { const v = c.match(/[\d.]+/g).map(Number).slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
          const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
          let worst = 99;
          document.querySelectorAll('.admin-nav__link').forEach((a) => { if (a.hidden) return; const bg = getComputedStyle(a).backgroundColor;
            ['span', 'small'].forEach((t) => { worst = Math.min(worst, ratio(getComputedStyle(a.querySelector(t)).color, bg)); }); });
          return worst;""")
        check("mode sombre : menu latéral lisible (contraste >= 4,5)", worst >= 4.5, str(worst))
        driver.execute_script("localStorage.removeItem('userDarkModePreference')")
        driver.get(inst.url("/admin.html"))
        time.sleep(1.8)
        crumbs = driver.execute_script("return [...document.querySelectorAll('.admin-breadcrumb li')].map(li => li.textContent.trim())")
        check("portail admin : fil d'Ariane Accueil › Administration, sans menu latéral en plus", crumbs == ["Accueil", "Administration"] and not driver.find_elements("css selector", ".admin-nav"), str(crumbs))
        titles = driver.execute_script("return [...document.querySelectorAll('main .content-card .section-title')].map(e => e.textContent.trim()).filter(t => !t.startsWith('Configuration')).slice(0, 3)")
        check("portail : trois regroupements (Comptes et droits, Votre organisation, Suivi et exploitation)", titles == ["Comptes et droits", "Votre organisation", "Suivi et exploitation"], str(titles))
        cards = driver.execute_script("return [...document.querySelectorAll('.admin-entry-card')].filter(a => a.offsetParent !== null).map(a => a.querySelector('.draft-title').textContent.trim())")
        check("portail : l'assistant d'organisation est une carte permanente, ainsi que Base de données, Parc, Journal, Corbeille",
              all(name in cards for name in ["Assistant d'organisation", "Base de données", "Parc matériel", "Journal", "Corbeille"]), str(cards))
        errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
        check("aucune erreur JavaScript", not errors, str(errors)[:200])
    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
