"""Suivi par quantite : ressources en stock sans identifiant individuel (vetements, consommables...).

Un journal de mouvements signes (`resource_stock_movements`) remplace le suivi objet par objet : le stock courant est
la somme des mouvements, par ressource et par variante (ex. taille). Comme pour le parc, le journal est immuable
(on corrige par un mouvement d'ajustement, jamais en modifiant l'existant) et l'alimentation depuis les dossiers est
idempotente (cle de deduplication).

Types de mouvement (quantite signee) :
  receipt (+)            reception de stock                    | adjustment (+/-)  ajustement d'inventaire
  loss (-)               perte / casse constatee en stock      | assigned (-)      remise a un agent (dossier signe)
  assign_correction      correction si la quantite du dossier change apres signature
  returned (+)           retour en stock, bon etat             | returned_degraded (0)  retour degrade (ne revient pas en stock)
  lost_by_holder (0)     non restitue                          | released (+)      dossier supprime : la remise est annulee
"""
import csv
import io
import json
import unicodedata
import uuid

from models.resource_rules import effective_tracking_mode
from models.inventory import DEGRADED_CONDITIONS, READY_CONDITIONS, _fields_of, align_fields
from models.units import EFFECTIVE_ASSIGNMENT_STATUSES, _holder_label, _when
from utils import mask_text, utc_now

QUANTITY_KEYS = ("quantite", "quantity", "nombre")
VARIANT_KEYS = ("taille", "pointure", "variante")
MANUAL_KINDS = ("receipt", "adjustment", "loss")
_OUT_TYPES = ("assigned", "assign_correction", "returned", "released")


class StockError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def ensure_stock_schema(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS resource_stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_code TEXT NOT NULL,
            variant TEXT NOT NULL DEFAULT '',
            quantity INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            form_id TEXT,
            holder_label TEXT,
            occurred_at TEXT NOT NULL,
            notes TEXT,
            actor TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            dedupe_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_stock_resource ON resource_stock_movements (resource_code, variant);
        CREATE INDEX IF NOT EXISTS idx_stock_form ON resource_stock_movements (form_id);
        CREATE TABLE IF NOT EXISTS resource_stock_thresholds (
            resource_code TEXT PRIMARY KEY,
            threshold INTEGER NOT NULL
        );
        """
    )


def _pick_key(schema, flag, names):
    for field in schema:
        if isinstance(field, dict) and field.get(flag) and field.get("key"):
            return field["key"]
    for field in schema:
        if isinstance(field, dict) and field.get("key") in names:
            return field["key"]
    return None


def stock_resource_config(connection):
    """{code: {"label", "quantity": cle du champ quantite ou None, "variant": cle du champ variante ou None, "fields"}}
    pour les ressources dont le mode de suivi est « quantity »."""
    config = {}
    for row in connection.execute("SELECT code, label, category, tracking_mode, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        if effective_tracking_mode(row["tracking_mode"], row["category"], schema) != "quantity":
            continue
        config[row["code"]] = {
            "label": row["label"],
            "quantity": _pick_key(schema, "quantity", QUANTITY_KEYS),
            "variant": _pick_key(schema, "variant", VARIANT_KEYS),
            "fields": {f["key"] for f in schema if isinstance(f, dict) and f.get("key")},
        }
    return config


def _as_quantity(value):
    """Quantite d'une ligne de dossier : entier >= 1 (defaut 1 si vide ou illisible)."""
    try:
        number = int(float(str(value).replace(",", ".").strip()))
    except (TypeError, ValueError):
        return 1
    return number if number >= 1 else 1


def _move(connection, code, variant, quantity, movement_type, occurred_at, dedupe_key, form_id=None,
          holder_label=None, notes=None, actor=None, source="dossier"):
    cursor = connection.execute(
        "INSERT OR IGNORE INTO resource_stock_movements (resource_code, variant, quantity, movement_type, form_id, holder_label,"
        " occurred_at, notes, actor, source, dedupe_key, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, variant, int(quantity), movement_type, form_id, holder_label, occurred_at, notes, actor, source, dedupe_key, utc_now()),
    )
    return cursor.rowcount


def sync_stock_for_form(connection, form_id, config=None):
    """Met le stock a jour d'apres l'etat courant d'un dossier. Idempotent ; ne modifie jamais le dossier.
    Les brouillons ne creent rien : le stock ne bouge qu'a la signature."""
    form = connection.execute(
        "SELECT id, status, nom, prenom, service, assigned_at, returned_at, updated_at FROM dotation_forms WHERE id = ?", (form_id,)
    ).fetchone()
    if not form or form["status"] not in EFFECTIVE_ASSIGNMENT_STATUSES:
        return 0
    config = config if config is not None else stock_resource_config(connection)
    if not config:
        return 0
    label = _holder_label(form)
    added = 0
    items = connection.execute(
        "SELECT item_key, returned_at, return_condition, details_json FROM dotation_items WHERE form_id = ? AND assigned = 1", (form_id,)
    ).fetchall()
    for item in items:
        resource = config.get(item["item_key"])
        if not resource:
            continue
        code = item["item_key"]
        try:
            details = json.loads(item["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        fields = align_fields(_fields_of(details), resource["fields"])
        quantity = _as_quantity(fields.get(resource["quantity"])) if resource["quantity"] else 1
        variant = str(fields.get(resource["variant"]) or "").strip() if resource["variant"] else ""
        when = _when(form["assigned_at"] or form["updated_at"])

        existing = connection.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS net, MIN(variant) AS variant, COUNT(*) AS n FROM resource_stock_movements"
            " WHERE form_id = ? AND resource_code = ? AND movement_type IN ('assigned', 'assign_correction')", (form_id, code)
        ).fetchone()
        if not existing["n"]:
            added += _move(connection, code, variant, -quantity, "assigned", when, f"assign:{form_id}:{code}", form_id, label)
        elif existing["net"] != -quantity:
            added += _move(connection, code, existing["variant"], -quantity - existing["net"], "assign_correction", when,
                           f"assign_fix:{form_id}:{code}:{quantity}", form_id, label, notes="Quantité modifiée après la signature")

        condition = item["return_condition"] or "pending"
        returned_when = _when(item["returned_at"] or form["returned_at"] or form["updated_at"])
        if returned_when < when:
            returned_when = when
        if condition in READY_CONDITIONS:
            added += _move(connection, code, variant, quantity, "returned", returned_when, f"returned:{form_id}:{code}", form_id, label)
        elif condition in DEGRADED_CONDITIONS:
            added += _move(connection, code, variant, 0, "returned_degraded", returned_when, f"returned_degraded:{form_id}:{code}",
                           form_id, label, notes=f"{quantity} retourné(s) dégradé(s) : non remis en stock")
        elif condition == "non_restitue":
            added += _move(connection, code, variant, 0, "lost_by_holder", returned_when, f"lost_by_holder:{form_id}:{code}",
                           form_id, label, notes=f"{quantity} non restitué(s)")
    return added


def release_stock_for_form(connection, form_id):
    """Dossier supprime : la remise n'a jamais eu lieu, le stock revient (mouvement de compensation, l'historique reste)."""
    added = 0
    rows = connection.execute(
        "SELECT resource_code, variant, SUM(quantity) AS net FROM resource_stock_movements WHERE form_id = ?"
        " GROUP BY resource_code, variant HAVING SUM(quantity) != 0", (form_id,)
    ).fetchall()
    for row in rows:
        added += _move(connection, row["resource_code"], row["variant"], -row["net"], "released", utc_now(),
                       f"release:{form_id}:{row['resource_code']}:{row['variant']}:{row['net']}", form_id,
                       notes="Dossier supprimé : remise annulée")
    return added


def reserved_by_variant(connection, config, now=None):
    """Quantites RESERVEES par des dossiers non signes (brouillon, attribution partielle, en attente de signature),
    {(code, variante): quantite}. Calcule a la volee, sans mouvement : le stock reel ne bouge qu'a la signature.
    Un dossier sans activite depuis RESERVATION_DAYS jours ne reserve plus (meme regle que les objets du parc)."""
    from datetime import datetime, timedelta, timezone
    from models.units import RESERVATION_DAYS
    limit = ((now or datetime.now(timezone.utc)) - timedelta(days=RESERVATION_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    reserved = {}
    if not config:
        return reserved
    rows = connection.execute(
        "SELECT i.item_key, i.details_json FROM dotation_items i JOIN dotation_forms f ON f.id = i.form_id"
        " WHERE i.assigned = 1 AND f.status NOT IN ('active', 'partial_return', 'returned', 'cancelled')"
        " AND COALESCE(f.updated_at, '') >= ?", (limit,)
    ).fetchall()
    for row in rows:
        resource = config.get(row["item_key"])
        if not resource:
            continue
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        fields = align_fields(_fields_of(details), resource["fields"])
        quantity = _as_quantity(fields.get(resource["quantity"])) if resource["quantity"] else 1
        variant = str(fields.get(resource["variant"]) or "").strip() if resource["variant"] else ""
        reserved[(row["item_key"], variant)] = reserved.get((row["item_key"], variant), 0) + quantity
    return reserved


def stock_levels(connection, mask=False):
    """Niveaux de stock par ressource et variante : en stock, detenu par des agents, seuil et alerte."""
    config = stock_resource_config(connection)
    thresholds = {r["resource_code"]: r["threshold"] for r in connection.execute("SELECT * FROM resource_stock_thresholds").fetchall()}
    placeholders = ",".join("?" * len(_OUT_TYPES))
    rows = connection.execute(
        "SELECT resource_code, variant, SUM(quantity) AS on_hand,"
        f" -SUM(CASE WHEN movement_type IN ({placeholders}) THEN quantity ELSE 0 END) AS held,"
        " MAX(occurred_at) AS last_movement FROM resource_stock_movements GROUP BY resource_code, variant",
        _OUT_TYPES,
    ).fetchall()
    by_code = {}
    for row in rows:
        if row["resource_code"] in config:
            by_code.setdefault(row["resource_code"], []).append(row)
    reserved = reserved_by_variant(connection, config)
    levels = []
    for code, resource in sorted(config.items(), key=lambda kv: kv[1]["label"] or kv[0]):
        threshold = thresholds.get(code)
        variants = [{"variant": r["variant"], "on_hand": r["on_hand"], "held": r["held"], "last_movement": r["last_movement"]}
                    for r in sorted(by_code.get(code, []), key=lambda r: r["variant"])]
        known = {v["variant"] for v in variants}
        # une taille reservee par un brouillon mais encore jamais mouvementee apparait quand meme (stock 0)
        variants += [{"variant": v, "on_hand": 0, "held": 0, "last_movement": ""} for (c, v) in sorted(reserved) if c == code and v not in known]
        for v in variants:
            v["reserved"] = reserved.get((code, v["variant"]), 0)
            v["available"] = v["on_hand"] - v["reserved"]
        total = sum(v["on_hand"] for v in variants)
        total_available = sum(v["available"] for v in variants)
        levels.append({
            "resource_code": code, "label": resource["label"], "has_variant": bool(resource["variant"]),
            "has_quantity_field": bool(resource["quantity"]), "threshold": threshold, "on_hand": total,
            "held": sum(v["held"] for v in variants), "variants": variants,
            "reserved": sum(v["reserved"] for v in variants), "available": total_available,
            "low": threshold is not None and total_available <= threshold, "inconsistent": any(v["on_hand"] < 0 for v in variants),
        })
    return levels


def list_movements(connection, resource_code, variant=None, limit=200, mask=False):
    query = "SELECT * FROM resource_stock_movements WHERE resource_code = ?"
    params = [resource_code]
    if variant is not None:
        query += " AND variant = ?"
        params.append(variant)
    query += " ORDER BY occurred_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit or 200), 1000)))
    result = []
    for row in connection.execute(query, params).fetchall():
        item = dict(row)
        item.pop("dedupe_key", None)
        if mask and item.get("holder_label"):
            item["holder_label"] = " ".join(mask_text(part) for part in str(item["holder_label"]).split(" "))
        result.append(item)
    return result


def add_manual_movement(connection, resource_code, kind, quantity, variant="", notes="", actor=None):
    """Reception, ajustement d'inventaire ou perte en stock. Reserve aux ressources suivies par quantite."""
    if resource_code not in stock_resource_config(connection):
        raise StockError("not_quantity_resource", "Cette ressource n'est pas suivie par quantité.")
    if kind not in MANUAL_KINDS:
        raise StockError("invalid_kind", "Type de mouvement inconnu.")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise StockError("invalid_quantity", "Quantité invalide.") from None
    if quantity == 0 or (kind != "adjustment" and quantity < 0):
        raise StockError("invalid_quantity", "La quantité doit être un entier positif (négatif accepté pour un ajustement).")
    if kind == "adjustment" and not str(notes or "").strip():
        raise StockError("note_required", "Un ajustement d'inventaire doit être justifié par une note.")
    signed = -quantity if kind == "loss" else quantity
    _move(connection, resource_code, str(variant or "").strip(), signed, kind, utc_now(), f"manual:{uuid.uuid4().hex}",
          notes=str(notes or "").strip() or None, actor=actor, source="manual")
    return signed


def set_threshold(connection, resource_code, threshold):
    if resource_code not in stock_resource_config(connection):
        raise StockError("not_quantity_resource", "Cette ressource n'est pas suivie par quantité.")
    if threshold in (None, ""):
        connection.execute("DELETE FROM resource_stock_thresholds WHERE resource_code = ?", (resource_code,))
        return None
    try:
        value = int(threshold)
    except (TypeError, ValueError):
        raise StockError("invalid_threshold", "Seuil invalide.") from None
    if value < 0:
        raise StockError("invalid_threshold", "Le seuil ne peut pas être négatif.")
    connection.execute(
        "INSERT INTO resource_stock_thresholds (resource_code, threshold) VALUES (?, ?)"
        " ON CONFLICT(resource_code) DO UPDATE SET threshold = excluded.threshold", (resource_code, value))
    return value


MAX_IMPORT_ROWS = 2000


def _plain(value):
    text = unicodedata.normalize("NFD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def _current_on_hand(connection, code, variant):
    return connection.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM resource_stock_movements WHERE resource_code = ? AND variant = ?", (code, variant)
    ).fetchone()[0]


def import_stock(connection, text, actor=None, dry_run=True):
    """Importe un INVENTAIRE depuis un CSV : la quantite du fichier est le stock CONSTATE pour la ressource et la taille.
    Colonnes : ressource, taille (ou variante, facultatif), quantite, note (facultatif). Un mouvement d'ajustement
    d'ecart est enregistre ; importer deux fois le meme fichier ne change plus rien (ecart nul, ligne ignoree).
    dry_run : verifie et compte sans rien ecrire. Retourne {rows, created, skipped, errors, dry_run}."""
    config = stock_resource_config(connection)
    by_label = {_plain(cfg["label"]): code for code, cfg in config.items()}
    by_code = {_plain(code): code for code in config}
    text = text.lstrip("﻿")
    sample = text[:2000]
    delimiter = max(";,	", key=sample.count) if sample else ";"
    rows = [{_plain(k): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)]
    report = {"rows": len(rows), "created": 0, "skipped": 0, "errors": [], "dry_run": dry_run}
    if len(rows) > MAX_IMPORT_ROWS:
        report["errors"].append({"line": 0, "message": f"Trop de lignes (maximum {MAX_IMPORT_ROWS})."})
        return report
    seen = set()
    for index, row in enumerate(rows, start=2):  # ligne 1 = en-tete
        token = _plain(row.get("ressource") or row.get("resource"))
        code = by_code.get(token) or by_label.get(token)
        if not code:
            report["errors"].append({"line": index, "message": f"Ressource inconnue ou non suivie par quantité : « {row.get('ressource') or row.get('resource') or ''} »."})
            continue
        variant = (row.get("taille") or row.get("variante") or row.get("variant") or "").strip()
        raw_quantity = row.get("quantite") or row.get("quantity") or row.get("stock") or ""
        try:
            quantity = int(float(raw_quantity.replace(",", ".")))
            if quantity < 0 or str(quantity) != str(int(float(raw_quantity.replace(",", ".")))):
                raise ValueError
        except (TypeError, ValueError):
            report["errors"].append({"line": index, "message": f"Quantité invalide : « {raw_quantity} » (entier positif ou nul attendu)."})
            continue
        key = (code, variant.lower())
        if key in seen:
            report["errors"].append({"line": index, "message": f"Doublon dans le fichier : {code} / {variant or 'sans taille'}."})
            continue
        seen.add(key)
        delta = quantity - _current_on_hand(connection, code, variant)
        if delta == 0:
            report["skipped"] += 1
            continue
        if not dry_run:
            note = (row.get("note") or "").strip() or f"Import d'inventaire : stock constaté {quantity}"
            _move(connection, code, variant, delta, "adjustment", utc_now(), f"import:{uuid.uuid4().hex}",
                  notes=note, actor=actor, source="import")
        report["created"] += 1
    return report
