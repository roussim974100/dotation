"""Materiel restitue reutilisable : quelles unites d'une ressource sont disponibles pour une nouvelle attribution.

Il n'existe pas de table d'inventaire : une « unite » est identifiee par la valeur de son champ
identifiant (numero de serie, immatriculation, numero de badge...) au sein d'une ressource. Son etat est
celui de sa DERNIERE ligne dans dotation_items (une reattribution posterieure la rend indisponible).
Fonctions pures (aucune dependance Flask), la requete SQL est isolee dans list_available_units.
"""
import json
import re
import unicodedata

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


_KEY_STOPWORDS = {"de", "du", "des", "la", "le", "les", "d", "l"}


def canonical_key(key):
    """Forme comparable d'un nom de champ, insensible a l'ecriture : « numeroSerie », « numero_de_serie » et
    « Numero de serie » donnent tous « numeroserie » ; « nomPoste » et « nom_du_poste » donnent « nomposte »."""
    text = unicodedata.normalize("NFD", str(key or "")).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", text)
    return "".join(w.lower() for w in words if w.lower() not in _KEY_STOPWORDS)


class SchemaKeys(set):
    """Cles des champs d'une ressource + anciens noms declares (alias) : {ancien nom: cle actuelle}."""
    aliases = {}


def schema_key_set(schema):
    keys = SchemaKeys(f["key"] for f in (schema or []) if isinstance(f, dict) and f.get("key"))
    keys.aliases = {canonical_key(a): f["key"] for f in (schema or []) if isinstance(f, dict) and f.get("key")
                    for a in (f.get("aliases") or []) if canonical_key(a)}
    return keys


def align_with_embedded_schema(fields, embedded_schema, current_schema):
    """Correspondance EXACTE, sans devinette : chaque dossier embarque la description des champs telle qu'elle etait
    a l'enregistrement (cle + libelle). Un champ actuel absent des valeurs est rattache a l'ancien champ de meme
    LIBELLE, dont la cle est connue avec certitude."""
    if not isinstance(fields, dict) or not isinstance(embedded_schema, list):
        return {}
    by_label = {}
    for f in embedded_schema:
        if isinstance(f, dict) and f.get("key") and f.get("label"):
            by_label.setdefault(canonical_key(f["label"]), []).append(f["key"])
    result = {}
    for f in current_schema or []:
        if not isinstance(f, dict) or not f.get("key") or f["key"] in fields:
            continue
        keys = [k for k in by_label.get(canonical_key(f.get("label")), []) if str(fields.get(k) or "").strip()]
        if len(keys) == 1:
            result[f["key"]] = fields[keys[0]]
    return result


def align_fields(fields, schema_keys, loose=False):
    """Renvoie les champs d'une ligne de dossier sous les noms du CATALOGUE actuel. Les anciens dossiers ont ete
    saisis avec d'autres noms de champs (numeroSerie) que ceux du catalogue (numero_de_serie) : sans cette
    correspondance, l'identifiant serait ignore. Un nom deja present dans le catalogue est garde tel quel."""
    alias_map = getattr(schema_keys, "aliases", None) or {}
    schema_keys = set(schema_keys)
    by_canonical = {}
    for key in schema_keys:
        by_canonical.setdefault(canonical_key(key), []).append(key)
    aligned = {}
    for key, value in (fields or {}).items():
        if key in schema_keys:
            aligned[key] = value
            continue
        candidates = by_canonical.get(canonical_key(key), [])
        if not candidates and canonical_key(key) in alias_map:
            candidates = [alias_map[canonical_key(key)]]  # ancien nom declare a la modification du catalogue : correspondance exacte
        if not candidates and loose:
            # Repli (affichage du formulaire seulement) : ancien nom plus court que le nom du catalogue (« adresse » -> « adresse_email »).
            # « numero » et « n° » sont equivalents (numeroSerie ~ n_de_serie_sn).
            own = canonical_key(key).replace("numero", "n")
            if len(own) >= 4:
                candidates = [k for c, keys in by_canonical.items() if len(c.replace("numero", "n")) >= 4
                              and (c.replace("numero", "n").startswith(own) or own.startswith(c.replace("numero", "n"))) for k in keys]
        if len(candidates) == 1 and candidates[0] not in fields:
            aligned.setdefault(candidates[0], value)
    return aligned


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


def find_current_holder(rows, identifier_key, value, exclude_form_id=None):
    """Si l'unite `value` est actuellement attribuee dans un AUTRE dossier (sa derniere ligne n'est pas
    restituee), retourne {service, since} ; sinon None. rows : lignes avec form_id, service, sort_key."""
    target = normalize_identifier(value)
    if not target:
        return None
    latest = None
    for row in rows:
        try:
            details = row["details_json"] if isinstance(row["details_json"], dict) else json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if normalize_identifier(_fields_of(details).get(identifier_key)) != target:
            continue
        order = (str(row.get("sort_key") or ""), row.get("item_id") or 0)
        if latest is None or order > latest[0]:
            latest = (order, row)
    if not latest:
        return None
    row = latest[1]
    if row.get("form_id") == exclude_form_id:
        return None  # c'est ce dossier lui-meme
    if (row.get("return_condition") or "pending") in READY_CONDITIONS | DEGRADED_CONDITIONS | {"non_restitue"}:
        return None  # restitue (ou declare perdu) : plus attribue
    return {"service": row.get("service") or "", "since": str(row.get("sort_key") or "")}


def list_holder_rows(connection, resource_code):
    return [dict(row) for row in connection.execute(
        """
        SELECT i.id AS item_id, i.form_id, i.details_json, i.return_condition, f.service AS service, f.updated_at AS sort_key
        FROM dotation_items i JOIN dotation_forms f ON f.id = i.form_id
        WHERE i.item_key = ? AND i.assigned = 1
        """,
        (resource_code,),
    ).fetchall()]


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
