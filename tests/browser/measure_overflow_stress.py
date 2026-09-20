"""Defilement horizontal : ecrans etroits (zoom Windows 125/150 %) et contenu long (noms, services, chips)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

JS_STRESS = """
document.querySelectorAll('#draftList tr').forEach((tr) => {
  const t = tr.querySelector('.draft-title'); if (t) t.textContent = 'DUPONT-MARTIN Marie-Christine — Direction générale des services techniques';
  const m = tr.querySelector('.draft-meta'); if (m) m.textContent = 'Prise de fonction : 12/09/2026 · Service des espaces verts et du patrimoine arboré';
});
"""
JS_MEASURE = """
const wrap = document.querySelector('.table-responsive');
const cols = [...document.querySelectorAll('#draftTableHead th')].map(th => th.textContent.trim().slice(0,12) + '=' + Math.round(th.getBoundingClientRect().width));
return {wrap: [wrap.scrollWidth, wrap.clientWidth], page: [document.documentElement.scrollWidth, document.documentElement.clientWidth], cols};
"""

if __name__ == "__main__":
    widths = [int(w) for w in sys.argv[1:]] or [800, 900, 1024, 1100, 1200, 1280]
    with Instance(copy_db="backend/dotation.db") as inst:
        for width in widths:
            driver = inst.driver(width=width, height=900)
            driver.get(inst.url("/index.html"))
            time.sleep(2.5)
            for label, stress in (("donnees reelles", False), ("contenu long", True)):
                if stress:
                    driver.execute_script(JS_STRESS)
                    time.sleep(0.3)
                r = driver.execute_script(JS_MEASURE)
                over = r["wrap"][0] > r["wrap"][1] + 1
                print("%5d px | %-15s | conteneur %s | page %s | %s" % (width, label, r["wrap"], r["page"], "DEFILEMENT (+%d px)" % (r["wrap"][0] - r["wrap"][1]) if over else "ok"))
                if over:
                    print("          colonnes:", ", ".join(r["cols"]))
            driver.quit()
