from utils import generate_id, utc_now


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
