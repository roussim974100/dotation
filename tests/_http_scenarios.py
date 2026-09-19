"""Scenarios HTTP executes DANS UN SOUS-PROCESSUS avec une base temporaire (APP_DATA_DIR) : aucune vraie base n'est touchee.
Affiche un JSON {nom: resultat} lu par tests/test_http_endpoints.py."""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import app as app_module  # noqa: E402  (cree des bases vierges dans APP_DATA_DIR)

app = app_module.app
results = {}

# Endpoints volontairement publics (pas d'authentification attendue).
PUBLIC_PREFIXES = ("/css/", "/js/", "/assets/", "/api/auth/", "/api/signature/", "/api/restitution-signature/",
                   "/signature/", "/restitution-signature/")
PUBLIC_EXACT = {
    "/", "/login", "/signup", "/logout", "/setup.html", "/api/settings/public", "/api/settings/logo", "/api/client-context",
    "/api/csrf-token", "/api/session", "/api/setup/status", "/api/setup/complete", "/about.html", "/contact.html",
    "/help.html", "/login.html", "/signup.html", "/favicon.ico", "/app-icon.svg", "/api/reference/resources", "/api/reference/services",
}


def fill(rule):
    return re.sub(r"<[^>]+>", "x", rule)


def admin_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["csrf_token"] = "jeton"
    return client


H = {"X-CSRF-Token": "jeton"}
rules = [r for r in app.url_map.iter_rules() if r.endpoint != "static"]

# 1) Aucun endpoint non public ne repond a un anonyme autre que refus / redirection.
anonymous = app.test_client()
leaks = []
for rule in rules:
    path = fill(rule.rule)
    if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES) or path.endswith((".png", ".svg", ".ico")):
        continue
    for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
        response = anonymous.open(path, method=method, json={} if method != "GET" else None)
        if response.status_code not in (301, 302, 303, 307, 308, 401, 403):
            leaks.append("%s %s -> %s" % (method, rule.rule, response.status_code))
results["anonymous_leaks"] = leaks

# 2) Un administrateur ne provoque aucune erreur serveur sur les GET sans parametre.
admin = admin_client()
errors = []
checked = 0
for rule in rules:
    if "GET" not in rule.methods or "<" in rule.rule:
        continue
    if rule.rule in ("/logout",) or rule.rule.endswith((".png", ".svg")):
        continue
    response = admin.get(rule.rule)
    checked += 1
    if response.status_code >= 500:
        errors.append("GET %s -> %s" % (rule.rule, response.status_code))
results["admin_get_errors"] = errors
results["admin_get_checked"] = checked

# 3) Scenarios fonctionnels.
def status(response):
    return response.status_code


def png(size=64):
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * size


r = admin.post("/api/admin/settings/logo-upload", data={"logo": (io.BytesIO(png()), "logo.png")}, headers=H, content_type="multipart/form-data")
results["logo_valid"] = status(r)
r = admin.post("/api/admin/settings/logo-upload", data={"logo": (io.BytesIO(png()), "logo.gif")}, headers=H, content_type="multipart/form-data")
results["logo_bad_extension"] = status(r)
r = admin.post("/api/admin/settings/logo-upload", data={"logo": (io.BytesIO(b"pas un png du tout"), "logo.png")}, headers=H, content_type="multipart/form-data")
results["logo_bad_magic"] = status(r)
r = admin.post("/api/admin/settings/logo-upload", data={"logo": (io.BytesIO(png(2 * 1024 * 1024 + 10)), "logo.png")}, headers=H, content_type="multipart/form-data")
results["logo_too_large"] = status(r)
r = admin.post("/api/admin/settings/logo-upload", data={}, headers=H, content_type="multipart/form-data")
results["logo_missing"] = status(r)

for name, path in (("trash", "/api/admin/trash"), ("logs", "/api/admin/logs"), ("unc_stats", "/api/admin/unc-stats"),
                   ("services_csv_template", "/api/admin/services/csv-template"), ("services_export_csv", "/api/admin/services/export-csv"),
                   ("forms_export", "/api/forms/export"), ("forms_export_unc", "/api/forms/export-unc"),
                   ("catalog_quality", "/api/admin/catalog/quality"), ("stock", "/api/stock"), ("units", "/api/units"),
                   ("units_stats", "/api/units/stats"), ("dashboard_stats", "/api/admin/dashboard-stats"),
                   ("backup_info", "/api/admin/backup/info"), ("groups", "/api/admin/groups"), ("session", "/api/session")):
    results[name] = status(admin.get(path))

body = admin.get("/api/admin/catalog/quality").get_json() or {}
results["catalog_quality_has_total"] = "total" in body
results["services_csv_is_text"] = "text" in (admin.get("/api/admin/services/csv-template").content_type or "")

results["pdf_batch_empty"] = status(admin.post("/api/forms/export-pdf-batch", json={"ids": []}, headers=H))
results["restitution_pdf_batch_empty"] = status(admin.post("/api/forms/export-restitution-pdf-batch", json={"ids": []}, headers=H))
results["restitution_pdf_unknown"] = status(admin.get("/api/forms/inconnu/restitution-pdf"))
results["pdf_unknown"] = status(admin.get("/api/forms/inconnu/pdf"))

r = admin.post("/api/stock/inconnue/movements", json={"kind": "receipt", "quantity": 3}, headers=H)
results["stock_unknown_resource"] = [status(r), (r.get_json() or {}).get("error")]
r = admin.post("/api/units/inconnue/actions", json={"action": "note", "notes": "x"}, headers=H)
results["unit_action_unknown"] = status(r)

# URL de logo : les schemas non http(s) sont refuses cote serveur.
admin.put("/api/admin/settings", json={"brand_logo_url": "file:///etc/passwd"}, headers=H)
saved = admin.get("/api/admin/settings").get_json() or {}
results["logo_url_file_scheme_stored"] = saved.get("brand_logo_url", saved.get("settings", {}).get("brand_logo_url") if isinstance(saved.get("settings"), dict) else None)

# Reglages : une mise a jour partielle ne vide rien, un type de beneficiaire invalide est refuse (400), le setup ne se rejoue pas.
admin.put("/api/admin/settings", json={"org_name": "Organisation Test", "support_email": "aide@test.fr"}, headers=H)
admin.put("/api/admin/settings", json={"theme_id": "foret"}, headers=H)
kept = admin.get("/api/admin/settings").get_json() or {}
kept = kept.get("raw") or {}
results["partial_put_keeps"] = [kept.get("org_name"), kept.get("support_email")]
r = admin.put("/api/admin/settings", json={"beneficiary_types": "agent:A,B"}, headers=H)
results["bad_beneficiary_status"] = status(r)
r = admin.post("/api/setup/complete", json={"org_name": "X", "org_context": "association", "beneficiary_types": "membre:Membre"}, headers=H)
results["setup_first_run"] = status(r)
r = admin.post("/api/setup/complete", json={"org_name": "Pirate", "org_context": "association", "beneficiary_types": "membre:Membre"}, headers=H)
results["setup_rerun_locked"] = status(r)
after = admin.get("/api/admin/settings").get_json() or {}
after = after.get("raw") or {}
results["setup_rerun_org_name"] = after.get("org_name")
r = admin.post("/api/setup/complete", json={"org_name": "Reconfiguree", "org_context": "association", "beneficiary_types": "membre:Membre", "confirm_reconfigure": True}, headers=H)
results["setup_rerun_confirmed"] = status(r)

# Assistant d'organisation : apercu sans ecriture, application uniquement du plan apercu, ajout seulement.
def resource_codes():
    return sorted(r["code"] for r in (admin.get("/api/admin/org-presets").get_json() or {}).get("resources", []))

wizard_before = resource_codes()
wizard_payload = {
    "settings": {"org_context": "other", "beneficiary_types": "member:Membre,staff:员工", "parc_retention_years": "4"},
    "resources": {"create": [{"template": "stock_vetement"}, {"template": "custom", "label": "Instrument de musique", "mode": "unit"}],
                  "deactivate": ["zoneAlarme"], "activate": []},
}
r = admin.post("/api/admin/org-wizard/preview", json=wizard_payload, headers=H)
preview = r.get_json() or {}
results["wizard_preview_status"] = status(r)
results["wizard_preview_writes_nothing"] = resource_codes() == wizard_before
results["wizard_preview_actions"] = sorted((a["action"], a["code"]) for a in preview.get("resources", []))
r = admin.post("/api/admin/org-wizard/apply", json={**wizard_payload, "plan_hash": "faux", "confirmed": True}, headers=H)
results["wizard_apply_bad_hash"] = status(r)
r = admin.post("/api/admin/org-wizard/apply", json={**wizard_payload, "plan_hash": preview.get("plan_hash")}, headers=H)
results["wizard_apply_unconfirmed"] = status(r)
r = admin.post("/api/admin/org-wizard/apply", json={**wizard_payload, "plan_hash": preview.get("plan_hash"), "confirmed": True}, headers=H)
results["wizard_apply_status"] = status(r)
after = admin.get("/api/admin/org-presets").get_json() or {}
results["wizard_created_codes"] = sorted(set(resource_codes()) - set(wizard_before))
results["wizard_zone_alarme_active"] = next((x["is_active"] for x in after.get("resources", []) if x["code"] == "zoneAlarme"), None)
results["wizard_settings_after"] = [after["current"]["org_context"], after["current"]["beneficiary_types"], after["current"]["parc_retention_years"]]
again = (admin.post("/api/admin/org-wizard/preview", json=wizard_payload, headers=H).get_json() or {})
results["wizard_second_preview_creates"] = [a["code"] for a in again.get("resources", []) if a["action"] == "create"]
results["wizard_second_preview_settings"] = again.get("settings")
r = admin.post("/api/admin/org-wizard/preview", json={"resources": {"create": [{"template": "custom", "label": "<img src=x onerror=1>", "mode": "unit"}]}}, headers=H)
results["wizard_xss_label"] = status(r)
r = admin.post("/api/admin/org-wizard/preview", json={"resources": {"create": [{"template": "inconnu"}]}}, headers=H)
results["wizard_unknown_template"] = [status(r), [a["action"] for a in (r.get_json() or {}).get("resources", [])]]
r = admin.post("/api/admin/org-wizard/preview", json={"settings": {"org_context": "nimporte"}}, headers=H)
results["wizard_bad_context"] = status(r)
results["wizard_anonymous"] = [status(app.test_client().get("/api/admin/org-presets")), status(app.test_client().post("/api/admin/org-wizard/apply", json={}))]

checklist = admin.get("/api/admin/startup-checklist").get_json() or {}
results["checklist"] = [checklist.get("total"), sorted(i["id"] for i in checklist.get("items", [])), 0 <= (checklist.get("percent") or -1) <= 100]
results["checklist_wizard_done_after_apply"] = next((i["done"] for i in checklist.get("items", []) if i["id"] == "wizard"), None)
results["checklist_anonymous"] = status(app.test_client().get("/api/admin/startup-checklist"))

# Limitation de connexion : la 11e tentative (meme IP) est refusee, meme avec un en-tete X-Forwarded-For different.
limited = None
for i in range(13):
    resp = app.test_client().post("/login", data={"username": "x", "password": "y"},
                                  headers={"X-Forwarded-For": "10.0.0.%d" % i}, environ_overrides={"REMOTE_ADDR": "8.8.8.8"})
    if "rate_limited" in (resp.headers.get("Location") or ""):
        limited = i + 1
        break
results["login_rate_limited_at_attempt"] = limited

# Mise a jour : la verification reseau est coupee (APP_UPDATE_CHECK=0) ; la mise a jour web est desactivee par defaut.
r = admin.get("/api/admin/update/status")
body = r.get_json() or {}
results["update_status"] = [r.status_code, sorted(body.keys())]
results["update_check_disabled"] = [status(admin.post("/api/admin/update/check", json={}, headers=H)), (admin.post("/api/admin/update/check", json={}, headers=H).get_json() or {}).get("enabled")]
r = admin.post("/api/admin/update/start", json={"password": "admin"}, headers=H)
results["update_start_disabled"] = [r.status_code, (r.get_json() or {}).get("error")]

from auth import build_user_context  # noqa: E402
results["admin_has_parc_manage"] = "parc.manage" in build_user_context("admin")["permissions"]

print("JSON>>" + json.dumps(results))
