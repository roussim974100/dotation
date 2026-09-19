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

UNIT_STATUSES = ("in_stock", "reserved", "assigned", "degraded", "maintenance", "lost", "retired", "unknown")
EVENT_TYPES = ("assigned", "returned", "returned_degraded", "lost", "released", "note", "found", "retired",
               "repair_started", "repair_done", "verified", "correction", "merged", "reserved",
               "reservation_released", "transferred")
# Une reservation (objet choisi dans un dossier pas encore signe) expire apres cette duree sans activite du dossier.
RESERVATION_DAYS = 30

# Actions manuelles (droit parc.manage) : evenement produit, etats de depart autorises, motif obligatoire.
MANUAL_ACTIONS = {
    "lost": {"event": "lost", "from": {"in_stock", "assigned", "degraded", "maintenance", "unknown"}, "note_required": True},
    "found": {"event": "found", "from": {"lost"}, "note_required": False},
    "retire": {"event": "retired", "from": {"in_stock", "degraded", "lost", "unknown", "maintenance"}, "note_required": True},
    "repair_start": {"event": "repair_started", "from": {"in_stock", "degraded"}, "note_required": False},
    "repair_done": {"event": "repair_done", "from": {"maintenance"}, "note_required": False},
    "verify": {"event": "verified", "from": {"unknown"}, "note_required": False},
    "note": {"event": "note", "from": None, "note_required": True},
    # Mobilite interne : l'objet change de detenteur sans etre restitue (le nouveau detenteur est obligatoire).
    "transfer": {"event": "transferred", "from": {"assigned"}, "note_required": False, "holder_required": True},
}


class UnitActionError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
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
        return "assigned", None  # y compris depuis « reserved » : la reservation devient attribution
    if event_type == "reserved":
        if current in (None, "in_stock", "degraded", "unknown"):
            return "reserved", None
        if current == "reserved":
            return "reserved", "double_reservation"
        return current, "reserved_while_" + current  # l'objet est deja pris : on signale, l'etat ne change pas
    if event_type == "reservation_released":
        return ("in_stock" if current == "reserved" else current or "in_stock"), None
    if event_type == "transferred":
        return "assigned", None
    if event_type == "returned":
        return "in_stock", None
    if event_type == "returned_degraded":
        return "degraded", None
    if event_type == "lost":
        return "lost", None if current == "assigned" else "lost_without_assignment"
    if event_type == "released":
        return "in_stock", None
    if event_type in ("note", "correction", "merged"):
        return current or "in_stock", None
    if event_type in ("found", "repair_done", "verified"):
        return "in_stock", None
    if event_type == "retired":
        return "retired", None
    if event_type == "repair_started":
        return "maintenance", None
    raise ValueError(f"Evenement inconnu : {event_type}")


def derive_state(events):
    """Etat courant d'une unite a partir de ses evenements (tries par date puis ordre d'insertion).
    Les reservations sont suivies par dossier et se superposent a l'etat de base : tant qu'un dossier au moins
    reserve l'objet disponible, il apparait « reserve » ; lever la reservation d'un dossier ne libere pas l'objet
    si un autre dossier le reserve encore."""
    base, holder, reservations = None, None, {}
    for event in events:
        kind, form = event["event_type"], event.get("form_id")
        if kind == "reserved":
            reservations[form] = event.get("holder_label")
            continue
        if kind == "reservation_released":
            reservations.pop(form, None)
            continue
        if kind in ("assigned", "released"):
            reservations.pop(form, None)  # la reservation de ce dossier devient attribution, ou disparait avec lui
        if kind == "released":
            # Dossier supprime : n'affecte l'etat de base que s'il detenait l'objet (pas s'il ne faisait que le reserver).
            if holder and holder.get("form_id") == form:
                base, holder = "in_stock", None
            continue
        base, _anomaly = next_status(base, kind)
        if kind in ("assigned", "transferred"):
            holder = {"form_id": form or (holder or {}).get("form_id"), "label": event.get("holder_label")}
        elif kind in ("returned", "returned_degraded", "lost", "retired", "found", "repair_started", "repair_done", "verified"):
            holder = None
    status = base or "in_stock"
    if reservations and status in ("in_stock", "degraded", "unknown"):
        last_form = list(reservations)[-1]
        return "reserved", {"form_id": last_form, "label": reservations[last_form]}
    return status, holder


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
        CREATE TABLE IF NOT EXISTS resource_unit_aliases (
            resource_code TEXT NOT NULL,
            identifier_norm TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            PRIMARY KEY (resource_code, identifier_norm)
        );
        CREATE INDEX IF NOT EXISTS idx_unit_events_unit ON resource_unit_events (unit_id, occurred_at, seq);
        CREATE INDEX IF NOT EXISTS idx_units_resource ON resource_units (resource_code, status);
        """
    )


# ---------------------------------------------------------------------------
# Ecriture
# ---------------------------------------------------------------------------

def unit_identifier_keys(connection):
    """{code de ressource: {"identifier": cle du champ identifiant, "fields": cles des champs de la ressource}} pour les
    ressources suivies par objet."""
    keys = {}
    for row in connection.execute("SELECT code, category, tracking_mode, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        if effective_tracking_mode(row["tracking_mode"], row["category"], schema) == "unit":
            key = resolve_identifier_key(schema)
            if key:
                keys[row["code"]] = {"identifier": key, "fields": {f["key"] for f in schema if isinstance(f, dict) and f.get("key")}}
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
    if not row:
        alias = connection.execute(
            "SELECT unit_id FROM resource_unit_aliases WHERE resource_code = ? AND identifier_norm = ?", (code, norm)
        ).fetchone()
        row = {"id": alias["unit_id"]} if alias else None
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
    if source == "manual":
        anomaly = None  # une action volontaire d'un gestionnaire n'est pas une incoherence de donnees
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


def _has_active_reservation(connection, unit_id, form_id):
    """Ce dossier reserve-t-il deja cet objet ? (son dernier evenement sur l'unite est une reservation)"""
    row = connection.execute(
        "SELECT event_type FROM resource_unit_events WHERE unit_id = ? AND form_id = ? ORDER BY occurred_at DESC, seq DESC LIMIT 1",
        (unit_id, form_id),
    ).fetchone()
    return bool(row and row["event_type"] == "reserved")


def sync_units_for_form(connection, form_id, keys=None):
    """Met le parc a jour d'apres l'etat courant d'un dossier. Idempotent ; ne modifie jamais le dossier."""
    form = connection.execute(
        "SELECT id, status, dossier_type, nom, prenom, service, assigned_at, returned_at, updated_at FROM dotation_forms WHERE id = ?", (form_id,)
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
        config = keys.get(item["item_key"])
        if not config:
            continue
        identifier_key = config["identifier"]
        try:
            details = json.loads(item["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        # Seuls les champs definis par la ressource : les anciens dossiers melangent des donnees internes.
        fields = {k: v for k, v in _fields_of(details).items() if k in config["fields"]}
        raw = fields.get(identifier_key)
        if not normalize_identifier(raw):
            continue
        condition = item["return_condition"] or "pending"
        event = ("returned" if condition in READY_CONDITIONS else "returned_degraded" if condition in DEGRADED_CONDITIONS
                 else "lost" if condition == "non_restitue" else None)
        # Dossier signe (ou restitution qui prouve l'attribution) : attribution effective. Brouillon : simple
        # reservation de l'objet, qui evite qu'un autre dossier le choisisse en meme temps.
        origin = "regularisation" if form["dossier_type"] == "sortie" else "dossier"
        if not effective and not event:
            if form["status"] == "cancelled":
                continue
            unit_id, _created = _get_or_create_unit(connection, item["item_key"], raw, fields, origin)
            touched.add(unit_id)
            if not _has_active_reservation(connection, unit_id, form_id):
                count = connection.execute("SELECT COUNT(*) FROM resource_unit_events WHERE unit_id = ? AND event_type = 'reserved' AND form_id = ?",
                                           (unit_id, form_id)).fetchone()[0]
                added += _record(connection, unit_id, "reserved", _when(form["updated_at"]), f"reserve:{form_id}:{count}", form_id, label, source="dossier")
            continue
        unit_id, _created = _get_or_create_unit(connection, item["item_key"], raw, fields, origin)
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
    # Reservations devenues sans objet : l'objet a ete retire du dossier (ou le dossier a ete annule).
    for row in connection.execute("SELECT DISTINCT unit_id FROM resource_unit_events WHERE form_id = ?", (form_id,)).fetchall():
        unit_id = row["unit_id"]
        if _has_active_reservation(connection, unit_id, form_id) and (unit_id not in touched or form["status"] == "cancelled"):
            added += _record(connection, unit_id, "reservation_released", _when(form["updated_at"]), f"unreserve:{form_id}:{form['updated_at']}",
                             form_id, label, notes="Objet retiré du dossier" if form["status"] != "cancelled" else "Dossier annulé", source="dossier")
            touched.add(unit_id)
    for unit_id in touched:
        recompute_unit(connection, unit_id)
    return added


def release_stale_reservations(connection, days=RESERVATION_DAYS, now=None):
    """Leve les reservations des dossiers sans activite depuis `days` jours (brouillon abandonne) ou disparus."""
    from datetime import datetime, timedelta, timezone
    limit = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    released = 0
    for unit in connection.execute("SELECT id FROM resource_units WHERE status = 'reserved'").fetchall():
        for form_id in {r["form_id"] for r in connection.execute(
            "SELECT DISTINCT form_id FROM resource_unit_events WHERE unit_id = ? AND event_type = 'reserved'", (unit["id"],)).fetchall()}:
            if not _has_active_reservation(connection, unit["id"], form_id):
                continue
            form = connection.execute("SELECT updated_at FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
            if form is None or (form["updated_at"] or "") < limit:
                _record(connection, unit["id"], "reservation_released", utc_now(), f"expire:{form_id}:{limit[:10]}", form_id,
                        notes=f"Réservation expirée (aucune activité depuis {days} jours)", source="auto")
                released += 1
        recompute_unit(connection, unit["id"])
    return released


def release_units_for_form(connection, form_id):
    """Dossier supprime : les objets qu'il detenait ou reservait sont liberes (l'historique reste, avec la mention).
    Un objet reserve par un autre dossier reste reserve."""
    count = 0
    for row in connection.execute("SELECT DISTINCT unit_id FROM resource_unit_events WHERE form_id = ?", (form_id,)).fetchall():
        unit = connection.execute("SELECT holder_form_id, status FROM resource_units WHERE id = ?", (row["unit_id"],)).fetchone()
        if not unit:
            continue
        holds = unit["status"] == "assigned" and unit["holder_form_id"] == form_id
        if holds or _has_active_reservation(connection, row["unit_id"], form_id):
            if _record(connection, row["unit_id"], "released", utc_now(), f"release:{form_id}", form_id,
                       notes="Dossier supprimé : attribution ou réservation annulée", source="dossier"):
                recompute_unit(connection, row["unit_id"])
                count += 1
    return count


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
        config = keys.get(item["item_key"])
        if not config:
            continue
        identifier_key = config["identifier"]
        try:
            fields = {k: v for k, v in _fields_of(json.loads(item["details_json"] or "{}")).items() if k in config["fields"]}
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
    release_stale_reservations(connection)
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


# ---------------------------------------------------------------------------
# Actions manuelles (droit parc.manage)
# ---------------------------------------------------------------------------

def _require_unit(connection, unit_id):
    row = connection.execute("SELECT * FROM resource_units WHERE id = ?", (unit_id,)).fetchone()
    if not row:
        raise UnitActionError("unknown_unit", "Unité introuvable.")
    return row


def correct_identifier(connection, unit_id, new_identifier, actor=None):
    unit = _require_unit(connection, unit_id)
    identifier = str(new_identifier or "").strip()
    norm = normalize_identifier(identifier)
    if not norm:
        raise UnitActionError("identifier_required", "Le nouvel identifiant est obligatoire.")
    if norm == unit["identifier_norm"] and identifier == unit["identifier"]:
        raise UnitActionError("no_change", "L'identifiant est déjà celui-ci.")
    clash = connection.execute(
        "SELECT id FROM resource_units WHERE resource_code = ? AND identifier_norm = ? AND id != ?",
        (unit["resource_code"], norm, unit_id),
    ).fetchone()
    if clash:
        raise UnitActionError("identifier_exists", "Une autre unité porte déjà cet identifiant : utilisez la fusion.")
    # L'ancienne graphie reste un alias : un dossier qui la contient encore retombera sur cette unite.
    connection.execute(
        "INSERT OR REPLACE INTO resource_unit_aliases (resource_code, identifier_norm, unit_id) VALUES (?,?,?)",
        (unit["resource_code"], unit["identifier_norm"], unit_id),
    )
    connection.execute(
        "UPDATE resource_units SET identifier = ?, identifier_norm = ?, updated_at = ? WHERE id = ?", (identifier, norm, utc_now(), unit_id)
    )
    _record(connection, unit_id, "correction", utc_now(), None, notes=f"Identifiant corrigé : {unit['identifier']} → {identifier}",
            actor=actor, source="manual")


def merge_units(connection, source_id, target_id, actor=None):
    """Fusionne `source` dans `target` (meme ressource) : ses evenements et son identifiant passent a la cible."""
    if source_id == target_id:
        raise UnitActionError("same_unit", "Choisissez une autre unité.")
    source, target = _require_unit(connection, source_id), _require_unit(connection, target_id)
    if source["resource_code"] != target["resource_code"]:
        raise UnitActionError("different_resource", "Les deux unités doivent appartenir à la même ressource.")
    for event in connection.execute("SELECT seq, dedupe_key FROM resource_unit_events WHERE unit_id = ?", (source_id,)).fetchall():
        key = event["dedupe_key"]
        new_key = f"{target_id}:{key[len(source_id) + 1:]}" if key and key.startswith(source_id + ":") else key
        if new_key and connection.execute("SELECT 1 FROM resource_unit_events WHERE dedupe_key = ?", (new_key,)).fetchone():
            connection.execute("DELETE FROM resource_unit_events WHERE seq = ?", (event["seq"],))  # deja present dans la cible
        else:
            connection.execute("UPDATE resource_unit_events SET unit_id = ?, dedupe_key = ? WHERE seq = ?", (target_id, new_key, event["seq"]))
    connection.execute("UPDATE resource_unit_aliases SET unit_id = ? WHERE unit_id = ?", (target_id, source_id))
    connection.execute(
        "INSERT OR REPLACE INTO resource_unit_aliases (resource_code, identifier_norm, unit_id) VALUES (?,?,?)",
        (source["resource_code"], source["identifier_norm"], target_id),
    )
    connection.execute("DELETE FROM resource_units WHERE id = ?", (source_id,))
    _record(connection, target_id, "merged", utc_now(), None, notes=f"Fusion de l'unité « {source['identifier']} »", actor=actor, source="manual")
    recompute_unit(connection, target_id)


def apply_manual_action(connection, unit_id, action, notes="", actor=None, params=None):
    """Applique une action de gestion du parc et retourne l'unite a jour. Les evenements ne sont jamais modifies."""
    params = params or {}
    unit = _require_unit(connection, unit_id)
    notes = str(notes or "").strip()
    if action == "correct":
        correct_identifier(connection, unit_id, params.get("new_identifier"), actor)
    elif action == "merge":
        merge_units(connection, unit_id, params.get("target_unit_id"), actor)
        return get_unit(connection, params.get("target_unit_id"))
    else:
        spec = MANUAL_ACTIONS.get(action)
        if not spec:
            raise UnitActionError("invalid_action", "Action inconnue.")
        if spec["from"] is not None and unit["status"] not in spec["from"]:
            raise UnitActionError("invalid_state", "Cette action n'est pas possible dans l'état actuel de l'unité.")
        if spec["note_required"] and not notes:
            raise UnitActionError("note_required", "Précisez le motif.")
        holder = str(params.get("holder_label") or "").strip()
        if spec.get("holder_required") and not holder:
            raise UnitActionError("holder_required", "Indiquez le nouveau détenteur.")
        _record(connection, unit_id, spec["event"], utc_now(), None, holder_label=holder or None, notes=notes or None, actor=actor, source="manual")
    recompute_unit(connection, unit_id)
    return get_unit(connection, unit_id)


def count_units_by_status(connection, resource_code=None):
    sql, params = "SELECT status, COUNT(*) AS n FROM resource_units", []
    if resource_code:
        sql += " WHERE resource_code = ?"
        params.append(resource_code)
    sql += " GROUP BY status"
    return {row["status"]: row["n"] for row in connection.execute(sql, params).fetchall()}


def find_holder_unit(connection, resource_code, identifier, exclude_form_id=None):
    """Objet deja pris (attribue ou reserve) par un AUTRE dossier : retourne {status, service, since} ou None."""
    norm = normalize_identifier(identifier)
    if not norm:
        return None
    row = connection.execute(
        """SELECT u.id, u.status, u.holder_form_id, u.holder_label FROM resource_units u WHERE u.resource_code = ?
           AND (u.identifier_norm = ? OR u.id IN (SELECT unit_id FROM resource_unit_aliases WHERE resource_code = ? AND identifier_norm = ?))""",
        (resource_code, norm, resource_code, norm),
    ).fetchone()
    if not row or row["status"] not in ("assigned", "reserved"):
        return None
    if exclude_form_id and row["holder_form_id"] == exclude_form_id:
        return None
    since = connection.execute(
        "SELECT MAX(occurred_at) FROM resource_unit_events WHERE unit_id = ? AND event_type IN ('assigned', 'reserved', 'transferred')", (row["id"],)
    ).fetchone()[0]
    label = row["holder_label"] or ""
    return {"status": row["status"], "service": label.split("·", 1)[1].strip() if "·" in label else "", "since": since or ""}


def available_units_for_resource(connection, resource_code):
    """Objets reutilisables (en stock ou restitues degrades), les plus recemment rendus d'abord."""
    rows = connection.execute(
        """SELECT u.identifier, u.fields_json, u.status,
                  (SELECT MAX(occurred_at) FROM resource_unit_events e WHERE e.unit_id = u.id AND e.event_type IN ('returned', 'returned_degraded', 'found', 'repair_done', 'verified')) AS returned_at
           FROM resource_units u WHERE u.resource_code = ? AND u.status IN ('in_stock', 'degraded')""",
        (resource_code,),
    ).fetchall()
    units = [{"identifier": r["identifier"], "fields": json.loads(r["fields_json"] or "{}"),
              "status": "degraded" if r["status"] == "degraded" else "ok", "returned_at": r["returned_at"] or ""} for r in rows]
    units.sort(key=lambda unit: (unit["returned_at"], unit["identifier"]), reverse=True)
    return units
