import json as _json

from utils import generate_id, utc_now


# ---------------------------------------------------------------------------
# Injection de la ressource partagée dans le dossier co-utilisateur
# ---------------------------------------------------------------------------

def _inject_resource_into_form(conn, target_form_id, source_resource):
    """Copie les champs matériels (marque, modèle, SN…) de la ressource partagée
    dans le dossier cible, sans écraser les données propres au co-utilisateur
    (date d'attribution, condition, notes, signature…).

    - Si la ressource est absente du dossier cible : on l'ajoute sélectionnée.
    - Si elle est déjà présente mais sans détails : on complète les champs.
    - Si elle est déjà remplie : on ne touche à rien.
    """
    row = conn.execute(
        "SELECT payload_json, updated_at FROM dotation_forms WHERE id = ?",
        (target_form_id,),
    ).fetchone()
    if not row:
        return

    try:
        payload = _json.loads(row["payload_json"] or "{}")
    except (TypeError, _json.JSONDecodeError):
        payload = {}

    additional = (payload.get("resources") or {}).get("additional") or []
    resource_id = source_resource.get("id") or source_resource.get("code")
    source_fields = source_resource.get("fields") or {}

    # Champs à propager (identification matérielle uniquement, pas les champs usage)
    SHARED_FIELD_KEYS = {
        "marque", "modele", "numeroSerie", "imei", "nomPoste",
        "nomTelephone", "nomTablette",
    }
    propagated_fields = {k: v for k, v in source_fields.items() if k in SHARED_FIELD_KEYS and v}

    if not propagated_fields:
        return  # Rien à propager

    existing = next((r for r in additional if (r.get("id") or r.get("code")) == resource_id), None)

    if existing is None:
        # Ajouter la ressource en copiant les métadonnées du catalogue (sans données usage)
        new_resource = {k: v for k, v in source_resource.items()
                        if k not in ("sharedWith", "shared", "assignedAt",
                                     "conditionAttribution", "conditionNotes")}
        new_resource["selected"] = True
        new_resource["fields"] = propagated_fields
        new_resource["sharedWith"] = []
        new_resource["shared"] = False  # le co-user n'est pas lui-même l'owner de la mutualisation
        additional.append(new_resource)
        changed = True
    else:
        # Compléter les champs vides seulement (ne pas écraser ce que l'utilisateur a saisi)
        existing_fields = existing.get("fields") or {}
        changed = False
        for key, val in propagated_fields.items():
            if not existing_fields.get(key):
                existing_fields[key] = val
                changed = True
        if changed:
            existing["fields"] = existing_fields
            existing["selected"] = True

    if not changed:
        return

    payload.setdefault("resources", {})["additional"] = additional
    conn.execute(
        "UPDATE dotation_forms SET payload_json = ?, updated_at = ? WHERE id = ?",
        (_json.dumps(payload, ensure_ascii=False), utc_now(), target_form_id),
    )


# ---------------------------------------------------------------------------
# Sync automatique depuis les ressources partagées d'un dossier
# ---------------------------------------------------------------------------

def sync_shared_pools_for_form(conn, form_id, resources):
    """Crée ou met à jour les pools partagés pour toutes les ressources
    marquées shared=True dans le payload d'un dossier.

    Appelé à chaque sauvegarde de dossier. Idempotent.
    """
    for resource in resources:
        resource_catalog_id = resource.get("id") or resource.get("code")
        shared = resource.get("shared") or False
        shared_with = resource.get("sharedWith") or []

        if not shared or not resource_catalog_id:
            continue

        # Trouver ou créer le pool pour ce dossier + ressource
        pool_row = conn.execute(
            "SELECT id FROM shared_pools WHERE owner_form_id = ? AND resource_catalog_id = ?",
            (form_id, resource_catalog_id),
        ).fetchone()

        if pool_row:
            pool_id = pool_row["id"]
        else:
            pool_id = generate_id("pool")
            now = utc_now()
            label = resource.get("label") or resource_catalog_id
            conn.execute(
                """INSERT INTO shared_pools
                   (id, label, notes, owner_form_id, resource_catalog_id, created_at, updated_at)
                   VALUES (?, ?, NULL, ?, ?, ?, ?)""",
                (pool_id, label, form_id, resource_catalog_id, now, now),
            )
            # Ajouter le dossier propriétaire comme membre
            conn.execute(
                "INSERT INTO shared_pool_members (pool_id, form_id, beneficiary_name, added_at) VALUES (?, ?, NULL, ?)",
                (pool_id, form_id, now),
            )

        # Synchroniser les co-utilisateurs
        # Récupérer les form_ids déjà membres (hors propriétaire)
        existing_members = {
            row["form_id"]: row["id"]
            for row in conn.execute(
                "SELECT id, form_id FROM shared_pool_members WHERE pool_id = ? AND form_id != ?",
                (pool_id, form_id),
            ).fetchall()
            if row["form_id"]
        }

        desired_form_ids = {
            entry["formId"]
            for entry in shared_with
            if entry.get("formId")
        }

        # Ajouter les nouveaux membres + propager la ressource dans leur dossier
        for entry in shared_with:
            fid = entry.get("formId")
            if not fid:
                continue
            if fid not in existing_members:
                conn.execute(
                    "INSERT INTO shared_pool_members (pool_id, form_id, beneficiary_name, added_at) VALUES (?, ?, NULL, ?)",
                    (pool_id, fid, utc_now()),
                )
            _inject_resource_into_form(conn, fid, resource)

        # Retirer les membres qui ne sont plus dans sharedWith
        for fid, member_id in existing_members.items():
            if fid not in desired_form_ids:
                conn.execute("DELETE FROM shared_pool_members WHERE id = ?", (member_id,))

        # Synchroniser l'équipement (1 item par ressource, mis à jour à chaque save)
        fields = resource.get("fields") or {}
        serial = (fields.get("numeroSerie") or fields.get("imei") or "").strip() or None
        marque = (fields.get("marque") or "").strip()
        modele = (fields.get("modele") or "").strip()
        item_label = " ".join(filter(None, [marque, modele])) or resource.get("label") or resource_catalog_id

        existing_item = conn.execute(
            "SELECT id FROM shared_pool_items WHERE pool_id = ?", (pool_id,)
        ).fetchone()
        if existing_item:
            conn.execute(
                "UPDATE shared_pool_items SET label = ?, serial_number = ? WHERE id = ?",
                (item_label, serial, existing_item["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO shared_pool_items
                   (pool_id, resource_type, label, serial_number, notes, created_at)
                   VALUES (?, ?, ?, ?, NULL, ?)""",
                (pool_id, resource.get("code") or resource_catalog_id, item_label, serial, utc_now()),
            )

        # Mettre à jour le timestamp du pool
        conn.execute("UPDATE shared_pools SET updated_at = ? WHERE id = ?", (utc_now(), pool_id))


def get_pool(conn, pool_id):
    row = conn.execute("SELECT * FROM shared_pools WHERE id = ?", (pool_id,)).fetchone()
    if not row:
        return None
    return _serialize_pool(conn, row)


def list_pools(conn):
    rows = conn.execute(
        "SELECT * FROM shared_pools ORDER BY label COLLATE NOCASE"
    ).fetchall()
    return [_serialize_pool(conn, r) for r in rows]


def _serialize_pool(conn, row):
    items = conn.execute(
        "SELECT * FROM shared_pool_items WHERE pool_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    members = conn.execute(
        """
        SELECT m.id, m.pool_id, m.form_id, m.beneficiary_name, m.added_at,
               f.nom, f.prenom, f.service, f.status
        FROM shared_pool_members m
        LEFT JOIN dotation_forms f ON f.id = m.form_id
        WHERE m.pool_id = ?
        ORDER BY m.added_at
        """,
        (row["id"],),
    ).fetchall()

    return {
        "id": row["id"],
        "label": row["label"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "items": [
            {
                "id": i["id"],
                "resource_type": i["resource_type"],
                "label": i["label"],
                "serial_number": i["serial_number"],
                "notes": i["notes"],
            }
            for i in items
        ],
        "members": [
            {
                "id": m["id"],
                "form_id": m["form_id"],
                "beneficiary_name": m["beneficiary_name"]
                    or (f"{m['prenom']} {m['nom']}" if m["nom"] else None),
                "service": m["service"],
                "form_status": m["status"],
                "added_at": m["added_at"],
            }
            for m in members
        ],
    }


def create_pool(conn, label, notes=None):
    pool_id = generate_id("pool")
    now = utc_now()
    conn.execute(
        "INSERT INTO shared_pools (id, label, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (pool_id, label.strip(), (notes or "").strip() or None, now, now),
    )
    return pool_id


def update_pool(conn, pool_id, label, notes=None):
    conn.execute(
        "UPDATE shared_pools SET label = ?, notes = ?, updated_at = ? WHERE id = ?",
        (label.strip(), (notes or "").strip() or None, utc_now(), pool_id),
    )


def delete_pool(conn, pool_id):
    conn.execute("DELETE FROM shared_pools WHERE id = ?", (pool_id,))


def add_item(conn, pool_id, resource_type, label, serial_number=None, notes=None):
    now = utc_now()
    conn.execute(
        """INSERT INTO shared_pool_items
           (pool_id, resource_type, label, serial_number, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            pool_id,
            resource_type.strip(),
            label.strip(),
            (serial_number or "").strip() or None,
            (notes or "").strip() or None,
            now,
        ),
    )


def update_item(conn, item_id, pool_id, resource_type, label, serial_number=None, notes=None):
    conn.execute(
        """UPDATE shared_pool_items
           SET resource_type = ?, label = ?, serial_number = ?, notes = ?
           WHERE id = ? AND pool_id = ?""",
        (
            resource_type.strip(),
            label.strip(),
            (serial_number or "").strip() or None,
            (notes or "").strip() or None,
            item_id,
            pool_id,
        ),
    )


def delete_item(conn, item_id, pool_id):
    conn.execute(
        "DELETE FROM shared_pool_items WHERE id = ? AND pool_id = ?",
        (item_id, pool_id),
    )


def add_member(conn, pool_id, form_id=None, beneficiary_name=None):
    conn.execute(
        """INSERT INTO shared_pool_members (pool_id, form_id, beneficiary_name, added_at)
           VALUES (?, ?, ?, ?)""",
        (
            pool_id,
            form_id or None,
            (beneficiary_name or "").strip() or None,
            utc_now(),
        ),
    )


def link_member_to_form(conn, member_id, pool_id, form_id):
    """Associe un membre sans dossier à un dossier existant."""
    conn.execute(
        "UPDATE shared_pool_members SET form_id = ?, beneficiary_name = NULL WHERE id = ? AND pool_id = ?",
        (form_id, member_id, pool_id),
    )


def delete_member(conn, member_id, pool_id):
    conn.execute(
        "DELETE FROM shared_pool_members WHERE id = ? AND pool_id = ?",
        (member_id, pool_id),
    )


def get_pools_for_form(conn, form_id):
    """Retourne les pools dont ce dossier est membre."""
    rows = conn.execute(
        """
        SELECT p.id, p.label, p.notes,
               m.id as member_id, m.added_at
        FROM shared_pool_members m
        JOIN shared_pools p ON p.id = m.pool_id
        WHERE m.form_id = ?
        ORDER BY p.label COLLATE NOCASE
        """,
        (form_id,),
    ).fetchall()
    return [
        {
            "pool_id": r["id"],
            "label": r["label"],
            "notes": r["notes"],
            "member_id": r["member_id"],
            "added_at": r["added_at"],
        }
        for r in rows
    ]
