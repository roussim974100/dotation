"""Parc : unites (objets individuels) et journal d'evenements immuable.

Une « unite » est un objet identifie (n° de serie, immatriculation, n° de badge...) d'une ressource dont le mode
de suivi est « unit ». Son historique est un journal d'evenements qu'on ne modifie jamais (une erreur se corrige
par un evenement, pas par une reecriture). Le journal est alimente automatiquement a chaque enregistrement de
dossier (sync_units_for_form, idempotent) et survit a la suppression du dossier d'origine.

Les transitions (next_status) sont pures : elles ne bloquent jamais un evenement reel, elles le signalent
(« anomalie ») quand il contredit l'etat connu, par exemple une double attribution.
"""
import json

from models.inventory import (
    DEGRADED_CONDITIONS, READY_CONDITIONS, _fields_of, normalize_identifier, resolve_identifier_key,
)
from models.resource_rules import effective_tracking_mode
from utils import generate_id, utc_now

UNIT_STATUSES = ("in_stock", "assigned", "degraded", "lost", "retired", "unknown")
EVENT_TYPES = ("assigned", "returned", "returned_degraded", "lost", "released", "note")
# Une attribution n'est effective qu'une fois le dossier signe (les brouillons relevent de la reservation, etape 4).
EFFECTIVE_ASSIGNMENT_STATUSES = {"active", "partial_return", "returned"}


# ---------------------------------------------------------------------------
# Transitions (pures)
# ---------------------------------------------------------------------------

def next_status(current, event_type):
    """Retourne (nouvel etat, anomalie ou None). Ne leve jamais pour un evenement connu : la realite prime."""
    if event_type == "assigned":
        if current == "assigned":
            return "assigned", "double_attribution"
        if current in ("lost", "retired"):
            return "assigned", "assigned_while_" + current
        return "assigned", None
    if event_type == "returned":
        return "in_stock", None
    if event_type == "returned_degraded":
        return "degraded", None
    if event_type == "lost":
        return "lost", None if current == "assigned" else "lost_without_assignment"
    if event_type == "released":
        return "in_stock", None
    if event_type == "note":
        return current or "in_stock", None
    raise ValueError(f"Evenement inconnu : {event_type}")


def derive_state(events):
    """Etat courant d'une unite a partir de ses evenements (tries par date puis ordre d'insertion)."""
    status, holder = None, None
    for event in events:
        status, _anomaly = next_status(status, event["event_type"])
        if event["event_type"] == "assigned":
            holder = {"form_id": event.get("form_id"), "label": event.get("holder_label")}
        elif event["event_type"] in ("returned", "returned_degraded", "lost", "released"):
            holder = None
    return (status or "in_stock"), holder


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_units_schema(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS resource_units (
            id TEXT PRIMARY KEY,
            resource_code TEXT NOT NULL,
            identifier TEXT NOT NULL,
            identifier_norm TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'in_stock',
            holder_form_id TEXT,
            holder_label TEXT,
            fields_json TEXT NOT NULL DEFAULT '{}',
            origin TEXT NOT NULL DEFAULT 'dossier',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (resource_code, identifier_norm)
        );
        CREATE TABLE IF NOT EXISTS resource_unit_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            form_id TEXT,
            holder_label TEXT,
            condition TEXT,
            notes TEXT,
            anomaly TEXT,
            actor TEXT,
            source TEXT NOT NULL DEFAULT 'auto',
            dedupe_key TEXT UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (unit_id) REFERENCES resource_units (id)
        );
        CREATE INDEX IF NOT EXISTS idx_unit_events_unit ON resource_unit_events (unit_id, occurred_at, seq);
        CREATE INDEX IF NOT EXISTS idx_units_resource ON resource_units (resource_code, status);
        """
    )


# ---------------------------------------------------------------------------
# Ecriture
# ---------------------------------------------------------------------------

def unit_identifier_keys(connection):
    """{code de ressource: cle du champ identifiant} pour les ressources suivies par objet."""
    keys = {}
    for row in connection.execute("SELECT code, category, tracking_mode, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        if effective_tracking_mode(row["tracking_mode"], row["category"], schema) == "unit":
            key = resolve_identifier_key(schema)
            if key:
                keys[row["code"]] = key
    return keys


def _when(value):
    """Date d'evenement comparable : une date sans heure vaut debut de journee."""
    text = str(value or "").strip()
    return text + "T00:00:00" if len(text) == 10 else text


def _holder_label(form):
    name = f"{form['nom'] or ''} {form['prenom'] or ''}".strip()
    return f"{name} · {form['service']}" if name and form["service"] else (name or form["service"] or "")


def _get_or_create_unit(connection, code, raw_identifier, fields, origin, status="in_stock"):
    norm = normalize_identifier(raw_identifier)
    row = connection.execute(
        "SELECT id FROM resource_units WHERE resource_code = ? AND identifier_norm = ?", (code, norm)
    ).fetchone()
    now = utc_now()
    clean = {k: v for k, v in fields.items() if isinstance(v, (str, int, float)) and str(v).strip() != ""}
    if row:
        connection.execute("UPDATE resource_units SET fields_json = ?, updated_at = ? WHERE id = ?", (json.dumps(clean, ensure_ascii=False), now, row["id"]))
        return row["id"], False
    unit_id = generate_id("unit")
    connection.execute(
        "INSERT INTO resource_units (id, resource_code, identifier, identifier_norm, status, fields_json, origin, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (unit_id, code, str(raw_identifier).strip(), norm, status, json.dumps(clean, ensure_ascii=False), origin, now, now),
    )
    return unit_id, True


def _record(connection, unit_id, event_type, occurred_at, dedupe_key, form_id=None, holder_label=None,
            condition=None, notes=None, actor=None, source="auto"):
    """Ajoute un evenement s'il n'existe pas deja (dedupe_key) ; retourne True si ajoute."""
    key = f"{unit_id}:{dedupe_key}" if dedupe_key else None
    if key and connection.execute("SELECT 1 FROM resource_unit_events WHERE dedupe_key = ?", (key,)).fetchone():
        return False
    # Anomalie evaluee sur l'etat de l'unite AU MOMENT de l'evenement (ceux qui le precedent), pas sur l'etat stocke.
    when = occurred_at or utc_now()
    before = [dict(row) for row in connection.execute(
        "SELECT event_type, form_id, holder_label FROM resource_unit_events WHERE unit_id = ? AND occurred_at <= ? ORDER BY occurred_at, seq",
        (unit_id, when),
    ).fetchall()]
    previous = derive_state(before)[0] if before else None
    _new_status, anomaly = next_status(previous, event_type)
    connection.execute(
        """INSERT INTO resource_unit_events
           (unit_id, event_type, occurred_at, form_id, holder_label, condition, notes, anomaly, actor, source, dedupe_key, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (unit_id, event_type, occurred_at or utc_now(), form_id, holder_label, condition, notes, anomaly, actor, source, key, utc_now()),
    )
    return True


def recompute_unit(connection, unit_id):
    events = [dict(row) for row in connection.execute(
        "SELECT event_type, form_id, holder_label FROM resource_unit_events WHERE unit_id = ? ORDER BY occurred_at, seq", (unit_id,)
    ).fetchall()]
    status, holder = derive_state(events)
    connection.execute(
        "UPDATE resource_units SET status = ?, holder_form_id = ?, holder_label = ?, updated_at = ? WHERE id = ?",
        (status, holder["form_id"] if holder else None, holder["label"] if holder else None, utc_now(), unit_id),
    )


def sync_units_for_form(connection, form_id, keys=None):
    """Met le parc a jour d'apres l'etat courant d'un dossier. Idempotent ; ne modifie jamais le dossier."""
    form = connection.execute(
        "SELECT id, status, nom, prenom, service, assigned_at, returned_at, updated_at FROM dotation_forms WHERE id = ?", (form_id,)
    ).fetchone()
    if not form:
        return 0
    keys = keys if keys is not None else unit_identifier_keys(connection)
    if not keys:
        return 0
    label = _holder_label(form)
    effective = form["status"] in EFFECTIVE_ASSIGNMENT_STATUSES
    touched, added = set(), 0
    items = connection.execute(
        "SELECT item_key, returned_at, return_condition, details_json FROM dotation_items WHERE form_id = ? AND assigned = 1", (form_id,)
    ).fetchall()
    for item in items:
        identifier_key = keys.get(item["item_key"])
        if not identifier_key:
            continue
        try:
            details = json.loads(item["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        fields = _fields_of(details)
        raw = fields.get(identifier_key)
        if not normalize_identifier(raw):
            continue
        condition = item["return_condition"] or "pending"
        event = ("returned" if condition in READY_CONDITIONS else "returned_degraded" if condition in DEGRADED_CONDITIONS
                 else "lost" if condition == "non_restitue" else None)
        # Un objet n'entre dans le parc qu'a la signature du dossier, ou si une restitution prouve qu'il a ete
        # attribue. Le choix dans un brouillon releve de la reservation (etape ulterieure), pas de l'etat reel.
        if not effective and not event:
            continue
        unit_id, _created = _get_or_create_unit(connection, item["item_key"], raw, fields, "dossier")
        touched.add(unit_id)
        assigned_when = _when(form["assigned_at"] or form["updated_at"])
        added += _record(connection, unit_id, "assigned", assigned_when, f"assign:{form_id}", form_id, label, source="dossier")
        if event:
            returned_when = _when(item["returned_at"] or form["returned_at"] or form["updated_at"])
            note = None
            if returned_when < assigned_when:
                # Un retour ne peut pas preceder l'attribution : il est ramene a l'attribution (ce qui classe aussi un retour
                # « du jour » apres l'attribution du jour). On n'annote que si la date est reellement anterieure.
                if returned_when[:10] < assigned_when[:10]:
                    note = f"Date de restitution ({returned_when[:10]}) antérieure à l'attribution : ramenée à la date d'attribution"
                returned_when = assigned_when
            added += _record(connection, unit_id, event, returned_when, f"{event}:{form_id}", form_id, label,
                             condition=condition, notes=note, source="dossier")
    for unit_id in touched:
        recompute_unit(connection, unit_id)
    return added


def release_units_for_form(connection, form_id):
    """Dossier supprime : l'objet qu'il detenait est libere (l'historique reste, avec la mention)."""
    rows = connection.execute("SELECT id FROM resource_units WHERE holder_form_id = ?", (form_id,)).fetchall()
    for row in rows:
        _record(connection, row["id"], "released", utc_now(), f"release:{form_id}", form_id,
                notes="Dossier supprimé : attribution annulée", source="dossier")
        recompute_unit(connection, row["id"])
    return len(rows)


def backfill_units(connection):
    """Reconstitue le parc depuis l'historique existant. Idempotent. Les lignes de dossiers supprimes donnent des
    unites « a verifier » (statut reel inconnu) tant qu'un administrateur ne les a pas confirmees."""
    ensure_units_schema(connection)
    keys = unit_identifier_keys(connection)
    forms = 0
    for row in connection.execute("SELECT id FROM dotation_forms").fetchall():
        sync_units_for_form(connection, row["id"], keys)
        forms += 1
    orphans = 0
    for item in connection.execute(
        "SELECT item_key, details_json FROM dotation_items WHERE assigned = 1 AND form_id NOT IN (SELECT id FROM dotation_forms)"
    ).fetchall():
        identifier_key = keys.get(item["item_key"])
        if not identifier_key:
            continue
        try:
            fields = _fields_of(json.loads(item["details_json"] or "{}"))
        except (TypeError, ValueError):
            continue
        raw = fields.get(identifier_key)
        if not normalize_identifier(raw):
            continue
        unit_id, created = _get_or_create_unit(connection, item["item_key"], raw, fields, "backfill_orphan", status="unknown")
        if created:
            _record(connection, unit_id, "note", utc_now(), "orphan", notes="Reconstitué depuis un dossier supprimé : statut réel à vérifier", source="backfill")
            recompute_unit(connection, unit_id)
            connection.execute("UPDATE resource_units SET status = 'unknown' WHERE id = ?", (unit_id,))
            orphans += 1
    return {"forms": forms, "orphan_units": orphans}


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def _public_unit(row, mask):
    unit = dict(row)
    unit["fields"] = json.loads(unit.pop("fields_json") or "{}")
    if mask:
        unit["holder_label"] = "—" if unit.get("holder_label") else None
    return unit


def list_units(connection, resource_code=None, query="", status=None, limit=200, mask=False):
    sql, params = "SELECT * FROM resource_units WHERE 1=1", []
    if resource_code:
        sql += " AND resource_code = ?"
        params.append(resource_code)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if query:
        sql += " AND (identifier_norm LIKE ? OR fields_json LIKE ?)"
        like = f"%{normalize_identifier(query)}%"
        params += [like, f"%{query}%"]
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(min(int(limit), 500))
    return [_public_unit(row, mask) for row in connection.execute(sql, params).fetchall()]


def get_unit(connection, unit_id, mask=False):
    row = connection.execute("SELECT * FROM resource_units WHERE id = ?", (unit_id,)).fetchone()
    if not row:
        return None
    unit = _public_unit(row, mask)
    events = [dict(e) for e in connection.execute(
        "SELECT event_type, occurred_at, form_id, holder_label, condition, notes, anomaly, actor, source FROM resource_unit_events WHERE unit_id = ? ORDER BY occurred_at, seq",
        (unit_id,),
    ).fetchall()]
    if mask:
        for event in events:
            event["holder_label"] = "—" if event["holder_label"] else None
    unit["events"] = events
    return unit
