"""Mesure le defilement horizontal des vues du tableau de bord, a plusieurs largeurs d'ecran."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

PAGES = ["/index.html", "/assignments-completed.html", "/restitutions-pending.html", "/restitutions-completed.html"]
WIDTHS = [1280, 1366, 1536, 1920]

JS = """
const wrap = document.querySelector('.table-responsive');
const table = document.querySelector('table.draft-table');
const rows = document.querySelectorAll('#draftList tr').length;
const cols = [...document.querySelectorAll('#draftTableHead th')].map(th => ({t: th.textContent.trim().slice(0,18), w: Math.round(th.getBoundingClientRect().width)}));
return {rows, page: [document.documentElement.scrollWidth, document.documentElement.clientWidth],
  wrap: wrap ? [wrap.scrollWidth, wrap.clientWidth] : null, table: table ? Math.round(table.getBoundingClientRect().width) : null, cols};
"""

if __name__ == "__main__":
    only = sys.argv[1:] or None
    with Instance(copy_db="backend/dotation.db") as inst:
        for width in WIDTHS:
            driver = inst.driver(width=width)
            for page in PAGES:
                if only and page not in only:
                    continue
                driver.get(inst.url(page))
                import time
                time.sleep(2.5)
                result = driver.execute_script(JS)
                over = result["wrap"] and result["wrap"][0] > result["wrap"][1] + 1
                print("%5d px %-30s lignes=%-3s tableau=%-5s conteneur=%-12s %s" % (
                    width, page, result["rows"], result["table"], result["wrap"], "  <-- DEFILEMENT HORIZONTAL" if over else "ok"))
                if width == WIDTHS[1]:
                    print("        colonnes:", ", ".join("%s=%s" % (c["t"], c["w"]) for c in result["cols"]))
            driver.quit()
