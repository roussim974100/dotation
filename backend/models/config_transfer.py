"""Export / import du paramétrage (Administration) : reprendre la configuration d'une installation dans une autre
(preprod -> prod, modèle pour un nouveau site). Sans dossier ni donnée personnelle : réglages d'organisation, services, ressources et champs.

Import ADDITIF : réglages appliqués (liste blanche), services et ressources créés s'ils n'existent pas ; une ressource déjà présente
(même code) n'est JAMAIS modifiée. `apply=False` ne fait que calculer le plan."""
import json

from models.catalog import normalize_resource_catalog_payload
from models.org_presets import WIZARD_SETTING_KEYS
from models.resource_rules import blocking_issues, validate_resource
from models.settings import SettingsValidationError, get_app_settings, save_app_settings
from utils import bool_to_int, generate_id, utc_now

FORMAT = "aquai-config"
VERSION = 1
SETTING_KEYS = WIZARD_SETTING_KEYS + ("theme_id", "dark_mode_policy")


def export_config(connection):
    settings = get_app_settings(connection)
    services = [{"label": r["label"], "is_active": bool(r["is_active"])}
                for r in connection.execute("SELECT label, is_active FROM service_catalog ORDER BY label COLLATE NOCASE").fetchall()]
    resources = []
    for row in connection.execute("SELECT * FROM resource_catalog ORDER BY display_order, label").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        resources.append({
            "code": row["code"], "label": row["label"], "description": row["description"], "category": row["category"],
            "issuer_service": row["issuer_service"], "requires_return": bool(row["requires_return"]),
            "has_assignment_date": bool(row["has_assignment_date"]), "has_assignment_condition": bool(row["has_assignment_condition"]),
            "has_assignment_notes": bool(row["has_assignment_notes"]), "display_order": row["display_order"],
            "trigger_key": row["trigger_key"], "tracking_mode": row["tracking_mode"], "is_active": bool(row["is_active"]),
            "field_schema": schema,
        })
    return {"format": FORMAT, "version": VERSION, "exportedAt": utc_now(),
            "settings": {k: settings.get(k, "") for k in SETTING_KEYS}, "services": services, "resources": resources}


def import_config(connection, data, apply=False):
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise SettingsValidationError("Fichier de paramétrage non reconnu.")
    if int(data.get("version") or 0) > VERSION:
        raise SettingsValidationError("Ce fichier vient d'une version plus récente de l'application.")
    plan = {"settings": [], "servicesToCreate": [], "resourcesToCreate": [], "resourcesSkipped": [], "errors": []}

    updates = {k: v for k, v in (data.get("settings") or {}).items() if k in SETTING_KEYS and isinstance(v, str)}
    current = get_app_settings(connection)
    plan["settings"] = [k for k, v in updates.items() if str(current.get(k, "")) != v]

    existing_services = {r["label"].strip().lower() for r in connection.execute("SELECT label FROM service_catalog").fetchall()}
    for item in data.get("services") or []:
        label = str((item or {}).get("label") or "").strip()
        if label and label.lower() not in existing_services:
            plan["servicesToCreate"].append({"label": label, "is_active": bool((item or {}).get("is_active", True))})
            existing_services.add(label.lower())

    existing_codes = {r["code"] for r in connection.execute("SELECT code FROM resource_catalog").fetchall()}
    to_create = []
    for item in data.get("resources") or []:
        resource = normalize_resource_catalog_payload(item if isinstance(item, dict) else {})
        if not resource["code"] or not resource["label"]:
            plan["errors"].append("Ressource sans code ou sans libellé ignorée.")
            continue
        if resource["code"] in existing_codes:
            plan["resourcesSkipped"].append(resource["code"])
            continue
        issues = blocking_issues(validate_resource(resource))
        if issues:
            plan["errors"].append(f"« {resource['code']} » : " + " ".join(i["message"] for i in issues))
            continue
        plan["resourcesToCreate"].append(resource["code"])
        existing_codes.add(resource["code"])
        to_create.append(resource)

    if not apply:
        return plan
    now = utc_now()
    if updates:
        save_app_settings(connection, updates)  # peut lever SettingsValidationError (ex. type de bénéficiaire encore utilisé)
    for service in plan["servicesToCreate"]:
        connection.execute("INSERT INTO service_catalog (id, label, is_active, is_builtin, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
                           (generate_id("service"), service["label"], bool_to_int(service["is_active"]), now, now))
    for resource in to_create:
        connection.execute(
            """INSERT INTO resource_catalog (id, code, label, description, category, issuer_service, requires_return, has_assignment_date,
               has_assignment_condition, has_assignment_notes, display_order, trigger_key, field_schema_json, is_active, tracking_mode, is_builtin,
               created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (generate_id("resource"), resource["code"], resource["label"], resource["description"], resource["category"], resource["issuer_service"],
             bool_to_int(resource["requires_return"]), bool_to_int(resource["has_assignment_date"]), bool_to_int(resource["has_assignment_condition"]),
             bool_to_int(resource["has_assignment_notes"]), resource["display_order"], resource["trigger_key"],
             json.dumps(resource["field_schema"], ensure_ascii=False), bool_to_int(resource["is_active"]), resource["tracking_mode"], now, now))
    return plan
