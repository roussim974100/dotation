import json
from datetime import datetime

from utils import (
    slugify_field_key, generate_id,
    format_export_datetime, format_assignment_condition_label,
)


# ---------------------------------------------------------------------------
# Normalisation du schema de champs dynamiques
# ---------------------------------------------------------------------------

def normalize_resource_field_schema(raw_schema):
    allowed_types = {"text", "textarea", "select", "date", "number", "checkbox", "list", "email_with_domain"}
    normalized = []
    for index, field in enumerate(raw_schema or []):
        label = str(field.get("label") or "").strip()
        key = slugify_field_key(field.get("key") or label or f"champ_{index + 1}")
        if not label or not key:
            continue
        field_type = str(field.get("type") or "text").strip().lower() or "text"
        if field_type not in allowed_types:
            field_type = "text"
        options = field.get("options") or []
        if not isinstance(options, list):
            options = []
        normalized.append({
            "key": key,
            "label": label,
            "type": field_type,
            "placeholder": str(field.get("placeholder") or "").strip(),
            "required": bool(field.get("required", False)),
            "options": [str(option).strip() for option in options if str(option or "").strip()],
            "suggest": bool(field.get("suggest", False)),
        })
    return normalized


# ---------------------------------------------------------------------------
# Ressources dynamiques
# ---------------------------------------------------------------------------

def summarize_dynamic_resource(resource):
    # Une ressource dynamique peut être décrite par plusieurs champs saisis
    # ou par un simple détail libre; on prépare ici un résumé stable.
    fields = resource.get("fields") or {}
    if isinstance(fields, dict):
        values = [str(value).strip() for value in fields.values() if str(value or "").strip()]
        if values:
            return " - ".join(values)
    return str(resource.get("details") or "").strip()


def uses_dynamic_resource_assignment_date(resource):
    if not isinstance(resource, dict):
        return True
    if "hasAssignmentDate" in resource or "has_assignment_date" in resource:
        return bool(resource.get("hasAssignmentDate", resource.get("has_assignment_date")))
    return True


def uses_dynamic_resource_assignment_condition(resource):
    if not isinstance(resource, dict):
        return False
    if "hasAssignmentCondition" in resource or "has_assignment_condition" in resource:
        return bool(resource.get("hasAssignmentCondition", resource.get("has_assignment_condition")))
    return False


def uses_dynamic_resource_assignment_notes(resource):
    if not isinstance(resource, dict):
        return False
    if "hasAssignmentNotes" in resource or "has_assignment_notes" in resource:
        return bool(resource.get("hasAssignmentNotes", resource.get("has_assignment_notes")))
    return False


def is_dynamic_resource_complete(resource):
    if not isinstance(resource, dict) or not resource.get("selected"):
        return False
    field_schema = normalize_resource_field_schema(resource.get("fieldSchema") or resource.get("field_schema") or [])
    field_values = resource.get("fields") or {}
    field_values_lower = {k.lower(): v for k, v in field_values.items()}
    if field_schema:
        for field in field_schema:
            value = str(field_values.get(field["key"]) or field_values_lower.get(field["key"].lower()) or "").strip()
            if field.get("required") and not value:
                return False
    elif not summarize_dynamic_resource(resource):
        return False
    if uses_dynamic_resource_assignment_date(resource) and not str(resource.get("assignedAt") or "").strip():
        return False
    return True


def is_dynamic_resource_payload(resource):
    if not isinstance(resource, dict):
        return False
    marker_keys = {
        "fieldSchema",
        "field_schema",
        "fields",
        "issuerService",
        "issuer_service",
        "triggerKey",
        "trigger_key",
        "displayOrder",
        "display_order",
        "requiresReturn",
        "requires_return",
    }
    return any(key in resource for key in marker_keys)


# ---------------------------------------------------------------------------
# Progression et validation des attributions
# ---------------------------------------------------------------------------

def extract_items(payload):
    # Transforme le payload métier en lignes d'équipements persistables.
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    restitution = payload.get("restitution", {})
    item_states = restitution.get("items", {})

    items = [
        ("ordinateur", "materiel", "Ordinateur", materiel.get("ordinateur", {})),
        ("ecran", "materiel", "Écran", materiel.get("ecran", {})),
        ("telephone", "materiel", "Téléphone", materiel.get("telephone", {})),
        ("tablette", "materiel", "Tablette", materiel.get("tablette", {})),
        ("vehicule", "materiel", "Véhicule", materiel.get("vehicule", {})),
        ("badge", "materiel", "Badge d'accès", materiel.get("badge", {})),
        ("cles", "materiel", "Clé(s)", materiel.get("cles", {})),
        ("veste", "materiel", "Veste", materiel.get("veste", {})),
        ("chaussuresSecurite", "materiel", "Chaussures de sécurité", materiel.get("chaussuresSecurite", {})),
        ("autre", "materiel", "Autre matériel", materiel.get("autre", {})),
        ("vpn", "immateriel", "VPN", immateriel.get("vpn", {})),
        ("email", "immateriel", "Email", immateriel.get("email", {})),
        ("zoneAlarme", "immateriel", "Zone alarme", immateriel.get("zoneAlarme", {})),
    ]

    resources_obj = payload.get("resources", {})
    additional = resources_obj.get("additional", []) if isinstance(resources_obj, dict) else []
    for resource in additional:
        items.append((
            resource.get("code") or resource.get("id") or generate_id("resource"),
            resource.get("category") or "materiel",
            resource.get("label") or "Ressource complémentaire",
            resource,
        ))

    extracted = []
    for item_key, category, label, details in items:
        if not isinstance(details, dict) or not details.get("selected"):
            continue

        state = item_states.get(item_key, {})
        return_state = state.get("state") or state.get("condition") or "pending"
        extracted.append(
            {
                "item_key": item_key,
                "category": category,
                "label": label,
                "assigned": True,
                "returned": return_state in {"returned", "returned_damaged", "transferred", "conforme", "degrade"},
                "returned_at": state.get("returnedAt"),
                "return_condition": return_state,
                "notes": state.get("notes"),
                "details_json": json.dumps(details, ensure_ascii=False),
            }
        )

    return extracted


def summarize_assignment_progress(payload):
    requested_items = extract_items(payload)
    total_requested = len(requested_items)
    completed = 0
    for item in requested_items:
        try:
            details = json.loads(item.get("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        if isinstance(details, dict) and (
            is_dynamic_resource_complete(details)
            if is_dynamic_resource_payload(details)
            else bool(details.get("assignedAt"))
        ):
            completed += 1
    start_at = (
        payload.get("meta", {}).get("startAt")
        or payload.get("beneficiaire", {}).get("datePriseFonction")
        or ""
    )
    if total_requested == 0:
        return {
            "startAt": start_at,
            "completed": 0,
            "total": 0,
            "ratio": 0,
            "timingStatus": "neutral",
            "timingLabel": "À planifier",
        }

    if completed >= total_requested:
        return {
            "startAt": start_at,
            "completed": completed,
            "total": total_requested,
            "ratio": 1,
            "timingStatus": "ok",
            "timingLabel": "Prêt",
        }

    if not start_at:
        return {
            "startAt": "",
            "completed": completed,
            "total": total_requested,
            "ratio": round(completed / total_requested, 4),
            "timingStatus": "neutral",
            "timingLabel": "À planifier",
        }

    try:
        if len(start_at) == 10:
            start_date = datetime.strptime(start_at, "%Y-%m-%d").date()
        else:
            start_date = datetime.fromisoformat(start_at.replace("Z", "+00:00")).date()
        days_until_start = (start_date - datetime.now().date()).days
    except ValueError:
        days_until_start = None

    if days_until_start is None:
        timing_status = "neutral"
        timing_label = "À planifier"
    elif days_until_start < 0:
        timing_status = "late"
        timing_label = "En retard"
    elif days_until_start <= 3:
        timing_status = "warning"
        timing_label = "En danger"
    else:
        timing_status = "ok"
        timing_label = "Dans les temps"

    return {
        "startAt": start_at,
        "completed": completed,
        "total": total_requested,
        "ratio": round(completed / total_requested, 4),
        "timingStatus": timing_status,
        "timingLabel": timing_label,
    }


def collect_resource_validation_errors(payload):
    errors = []
    materiel = payload.get("materiel", {})
    immateriel = payload.get("immateriel", {})
    resources_obj = payload.get("resources", {})
    resources = resources_obj.get("additional", []) if isinstance(resources_obj, dict) else []

    fixed_rules = [
        ("ordinateur", materiel.get("ordinateur", {}), [
            ("Marque ordinateur", "marque"),
            ("Modèle ordinateur", "modele"),
            ("Numéro de série ordinateur", "numeroSerie"),
        ]),
        ("ecran", materiel.get("ecran", {}), [
            ("Marque écran", "marque"),
            ("Modèle écran", "modele"),
            ("Numéro de série écran", "numeroSerie"),
        ]),
        ("telephone", materiel.get("telephone", {}), [
            ("Marque téléphone", "marque"),
            ("Modèle téléphone", "modele"),
            ("N° de série (SN)", "numeroSerie"),
        ]),
        ("tablette", materiel.get("tablette", {}), [
            ("Marque tablette", "marque"),
            ("Modèle tablette", "modele"),
            ("Numéro de série tablette", "numeroSerie"),
        ]),
        ("vehicule", materiel.get("vehicule", {}), [
            ("Marque véhicule", "marque"),
            ("Modèle véhicule", "modele"),
            ("Immatriculation", "immatriculation"),
        ]),
        ("badge", materiel.get("badge", {}), [
            ("Numéro de badge", "numero"),
        ]),
        ("autre", materiel.get("autre", {}), [
            ("Description autre matériel", "description"),
        ]),
        ("email", immateriel.get("email", {}), [
            ("Adresse email", "adresse"),
        ]),
    ]

    for _, resource, rules in fixed_rules:
        if not isinstance(resource, dict) or not resource.get("selected"):
            continue
        for label, key in rules:
            value = str(resource.get(key) or "").strip()
            if not value:
                errors.append(f"{label} manquant")
                continue

    if materiel.get("cles", {}).get("selected") and not [value for value in materiel.get("cles", {}).get("values", []) if str(value).strip()]:
        errors.append("Au moins une clé doit être renseignée")

    if immateriel.get("zoneAlarme", {}).get("selected") and not [value for value in immateriel.get("zoneAlarme", {}).get("zones", []) if str(value).strip()]:
        errors.append("Au moins une zone alarme doit être renseignée")

    for resource in resources:
        if not isinstance(resource, dict) or not resource.get("selected"):
            continue
        field_schema = normalize_resource_field_schema(resource.get("fieldSchema") or resource.get("field_schema") or [])
        field_values = resource.get("fields") or {}
        # Index insensible à la casse : slugify_field_key passe les clés en minuscules,
        # mais les valeurs stockées peuvent être en camelCase (ex: "numeroSerie").
        field_values_lower = {k.lower(): v for k, v in field_values.items()}
        if field_schema:
            for field in field_schema:
                value = str(field_values.get(field["key"]) or field_values_lower.get(field["key"].lower()) or "").strip()
                if field.get("required") and not value:
                    errors.append(f"{resource.get('label') or 'Ressource'} : {field['label']} manquant")
                    continue
        elif not summarize_dynamic_resource(resource):
            errors.append(f"{resource.get('label') or 'Ressource complémentaire'} incomplète")
        if uses_dynamic_resource_assignment_date(resource) and not str(resource.get("assignedAt") or "").strip():
            errors.append(f"{resource.get('label') or 'Ressource'} : date d'attribution manquante")

    return errors


# ---------------------------------------------------------------------------
# Statut workflow effectif
# ---------------------------------------------------------------------------

def derive_restitution_workflow_status(item_states, signature_status="", signature_data=""):
    states = list((item_states or {}).values())
    base_status = "returned"
    if states and any((state or {}).get("state") == "non_restitue" for state in states):
        base_status = "partial_return"

    # Une restitution préparée pour signature à distance ne doit pas être
    # considérée comme terminée tant que la signature de restitution n'a pas
    # été effectivement recueillie.
    if base_status == "returned" and signature_status == "deferred" and not signature_data:
        return "awaiting_signature"

    return base_status


def compute_effective_workflow_status(payload):
    # Recalcule le statut métier à partir de l'état réel du dossier.
    # Cela permet aussi de corriger à l'affichage les anciennes fiches
    # enregistrées avec "active" alors que toutes les attributions
    # n'étaient pas encore datées.
    workflow = payload.get("workflow", {})
    current_status = workflow.get("status") or "draft"
    restitution = payload.get("restitution", {})

    if current_status == "cancelled":
        return current_status
    if current_status in {"returned", "partial_return"} or (
        current_status == "awaiting_signature"
        and (
            restitution.get("items")
            or restitution.get("returnedAt")
            or restitution.get("signatureStatus") == "deferred"
        )
    ):
        # Respect l'intention "en attente de finalisation" : si l'utilisateur a
        # explicitement enregistré en attente (pendingFinalization), on ne recalcule
        # pas vers "returned" tant que ce flag est présent.
        if current_status == "partial_return" and restitution.get("pendingFinalization"):
            return "partial_return"
        return derive_restitution_workflow_status(
            restitution.get("items", {}),
            restitution.get("signatureStatus") or "",
            restitution.get("signatureDataUrl") or "",
        )

    validation = payload.get("validation", {})
    has_signature = bool(validation.get("signatureDataUrl"))
    rgpd_accepted = bool(validation.get("rgpdAccepted"))
    resource_errors = payload.get("meta", {}).get("resourceValidationErrors")
    if not isinstance(resource_errors, list):
        resource_errors = collect_resource_validation_errors(payload)

    progress = summarize_assignment_progress(payload)
    if not has_signature and not resource_errors and progress["total"] > 0 and progress["completed"] >= progress["total"]:
        return "awaiting_signature"
    if not has_signature or not rgpd_accepted:
        return "draft"
    if resource_errors or progress["completed"] < progress["total"]:
        return "partial_assignment"

    if current_status == "active":
        return "active"

    return "partial_assignment"


def derive_dossier_status(payload):
    workflow_status = compute_effective_workflow_status(payload)
    has_signature = bool(payload.get("validation", {}).get("signatureDataUrl"))
    has_items = any(
        item.get("selected")
        for section in [payload.get("materiel", {}), payload.get("immateriel", {})]
        for item in section.values()
        if isinstance(item, dict)
    )

    if workflow_status in {"returned", "partial_return"}:
        return "en_restitution"
    if workflow_status == "cancelled":
        return "clos"
    if workflow_status == "awaiting_signature":
        return "en_signature"
    if workflow_status == "active":
        return "actif"
    if workflow_status == "partial_assignment":
        return "partiellement_complete"
    if has_items or has_signature:
        return "en_preparation"
    return "a_preparer"


# ---------------------------------------------------------------------------
# Éligibilité à la restitution et entrées ressources
# ---------------------------------------------------------------------------

def is_restitution_eligible_material_details(details):
    if not isinstance(details, dict):
        return True
    category = details.get("category")
    if category and category != "materiel":
        return False
    if "requiresReturn" in details or "requires_return" in details:
        return bool(details.get("requiresReturn", details.get("requires_return")))
    return True


def describe_assignment_condition(item):
    if not isinstance(item, dict):
        return []
    parts = []
    is_immaterial = item.get("category") == "immateriel"
    show_assignment_date = True
    if is_dynamic_resource_payload(item):
        show_assignment_date = uses_dynamic_resource_assignment_date(item)
    if show_assignment_date and item.get("assignedAt"):
        parts.append(f"Date d'attribution : {format_export_datetime(item.get('assignedAt'))}")
    show_assignment_condition = not is_immaterial
    if is_dynamic_resource_payload(item):
        show_assignment_condition = uses_dynamic_resource_assignment_condition(item)
    if show_assignment_condition and item.get("conditionAttribution"):
        parts.append(f"État à la remise : {format_assignment_condition_label(item.get('conditionAttribution'))}")
    notes = str(item.get("conditionNotes") or "").strip()
    show_assignment_notes = not is_immaterial
    if is_dynamic_resource_payload(item):
        show_assignment_notes = uses_dynamic_resource_assignment_notes(item)
    if notes and show_assignment_notes:
        parts.append(f"Observation de remise : {notes}")
    return parts


def collect_resource_entries(payload):
    _raw_mat = payload.get("materiel") or {}
    _raw_imm = payload.get("immateriel") or {}
    materiel = {k: v for k, v in _raw_mat.items() if isinstance(v, dict)}
    immateriel = {k: v for k, v in _raw_imm.items() if isinstance(v, dict)}
    resources_obj = payload.get("resources", {})
    additional = resources_obj.get("additional", []) if isinstance(resources_obj, dict) else []

    entries = []

    def add_entry(item_key, category, service, label, details, include_if_empty=False, assignment_source=None):
        clean_details = [str(detail).strip() for detail in details if str(detail or "").strip()]
        if not clean_details and not include_if_empty:
            return
        assignment_summary = " - ".join(describe_assignment_condition(assignment_source))
        entries.append(
            {
                "itemKey": item_key,
                "category": category or "materiel",
                "service": service or "Non défini",
                "label": label,
                "details": " - ".join(clean_details) if clean_details else "-",
                "assignedAt": assignment_source.get("assignedAt") if isinstance(assignment_source, dict) else "",
                "assignmentCondition": assignment_source.get("conditionAttribution") if isinstance(assignment_source, dict) else "",
                "assignmentConditionLabel": format_assignment_condition_label(assignment_source.get("conditionAttribution")) if isinstance(assignment_source, dict) and assignment_source.get("conditionAttribution") else "",
                "assignmentConditionNotes": assignment_source.get("conditionNotes") if isinstance(assignment_source, dict) else "",
                "assignmentSummary": assignment_summary,
            }
        )

    if materiel.get("ordinateur", {}).get("selected"):
        item = materiel["ordinateur"]
        add_entry("ordinateur", "materiel", "DSI", "Ordinateur", [item.get("nomPoste"), item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if materiel.get("ecran", {}).get("selected"):
        item = materiel["ecran"]
        add_entry("ecran", "materiel", "DSI", "Écran", [item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if materiel.get("telephone", {}).get("selected"):
        item = materiel["telephone"]
        add_entry("telephone", "materiel", "DSI", "Téléphone", [item.get("nomTelephone"), item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if materiel.get("tablette", {}).get("selected"):
        item = materiel["tablette"]
        add_entry("tablette", "materiel", "DSI", "Tablette", [item.get("nomTablette"), item.get("marque"), item.get("modele"), item.get("numeroSerie")], assignment_source=item)
    if immateriel.get("email", {}).get("selected"):
        add_entry("email", "immateriel", "DSI", "Messagerie", [immateriel["email"].get("adresse")], assignment_source=immateriel["email"])
    if immateriel.get("vpn", {}).get("selected"):
        add_entry("vpn", "immateriel", "DSI", "VPN", [], include_if_empty=True, assignment_source=immateriel["vpn"])
    if materiel.get("badge", {}).get("selected"):
        add_entry("badge", "materiel", "Bâtiment", "Badge d'accès", [materiel["badge"].get("numero")], assignment_source=materiel["badge"])
    if materiel.get("cles", {}).get("selected"):
        add_entry("cles", "materiel", "Bâtiment", "Clé(s)", materiel["cles"].get("values") or [], assignment_source=materiel["cles"])
    if materiel.get("veste", {}).get("selected"):
        add_entry("veste", "materiel", "Bâtiment", "Veste", [], include_if_empty=True, assignment_source=materiel["veste"])
    if materiel.get("chaussuresSecurite", {}).get("selected"):
        add_entry("chaussuresSecurite", "materiel", "Bâtiment", "Chaussures de sécurité", [], include_if_empty=True, assignment_source=materiel["chaussuresSecurite"])
    if immateriel.get("zoneAlarme", {}).get("selected"):
        add_entry("zoneAlarme", "immateriel", "Bâtiment", "Zone alarme", immateriel["zoneAlarme"].get("zones") or [], assignment_source=immateriel["zoneAlarme"])
    if materiel.get("vehicule", {}).get("selected"):
        item = materiel["vehicule"]
        add_entry("vehicule", "materiel", "Autres services", "Véhicule", [item.get("marque"), item.get("modele"), item.get("immatriculation")], assignment_source=item)
    if materiel.get("autre", {}).get("selected"):
        add_entry("autre", "materiel", "Autres services", "Autre ressource", [materiel["autre"].get("description")], assignment_source=materiel["autre"])

    for resource in additional:
        if not resource.get("selected"):
            continue
        add_entry(
            resource.get("code") or resource.get("id") or generate_id("resource"),
            resource.get("category") or "materiel",
            resource.get("issuerService") or resource.get("issuer_service") or "Autres services",
            resource.get("label") or "Ressource complémentaire",
            [summarize_dynamic_resource(resource)],
            assignment_source=resource,
        )

    return entries
