"""Audit du MODE SOMBRE : mesure le contraste réel (texte / fond effectif) de chaque texte visible, page par page, sur une instance
isolée avec des données fictives. Liste les couples illisibles (< 4,5, ou < 3 pour les grands textes).
    python tests/browser/audit_dark.py [page ...]
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "docs" / "presentation"))
import demo_data  # noqa: E402
from browser_harness import Instance  # noqa: E402

PAGES = ["index.html", "assignments-completed.html", "restitutions-pending.html", "restitutions-completed.html", "form.html", "parc.html",
         "executive-dashboard.html", "admin.html", "admin-comptes.html", "admin-services.html", "admin-ressources.html",
         "admin-ressources-ordre.html", "admin-personnalisation.html", "admin-db.html", "logs.html", "trash.html", "help.html",
         "about.html", "contact.html", "account.html"]

AUDIT_JS = r"""
const parse = (c) => { const m = c.match(/[\d.]+/g); if (!m) return null; const v = m.map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
const lin = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
const over = (top, bottom) => ({ r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a), b: top.b * top.a + bottom.b * (1 - top.a), a: 1 });
function bgOf(el) {
  const layers = [];
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const cs = getComputedStyle(n);
    let c = parse(cs.backgroundColor);
    if ((!c || c.a === 0) && cs.backgroundImage && cs.backgroundImage.includes('gradient')) {
      const stops = cs.backgroundImage.match(/rgba?\([^)]+\)/g);
      if (stops) { const cols = stops.map(parse).filter(Boolean); c = { r: cols.reduce((s, x) => s + x.r, 0) / cols.length, g: cols.reduce((s, x) => s + x.g, 0) / cols.length, b: cols.reduce((s, x) => s + x.b, 0) / cols.length, a: 1 }; }
    }
    if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
  }
  let base = { r: 0, g: 0, b: 0, a: 1 };
  const bodyBg = parse(getComputedStyle(document.body).backgroundColor); if (bodyBg && bodyBg.a > 0) base = bodyBg;
  for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
  return base;
}
const visible = (el) => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; const cs = getComputedStyle(el);
  if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.1) return false; return true; };
const seen = new Map();
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
while (walker.nextNode()) {
  const t = walker.currentNode; const text = t.textContent.trim(); if (!text) continue;
  const el = t.parentElement; if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION'].includes(el.tagName)) continue;
  if (!visible(el)) continue;
  const cs = getComputedStyle(el);
  const fg = parse(cs.color); if (!fg) continue;
  const bg = bgOf(el);
  const fgEff = fg.a < 1 ? over(fg, bg) : fg;
  const ratio = (Math.max(lum(fgEff), lum(bg)) + 0.05) / (Math.min(lum(fgEff), lum(bg)) + 0.05);
  const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
  const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
  if (ratio < need) {
    const key = el.tagName.toLowerCase() + '.' + (el.className && el.className.baseVal === undefined ? String(el.className).split(' ').slice(0, 2).join('.') : '') + ' | ' + cs.color + ' on ' + `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`;
    const entry = seen.get(key) || { key, ratio: Math.round(ratio * 10) / 10, n: 0, sample: text.slice(0, 40) };
    entry.n += 1; seen.set(key, entry);
  }
}
return JSON.stringify([...seen.values()].sort((a, b) => a.ratio - b.ratio));
"""


def api(driver, method, path, body=None):
    script = ("const [m,p,b]=arguments;return fetch(p,{method:m,credentials:'same-origin',headers:{'Content-Type':'application/json',"
              "'X-CSRF-Token':'jeton-navigateur'},body:b?JSON.stringify(b):undefined}).then(async r=>({status:r.status}))")
    return driver.execute_script(script, method, path, body)


def seed(driver):
    api(driver, "POST", "/api/setup/complete", {"org_name": "Ville de Démonstration", "dpo_email": "dpo@ville-demo.example", "org_context": "public_collectivite",
                                                 "beneficiary_types": "agent:Agent,elu:Élu(e)", "support_email": "aide@ville-demo.example"})
    api(driver, "POST", "/api/admin/resources", {"code": "polo", "label": "Polo de service", "description": "", "category": "materiel", "issuer_service": "RH",
        "requires_return": True, "has_assignment_date": True, "has_assignment_condition": True, "has_assignment_notes": True, "display_order": 500,
        "is_active": True, "tracking_mode": "quantity", "field_schema": [{"key": "quantite", "label": "Quantité", "type": "number", "required": True}]})
    api(driver, "POST", "/api/stock/polo/movements", {"kind": "receipt", "quantity": 3, "variant": "M", "notes": "test"})
    api(driver, "PUT", "/api/stock/polo/threshold", {"threshold": 5})
    plan = [(0, {"status": "active"}), (1, {"status": "active"}), (2, {"status": "draft"}), (3, {"status": "active", "returned": {"ordinateur": "degrade"}}),
            (4, {"status": "active", "returned": {"ordinateur": "conforme"}}), (5, {"status": "draft"})]
    for index, kwargs in plan:
        api(driver, "POST", "/api/forms", demo_data.payload(index, **kwargs))


if __name__ == "__main__":
    pages = sys.argv[1:] or PAGES
    with Instance(port=5075) as inst:
        driver = inst.driver(width=1366, height=900)
        driver.get(inst.url("/parc.html"))
        seed(driver)
        driver.execute_script("localStorage.setItem('userDarkModePreference','dark')")
        total = 0
        for page in pages:
            driver.get(inst.url("/" + page))
            time.sleep(2.2)
            if driver.execute_script("return document.documentElement.dataset.colorMode") != "dark":
                driver.refresh()
                time.sleep(2.2)
            try:
                found = json.loads(driver.execute_script(AUDIT_JS))
            except Exception as error:
                print(f"== {page} : erreur d'audit {str(error)[:80]}")
                continue
            print(f"== {page} : {len(found)} couple(s) illisible(s)")
            for item in found[:14]:
                print(f"   {item['ratio']:>4} ×{item['n']:<3} {item['key']}   « {item['sample']} »")
            total += len(found)
        print(f"\nTotal : {total} couple(s) à corriger")
