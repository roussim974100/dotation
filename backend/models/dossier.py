import json

from database import get_db
from utils import utc_now, generate_id, normalize_dossier_type
from models.workflow import derive_dossier_status


def sync_person_and_dossier(connection, payload, existing_row=None):
    beneficiaire = payload.get("beneficiaire", {})
    dossier = payload.get("dossier", {})
    meta = payload.setdefault("meta", {})
    saved_at = meta.get("savedAt") or utc_now()
    assigned_at = meta.get("assignedAt") or saved_at
    start_at = meta.get("startAt") or assigned_at

    person_id = meta.get("personId")
    dossier_id = meta.get("dossierId")
    if existing_row:
        dossier_id = dossier_id or existing_row["dossier_id"]

    if dossier_id and not person_id:
        dossier_row = connection.execute(
            "SELECT person_id FROM onboarding_dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
        if dossier_row:
            person_id = dossier_row["person_id"]

    if not person_id:
        person_id = generate_id("person")
    if not dossier_id:
        dossier_id = generate_id("dossier")

    person_exists = connection.execute(
        "SELECT id, created_at FROM persons WHERE id = ?",
        (person_id,),
    ).fetchone()
    person_row = {
        "id": person_id,
        "nom": beneficiaire.get("nom", ""),
        "prenom": beneficiaire.get("prenom", ""),
        "qualite": beneficiaire.get("qualite") or "agent",
        "service": beneficiaire.get("service"),
        "fonction": beneficiaire.get("fonction"),
        "mandat": beneficiaire.get("mandat"),
        "date_arrivee": start_at,
        "is_active": 1,
        "created_at": person_exists["created_at"] if person_exists else saved_at,
        "updated_at": saved_at,
    }

    if person_exists:
        connection.execute(
            """
            UPDATE persons
            SET nom = :nom,
                prenom = :prenom,
                qualite = :qualite,
                service = :service,
                fonction = :fonction,
                mandat = :mandat,
                date_arrivee = :date_arrivee,
                is_active = :is_active,
                updated_at = :updated_at
            WHERE id = :id
            """,
            person_row,
        )
    else:
        connection.execute(
            """
            INSERT INTO persons (
                id, nom, prenom, qualite, service, fonction, mandat,
                date_arrivee, is_active, created_at, updated_at
            ) VALUES (
                :id, :nom, :prenom, :qualite, :service, :fonction, :mandat,
                :date_arrivee, :is_active, :created_at, :updated_at
            )
            """,
            person_row,
        )

    dossier_exists = connection.execute(
        "SELECT id, created_at FROM onboarding_dossiers WHERE id = ?",
        (dossier_id,),
    ).fetchone()
    dossier_row = {
        "id": dossier_id,
        "person_id": person_id,
        "dossier_type": normalize_dossier_type(dossier.get("type")),
        "status": derive_dossier_status(payload),
        "assigned_at": assigned_at,
        "notes": payload.get("restitution", {}).get("notes") or "",
        "created_at": dossier_exists["created_at"] if dossier_exists else saved_at,
        "updated_at": saved_at,
    }

    if dossier_exists:
        connection.execute(
            """
            UPDATE onboarding_dossiers
            SET person_id = :person_id,
                dossier_type = :dossier_type,
                status = :status,
                assigned_at = :assigned_at,
                notes = :notes,
                updated_at = :updated_at
            WHERE id = :id
            """,
            dossier_row,
        )
    else:
        connection.execute(
            """
            INSERT INTO onboarding_dossiers (id, person_id, dossier_type, status, assigned_at, notes, created_at, updated_at)
            VALUES (:id, :person_id, :dossier_type, :status, :assigned_at, :notes, :created_at, :updated_at)
            """,
            dossier_row,
        )

    meta["personId"] = person_id
    meta["dossierId"] = dossier_id
    meta["assignedAt"] = assigned_at
    meta["startAt"] = start_at
    return person_id, dossier_id


def migrate_forms_to_dossiers(connection):
    rows = connection.execute(
        "SELECT id, dossier_id, payload_json, created_at, updated_at FROM dotation_forms"
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload.setdefault("meta", {})
        payload["meta"].setdefault("id", row["id"])
        payload["meta"].setdefault("createdAt", row["created_at"])
        payload["meta"].setdefault("savedAt", row["updated_at"])
        _, dossier_id = sync_person_and_dossier(connection, payload, row)
        connection.execute(
            "UPDATE dotation_forms SET dossier_id = ?, payload_json = ? WHERE id = ?",
            (dossier_id, json.dumps(payload, ensure_ascii=False), row["id"]),
        )
