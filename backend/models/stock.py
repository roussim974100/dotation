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
import json
import uuid

from models.resource_rules import effective_tracking_mode
from models.inventory import DEGRADED_CONDITIONS, READY_CONDITIONS, _fields_of
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
        fields = {k: v for k, v in _fields_of(details).items() if k in resource["fields"]}
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
    levels = []
    for code, resource in sorted(config.items(), key=lambda kv: kv[1]["label"] or kv[0]):
        threshold = thresholds.get(code)
        variants = [{"variant": r["variant"], "on_hand": r["on_hand"], "held": r["held"], "last_movement": r["last_movement"]}
                    for r in sorted(by_code.get(code, []), key=lambda r: r["variant"])]
        total = sum(v["on_hand"] for v in variants)
        levels.append({
            "resource_code": code, "label": resource["label"], "has_variant": bool(resource["variant"]),
            "has_quantity_field": bool(resource["quantity"]), "threshold": threshold, "on_hand": total,
            "held": sum(v["held"] for v in variants), "variants": variants,
            "low": threshold is not None and total <= threshold, "inconsistent": any(v["on_hand"] < 0 for v in variants),
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
