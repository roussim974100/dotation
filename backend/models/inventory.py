"""Materiel restitue reutilisable : quelles unites d'une ressource sont disponibles pour une nouvelle attribution.

Il n'existe pas de table d'inventaire : une « unite » est identifiee par la valeur de son champ
identifiant (numero de serie, immatriculation, numero de badge...) au sein d'une ressource. Son etat est
celui de sa DERNIERE ligne dans dotation_items (une reattribution posterieure la rend indisponible).
Fonctions pures (aucune dependance Flask), la requete SQL est isolee dans list_available_units.
"""
import json

PREFERRED_IDENTIFIER_KEYS = ("numeroSerie", "numeroserie", "numero_de_serie", "immatriculation", "numero", "identifiant")
READY_CONDITIONS = {"conforme", "bon", "returned"}
DEGRADED_CONDITIONS = {"degrade", "returned_damaged"}


def resolve_identifier_key(schema):
    """Champ qui identifie un objet : celui marque `identifier` dans le catalogue, sinon le premier champ de
    la liste habituelle (n° de serie, immatriculation, n°...). None si la ressource n'est pas identifiable."""
    fields = [f for f in (schema or []) if isinstance(f, dict) and f.get("key")]
    for field in fields:
        if field.get("identifier"):
            return field["key"]
    present = {f["key"] for f in fields}
    for key in PREFERRED_IDENTIFIER_KEYS:
        if key in present:
            return key
    return None


def normalize_identifier(value):
    return " ".join(str(value or "").split()).lower()


def _fields_of(details):
    # Format actuel : details["fields"] ; ancien format : champs a plat dans details.
    nested = details.get("fields")
    return nested if isinstance(nested, dict) and nested else details


def compute_available_units(rows, identifier_key, field_keys=None):
    """rows : dicts {details_json, return_condition, returned_at, sort_key, item_id}. Retourne les unites dont la
    derniere ligne est restituee (bon etat) ou restituee degradee, les plus recemment rendues d'abord."""
    latest = {}
    for row in rows:
        try:
            details = row["details_json"] if isinstance(row["details_json"], dict) else json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        fields = _fields_of(details)
        raw = fields.get(identifier_key)
        identity = normalize_identifier(raw)
        if not identity:
            continue
        order = (str(row.get("sort_key") or ""), row.get("item_id") or 0)
        if identity not in latest or order > latest[identity][0]:
            latest[identity] = (order, row, fields, raw)

    units = []
    for _order, row, fields, raw in latest.values():
        condition = row.get("return_condition") or "pending"
        if condition in READY_CONDITIONS:
            status = "ok"
        elif condition in DEGRADED_CONDITIONS:
            status = "degraded"
        else:
            continue  # en cours d'attribution, non restitue, transfere...
        units.append({
            "identifier": str(raw).strip(),
            # Seuls les champs definis par la ressource : les anciens dossiers melangent des donnees internes
            # (date d'attribution, etat a la remise...) qui n'ont pas a etre reprises.
            "fields": {k: v for k, v in fields.items()
                       if (field_keys is None or k in field_keys) and isinstance(v, (str, int, float)) and str(v).strip() != ""},
            "status": status,
            "returned_at": row.get("returned_at") or "",
        })
    units.sort(key=lambda unit: (unit["returned_at"], unit["identifier"]), reverse=True)
    return units


def list_available_units(connection, resource_code, identifier_key, field_keys=None):
    rows = connection.execute(
        """
        SELECT i.id AS item_id, i.details_json, i.return_condition, i.returned_at, f.updated_at AS sort_key
        FROM dotation_items i JOIN dotation_forms f ON f.id = i.form_id
        WHERE i.item_key = ? AND i.assigned = 1
        """,
        (resource_code,),
    ).fetchall()
    return compute_available_units([dict(row) for row in rows], identifier_key, field_keys)
