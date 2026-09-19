"""Injecte un CSS candidat dans les vues du tableau de bord et mesure le defilement horizontal (page et tableau)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

PAGES = ["/index.html", "/restitutions-pending.html", "/assignments-completed.html", "/restitutions-completed.html"]
JS = """
var wrap = document.querySelector('.table-responsive');
var cols = Array.prototype.map.call(document.querySelectorAll('#draftTableHead th'), function (th) { return th.textContent.trim().slice(0, 10) + '=' + Math.round(th.getBoundingClientRect().width); });
return {page: [document.documentElement.scrollWidth, document.documentElement.clientWidth],
        wrap: wrap ? [wrap.scrollWidth, wrap.clientWidth] : null, cols: cols};
"""
STRESS = """
document.querySelectorAll('#draftList tr').forEach(function (tr) {
  var t = tr.querySelector('.draft-title'); if (t) t.textContent = 'DUPONT-MARTIN Marie-Christine — Direction générale des services techniques';
});
"""

if __name__ == "__main__":
    css = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 and sys.argv[1] != "-" else ""
    widths = [int(w) for w in sys.argv[2:]] or [900, 1024, 1100, 1200, 1280, 1366]
    inject = "var s=document.createElement('style');s.textContent=arguments[0];document.head.appendChild(s);"
    bad = 0
    with Instance(copy_db="backend/dotation.db") as inst:
        for width in widths:
            driver = inst.driver(width=width, height=900)
            for page in PAGES:
                driver.get(inst.url(page))
                time.sleep(2.2)
                if css:
                    driver.execute_script(inject, css)
                    time.sleep(0.2)
                driver.execute_script(STRESS)
                r = driver.execute_script(JS)
                page_over = r["page"][0] > r["page"][1] + 1
                wrap_over = r["wrap"] and r["wrap"][0] > r["wrap"][1] + 1
                bad += bool(page_over or wrap_over)
                print("%5d px %-28s page=%-11s tableau=%-12s %s" % (width, page, r["page"], r["wrap"],
                      ("<-- PAGE" if page_over else "") + (" <-- TABLEAU" if wrap_over else "") or "ok"))
                if (page_over or wrap_over) and width in (1280, 1100):
                    print("        colonnes:", ", ".join(r["cols"]))
            driver.quit()
    print("\nCas avec defilement horizontal :", bad)
