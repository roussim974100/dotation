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
