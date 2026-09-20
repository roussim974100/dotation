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
        # 404 accepte pour /api/debug : routes fermees en production (aucune information, meme pas leur existence)
        if response.status_code not in (301, 302, 303, 307, 308, 401, 403) and not (path.startswith("/api/debug/") and response.status_code == 404):
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

# Seuil d'alerte pilotage (timing_warning_days) : le changer modifie bien l'etat « En danger » des dossiers listes (et rien d'autre).
import datetime as _dt
_start = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()
_form = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "PILOTAGE", "prenom": "Test", "qualite": "agent", "datePriseFonction": _start},
         "resources": {"additional": [{"id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel", "requiresReturn": True,
                                       "selected": True, "fields": {"marque": "X"}, "details": ""}]},
         "workflow": {"status": "draft"}, "meta": {"startAt": _start}}
admin.post("/api/forms", json=_form, headers=H)


def _pilotage():
    rows = admin.get("/api/forms").get_json() or []
    row = next((x for x in rows if x.get("nom") == "PILOTAGE"), {})
    return [row.get("timingStatus"), row.get("timingLabel")]


admin.put("/api/admin/settings", json={"timing_warning_days": 3}, headers=H)
results["pilotage_seuil_3"] = _pilotage()
admin.put("/api/admin/settings", json={"timing_warning_days": 7}, headers=H)
results["pilotage_seuil_7"] = _pilotage()
results["pilotage_public_payload"] = (admin.get("/api/settings/public").get_json() or {}).get("timingWarningDays")
admin.put("/api/admin/settings", json={"timing_warning_days": 3}, headers=H)
results["pilotage_retour_seuil_3"] = _pilotage()
_stats_a = (admin.get("/api/admin/dashboard-stats").get_json() or {}).get("timing_distribution")
admin.put("/api/admin/settings", json={"timing_warning_days": 30}, headers=H)
results["synthese_inchangee_par_le_seuil"] = _stats_a == (admin.get("/api/admin/dashboard-stats").get_json() or {}).get("timing_distribution")
admin.put("/api/admin/settings", json={"timing_warning_days": 3}, headers=H)

# Anciens dossiers : valeurs saisies sous d'anciens noms (nomPoste, numeroSerie, adresse), catalogue aux noms actuels (nom_du_poste...).
admin.post("/api/admin/resources", json={
    "code": "poste_ancien", "label": "Poste ancien", "description": "", "category": "materiel", "issuer_service": "DSI", "requires_return": True,
    "has_assignment_date": True, "has_assignment_condition": True, "has_assignment_notes": True, "display_order": 900, "is_active": True, "tracking_mode": "unit",
    "field_schema": [{"key": "nom_du_poste", "label": "Nom du poste", "type": "text", "required": False},
                     {"key": "marque", "label": "Marque", "type": "text", "required": True},
                     {"key": "numero_de_serie", "label": "N° de série", "type": "text", "required": True, "identifier": True},
                     {"key": "adresse_email", "label": "Adresse e-mail", "type": "text", "required": False}]}, headers=H)
_legacy = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "ANCIEN", "prenom": "Champs", "qualite": "agent"},
           "resources": {"additional": [{"id": 1, "code": "poste_ancien", "label": "Poste ancien", "category": "materiel", "requiresReturn": True, "selected": True,
                                         "fields": {"marque": "HP", "nomPoste": "PC-ANCIEN-1", "numeroSerie": "SN-ANCIEN-1", "adresse": "ancien@exemple.fr"}, "details": ""}]},
           "workflow": {"status": "draft"}, "meta": {}}
_created = admin.post("/api/forms", json=_legacy, headers=H).get_json() or {}
_fid = (_created.get("summary") or {}).get("id")
_read = (admin.get(f"/api/forms/{_fid}").get_json() or {}).get("data", {}) if _fid else {}
_fields = (((_read.get("resources") or {}).get("additional") or [{}])[0]).get("fields", {})
results["legacy_fields_aligned"] = {k: _fields.get(k) for k in ("nom_du_poste", "numero_de_serie", "adresse_email", "marque")}
results["legacy_fields_old_keys_kept"] = {k: _fields.get(k) for k in ("nomPoste", "numeroSerie", "adresse")}
results["legacy_form_id"] = _fid
_scan = admin.get("/api/admin/field-health").get_json() or {}
results["health_scan_before"] = sorted((o["field"], o["target"]) for o in _scan.get("orphans", []) if o["code"] == "poste_ancien")
_rep = admin.post("/api/admin/field-health/repair", headers=H).get_json() or {}
results["health_repaired_fields"] = _rep.get("repairedFields")
_scan2 = admin.get("/api/admin/field-health").get_json() or {}
results["health_scan_after"] = [o for o in _scan2.get("orphans", []) if o["code"] == "poste_ancien"]

# ---- Ressources personnalisees de bout en bout : creation, saisie, aller-retour sans perte, renommage de cle, masquage ----
_types = [{"key": "N° de série", "label": "N° de série", "type": "text", "required": True, "identifier": True},
          {"key": "numeroInventaire", "label": "Numéro d'inventaire", "type": "text"},
          {"key": "Adresse e-mail", "label": "Adresse e-mail", "type": "email_with_domain"},
          {"key": "couleur", "label": "Couleur", "type": "select", "options": ["Rouge", "Bleu"]},
          {"key": "achete_le", "label": "Acheté le", "type": "date"},
          {"key": "prix", "label": "Prix", "type": "number"},
          {"key": "garantie", "label": "Garantie", "type": "checkbox"},
          {"key": "notes", "label": "Notes", "type": "textarea"},
          {"key": "libellé étrange !", "label": "Libellé étrange !", "type": "text"}]
_r = admin.post("/api/admin/resources", json={
    "code": "custom_e2e", "label": "Ressource E2E", "description": "", "category": "materiel", "issuer_service": "DSI", "requires_return": True,
    "has_assignment_date": True, "has_assignment_condition": True, "has_assignment_notes": True, "display_order": 901, "is_active": True,
    "tracking_mode": "unit", "field_schema": _types}, headers=H)
results["e2e_create_status"] = _r.status_code
_rid = next((r["id"] for r in (admin.get("/api/admin/resources").get_json() or []) if r.get("code") == "custom_e2e"), None)


def _schema_now():
    row = next((r for r in (admin.get("/api/admin/resources").get_json() or []) if r.get("code") == "custom_e2e"), {})
    return row.get("field_schema") or row.get("fieldSchema") or []


_sch = _schema_now()
results["e2e_keys"] = [f["key"] for f in _sch]
_values = {f["key"]: {"text": "V-" + f["key"], "email_with_domain": "a@ville.fr", "select": "Rouge", "date": "2026-01-02",
                      "number": "12.5", "checkbox": "true", "textarea": "ligne1 ligne2"}.get(f["type"], "x") for f in _sch}
_body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "E2E", "prenom": "Test", "qualite": "agent"},
         "resources": {"additional": [{"id": _rid, "code": "custom_e2e", "label": "Ressource E2E", "category": "materiel", "requiresReturn": True,
                                       "selected": True, "fieldSchema": _sch, "fields": dict(_values), "details": ""}]},
         "workflow": {"status": "draft"}, "meta": {}}
_c = admin.post("/api/forms", json=_body, headers=H).get_json() or {}
_id = (_c.get("summary") or {}).get("id")


def _fields_of_form():
    data = (admin.get(f"/api/forms/{_id}").get_json() or {}).get("data", {})
    return (((data.get("resources") or {}).get("additional") or [{}])[0]).get("fields", {}), data


_f1, _d1 = _fields_of_form()
results["e2e_roundtrip_lossless"] = all(_f1.get(k) == v for k, v in _values.items())
# PUT(GET) : renvoyer tel quel ce qu'on a lu ne change aucune valeur (idempotence)
admin.put(f"/api/forms/{_id}", json=_d1, headers=H)
_f2, _ = _fields_of_form()
results["e2e_put_get_idempotent"] = _f2 == _f1
# une valeur inconnue du catalogue (ancien nom) survit a un enregistrement
_d1["resources"]["additional"][0]["fields"]["ancienChamp"] = "VALEUR-ORPHELINE"
admin.put(f"/api/forms/{_id}", json=_d1, headers=H)
results["e2e_orphan_kept_on_save"] = _fields_of_form()[0].get("ancienChamp") == "VALEUR-ORPHELINE"
# renommage de la cle d'un champ (meme libelle) : la valeur reste retrouvable, l'alias est memorise, et survit a une sauvegarde sans alias
_new = [dict(f) for f in _sch]
for f in _new:
    f.pop("aliases", None)
    if f["key"] == "numeroinventaire" or f["key"] == "numeroInventaire":
        f["key"] = "inventaire_num"
admin.put(f"/api/admin/resources/{_rid}", json={"field_schema": _new}, headers=H)
_after = _schema_now()
_inv = next((f for f in _after if f["key"] == "inventaire_num"), {})
results["e2e_alias_after_rename"] = _inv.get("aliases")
admin.put(f"/api/admin/resources/{_rid}", json={"field_schema": [{k: v for k, v in f.items() if k != "aliases"} for f in _after]}, headers=H)
results["e2e_alias_survives_next_save"] = next((f for f in _schema_now() if f["key"] == "inventaire_num"), {}).get("aliases")
_f3, _ = _fields_of_form()
results["e2e_value_visible_after_rename"] = _f3.get("inventaire_num") == _values.get("numeroInventaire", _values.get("numeroinventaire"))
# cle deja valide : gardee telle quelle (casse comprise), pas de derive
results["e2e_key_case_preserved"] = "numeroInventaire" in results["e2e_keys"] or "numeroinventaire" in results["e2e_keys"]
# masquage : le champ reste dans le schema
_hid = [dict(f) for f in _after]
for f in _hid:
    if f["key"] == "notes":
        f["hidden"] = True
admin.put(f"/api/admin/resources/{_rid}", json={"field_schema": _hid}, headers=H)
results["e2e_hidden_field_still_in_schema"] = any(f["key"] == "notes" and f.get("hidden") for f in _schema_now())
results["e2e_hidden_value_kept"] = _fields_of_form()[0].get("notes") == "ligne1 ligne2"
results["e2e_pdf_status"] = admin.get(f"/api/forms/{_id}/pdf").status_code
_exp = admin.get("/api/forms/export")
results["e2e_export_contains_values"] = _exp.status_code == 200 and (b"V-" in _exp.data or "V-" in _exp.get_data(as_text=True))

_health = admin.get("/api/admin/health").get_json() or {}
results["health_report"] = {k: _health.get(k) for k in ("integrity", "brokenReferences")}
results["health_report_has_schema_version"] = _health.get("schemaVersion")
results["health_report_status_known"] = _health.get("status") in ("ok", "attention")

# ---- Export puis import d'une base (schema remis a niveau, donnees conservees) ----
_before = len(admin.get("/api/forms").get_json() or [])
_exp = admin.get("/api/admin/db/export")
results["db_export_is_sqlite"] = _exp.status_code == 200 and _exp.data[:15] == b"SQLite format 3"
_imp = admin.post("/api/admin/db/import", data={"file": (io.BytesIO(_exp.data), "export.db")}, content_type="multipart/form-data", headers=H)
results["db_import_status"] = _imp.status_code
results["db_import_keeps_forms"] = len(admin.get("/api/forms").get_json() or []) == _before
_after = admin.get("/api/admin/health").get_json() or {}
results["db_import_health"] = [_after.get("integrity"), _after.get("schemaVersion")]

# Import d'une base « ancienne » (sans table de migrations ni identifiants de champs) : remise a niveau immediate
import sqlite3 as _sql
import tempfile as _tmp
_old_path = os.path.join(_tmp.gettempdir(), "aquai_ancienne_base.db")
open(_old_path, "wb").write(_exp.data)
_oc = _sql.connect(_old_path)
_oc.execute("DROP TABLE IF EXISTS schema_migrations")
_oc.execute("UPDATE resource_catalog SET field_schema_json = REPLACE(field_schema_json, '\"id\": \"fld_', '\"idx\": \"fld_')")
_oc.execute("PRAGMA user_version = 0")
_oc.commit()
_oc.close()
_old_bytes = open(_old_path, "rb").read()
os.unlink(_old_path)
_imp2 = admin.post("/api/admin/db/import", data={"file": (io.BytesIO(_old_bytes), "ancienne.db")}, content_type="multipart/form-data", headers=H)
_h2 = admin.get("/api/admin/health").get_json() or {}
_res = next((r for r in (admin.get("/api/admin/resources").get_json() or []) if r.get("code") == "ordinateur"), {})
results["old_db_import"] = [_imp2.status_code, _h2.get("schemaVersion"), all(f.get("id") for f in (_res.get("field_schema") or _res.get("fieldSchema") or []))]

# ---- Vocabulaire : types de beneficiaires configures acceptes cote serveur, libelles de statut publies ----
admin.put("/api/admin/settings", json={"beneficiary_types": "agent:Agent,elu:Élu(e),stagiaire:Stagiaire"}, headers=H)
_reg = admin.post("/api/forms/regularisation", json={"nom": "VOCAB", "prenom": "Stagiaire", "qualite": "stagiaire", "resourceIds": [_rid]}, headers=H)
_reg_id = (_reg.get_json() or {}).get("form_id")
_reg_read = (admin.get(f"/api/forms/{_reg_id}").get_json() or {}) if _reg_id else {}
results["vocab_custom_type_kept"] = [_reg.status_code, ((_reg_read.get("data") or {}).get("beneficiaire") or {}).get("qualite")]
results["vocab_public_status_labels"] = ((admin.get("/api/settings/public").get_json() or {}).get("statusLabels") or {}).get("awaiting_signature")
from utils import format_beneficiary_label as _fbl  # noqa: E402
results["vocab_label_python"] = _fbl("stagiaire")
admin.put("/api/admin/settings", json={"beneficiary_types": "agent:Agent,elu:Élu(e),stagiaire:Stagiaire,conseiller:Conseiller|mandat"}, headers=H)
_reg2 = admin.post("/api/forms/regularisation", json={"nom": "MANDAT", "prenom": "Conseil", "qualite": "conseiller", "mandat": "Conseiller municipal", "resourceIds": [_rid]}, headers=H)
_reg2_read = (admin.get(f"/api/forms/{(_reg2.get_json() or {}).get('form_id')}").get_json() or {})
results["mandate_custom_type"] = [((_reg2_read.get("data") or {}).get("beneficiaire") or {}).get("mandat"), (_reg2_read.get("summary") or {}).get("title", "")[:20]]
results["mandate_public_flag"] = {t["value"]: t.get("mandate") for t in ((admin.get("/api/settings/public").get_json() or {}).get("beneficiaryTypes") or [])}
admin.put("/api/admin/settings", json={"beneficiary_types": "agent:Agent,elu:Élu(e)"}, headers=H)

# ---- Profil « donnees masquees » avec droit de modification : lecture masquee, ecriture refusee ----
import auth as _auth  # noqa: E402
from database import get_users_db as _gudb  # noqa: E402
with _gudb() as _uc:
    _uc.execute("INSERT OR REPLACE INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) VALUES ('lecteur_masque','Lecteur masque','',?,'masked','2026-01-01','2026-01-01')",
                (json.dumps(["forms.read_list", "forms.read_detail", "forms.view_all", "forms.edit"]),))
_real_get_user_record = _auth.get_user_record
_auth.get_user_record = lambda username: ({"username": "masque", "groups": ["lecteur_masque"], "active": True, "role": "user"} if username == "masque" else _real_get_user_record(username))
masked = app.test_client()
with masked.session_transaction() as _s:
    _s["user"] = "masque"
    _s["csrf_token"] = "jeton"
_mid = ((admin.post("/api/forms", json={"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "MASQUE", "prenom": "Personne", "qualite": "agent"}, "resources": {"additional": []},
                                        "workflow": {"status": "draft"}, "meta": {}}, headers=H).get_json() or {}).get("summary") or {}).get("id")
_masked_read = masked.get(f"/api/forms/{_mid}")
results["masked_can_read"] = _masked_read.status_code
_masked_data = (_masked_read.get_json() or {}).get("data", {})
results["masked_put"] = masked.put(f"/api/forms/{_mid}", json=_masked_data, headers=H).get_json()
results["masked_put_status"] = masked.put(f"/api/forms/{_mid}", json=_masked_data, headers=H).status_code
results["masked_real_name_intact"] = ((admin.get(f"/api/forms/{_mid}").get_json() or {}).get("data", {}).get("beneficiaire") or {}).get("nom")
_auth.get_user_record = _real_get_user_record

# ---- Export / import du parametrage (additif) ----
_cfg = admin.get("/api/admin/config-export")
_cfg_data = json.loads(_cfg.data.decode("utf-8"))
results["config_export"] = [_cfg.status_code, _cfg_data.get("format"), "custom_e2e" in [r["code"] for r in _cfg_data.get("resources", [])], "beneficiaire" in json.dumps(_cfg_data)]
_cfg_data["resources"].append({"code": "import_nouvelle", "label": "Importee", "category": "materiel", "requires_return": True, "tracking_mode": "none",
                               "field_schema": [{"key": "ref", "label": "Référence", "type": "text"}]})
_cfg_data["resources"][0]["label"] = "NE DOIT PAS CHANGER"  # une ressource deja presente n'est jamais modifiee
_first_code = _cfg_data["resources"][0]["code"]
_preview = admin.post("/api/admin/config-import", json=_cfg_data, headers=H).get_json()
_codes_before = sorted(r["code"] for r in (admin.get("/api/admin/resources").get_json() or []))
results["config_preview"] = [_preview["applied"], _preview["plan"]["resourcesToCreate"], "import_nouvelle" in _codes_before]
_applied = admin.post("/api/admin/config-import?apply=1", json=_cfg_data, headers=H).get_json()
_after_codes = {r["code"]: r for r in (admin.get("/api/admin/resources").get_json() or [])}
results["config_apply"] = [_applied["applied"], "import_nouvelle" in _after_codes, _after_codes[_first_code]["label"] != "NE DOIT PAS CHANGER"]
_again = admin.post("/api/admin/config-import?apply=1", json=_cfg_data, headers=H).get_json()
results["config_idempotent"] = [_again["plan"]["resourcesToCreate"], _again["plan"]["servicesToCreate"]]
results["config_bad_file"] = admin.post("/api/admin/config-import", json={"format": "autre"}, headers=H).status_code

# ---- Initialisation idempotente : rejouer init_db() ne change ni le schema ni les donnees ----
from database import get_db as _gdb  # noqa: E402


def _schema_and_counts():
    with _gdb() as _c:
        tables = [r[0] for r in _c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        columns = {t: [r[1] for r in _c.execute(f"PRAGMA table_info({t})").fetchall()] for t in tables}
        counts = {t: _c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables if t not in ("app_logs", "audit_events", "unit_events")}
        return columns, counts, _c.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]


_before_init = _schema_and_counts()
app_module.init_db()
app_module.init_db()
_after_init = _schema_and_counts()
results["init_idempotent_schema"] = _before_init[0] == _after_init[0]
results["init_idempotent_data"] = {k: (v, _after_init[1].get(k)) for k, v in _before_init[1].items() if v != _after_init[1].get(k)}
results["init_idempotent_migrations"] = _before_init[2] == _after_init[2]

# ---- Suppression d'une ressource : refusee si des dossiers la portent, permise sinon ----
results["delete_used_resource"] = [admin.delete(f"/api/admin/resources/{_rid}", headers=H).status_code]
admin.post("/api/admin/resources", json={"code": "jamais_utilisee", "label": "Jamais utilisee", "category": "immateriel", "requires_return": False, "display_order": 990, "is_active": True, "field_schema": []}, headers=H)
_unused = next((r["id"] for r in (admin.get("/api/admin/resources").get_json() or []) if r.get("code") == "jamais_utilisee"), None)
results["delete_unused_resource"] = admin.delete(f"/api/admin/resources/{_unused}", headers=H).status_code if _unused else None

# ---- Verrou optimiste : deux enregistrements successifs a partir de la meme version chargee ----
_lock_body = {"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": "VERROU", "prenom": "Test", "qualite": "agent"},
              "resources": {"additional": []}, "workflow": {"status": "draft"}, "meta": {}}
_lid = ((admin.post("/api/forms", json=_lock_body, headers=H).get_json() or {}).get("summary") or {}).get("id")
_loaded = (admin.get(f"/api/forms/{_lid}").get_json() or {}).get("data", {})
_base = _loaded["meta"]["savedAt"]
_first = dict(_loaded, meta=dict(_loaded["meta"], baseSavedAt=_base))
_first["beneficiaire"] = dict(_first["beneficiaire"], fonction="Premiere modification")
results["lock_first_save"] = admin.put(f"/api/forms/{_lid}", json=_first, headers=H).status_code
_second = dict(_loaded, meta=dict(_loaded["meta"], baseSavedAt=_base))  # meme version de depart : perimee
_second["beneficiaire"] = dict(_second["beneficiaire"], fonction="Seconde modification")
_r2 = admin.put(f"/api/forms/{_lid}", json=_second, headers=H)
results["lock_second_save"] = [_r2.status_code, (_r2.get_json() or {}).get("error")]
results["lock_value_kept"] = ((admin.get(f"/api/forms/{_lid}").get_json() or {}).get("data", {}).get("beneficiaire") or {}).get("fonction")
_nobase = dict(_loaded)
_nobase["meta"] = {k: v for k, v in _loaded["meta"].items() if k != "baseSavedAt"}
results["lock_without_base_still_saves"] = admin.put(f"/api/forms/{_lid}", json=_nobase, headers=H).status_code

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
