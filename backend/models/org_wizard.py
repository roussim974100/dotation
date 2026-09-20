"""Assistant d'organisation : plan (pur, sans ecriture) puis application (une transaction, sauvegarde prealable, audit).

`plan_org_wizard` est la SEULE fonction qui decide de ce qui change : l'apercu et l'application l'appellent toutes les deux,
et l'application recalcule le plan (jamais de plan venu du navigateur). Regles :
  - creation de ressources seulement a partir de modeles du serveur (jamais de schema venu du client) ;
  - une ressource equivalente deja presente n'est jamais recreee ;
  - desactiver n'est permis que pour une ressource jamais utilisee dans un dossier ;
  - aucun dossier, aucune ressource utilisee, aucun identifiant n'est jamais modifie ni supprime.
"""
import hashlib
import json
import os
import re
import unicodedata

from database import get_db
from models.audit import insert_app_log
from models.catalog import normalize_resource_catalog_payload
from models.org_presets import ORG_CONTEXTS, RESOURCE_TEMPLATES, WIZARD_SETTING_KEYS
from models.resource_rules import blocking_issues, validate_resource
from models.settings import (MAX_TEXT_LENGTH, SettingsValidationError, get_app_settings, normalize_beneficiary_types,
                             save_app_settings)
from utils import bool_to_int, generate_id, utc_now

INT_SETTINGS = {"restitution_phase1_unlock_days": (0, 365), "timing_warning_days": (0, 365), "parc_retention_years": (1, 30)}
CUSTOM_MODES = {"unit", "none", "quantity", "access"}
_LABEL_FORBIDDEN = set("<>&\"\\")


def _slug(text):
    text = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _clean_label(value, what):
    label = str(value or "").strip()
    if not label or len(label) > 80 or any(ch in _LABEL_FORBIDDEN or ord(ch) < 32 for ch in label):
        raise SettingsValidationError(f"Nom invalide pour {what} : 1 à 80 caractères, sans < > & \" ni \\.")
    return label


def _resource_usage(connection, code):
    """Nombre de lignes de dossier qui utilisent cette ressource (0 = jamais utilisee)."""
    used = connection.execute("SELECT COUNT(*) FROM dotation_items WHERE item_key = ?", (code,)).fetchone()[0]
    if used:
        return used
    return connection.execute("SELECT COUNT(*) FROM dotation_forms WHERE payload_json LIKE ?", (f'%"{code}"%',)).fetchone()[0]


def _default_fields_for_mode(mode):
    return {
        "unit": [{"label": "Désignation", "required": True}, {"label": "N° d'identification", "required": True, "identifier": True}],
        "quantity": [{"label": "Quantité", "type": "number", "required": True}],
        "access": [{"label": "Identifiant du compte", "required": True}],
        "none": [],
    }[mode]


def _schema(fields):
    return [{"key": _slug(f["label"]) or "champ", "label": f["label"], "type": f.get("type", "text"),
             "required": bool(f.get("required")), "identifier": bool(f.get("identifier")), "suggest": bool(f.get("suggest"))}
            for f in fields]


def _normalize_settings(raw_settings, current):
    """Valide les reglages proposes et ne garde que ceux qui changent. Retourne la liste [{key, from, to}]."""
    changes = []
    for key in WIZARD_SETTING_KEYS:
        if key not in (raw_settings or {}) or raw_settings[key] is None:
            continue
        value = str(raw_settings[key]).strip()
        if key == "org_context":
            if value not in ORG_CONTEXTS:
                raise SettingsValidationError("Type d'organisation inconnu.")
        elif key == "beneficiary_types":
            value = normalize_beneficiary_types(value)
        elif key in INT_SETTINGS:
            low, high = INT_SETTINGS[key]
            try:
                value = str(max(low, min(high, int(value))))
            except ValueError:
                raise SettingsValidationError(f"« {key} » doit être un nombre entier.")
        elif len(value) > MAX_TEXT_LENGTH:
            raise SettingsValidationError(f"« {key} » est trop long ({MAX_TEXT_LENGTH} caractères max).")
        if value != (current.get(key) or ""):
            changes.append({"key": key, "from": current.get(key) or "", "to": value})
    return changes


def plan_org_wizard(connection, payload):
    """Calcule ce que l'assistant ferait, sans rien ecrire. Leve SettingsValidationError si l'entree est invalide."""
    payload = payload if isinstance(payload, dict) else {}
    settings_changes = _normalize_settings(payload.get("settings"), get_app_settings(connection))
    catalog = {row["code"]: dict(row) for row in connection.execute("SELECT code, label, is_active, is_builtin FROM resource_catalog").fetchall()}
    resources_in = payload.get("resources") if isinstance(payload.get("resources"), dict) else {}
    actions, warnings, taken = [], [], set(catalog)

    for code in dict.fromkeys(resources_in.get("activate") or []):
        row = catalog.get(code)
        if not row:
            actions.append({"action": "blocked", "code": str(code)[:60], "label": "", "reason": "Ressource inconnue."})
        elif row["is_active"]:
            actions.append({"action": "exists", "code": code, "label": row["label"], "reason": "Déjà actif."})
        else:
            actions.append({"action": "activate", "code": code, "label": row["label"], "reason": "Réactivée (aucune donnée n'est modifiée)."})

    for code in dict.fromkeys(resources_in.get("deactivate") or []):
        row = catalog.get(code)
        if not row:
            actions.append({"action": "blocked", "code": str(code)[:60], "label": "", "reason": "Ressource inconnue."})
        elif not row["is_active"]:
            actions.append({"action": "exists", "code": code, "label": row["label"], "reason": "Déjà désactivée."})
        else:
            used = _resource_usage(connection, code)
            if used:
                actions.append({"action": "blocked", "code": code, "label": row["label"],
                                "reason": f"Utilisée dans {used} dossier(s) : elle reste active."})
            else:
                actions.append({"action": "deactivate", "code": code, "label": row["label"],
                                "reason": "Jamais utilisée : masquée des nouveaux dossiers (réactivable à tout moment)."})

    for item in resources_in.get("create") or []:
        item = item if isinstance(item, dict) else {}
        template_id = str(item.get("template") or "")
        custom = template_id == "custom"
        if not custom and template_id not in RESOURCE_TEMPLATES:
            actions.append({"action": "blocked", "code": template_id[:60], "label": "", "reason": "Modèle inconnu."})
            continue
        template = RESOURCE_TEMPLATES.get(template_id)
        if custom:
            mode = str(item.get("mode") or "")
            if mode not in CUSTOM_MODES:
                raise SettingsValidationError("Mode de suivi inconnu pour la ressource sur mesure.")
            label = _clean_label(item.get("label"), "la ressource sur mesure")
            template = {"mode": mode, "label": label, "description": "", "fields": _default_fields_for_mode(mode),
                        "category": "immateriel" if mode == "access" else "materiel", "requires_return": mode != "access", "builtin_codes": []}
        else:
            label = _clean_label(item.get("label") or template["label"], "la ressource")
        equivalent = next((c for c in template["builtin_codes"] if c in catalog), None)
        if equivalent and not custom:
            actions.append({"action": "exists", "code": equivalent, "label": catalog[equivalent]["label"],
                            "reason": "Une ressource équivalente existe déjà : rien à créer."})
            continue
        # Code STABLE (pas de suffixe) : rejouer l'assistant ne recree jamais la meme ressource. Modele : son identifiant ;
        # sur mesure : le nom ; sans caracteres latins, une empreinte du nom (les libelles peuvent etre dans toute langue).
        code = _slug(label) if custom else template_id
        if not code:
            code = "res_" + hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
        if code in taken:
            row = catalog.get(code)
            actions.append({"action": "exists", "code": code, "label": row["label"] if row else label,
                            "reason": "Déjà présent : rien à créer." if row else "Déjà demandé dans ce même plan."})
            continue
        taken.add(code)
        resource = normalize_resource_catalog_payload({
            "code": code, "label": label, "description": template["description"], "category": template["category"],
            "requires_return": template["requires_return"], "tracking_mode": template["mode"], "is_active": True,
            "field_schema": _schema(template["fields"]),
        })
        blocking = blocking_issues(validate_resource(resource))
        if blocking:
            actions.append({"action": "blocked", "code": code, "label": label, "reason": "Configuration invalide : " + ", ".join(i["code"] for i in blocking)})
            continue
        actions.append({"action": "create", "code": code, "label": label, "reason": "Nouvelle ressource.", "resource": resource})

    if not actions and not settings_changes:
        warnings.append("Aucun changement à appliquer.")
    core = {"settings": settings_changes,
            "resources": [{k: v for k, v in a.items() if k != "resource"} | ({"fields": [f["key"] for f in a["resource"]["field_schema"]]} if "resource" in a else {}) for a in actions]}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"settings": settings_changes, "resources": [{k: v for k, v in a.items() if k != "resource"} for a in actions],
            "warnings": warnings, "plan_hash": digest, "_creations": [a["resource"] for a in actions if a["action"] == "create"]}


def public_plan(plan):
    return {k: v for k, v in plan.items() if not k.startswith("_")}


class PlanChanged(Exception):
    """L'etat du serveur ou la demande ont change depuis l'apercu."""


def safety_copy():
    """Copie de la base principale avant application ; retourne le nom du fichier ou None (l'echec est signale, pas bloquant)."""
    try:
        import backup
        from config import DB_PATH
        os.makedirs(backup.BACKUP_DIR, exist_ok=True)
        name = f"avant_assistant_{utc_now().replace(':', '').replace('-', '')[:15]}.db"
        backup.snapshot_sqlite(DB_PATH, os.path.join(backup.BACKUP_DIR, name))
        return name
    except Exception:
        return None


def apply_org_wizard(payload, expected_hash, actor=None):
    """Recalcule le plan, verifie qu'il est identique a celui apercu, sauvegarde puis applique en UNE transaction."""
    with get_db() as connection:
        plan = plan_org_wizard(connection, payload)
    if not expected_hash or plan["plan_hash"] != expected_hash:
        raise PlanChanged()
    copy_name = safety_copy()
    now = utc_now()
    with get_db() as connection:
        plan = plan_org_wizard(connection, payload)  # recalcul dans la transaction d'ecriture
        if plan["plan_hash"] != expected_hash:
            raise PlanChanged()
        for resource in plan["_creations"]:
            connection.execute(
                """INSERT INTO resource_catalog (id, code, label, description, category, issuer_service, requires_return,
                   has_assignment_date, has_assignment_condition, has_assignment_notes, display_order, trigger_key,
                   field_schema_json, is_active, tracking_mode, is_builtin, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (generate_id("resource"), resource["code"], resource["label"], resource["description"], resource["category"],
                 resource["issuer_service"], bool_to_int(resource["requires_return"]), bool_to_int(resource["has_assignment_date"]),
                 bool_to_int(resource["has_assignment_condition"]), bool_to_int(resource["has_assignment_notes"]),
                 resource["display_order"], resource["trigger_key"], json.dumps(resource["field_schema"], ensure_ascii=False),
                 bool_to_int(resource["is_active"]), resource["tracking_mode"], now, now),
            )
        for action in plan["resources"]:
            if action["action"] in ("activate", "deactivate"):
                connection.execute("UPDATE resource_catalog SET is_active = ?, updated_at = ? WHERE code = ?",
                                   (1 if action["action"] == "activate" else 0, now, action["code"]))
        if plan["settings"]:
            save_app_settings(connection, {change["key"]: change["to"] for change in plan["settings"]})
        summary = {
            "created": [a["code"] for a in plan["resources"] if a["action"] == "create"],
            "activated": [a["code"] for a in plan["resources"] if a["action"] == "activate"],
            "deactivated": [a["code"] for a in plan["resources"] if a["action"] == "deactivate"],
            "settings": [{"key": c["key"], "from": c["from"], "to": c["to"]} for c in plan["settings"]],
            "safety_copy": copy_name,
        }
        insert_app_log(connection, "admin", "org_wizard_applied", "Assistant d'organisation appliqué", "settings", "org_wizard",
                       summary, actor=actor)
    return {"applied": True, "summary": summary, "safety_copy": copy_name}
