"""Fiche d'un objet du Parc en MODE SOMBRE : dates de l'historique de vie visibles (contraste >= 4,5 : WCAG AA), heure affichee
quand elle est connue. Copie de la base de developpement, jamais l'originale.
    python tests/browser/check_dark_fiche.py [numero_de_serie] [chemin_capture.png]"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

JS_CONTRAST = """
function parse(c) { var m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; var p = m[1].split(',').map(parseFloat); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; }
function lum(c) { var f = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); }
function background(el) {
  while (el) { var c = parse(getComputedStyle(el).backgroundColor); if (c && c.a > 0.9) return c; el = el.parentElement; }
  return {r: 255, g: 255, b: 255, a: 1};
}
function ratio(el) {
  var fg = parse(getComputedStyle(el).color), bg = background(el);
  var l1 = lum(fg), l2 = lum(bg);
  return Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100;
}
var out = {when: [], labels: [], notes: [], placeholders: []};
document.querySelectorAll('#parcModalBody .parc-when').forEach(function (e) { out.when.push([e.textContent.trim(), ratio(e)]); });
document.querySelectorAll('#parcModalBody dt').forEach(function (e) { out.labels.push([e.textContent.trim(), ratio(e)]); });
document.querySelectorAll('#parcModalBody .text-muted').forEach(function (e) { if (e.tagName !== 'DT') out.notes.push([e.textContent.trim().slice(0, 25), ratio(e)]); });
document.querySelectorAll('#parcModalBody input[placeholder], #parcModalBody textarea[placeholder]').forEach(function (e) {
  var fg = parse(getComputedStyle(e, '::placeholder').color), bg = background(e);
  var l1 = lum(fg), l2 = lum(bg);
  out.placeholders.push([e.getAttribute('placeholder').slice(0, 25), Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100]);
});
return out;
"""

if __name__ == "__main__":
    serial = sys.argv[1] if len(sys.argv) > 1 else "1215240131726"
    shot = sys.argv[2] if len(sys.argv) > 2 else None
    bad = []
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=1366, height=1100)
        driver.get(inst.url("/parc.html"))
        time.sleep(2.5)
        # vrai mode sombre de l'application : preference utilisateur enregistree, puis rechargement (applyBrandingTheme)
        driver.execute_script("localStorage.setItem('userDarkModePreference', 'dark');")
        driver.get(inst.url("/parc.html"))
        time.sleep(2.5)
        print("mode :", driver.execute_script("return document.documentElement.dataset.colorMode"))
        driver.find_element(By.ID, "parcSearch").send_keys(serial)
        time.sleep(1.5)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "[data-parc-open]"))
        time.sleep(1.5)
        result = driver.execute_script(JS_CONTRAST)
        print("Historique de vie (date : contraste) :")
        for text, ratio in result["when"]:
            print("   %-28s %5.2f %s" % (text, ratio, "OK" if ratio >= 4.5 else "TROP FAIBLE"))
            if ratio < 4.5:
                bad.append(text)
        print("Libellés de la fiche :", [(t, r) for t, r in result["labels"]])
        bad += [t for t, r in result["labels"] + result["notes"] if r < 4.5]
        print("Notes / auteurs :", [(t, r) for t, r in result["notes"]])
        print("Textes d'aide des champs :", result["placeholders"])
        bad += [t for t, r in result["placeholders"] if r < 3.0]  # texte d'aide : seuil WCAG des composants (3:1)
        if shot:
            driver.save_screenshot(shot)
    print("\n=> %s" % ("contraste suffisant partout" if not bad else "contraste insuffisant : %s" % bad))
    sys.exit(0 if not bad else 1)
