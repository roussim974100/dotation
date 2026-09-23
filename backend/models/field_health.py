"""Sante des champs de ressources : valeurs de dossiers saisies sous un nom que le catalogue actuel ne connait plus.

scan_orphan_fields : lecture seule, liste les valeurs « orphelines » par ressource.
repair_orphan_fields : ajoute, sous le nom actuel du catalogue, les valeurs dont la correspondance est sans ambiguite.
Rien n'est jamais retire ni ecrase (les anciens noms restent) ; l'operation est idempotente."""
import json

from models.inventory import align_fields, align_with_embedded_schema, schema_key_set


def _schemas(connection):
    result = {}
    for row in connection.execute("SELECT code, label, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            schema = []
        keys = schema_key_set(schema)
        if keys:
            result[row["code"]] = {"label": row["label"], "keys": keys, "schema": schema}
    return result


def _walk(connection, apply_changes):
    schemas = _schemas(connection)
    found = {}  # (code, ancien nom) -> {"count", "target"}
    changed_forms = 0
    for row in connection.execute("SELECT id, payload_json FROM dotation_forms").fetchall():
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        resources = payload.get("resources")
        additional = resources.get("additional") if isinstance(resources, dict) else None
        if not isinstance(additional, list):
            continue
        modified = False
        added_by_code = {}
        for entry in additional:
            info = schemas.get(entry.get("code")) if isinstance(entry, dict) else None
            fields = entry.get("fields") if isinstance(entry, dict) else None
            if not info or not isinstance(fields, dict):
                continue
            aligned = align_fields(fields, info["keys"], loose=True)
            aligned.update(align_with_embedded_schema(fields, entry.get("fieldSchema"), info["schema"]))
            for key, value in list(fields.items()):
                if key in info["keys"] or not str(value or "").strip():
                    continue
                target = next((k for k, v in aligned.items() if v == value and k not in fields), None)
                already_there = any(str(fields.get(k) or "").strip() == str(value).strip() for k in info["keys"])
                if already_there:
                    continue  # la valeur existe deja sous un nom actuel : rien a signaler ni a reparer
                item = found.setdefault((entry["code"], key), {"count": 0, "target": target})
                item["count"] += 1
                if apply_changes and target and not str(fields.get(target) or "").strip():
                    fields[target] = value
                    added_by_code.setdefault(entry["code"], {})[target] = value
                    modified = True
        if modified:
            connection.execute("UPDATE dotation_forms SET payload_json = ? WHERE id = ?", (json.dumps(payload, ensure_ascii=False), row["id"]))
            changed_forms += 1
            # meme rattachement dans la copie a plat lue par le parc et les restitutions (ajout seulement)
            for code, added in added_by_code.items():
                for item in connection.execute("SELECT id, details_json FROM dotation_items WHERE form_id = ? AND item_key = ?", (row["id"], code)).fetchall():
                    try:
                        details = json.loads(item["details_json"] or "{}")
                    except (TypeError, ValueError):
                        continue
                    item_fields = details.get("fields")
                    if not isinstance(item_fields, dict):
                        continue
                    for key, value in added.items():
                        if not str(item_fields.get(key) or "").strip():
                            item_fields[key] = value
                    connection.execute("UPDATE dotation_items SET details_json = ? WHERE id = ?", (json.dumps(details, ensure_ascii=False), item["id"]))
    rows = [{"code": code, "resource": schemas[code]["label"], "field": key, "dossiers": v["count"], "target": v["target"]}
            for (code, key), v in sorted(found.items())]
    return rows, changed_forms


def scan_orphan_fields(connection):
    rows, _ = _walk(connection, False)
    return {"orphans": rows, "repairable": sum(1 for r in rows if r["target"]), "unmatched": sum(1 for r in rows if not r["target"])}


def repair_orphan_fields(connection):
    rows, changed = _walk(connection, True)
    return {"repairedForms": changed, "repairedFields": sum(r["dossiers"] for r in rows if r["target"]), "unmatched": sum(1 for r in rows if not r["target"])}
