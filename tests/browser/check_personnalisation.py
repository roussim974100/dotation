"""Page Personnalisation : CHAQUE champ, modifié seul, est bien enregistré (régression : modifier uniquement « Seuil d'alerte pilotage »
répondait « Aucune modification à enregistrer » et n'envoyait rien). Vérifie aussi que le message « aucune modification » est VISIBLE.
    python tests/browser/check_personnalisation.py                      # instance isolée (base vierge, port 5055)
    python tests/browser/check_personnalisation.py http://127.0.0.1:5000  # serveur local DÉJÀ lancé et connecté (Chrome sur le port 9222) :
                                                                        # les réglages actuels sont sauvegardés puis REMIS à la fin
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_harness import Instance  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

# (id du champ, clé enregistrée, nouvelle valeur, type)
FIELDS = [
    ("brandingOrgName", "org_name", "Commune de Test", "text"),
    ("brandingDpoEmail", "dpo_email", "dpo@test.example", "text"),
    ("brandingEmailDomains", "email_domains", "test.example", "text"),
    ("brandingSupportName", "support_name", "Support Test", "text"),
    ("brandingSupportRole", "support_role", "Responsable test", "text"),
    ("brandingSupportEmail", "support_email", "aide@test.example", "text"),
    ("brandingBeneficiaryTypes", "beneficiary_types", "agent:Agent,elu:Élu(e),stagiaire:Stagiaire", "text"),
    ("brandingPhase1UnlockDays", "restitution_phase1_unlock_days", "4", "text"),
    ("brandingTimingWarningDays", "timing_warning_days", "7", "text"),
    ("brandingParcRetentionYears", "parc_retention_years", "8", "text"),
    ("brandingTheme", "theme_id", "foret", "select"),
    ("brandingDarkMode", "dark_mode_policy", "allowed", "select"),
    ("brandingOrgContext", "org_context", "association", "select"),
]

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))


def raw_settings(driver):
    return driver.execute_script(
        "return fetch('/api/admin/settings', {credentials:'same-origin', cache:'no-store'}).then(r => r.json()).then(j => j.raw)")


def set_value(driver, element_id, value, kind):
    driver.execute_script(
        """const el = document.getElementById(arguments[0]);
           el.value = arguments[1];
           el.dispatchEvent(new Event('input', {bubbles: true}));
           el.dispatchEvent(new Event('change', {bubbles: true}));""", element_id, value)


def run(driver, base):
    for element_id, key, value, kind in FIELDS:
        driver.get(base + "/admin-personnalisation.html")
        time.sleep(2)
        before = str(raw_settings(driver).get(key, ""))
        set_value(driver, element_id, value, kind)
        driver.execute_script("document.getElementById('saveBrandingBtn').click()")
        time.sleep(0.5)
        saved = False
        for _ in range(30):
            time.sleep(0.4)
            if str(raw_settings(driver).get(key, "")) == value:
                saved = True
                break
        check(f"{element_id} modifié SEUL → enregistré ({key})", saved, f"avant={before!r}, après={raw_settings(driver).get(key)!r}")

    # aucune modification : message visible dans la fenêtre, sans envoi
    driver.get(base + "/admin-personnalisation.html")
    time.sleep(2)
    driver.execute_script("document.getElementById('saveBrandingBtn').click()")
    time.sleep(1.2)
    visible = driver.execute_script("""const n = document.getElementById('brandingNotice'); if (!n || n.classList.contains('d-none')) return false;
        const r = n.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && n.textContent.includes('Aucune modification');""")
    check("sans modification : le message « Aucune modification à enregistrer » est visible à l'écran", visible)

    # plusieurs champs à la fois, dont un réglage numérique
    driver.get(base + "/admin-personnalisation.html")
    time.sleep(2)
    set_value(driver, "brandingOrgName", "Commune de Test 2", "text")
    set_value(driver, "brandingTimingWarningDays", "9", "text")
    driver.execute_script("document.getElementById('saveBrandingBtn').click()")
    time.sleep(3)
    raw = raw_settings(driver)
    check("deux champs modifiés ensemble (dont un numérique) : les deux sont enregistrés", raw.get("org_name") == "Commune de Test 2" and str(raw.get("timing_warning_days")) == "9", str(raw)[:120])


RESTORE_KEYS = ("org_name", "dpo_email", "email_domains", "brand_logo_mode", "brand_logo_url", "theme_id", "dark_mode_policy", "org_context",
                "beneficiary_types", "support_name", "support_email", "support_role", "restitution_phase1_unlock_days", "timing_warning_days", "parc_retention_years")


def put_settings(driver, values):
    return driver.execute_script(
        """const values = arguments[0];
           return fetch('/api/csrf-token', {credentials:'same-origin'}).then(r => r.json()).then(t =>
             fetch('/api/admin/settings', {method:'PUT', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRF-Token': t.token}, body: JSON.stringify(values)}).then(r => r.status));""", values)


if __name__ == "__main__":
    target = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else None
    if target:
        from attach import attach
        driver = attach()
        driver.get(target + "/admin-personnalisation.html")
        time.sleep(2.5)
        if "/login" in driver.current_url:
            print("Non connecté sur", target, ": connectez-vous dans la fenêtre Chrome puis relancez.")
            sys.exit(2)
        saved = {k: v for k, v in (raw_settings(driver) or {}).items() if k in RESTORE_KEYS}
        print(f"Cible : {target} (réglages actuels sauvegardés : {len(saved)} champs)")
        try:
            run(driver, target)
        finally:
            status = put_settings(driver, saved)
            after = raw_settings(driver)
            identical = all(str(after.get(k, "")) == str(v) for k, v in saved.items())
            print(f"Réglages d'origine remis (HTTP {status}) : {'identiques à l’état de départ' if identical else 'ÉCART, à vérifier'}")
            results.append(identical)
    else:
        with Instance() as inst:
            driver = inst.driver(width=1366, height=900)
            run(driver, inst.url(""))
            errors = [e for e in inst.console_errors(driver) if "favicon" not in e]
            check("aucune erreur JavaScript", not errors, str(errors)[:200])
    print(f"\n{sum(results)}/{len(results)} vérifications réussies")
    sys.exit(0 if all(results) else 1)
