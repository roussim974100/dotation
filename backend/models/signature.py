import json
import secrets
from datetime import datetime, timedelta, timezone

from utils import generate_id, utc_now
from models.audit import insert_audit_event, insert_app_log, current_actor


# ---------------------------------------------------------------------------
# Helpers de type et de métadonnées
# ---------------------------------------------------------------------------

def signature_link_label(link_type):
    if link_type == "restitution":
        return "Lien de signature de restitution"
    return "Lien de signature"


def signature_link_scope(link_type):
    if link_type == "restitution":
        return "restitution_signature"
    return "signature"


def signature_link_public_url(link_type, token):
    if link_type == "restitution":
        return f"/restitution-signature/{token}"
    return f"/signature/{token}"


def signature_link_public_actor(link_type):
    if link_type == "restitution":
        return "public_restitution_signature_link"
    return "public_signature_link"


def signature_link_expiration(hours=72):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def generate_signature_token():
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Lecture / matérialisation
# ---------------------------------------------------------------------------

def materialize_signature_link(connection, row):
    # Lecture normalisée d'un lien avec expiration recalculée à la volée,
    # pour éviter d'éparpiller cette logique dans plusieurs routes.
    if not row:
        return None

    data = {key: row[key] for key in row.keys()}
    if data["status"] == "active" and data.get("expires_at"):
        try:
            expired = datetime.fromisoformat(data["expires_at"]) <= datetime.now(timezone.utc)
        except ValueError:
            expired = False
        if expired:
            data["status"] = "expired"
            connection.execute(
                "UPDATE signature_links SET status = 'expired' WHERE id = ?",
                (data["id"],),
            )
    return data


def serialize_signature_link(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "formId": row["form_id"],
        "type": row["link_type"],
        "status": row["status"],
        "createdBy": row["created_by"],
        "createdAt": row["created_at"],
        "expiresAt": row["expires_at"],
        "usedAt": row["used_at"],
        "revokedAt": row["revoked_at"],
        "revokedBy": row["revoked_by"],
        "lastOpenedAt": row["last_opened_at"],
        "lastOpenedIp": row["last_opened_ip"],
        "notes": row["notes"] or "",
        "url": signature_link_public_url(row["link_type"], row["token"]) if row["status"] == "active" else "",
    }


def get_latest_signature_link(connection, form_id, link_type="assignment"):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE form_id = ? AND link_type = ? ORDER BY created_at DESC LIMIT 1",
        (form_id, link_type),
    ).fetchone()
    return materialize_signature_link(connection, row)


def get_signature_link_by_id(connection, link_id):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE id = ?",
        (link_id,),
    ).fetchone()
    return materialize_signature_link(connection, row)


def get_signature_link_by_token(connection, token):
    row = connection.execute(
        "SELECT * FROM signature_links WHERE token = ?",
        (token,),
    ).fetchone()
    return materialize_signature_link(connection, row)


# ---------------------------------------------------------------------------
# Création / révocation
# ---------------------------------------------------------------------------

def revoke_signature_links_for_form(connection, form_id, actor=None, except_id=None, link_type="assignment"):
    actor = actor or current_actor()
    now = utc_now()
    rows = connection.execute(
        "SELECT * FROM signature_links WHERE form_id = ? AND link_type = ? AND status = 'active'",
        (form_id, link_type),
    ).fetchall()
    revoked = []
    for row in rows:
        if except_id and row["id"] == except_id:
            continue
        connection.execute(
            """
            UPDATE signature_links
            SET status = 'revoked', revoked_at = ?, revoked_by = ?
            WHERE id = ?
            """,
            (now, actor, row["id"]),
        )
        revoked.append(row["id"])
    return revoked


def create_signature_link(connection, form_id, actor=None, expires_in_hours=72, link_type="assignment"):
    actor = actor or current_actor()
    form_row = connection.execute(
        "SELECT id, dossier_id, title, payload_json FROM dotation_forms WHERE id = ?",
        (form_id,),
    ).fetchone()
    if not form_row:
        raise ValueError("Dossier introuvable.")

    payload = json.loads(form_row["payload_json"] or "{}")
    if link_type == "restitution":
        restitution = payload.get("restitution", {})
        has_restitution = bool(restitution.get("returnedAt"))
        if not has_restitution:
            raise ValueError("La restitution doit être préparée avant de générer un lien.")
        if restitution.get("signatureDataUrl"):
            raise ValueError("Cette restitution est déjà signée.")
    else:
        validation = payload.get("validation", {})
        if validation.get("signatureDataUrl"):
            raise ValueError("Ce dossier est déjà signé.")

    revoke_signature_links_for_form(connection, form_id, actor=actor, link_type=link_type)
    now = utc_now()
    row = {
        "id": generate_id("siglink"),
        "form_id": form_id,
        "link_type": link_type,
        "token": generate_signature_token(),
        "status": "active",
        "created_by": actor,
        "created_at": now,
        "expires_at": signature_link_expiration(expires_in_hours),
        "used_at": None,
        "revoked_at": None,
        "revoked_by": None,
        "last_opened_at": None,
        "last_opened_ip": None,
        "notes": "",
    }
    connection.execute(
        """
        INSERT INTO signature_links (
            id, form_id, link_type, token, status, created_by, created_at, expires_at,
            used_at, revoked_at, revoked_by, last_opened_at, last_opened_ip, notes
        ) VALUES (
            :id, :form_id, :link_type, :token, :status, :created_by, :created_at, :expires_at,
            :used_at, :revoked_at, :revoked_by, :last_opened_at, :last_opened_ip, :notes
        )
        """,
        row,
    )
    link_label = signature_link_label(link_type)
    link_scope = signature_link_scope(link_type)
    insert_audit_event(
        connection,
        form_row["dossier_id"],
        "signature_link_created",
        f"{link_label} généré",
        {"form_id": form_id, "title": form_row["title"], "expires_at": row["expires_at"], "link_type": link_type},
    )
    insert_app_log(
        connection,
        link_scope,
        "signature_link_created",
        f"{link_label} généré",
        "form",
        form_id,
        {"title": form_row["title"], "expires_at": row["expires_at"], "link_type": link_type},
        actor=actor,
    )
    return row


def revoke_signature_link(connection, link_id, actor=None):
    actor = actor or current_actor()
    row = get_signature_link_by_id(connection, link_id)
    if not row:
        return None
    if row["status"] in {"used", "revoked"}:
        return row
    now = utc_now()
    connection.execute(
        "UPDATE signature_links SET status = 'revoked', revoked_at = ?, revoked_by = ? WHERE id = ?",
        (now, actor, link_id),
    )
    form_row = connection.execute(
        "SELECT dossier_id, title FROM dotation_forms WHERE id = ?",
        (row["form_id"],),
    ).fetchone()
    if form_row:
        link_label = signature_link_label(row["link_type"])
        link_scope = signature_link_scope(row["link_type"])
        insert_audit_event(
            connection,
            form_row["dossier_id"],
            "signature_link_revoked",
            f"{link_label} révoqué",
            {"form_id": row["form_id"], "title": form_row["title"], "link_type": row["link_type"]},
        )
        insert_app_log(
            connection,
            link_scope,
            "signature_link_revoked",
            f"{link_label} révoqué",
            "form",
            row["form_id"],
            {"title": form_row["title"], "link_type": row["link_type"]},
            actor=actor,
        )
    return get_signature_link_by_id(connection, link_id)
