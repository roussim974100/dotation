"""Dans le tableau du dashboard, trouve les elements qui depassent du conteneur .table-responsive."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402

JS = """
var wrap = document.querySelector('.table-responsive');
var right = wrap.getBoundingClientRect().right;
var out = [];
var all = wrap.querySelectorAll('*');
for (var i = 0; i < all.length; i++) {
  var el = all[i], r = el.getBoundingClientRect();
  if (r.width > 0 && r.right > right + 1) {
    out.push({tag: el.tagName.toLowerCase() + '.' + Array.prototype.slice.call(el.classList, 0, 3).join('.'), width: Math.round(r.width), over: Math.round(r.right - right),
              text: (el.children.length === 0 ? el.textContent.trim().slice(0, 30) : ''), ws: getComputedStyle(el).whiteSpace});
  }
}
return {wrap: [wrap.scrollWidth, wrap.clientWidth], items: out.slice(0, 14)};
"""
if __name__ == "__main__":
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1100
    page = sys.argv[2] if len(sys.argv) > 2 else "/index.html"
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=width)
        driver.get(inst.url(page))
        time.sleep(2.5)
        result = driver.execute_script(JS)
        print("fenetre", width, "| tableau", result["wrap"])
        for it in result["items"]:
            print("  %-46s largeur=%-4d depasse de %-4d white-space=%-8s %r" % (it["tag"][:46], it["width"], it["over"], it["ws"], it["text"]))
