"""Trouve les elements qui debordent de la fenetre (cause d'un defilement horizontal de la page)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

JS = """
var vw = document.documentElement.clientWidth;
var out = [];
function depthOf(e) { var d = 0; while (e.parentElement) { d++; e = e.parentElement; } return d; }
var all = document.querySelectorAll('body *');
for (var i = 0; i < all.length; i++) {
  var el = all[i];
  var r = el.getBoundingClientRect();
  if (r.width > 0 && r.right > vw + 1) {
    var cs = getComputedStyle(el);
    out.push({tag: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + Array.prototype.slice.call(el.classList, 0, 3).join('.'),
              width: Math.round(r.width), right: Math.round(r.right), minW: cs.minWidth, w: cs.width, depth: depthOf(el)});
  }
}
out.sort(function (a, b) { return a.depth - b.depth; });
return {vw: vw, scroll: document.documentElement.scrollWidth, items: out.slice(0, 12)};
"""

if __name__ == "__main__":
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1280
    page = sys.argv[2] if len(sys.argv) > 2 else "/index.html"
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=width)
        driver.get(inst.url(page))
        time.sleep(2.5)
        result = driver.execute_script(JS)
        print("fenetre %d | largeur de la page %d" % (result["vw"], result["scroll"]))
        for item in result["items"]:
            print("  prof.%-2d %-52s largeur=%-5d droite=%-5d min-width=%-8s width=%s" % (
                item["depth"], item["tag"][:52], item["width"], item["right"], item["minW"], item["w"]))
