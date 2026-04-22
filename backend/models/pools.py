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

def _deselect_resource_from_form(conn, form_id, resource_catalog_id):
    """Décoche et désactive la mutualisation d'une ressource dans le dossier d'un membre retiré."""
    row = conn.execute(
        "SELECT payload_json FROM dotation_forms WHERE id = ?", (form_id,)
    ).fetchone()
    if not row:
        return
    try:
        payload = _json.loads(row["payload_json"] or "{}")
    except (TypeError, _json.JSONDecodeError):
        return

    additional = (payload.get("resources") or {}).get("additional") or []
    changed = False
    for resource in additional:
        rid = resource.get("id") or resource.get("code")
        if rid == resource_catalog_id:
            resource["selected"] = False
            resource["shared"] = False
            resource.pop("poolId", None)
            resource.pop("sharedWith", None)
            changed = True

    if changed:
        payload.setdefault("resources", {})["additional"] = additional
        conn.execute(
            "UPDATE dotation_forms SET payload_json = ?, updated_at = ? WHERE id = ?",
            (_json.dumps(payload, ensure_ascii=False), utc_now(), form_id),
        )


def sync_shared_pools_for_form(conn, form_id, resources):
    """Crée ou met à jour les pools partagés pour toutes les ressources
    marquées shared=True dans le payload d'un dossier.

    Modèle symétrique : n'importe quel membre peut gérer la liste.
    Appelé à chaque sauvegarde de dossier. Idempotent.
    """
    for resource in resources:
        resource_catalog_id = resource.get("id") or resource.get("code")
        shared = resource.get("shared") or False
        shared_with = resource.get("sharedWith") or []
        pool_id_hint = resource.get("poolId")

        if not resource_catalog_id:
            continue

        # Cas "décoché avec poolId" : l'utilisateur quitte volontairement le pool
        if not shared and pool_id_hint:
            conn.execute(
                "UPDATE shared_pool_members SET removed_at = ? WHERE pool_id = ? AND form_id = ?",
                (utc_now(), pool_id_hint, form_id),
            )
            # Supprimer le pool s'il n'a plus de membres ACTIFS
            remaining = conn.execute(
                "SELECT COUNT(*) as n FROM shared_pool_members WHERE pool_id = ? AND removed_at IS NULL",
                (pool_id_hint,),
            ).fetchone()
            if remaining and remaining["n"] == 0:
                conn.execute("DELETE FROM shared_pools WHERE id = ?", (pool_id_hint,))
            continue

        if not shared:
            continue

        # Chercher le pool : par poolId d'abord, puis par appartenance de ce dossier
        pool_row = None
        if pool_id_hint:
            pool_row = conn.execute(
                "SELECT id FROM shared_pools WHERE id = ?", (pool_id_hint,)
            ).fetchone()
        if not pool_row:
            pool_row = conn.execute(
                """SELECT p.id FROM shared_pools p
                   JOIN shared_pool_members m ON m.pool_id = p.id
                   WHERE m.form_id = ? AND m.removed_at IS NULL AND p.resource_catalog_id = ?""",
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
            conn.execute(
                "INSERT INTO shared_pool_members (pool_id, form_id, beneficiary_name, added_at) VALUES (?, ?, NULL, ?)",
                (pool_id, form_id, now),
            )

        # S'assurer que le dossier qui sauvegarde est bien membre actif
        self_member = conn.execute(
            "SELECT id, removed_at FROM shared_pool_members WHERE pool_id = ? AND form_id = ?",
            (pool_id, form_id),
        ).fetchone()
        if self_member:
            # Réactiver si avait été retiré
            if self_member["removed_at"]:
                conn.execute(
                    "UPDATE shared_pool_members SET removed_at = NULL, added_at = ? WHERE id = ?",
                    (utc_now(), self_member["id"]),
                )
        else:
            # Nouveau membre
            conn.execute(
                "INSERT INTO shared_pool_members (pool_id, form_id, beneficiary_name, added_at) VALUES (?, ?, NULL, ?)",
                (pool_id, form_id, utc_now()),
            )

        # Synchroniser les autres membres depuis sharedWith
        # (exclure les members déjà retirés pour ne pas les reconsidérer)
        existing_members = {
            row["form_id"]: row["id"]
            for row in conn.execute(
                "SELECT id, form_id FROM shared_pool_members WHERE pool_id = ? AND form_id != ? AND removed_at IS NULL",
                (pool_id, form_id),
            ).fetchall()
            if row["form_id"]
        }

        desired_form_ids = {entry["formId"] for entry in shared_with if entry.get("formId")}

        # Ajouter les nouveaux membres et propager la ressource dans leur dossier
        for entry in shared_with:
            fid = entry.get("formId")
            if not fid:
                continue
            # Réactiver un membre retiré s'il est ajouté de nouveau
            existing = conn.execute(
                "SELECT id, removed_at FROM shared_pool_members WHERE pool_id = ? AND form_id = ?",
                (pool_id, fid),
            ).fetchone()
            if existing and existing["removed_at"]:
                # Réactiver
                conn.execute(
                    "UPDATE shared_pool_members SET removed_at = NULL, added_at = ? WHERE id = ?",
                    (utc_now(), existing["id"]),
                )
            elif not existing:
                # Nouveau membre
                conn.execute(
                    "INSERT INTO shared_pool_members (pool_id, form_id, beneficiary_name, added_at) VALUES (?, ?, NULL, ?)",
                    (pool_id, fid, utc_now()),
                )
            _inject_resource_into_form(conn, fid, resource)

        # Marquer comme retiré les membres absents de sharedWith (soft-delete)
        for fid, member_id in existing_members.items():
            if fid not in desired_form_ids:
                conn.execute(
                    "UPDATE shared_pool_members SET removed_at = ? WHERE id = ?",
                    (utc_now(), member_id),
                )
                _deselect_resource_from_form(conn, fid, resource_catalog_id)

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
        SELECT m.id, m.pool_id, m.form_id, m.beneficiary_name, m.added_at, m.removed_at,
               f.nom, f.prenom, f.service, f.status
        FROM shared_pool_members m
        LEFT JOIN dotation_forms f ON f.id = m.form_id
        WHERE m.pool_id = ?
        ORDER BY m.added_at
        """,
        (row["id"],),
    ).fetchall()

    active_members = [m for m in members if not m["removed_at"]]
    removed_members = [m for m in members if m["removed_at"]]

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
                "removed_at": m["removed_at"],
            }
            for m in active_members
        ],
        "history": [
            {
                "id": m["id"],
                "form_id": m["form_id"],
                "beneficiary_name": m["beneficiary_name"]
                    or (f"{m['prenom']} {m['nom']}" if m["nom"] else None),
                "service": m["service"],
                "added_at": m["added_at"],
                "removed_at": m["removed_at"],
            }
            for m in removed_members
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
    """Marque un membre comme retiré (soft-delete pour traçabilité)."""
    conn.execute(
        "UPDATE shared_pool_members SET removed_at = ? WHERE id = ? AND pool_id = ?",
        (utc_now(), member_id, pool_id),
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
