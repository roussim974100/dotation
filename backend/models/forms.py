import json
from datetime import datetime
from flask import session

from utils import (
    utc_now, bool_to_int, normalize_dossier_type,
    build_title, format_export_datetime, get_signature_datetime,
    format_beneficiary_label, format_status_label, format_restitution_state_label,
    dossier_type_label, mask_text, mask_payload, AppError,
)
from database import get_db
from auth import current_user
from models.audit import insert_audit_event, insert_app_log
from models.workflow import (
    collect_resource_entries, collect_resource_validation_errors,
    compute_effective_workflow_status, summarize_assignment_progress,
    summarize_dynamic_resource, is_restitution_eligible_material_details,
    describe_assignment_condition, extract_items,
)
from models.dossier import sync_person_and_dossier
from models.settings import get_app_settings, DEFAULT_APP_SETTINGS, get_dpo_email
from utils import generate_id

# Clés de champs dont les valeurs saisies sont mémorisées pour autocomplete
_SUGGEST_FIELD_KEYS = {"marque", "modele", "nomPoste", "nomTelephone", "nomTablette"}
_SUGGEST_LIST_KEYS = {"zones"}


def _upsert_field_suggestions(connection, payload):
    """Mémorise en DB les valeurs saisies pour les champs avec suggest."""
    now = utc_now()
    service = (payload.get("beneficiaire") or {}).get("service") or ""
    to_upsert = []

    # Champs texte des ressources additionnelles
    for resource in (payload.get("resources") or {}).get("additional") or []:
        fields = resource.get("fields") or {}
        for key in _SUGGEST_FIELD_KEYS:
            val = str(fields.get(key) or "").strip()
            if val:
                to_upsert.append(("", key, val, ""))
        for key in _SUGGEST_LIST_KEYS:
            items = fields.get(key)
            if isinstance(items, list):
                for item in items:
                    val = str(item or "").strip()
                    if val:
                        to_upsert.append(("", key, val, ""))

    # Chemins UNC — scoped par service du dossier
    for entry in (payload.get("unc_acces") or []):
        chemin = str(entry.get("chemin") or "").strip()
        if chemin:
            to_upsert.append(("", "unc_chemin", chemin, service))

    for _, field_key, value, svc in to_upsert:
        existing = connection.execute(
            "SELECT id FROM field_suggestions WHERE field_key = ? AND value = ? AND service = ?",
            (field_key, value, svc),
        ).fetchone()
        if not existing:
            connection.execute(
                "INSERT INTO field_suggestions (id, field_key, value, service, created_at) VALUES (?, ?, ?, ?, ?)",
                (generate_id("sugg"), field_key, value, svc, now),
            )


def migrate_field_suggestions_from_history(connection):
    """Peuple field_suggestions depuis les dossiers existants (migration one-shot)."""
    count = connection.execute("SELECT COUNT(*) FROM field_suggestions").fetchone()[0]
    if count > 0:
        return  # Déjà peuplé
    rows = connection.execute(
        "SELECT payload_json FROM dotation_forms WHERE payload_json IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        _upsert_field_suggestions(connection, payload)


def _apply_retraits_to_source(connection, form_id, source_form_id, retraits_items):
    """Quand dossier mise_a_jour passe active, marquer items du source comme returned."""
    if not source_form_id or not retraits_items:
        return

    now = utc_now()
    condition_map = {"Bon": "conforme", "Dégâts": "degrade", "Autre": "autre"}

    # Mettre à jour dotation_items du source
    for item_key, item_data in retraits_items.items():
        if not item_data.get("selected"):
            continue
        etat = item_data.get("etat", "Bon")
        notes = item_data.get("notes", "")
        return_condition = condition_map.get(etat, "conforme")
        connection.execute(
            """
            UPDATE dotation_items
            SET returned = 1, returned_at = ?, return_condition = ?, notes = ?
            WHERE form_id = ? AND item_key = ?
            """,
            (now, return_condition, notes, source_form_id, item_key),
        )

    # Charger et mettre à jour le payload du source
    source_row = connection.execute(
        "SELECT payload_json, dossier_id FROM dotation_forms WHERE id = ?",
        (source_form_id,),
    ).fetchone()
    if source_row:
        source_payload = json.loads(source_row["payload_json"] or "{}")
        restitution = source_payload.setdefault("restitution", {})
        items = restitution.setdefault("items", {})
        for item_key, item_data in retraits_items.items():
            if not item_data.get("selected"):
                continue
            etat = item_data.get("etat", "Bon")
            notes = item_data.get("notes", "")
            return_condition = condition_map.get(etat, "conforme")
            items[item_key] = {
                "state": return_condition,
                "notes": notes,
                "returnedAt": now,
            }
        connection.execute(
            "UPDATE dotation_forms SET payload_json = ? WHERE id = ?",
            (json.dumps(source_payload, ensure_ascii=False), source_form_id),
        )
        source_dossier_id = source_row["dossier_id"]
        if source_dossier_id:
            insert_audit_event(
                connection,
                source_dossier_id,
                "form_retrait",
                f"Ressources retirees via dossier de mise a jour #{form_id}",
                {"source_form_id": form_id, "items": list(retraits_items.keys())},
            )


def build_form_export_lines(payload):
    beneficiaire = payload.get("beneficiaire", {})
    workflow = payload.get("workflow", {})
    dossier = payload.get("dossier", {})
    validation = payload.get("validation", {})
    restitution = payload.get("restitution", {})
    signature_datetime = get_signature_datetime(payload)
    lines = [
        "DOSSIER D'ATTRIBUTION DE RESSOURCES",
        "",
        f"Etat : {format_status_label(workflow.get('status') or 'draft')}",
        f"Type de dossier : {dossier_type_label(dossier.get('type'))}",
        f"Date de prise de fonction : {format_export_datetime(payload.get('meta', {}).get('startAt'))}",
        f"Date et heure de remise : {format_export_datetime(payload.get('meta', {}).get('assignedAt'))}",
        "",
        "Beneficiaire",
        f"Nom : {beneficiaire.get('nom') or '-'}",
        f"Prenom : {beneficiaire.get('prenom') or '-'}",
        f"Qualite : {format_beneficiary_label(beneficiaire.get('qualite'))}",
        f"Service : {beneficiaire.get('service') or '-'}",
        f"Fonction : {beneficiaire.get('fonction') or '-'}",
        f"Mandat : {beneficiaire.get('mandat') or '-'}",
        f"Service de destination : {dossier.get('serviceDestination') or '-'}",
        "",
        "Ressources attribuees",
    ]

    resources = collect_resource_entries(payload)
    if resources:
        current_service = None
        for entry in resources:
            if entry["service"] != current_service:
                current_service = entry["service"]
                lines.append(f"{current_service}")
            lines.append(f"- {entry['label']} : {entry['details']}")
    else:
        lines.append("- Aucune ressource renseignee")

    unc_entries = payload.get("unc_acces") or []
    if unc_entries:
        _ACCES = {"lecture": "Lecture", "lecture_ecriture": "Lecture / Ecriture", "refuse": "Acces refuse"}
        _STATUT = {"demande": "Demande", "en_cours": "En cours", "provisionne": "Provisionne"}
        lines.append("")
        lines.append("Acces reseau (UNC)")
        for e in unc_entries:
            acces = _ACCES.get(e.get("acces") or "", e.get("acces") or "-")
            statut = _STATUT.get(e.get("statut") or "", e.get("statut") or "-")
            commentaire = f" ({e['commentaire']})" if e.get("commentaire") else ""
            lines.append(f"- {e.get('chemin') or '-'} : {acces} / {statut}{commentaire}")

    lines.extend(
        [
            "",
            "Restitution",
            f"Etat de restitution : {format_status_label(workflow.get('status') or 'draft')}",
            f"Date de restitution : {format_export_datetime(restitution.get('returnedAt'))}",
            f"Motif : {restitution.get('reason') or '-'}",
            f"Observations : {restitution.get('notes') or '-'}",
            "",
            "Validation",
            f"Information RGPD portee a connaissance : {'Oui' if validation.get('rgpdAccepted') else 'Non'}",
            f"Signature presente : {'Oui' if validation.get('signatureDataUrl') else 'Non'}",
            f"Date de signature : {signature_datetime}",
        ]
    )
    return lines


def normalize_workflow_before_save(payload):
    workflow = payload.setdefault("workflow", {})
    current_status = workflow.get("status") or "draft"
    restitution = payload.get("restitution", {})

    if current_status in {"returned", "partial_return", "cancelled"} or (
        current_status == "awaiting_signature"
        and (
            restitution.get("items")
            or restitution.get("returnedAt")
            or restitution.get("signatureStatus") == "deferred"
        )
    ):
        return payload

    resource_errors = collect_resource_validation_errors(payload)
    payload.setdefault("meta", {})["resourceValidationErrors"] = resource_errors
    workflow["status"] = compute_effective_workflow_status(payload)
    if workflow["status"] == "active":
        payload["meta"]["lockedAt"] = payload["meta"].get("lockedAt") or utc_now()
        return payload

    payload["meta"]["lockedAt"] = ""
    return payload


def _sanitize_unc_acces(payload):
    entries = payload.get("unc_acces") or []
    valid_acces = {"lecture", "lecture_ecriture", "refuse"}
    valid_statut = {"demande", "en_cours", "provisionne"}
    sanitized = []
    for e in entries:
        chemin = (e.get("chemin") or "").strip()
        if not chemin:
            continue
        sanitized.append({
            "chemin": chemin,
            "acces": e.get("acces") if e.get("acces") in valid_acces else "lecture",
            "statut": e.get("statut") if e.get("statut") in valid_statut else "demande",
            "commentaire": (e.get("commentaire") or "").strip()[:500],
        })
    payload["unc_acces"] = sanitized
    return payload


def persist_form(payload, allow_locked_update=False):
    if not payload.get("beneficiaire", {}).get("nom") or not payload.get("beneficiaire", {}).get("prenom"):
        raise AppError("invalid_form_data", "Les champs nom et prénom sont obligatoires.")
    payload = _sanitize_unc_acces(payload)

    payload = normalize_workflow_before_save(payload)
    form_id = payload.setdefault("meta", {}).get("id") or str(int(datetime.now().timestamp() * 1000))
    payload["meta"]["id"] = form_id
    payload["meta"]["savedAt"] = utc_now()

    title = build_title(payload)
    status = payload.get("workflow", {}).get("status") or "draft"
    beneficiaire = payload.get("beneficiaire", {})
    validation = payload.get("validation", {})
    restitution = payload.get("restitution", {})
    dossier = payload.get("dossier", {})
    assigned_at = payload.get("meta", {}).get("assignedAt") or payload["meta"]["savedAt"]
    payload["meta"]["startAt"] = payload.get("meta", {}).get("startAt") or ""

    row = {
        "id": form_id,
        "dossier_id": payload.get("meta", {}).get("dossierId"),
        "dossier_type": normalize_dossier_type(dossier.get("type")),
        "title": title,
        "status": status,
        "beneficiary_type": beneficiaire.get("qualite"),
        "nom": beneficiaire.get("nom", ""),
        "prenom": beneficiaire.get("prenom", ""),
        "service": beneficiaire.get("service"),
        "fonction": beneficiaire.get("fonction"),
        "mandat": beneficiaire.get("mandat"),
        "rgpd_accepted": bool_to_int(validation.get("rgpdAccepted")),
        "signature_data": validation.get("signatureDataUrl"),
        "assigned_at": assigned_at,
        "returned_at": restitution.get("returnedAt"),
        "return_reason": restitution.get("reason"),
        "return_notes": restitution.get("notes"),
        "source_form_id": dossier.get("sourceFormId"),
        "payload_json": "",
        "created_at": payload.get("meta", {}).get("createdAt") or payload["meta"]["savedAt"],
        "updated_at": payload["meta"]["savedAt"],
    }

    items = extract_items(payload)

    with get_db() as connection:
        exists = connection.execute(
            "SELECT id, dossier_id, created_at, signature_data, payload_json FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).fetchone()
        if exists:
            existing_payload = json.loads(exists["payload_json"])
            if existing_payload.get("meta", {}).get("lockedAt") and not allow_locked_update:
                raise AppError("form_locked", "Cette fiche est signée et verrouillée. Elle ne peut plus être modifiée.")
            row["created_at"] = exists["created_at"]
        _, dossier_id = sync_person_and_dossier(connection, payload, exists)
        row["dossier_id"] = dossier_id
        row["assigned_at"] = payload.get("meta", {}).get("assignedAt") or row["assigned_at"]
        row["payload_json"] = json.dumps(payload, ensure_ascii=False)

        if exists:
            connection.execute(
                """
                UPDATE dotation_forms
                SET title = :title,
                    dossier_id = :dossier_id,
                    dossier_type = :dossier_type,
                    status = :status,
                    beneficiary_type = :beneficiary_type,
                    nom = :nom,
                    prenom = :prenom,
                    service = :service,
                    fonction = :fonction,
                    mandat = :mandat,
                    rgpd_accepted = :rgpd_accepted,
                    signature_data = :signature_data,
                    assigned_at = :assigned_at,
                    returned_at = :returned_at,
                    return_reason = :return_reason,
                    return_notes = :return_notes,
                    source_form_id = :source_form_id,
                    payload_json = :payload_json,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                row,
            )
        else:
            connection.execute(
                """
                INSERT INTO dotation_forms (
                    id, dossier_id, dossier_type, title, status, beneficiary_type, nom, prenom, service, fonction, mandat,
                    rgpd_accepted, signature_data, assigned_at, returned_at, return_reason,
                    return_notes, source_form_id, payload_json, created_at, updated_at
                ) VALUES (
                    :id, :dossier_id, :dossier_type, :title, :status, :beneficiary_type, :nom, :prenom, :service, :fonction, :mandat,
                    :rgpd_accepted, :signature_data, :assigned_at, :returned_at, :return_reason,
                    :return_notes, :source_form_id, :payload_json, :created_at, :updated_at
                )
                """,
                row,
            )

        connection.execute("DELETE FROM dotation_items WHERE form_id = ?", (form_id,))
        connection.executemany(
            """
            INSERT INTO dotation_items (
                form_id, item_key, category, label, assigned, returned,
                returned_at, return_condition, notes, details_json
            ) VALUES (
                :form_id, :item_key, :category, :label, :assigned, :returned,
                :returned_at, :return_condition, :notes, :details_json
            )
            """,
            [
                {
                    "form_id": form_id,
                    **item,
                    "assigned": bool_to_int(item["assigned"]),
                    "returned": bool_to_int(item["returned"]),
                }
                for item in items
            ],
        )
        insert_audit_event(
            connection,
            dossier_id,
            "form_updated" if exists else "form_created",
            "Dossier d'attribution mis a jour" if exists else "Dossier d'attribution cree",
            {"form_id": form_id, "status": status},
        )
        insert_app_log(
            connection,
            "dossier",
            "form_updated" if exists else "form_created",
            "Dossier d'attribution mis a jour" if exists else "Dossier d'attribution cree",
            "form",
            form_id,
            {"dossier_id": dossier_id, "status": status, "title": title},
            target_label=title,
        )
        _upsert_field_suggestions(connection, payload)

        # Apply retraits if this is a mise_a_jour form with retraits
        # Check based on dossier type and presence of retraits, not computed status
        if dossier.get("type") == "mise_a_jour":
            source_form_id = dossier.get("sourceFormId")
            retraits_items = (payload.get("retraits") or {}).get("items") or {}
            if source_form_id and retraits_items:
                _apply_retraits_to_source(connection, form_id, source_form_id, retraits_items)

    return get_form(form_id)


def row_to_summary(row):
    payload = {}
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    effective_status = compute_effective_workflow_status(payload)
    progress = summarize_assignment_progress(payload)
    summary = {
        "id": row["id"],
        "dossierId": row["dossier_id"],
        "dossierType": row["dossier_type"],
        "title": row["title"],
        "status": effective_status,
        "isLocked": effective_status == "active",
        "beneficiaryType": row["beneficiary_type"],
        "nom": row["nom"],
        "prenom": row["prenom"],
        "service": row["service"],
        "fonction": row["fonction"],
        "mandat": row["mandat"],
        "assignedAt": row["assigned_at"],
        "startAt": progress["startAt"],
        "returnedAt": row["returned_at"],
        "updatedAt": row["updated_at"],
        "uncAccesCount": len(payload.get("unc_acces") or []),
        "pendingFinalization": bool(payload.get("restitution", {}).get("pendingFinalization")),
        "completedResources": progress["completed"],
        "totalResources": progress["total"],
        "resourceProgressRatio": progress["ratio"],
        "timingStatus": progress["timingStatus"],
        "timingLabel": progress["timingLabel"],
        "data": payload,
    }
    user = current_user()
    if user and user.get("data_scope") == "masked":
        summary["nom"] = mask_text(summary["nom"])
        summary["prenom"] = mask_text(summary["prenom"])
        prefix = (summary["mandat"] if summary["beneficiaryType"] == "elu" else summary["service"]) or (
            "MANDAT" if summary["beneficiaryType"] == "elu" else "SERVICE"
        )
        summary["title"] = f"{str(prefix).upper()} - {summary['nom']} {summary['prenom']}".strip()
    return summary


def get_form(form_id):
    with get_db() as connection:
        form_row = connection.execute(
            "SELECT * FROM dotation_forms WHERE id = ?",
            (form_id,),
        ).fetchone()
        if not form_row:
            return None

        items = connection.execute(
            "SELECT * FROM dotation_items WHERE form_id = ? ORDER BY id ASC",
            (form_id,),
        ).fetchall()

        # Charger tous les pools dont ce dossier est membre (propriétaire ou co-utilisateur)
        # Modèle symétrique : tous les membres voient le même état
        pool_by_resource = {}  # resource_catalog_id -> {pool_id, other_members[]}
        for pool in connection.execute(
            """SELECT p.id, p.resource_catalog_id
               FROM shared_pools p
               JOIN shared_pool_members m ON m.pool_id = p.id
               WHERE m.form_id = ?""",
            (form_id,),
        ).fetchall():
            other_members = connection.execute(
                """SELECT m.form_id, f.nom, f.prenom, f.service
                   FROM shared_pool_members m
                   LEFT JOIN dotation_forms f ON f.id = m.form_id
                   WHERE m.pool_id = ? AND m.form_id != ?""",
                (pool["id"], form_id),
            ).fetchall()
            pool_by_resource[pool["resource_catalog_id"]] = {
                "poolId": pool["id"],
                "members": [
                    {"formId": m["form_id"], "nom": m["nom"], "prenom": m["prenom"], "service": m["service"]}
                    for m in other_members if m["form_id"]
                ],
            }

    payload = json.loads(form_row["payload_json"])

    # Injecter l'état mutualisé depuis la DB (source de vérité) pour tous les membres
    resources_obj = payload.get("resources", {})
    additional = resources_obj.get("additional", []) if isinstance(resources_obj, dict) else []
    for resource in additional:
        rid = resource.get("id") or resource.get("code")
        if rid in pool_by_resource:
            pool_info = pool_by_resource[rid]
            resource["shared"] = True
            resource["poolId"] = pool_info["poolId"]
            resource["sharedWith"] = pool_info["members"]

    payload.setdefault("meta", {})
    payload.setdefault("dossier", {})
    payload["meta"]["id"] = form_row["id"]
    payload["meta"]["dossierId"] = form_row["dossier_id"]
    payload["meta"]["createdAt"] = form_row["created_at"]
    payload["meta"]["savedAt"] = form_row["updated_at"]
    payload["meta"]["assignedAt"] = form_row["assigned_at"]
    payload["dossier"]["type"] = normalize_dossier_type(payload.get("dossier", {}).get("type") or form_row["dossier_type"] or "arrivee")
    payload.setdefault("workflow", {})["status"] = compute_effective_workflow_status(payload)
    if payload["workflow"]["status"] != "active":
        payload["meta"]["lockedAt"] = ""
    user = current_user()
    if user and user.get("data_scope") == "masked":
        payload = mask_payload(payload)

    return {
        "summary": row_to_summary(form_row),
        "data": payload,
        "items": [
            {
                "id": item["id"],
                "itemKey": item["item_key"],
                "category": item["category"],
                "label": item["label"],
                "assigned": bool(item["assigned"]),
                "returned": bool(item["returned"]),
                "returnedAt": item["returned_at"],
                "returnCondition": item["return_condition"],
                "notes": item["notes"],
                "details": json.loads(item["details_json"]) if item["details_json"] else {},
            }
            for item in items
        ],
    }


def build_signature_public_payload(form_data, link_row):
    payload = form_data["data"]
    settings = get_app_settings()
    org_name = settings.get("org_name") or DEFAULT_APP_SETTINGS["org_name"]
    dpo_email = get_dpo_email(settings)
    beneficiaire = payload.get("beneficiaire", {})
    grouped_resources = {"materiel": [], "immateriel": []}
    for entry in collect_resource_entries(payload):
        grouped_resources.setdefault(entry["category"], []).append({
            "label": entry["label"],
            "details": entry["details"],
            "service": entry["service"],
            "assignmentConditionLabel": entry.get("assignmentConditionLabel") or "",
            "assignmentConditionNotes": entry.get("assignmentConditionNotes") or "",
            "assignmentSummary": entry.get("assignmentSummary") or "",
        })

    return {
        "link": {
            "status": link_row["status"],
            "expiresAt": link_row["expires_at"],
            "type": link_row["link_type"],
        },
        "form": {
            "id": form_data["summary"]["id"],
            "title": form_data["summary"]["title"],
            "dossierType": form_data["summary"]["dossierType"],
            "beneficiaire": {
                "nom": beneficiaire.get("nom") or "",
                "prenom": beneficiaire.get("prenom") or "",
                "qualite": beneficiaire.get("qualite") or "",
                "service": beneficiaire.get("service") or "",
                "fonction": beneficiaire.get("fonction") or "",
                "mandat": beneficiaire.get("mandat") or "",
            },
            "resources": grouped_resources,
            "rgpdText": [
                f"Les donnees a caractere personnel renseignees dans ce dossier font l'objet d'un traitement par {org_name} afin d'assurer la gestion des attributions de ressources professionnelles, le suivi des remises et, le cas echeant, des restitutions.",
                "Conformement au reglement general sur la protection des donnees et a la loi Informatique et Libertes, la personne concernee dispose notamment de droits d'acces, de rectification, d'effacement, de limitation et d'opposition, dans les conditions prevues par la reglementation applicable.",
                f"Pour toute question relative au traitement de ses donnees personnelles ou pour exercer ses droits, la personne concernee peut contacter le delegue a la protection des donnees a l'adresse suivante : {dpo_email}.",
            ],
        },
    }


def build_restitution_signature_public_payload(form_data, link_row):
    payload = form_data["data"]
    beneficiaire = payload.get("beneficiaire", {})
    restitution = payload.get("restitution", {})
    material_index = {
        item["itemKey"]: item
        for item in (form_data.get("items") or [])
        if item.get("category") == "materiel" and is_restitution_eligible_material_details(item.get("details") or {})
    }
    restitution_items = []
    for item_key, state in (restitution.get("items") or {}).items():
        item = material_index.get(item_key, {})
        details = item.get("details") or {}
        detail_text = summarize_dynamic_resource(details) if details.get("fields") else " - ".join(
            str(value).strip()
            for key, value in details.items()
            if key not in {"selected", "conditionAttribution", "conditionNotes"} and str(value or "").strip()
        )
        restitution_items.append(
            {
                "label": item.get("label") or item_key,
                "details": detail_text or "Sans detail complementaire",
                "state": state.get("state") or state.get("condition") or "conforme",
                "stateLabel": format_restitution_state_label(state.get("state") or state.get("condition") or "conforme"),
                "notes": state.get("notes") or "",
                "assignmentSummary": " - ".join(describe_assignment_condition(details)),
            }
        )

    return {
        "link": {
            "status": link_row["status"],
            "expiresAt": link_row["expires_at"],
            "type": link_row["link_type"],
        },
        "form": {
            "id": form_data["summary"]["id"],
            "title": form_data["summary"]["title"],
            "beneficiaire": {
                "nom": beneficiaire.get("nom") or "",
                "prenom": beneficiaire.get("prenom") or "",
                "qualite": beneficiaire.get("qualite") or "",
                "service": beneficiaire.get("service") or "",
                "fonction": beneficiaire.get("fonction") or "",
                "mandat": beneficiaire.get("mandat") or "",
            },
            "restitution": {
                "returnedAt": restitution.get("returnedAt") or "",
                "reason": restitution.get("reason") or "",
                "notes": restitution.get("notes") or "",
                "items": restitution_items,
                "signataireDecision": restitution.get("signataireDecision") or "confirmed",
                "signataireComment": restitution.get("signataireComment") or "",
            },
        },
    }
