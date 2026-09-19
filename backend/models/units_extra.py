"""Parc : conservation RGPD, import CSV du parc initial et indicateurs.

Separe de models/units.py (coeur : etats, journal, synchronisation) pour rester lisible.
"""
import csv
import io
import json
import unicodedata
from datetime import datetime, timedelta, timezone

from models.inventory import align_fields, normalize_identifier, resolve_identifier_key
from models.resource_rules import effective_tracking_mode
from models.units import _get_or_create_unit, _record, recompute_unit
from utils import utc_now

ANONYMIZED_LABEL = "Ancien détenteur (anonymisé)"
DEFAULT_RETENTION_YEARS = 5
MAX_IMPORT_ROWS = 5000

# Statut souhaite a l'import -> evenement qui y mene.
IMPORT_EVENTS = {"in_stock": "verified", "degraded": "returned_degraded", "lost": "lost", "retired": "retired"}
STATUS_WORDS = {
    "in_stock": {"en stock", "stock", "disponible", "in_stock"},
    "degraded": {"degrade", "en mauvais etat", "abime", "degraded"},
    "lost": {"perdu", "vole", "lost"},
    "retired": {"reforme", "hors service", "retired"},
}


# ---------------------------------------------------------------------------
# Conservation RGPD
# ---------------------------------------------------------------------------

def anonymize_old_holders(connection, years=DEFAULT_RETENTION_YEARS, now=None):
    """Au-dela de `years` ans, le nom du detenteur est retire des evenements (l'evenement lui-meme est conserve :
    l'historique d'un objet garde sa valeur). Un objet actuellement detenu n'est jamais anonymise."""
    years = max(1, int(years))
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=365 * years)).strftime("%Y-%m-%dT%H:%M:%S")
    cursor = connection.execute(
        """UPDATE resource_unit_events SET holder_label = ?
           WHERE holder_label IS NOT NULL AND holder_label != ? AND holder_label != '' AND occurred_at < ?
             AND NOT EXISTS (SELECT 1 FROM resource_units u WHERE u.id = resource_unit_events.unit_id
                             AND u.status IN ('assigned', 'reserved') AND u.holder_form_id = resource_unit_events.form_id)""",
        (ANONYMIZED_LABEL, ANONYMIZED_LABEL, cutoff),
    )
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Import CSV
# ---------------------------------------------------------------------------

def _plain(value):
    text = unicodedata.normalize("NFD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def _unit_resources(connection):
    """{code: {label, identifier_key, fields: {cle: libelle}}} pour les ressources suivies par objet."""
    result = {}
    for row in connection.execute("SELECT code, label, category, tracking_mode, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        if effective_tracking_mode(row["tracking_mode"], row["category"], schema) != "unit":
            continue
        key = resolve_identifier_key(schema)
        if key:
            result[row["code"]] = {"label": row["label"], "identifier_key": key,
                                   "fields": {f["key"]: f.get("label") or f["key"] for f in schema if isinstance(f, dict) and f.get("key")}}
    return result


def _read_rows(text):
    text = text.lstrip("﻿")
    sample = text[:2000]
    delimiter = max(";,\t", key=sample.count) if sample else ";"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = [{_plain(k): (v or "").strip() for k, v in row.items() if k} for row in reader]
    return rows


def import_units(connection, text, actor=None, dry_run=True):
    """Importe un parc initial depuis un CSV. Colonnes : ressource, identifiant (ou le libelle du champ identifiant),
    etat (facultatif : en stock par defaut) et, au choix, une colonne par champ de la ressource (marque, modele...).
    dry_run : verifie et compte sans rien ecrire. Retourne {rows, created, skipped, errors}."""
    resources = _unit_resources(connection)
    by_label = {_plain(cfg["label"]): code for code, cfg in resources.items()}
    by_code = {_plain(code): code for code in resources}
    rows = _read_rows(text)
    report = {"rows": len(rows), "created": 0, "skipped": 0, "errors": [], "dry_run": dry_run}
    if len(rows) > MAX_IMPORT_ROWS:
        report["errors"].append({"line": 0, "message": f"Trop de lignes (maximum {MAX_IMPORT_ROWS})."})
        return report
    seen = set()
    for index, row in enumerate(rows, start=2):  # ligne 1 = en-tete
        token = _plain(row.get("ressource") or row.get("resource"))
        code = by_code.get(token) or by_label.get(token)
        if not code:
            report["errors"].append({"line": index, "message": f"Ressource inconnue ou non suivie par objet : « {row.get('ressource') or row.get('resource') or ''} »."})
            continue
        cfg = resources[code]
        label_to_key = {_plain(label): key for key, label in cfg["fields"].items()}
        key_by_plain = {_plain(key): key for key in cfg["fields"]}
        identifier = row.get("identifiant") or row.get("identifier") or row.get(_plain(cfg["fields"][cfg["identifier_key"]])) or row.get(_plain(cfg["identifier_key"]))
        if not normalize_identifier(identifier):
            report["errors"].append({"line": index, "message": "Identifiant manquant."})
            continue
        status_word = _plain(row.get("etat") or row.get("statut") or row.get("status") or "en stock")
        status = next((s for s, words in STATUS_WORDS.items() if status_word in words), None)
        if not status:
            report["errors"].append({"line": index, "message": f"État inconnu : « {status_word} » (en stock, dégradé, perdu, réformé)."})
            continue
        key = (code, normalize_identifier(identifier))
        if key in seen:
            report["errors"].append({"line": index, "message": f"Doublon dans le fichier : {identifier}."})
            continue
        seen.add(key)
        exists = connection.execute(
            """SELECT 1 FROM resource_units WHERE resource_code = ? AND (identifier_norm = ?
               OR id IN (SELECT unit_id FROM resource_unit_aliases WHERE resource_code = ? AND identifier_norm = ?))""",
            (code, key[1], code, key[1]),
        ).fetchone()
        if exists:
            report["skipped"] += 1
            continue
        fields = {cfg["identifier_key"]: identifier}
        for column, value in row.items():
            field_key = key_by_plain.get(column) or label_to_key.get(column)
            if field_key and value and field_key != cfg["identifier_key"]:
                fields[field_key] = value
        if not dry_run:
            unit_id, _created = _get_or_create_unit(connection, code, identifier, fields, "import", status="in_stock")
            _record(connection, unit_id, IMPORT_EVENTS[status], utc_now(), None, notes="Import du parc initial", actor=actor, source="import")
            recompute_unit(connection, unit_id)
        report["created"] += 1
    return report


# ---------------------------------------------------------------------------
# Indicateurs
# ---------------------------------------------------------------------------

def _days(start, end):
    try:
        a = datetime.fromisoformat(str(start).replace("Z", "+00:00")[:19])
        b = datetime.fromisoformat(str(end).replace("Z", "+00:00")[:19])
    except ValueError:
        return None
    return max(0.0, (b - a).total_seconds() / 86400)


def compute_indicators(connection, resource_code=None, long_hold_days=365, now=None):
    """Indicateurs du parc : repartition, duree moyenne de detention, taux de degradation, objets detenus depuis
    tres longtemps, rotation, anomalies."""
    where, params = ("WHERE u.resource_code = ?", [resource_code]) if resource_code else ("", [])
    units = connection.execute(f"SELECT u.id, u.status FROM resource_units u {where}", params).fetchall()
    events = connection.execute(
        f"""SELECT e.unit_id, e.event_type, e.occurred_at, e.anomaly FROM resource_unit_events e
            JOIN resource_units u ON u.id = e.unit_id {where} ORDER BY e.occurred_at, e.seq""", params
    ).fetchall()
    per_unit, anomalies = {}, 0
    for event in events:
        per_unit.setdefault(event["unit_id"], []).append(event)
        anomalies += 1 if event["anomaly"] else 0
    now_text = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")
    durations, assignments, returned_ok, returned_bad, long_held = [], 0, 0, 0, 0
    for unit_events in per_unit.values():
        open_since = None
        for event in unit_events:
            kind = event["event_type"]
            if kind == "assigned":
                assignments += 1
                open_since = event["occurred_at"]
            elif kind in ("returned", "returned_degraded", "lost", "released") and open_since:
                span = _days(open_since, event["occurred_at"])
                if span is not None:
                    durations.append(span)
                open_since = None
            returned_ok += 1 if kind == "returned" else 0
            returned_bad += 1 if kind == "returned_degraded" else 0
        if open_since:
            span = _days(open_since, now_text)
            long_held += 1 if span is not None and span > long_hold_days else 0
    total_returns = returned_ok + returned_bad
    status_counts = {}
    for unit in units:
        status_counts[unit["status"]] = status_counts.get(unit["status"], 0) + 1
    return {
        "units": len(units),
        "by_status": status_counts,
        "avg_hold_days": round(sum(durations) / len(durations), 1) if durations else None,
        "damage_rate": round(100 * returned_bad / total_returns, 1) if total_returns else None,
        "assignments_per_unit": round(assignments / len(units), 2) if units else None,
        "long_held": long_held,
        "long_hold_days": long_hold_days,
        "anomalies": anomalies,
        "to_verify": status_counts.get("unknown", 0),
    }


# ---------------------------------------------------------------------------
# Donnees a verifier : lignes sans identifiant, doublons probables
# ---------------------------------------------------------------------------

# Mots qui n'identifient rien dans « Badge 40 », « N° 40 », « carte 40 » : seul le numero compte.
_LABEL_WORDS = {"badge", "n", "no", "num", "numero", "nr", "carte", "tag", "telepeage", "ref", "reference"}


def duplicate_key(identifier):
    """Cle de rapprochement de deux identifiants qui designent probablement le meme objet :
    « Badge 40 », « N° 40 » et « 40 » -> « 40 » ; « 019 » et « 19 » -> « 19 » ; sinon les caracteres alphanumeriques."""
    import re
    tokens = re.findall(r"[a-z0-9]+", _plain(identifier))
    words = [t for t in tokens if not t.isdigit()]
    numbers = [t for t in tokens if t.isdigit()]
    if len(numbers) == 1 and all(w in _LABEL_WORDS for w in words):
        return numbers[0].lstrip("0") or "0"
    return "".join(tokens)


def _mask_holder(label, mask):
    if not mask or not label:
        return label
    from utils import mask_text
    return " ".join(mask_text(part) for part in str(label).split(" "))


def find_incomplete_lines(connection, mask=False, limit=500):
    """Lignes attribuees sur une ressource suivie par objet MAIS sans identifiant : elles n'apparaissent pas dans le parc.
    Un dossier annule est ignore. Retourne [{form_id, resource_code, resource_label, holder_label, status, updated_at}]."""
    from models.inventory import _fields_of
    from models.units import _holder_label, unit_identifier_keys
    keys = unit_identifier_keys(connection)
    labels = {r["code"]: r["label"] for r in connection.execute("SELECT code, label FROM resource_catalog").fetchall()}
    result = []
    rows = connection.execute(
        "SELECT i.form_id, i.item_key, i.details_json, f.status, f.nom, f.prenom, f.service, f.updated_at"
        " FROM dotation_items i JOIN dotation_forms f ON f.id = i.form_id"
        " WHERE i.assigned = 1 AND f.status != 'cancelled' ORDER BY f.updated_at DESC"
    ).fetchall()
    for row in rows:
        config = keys.get(row["item_key"])
        if not config:
            continue
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        fields = align_fields(_fields_of(details), config["fields"])
        if normalize_identifier(fields.get(config["identifier"])):
            continue
        result.append({
            "form_id": row["form_id"], "resource_code": row["item_key"], "resource_label": labels.get(row["item_key"], row["item_key"]),
            "holder_label": _mask_holder(_holder_label(row), mask), "status": row["status"], "updated_at": row["updated_at"],
        })
        if len(result) >= limit:
            break
    return result


def find_duplicate_candidates(connection, mask=False):
    """Groupes d'unites d'une meme ressource dont les identifiants se ressemblent (voir duplicate_key). Ne fusionne rien :
    c'est une aide a la decision, la fusion reste une action manuelle (parc.manage)."""
    groups = {}
    for unit in connection.execute(
        "SELECT id, resource_code, identifier, status, holder_label FROM resource_units ORDER BY resource_code, identifier"
    ).fetchall():
        key = duplicate_key(unit["identifier"])
        if key:
            groups.setdefault((unit["resource_code"], key), []).append(unit)
    labels = {r["code"]: r["label"] for r in connection.execute("SELECT code, label FROM resource_catalog").fetchall()}
    result = []
    for (code, key), units in sorted(groups.items()):
        if len(units) < 2:
            continue
        result.append({
            "resource_code": code, "resource_label": labels.get(code, code), "key": key,
            "units": [{"id": u["id"], "identifier": u["identifier"], "status": u["status"], "holder_label": _mask_holder(u["holder_label"], mask)} for u in units],
        })
    return result
