"""Base « squelette » : reconstruit, depuis un paquet de diagnostic, une base SYNTHÉTIQUE au même schéma, avec les mêmes ressources
(codes, champs, types, drapeaux), des volumes comparables et les mêmes anomalies (payloads illisibles, format ancien), remplie de
données fictives. Permet de reproduire chez soi un problème observé chez un client, sans jamais avoir ses données.

    python tools/build_skeleton.py aquai_diagnostic.json dossier_de_sortie [--max-forms 500]

Limites : les bugs qui dépendent d'une valeur précise, de corrélations entre champs, de la concurrence ou des plans de requête
ne sont pas reproduits fidèlement (le paquet ne contient volontairement aucune valeur)."""
import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FICTIVE = {"text": "Valeur-{n}", "textarea": "Texte fictif {n}", "number": "{n}", "date": "2026-01-{d:02d}", "checkbox": "true", "list": "Element {n}",
           "email_with_domain": "personne{n}@exemple.invalid", "select": None}


def load_pack(path):
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read("diagnostic.json").decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def fictive_value(field, n):
    kind = field.get("type") or "text"
    if kind == "select":
        return "Option A"
    template = FICTIVE.get(kind, "Valeur-{n}")
    return template.format(n=n, d=(n % 27) + 1)


def build(pack, out_dir, max_forms=500):
    os.makedirs(out_dir, exist_ok=True)
    os.environ["APP_DATA_DIR"] = str(out_dir)
    os.environ.setdefault("APP_UPDATE_CHECK", "0")
    os.environ.setdefault("APP_HEALTH_INTERVAL_HOURS", "0")
    sys.path.insert(0, str(ROOT / "backend"))
    import app as app_module  # noqa: F401 - initialise la base vierge (schema + migrations) dans out_dir
    from database import get_db
    from models.catalog import normalize_resource_catalog_payload
    from models.forms import persist_form
    from utils import bool_to_int, generate_id, utc_now

    resources = pack.get("resources") or []
    with get_db() as connection:
        existing = {r["code"] for r in connection.execute("SELECT code FROM resource_catalog").fetchall()}
        now = utc_now()
        for resource in resources:
            if resource["code"] in existing or resource["code"] == "(masqué)":
                continue
            data = normalize_resource_catalog_payload({
                "code": resource["code"], "label": resource["code"], "category": resource.get("category") or "materiel", "tracking_mode": resource.get("trackingMode") or "",
                "requires_return": resource.get("requiresReturn", True), "is_active": resource.get("active", True), "display_order": 900,
                "field_schema": [{"id": f.get("id"), "key": f["key"], "label": f["key"], "type": f.get("type") or "text", "required": f.get("required", False),
                                  "identifier": f.get("identifier", False), "hidden": f.get("hidden", False), "suggest": f.get("suggest", False),
                                  "options": ["Option A", "Option B"] if f.get("type") == "select" else []} for f in resource.get("fields", []) if f.get("key") != "(masqué)"]})
            connection.execute(
                """INSERT INTO resource_catalog (id, code, label, description, category, issuer_service, requires_return, has_assignment_date, has_assignment_condition,
                   has_assignment_notes, display_order, trigger_key, field_schema_json, is_active, tracking_mode, is_builtin, created_at, updated_at)
                   VALUES (?, ?, ?, '', ?, '', ?, 1, 0, 0, ?, '', ?, ?, ?, 0, ?, ?)""",
                (generate_id("resource"), data["code"], data["label"], data["category"], bool_to_int(data["requires_return"]), data["display_order"],
                 json.dumps(data["field_schema"], ensure_ascii=False), bool_to_int(data["is_active"]), data["tracking_mode"], now, now))
        catalog = {r["code"]: r for r in (dict(x) for x in connection.execute("SELECT id, code, label, category, field_schema_json FROM resource_catalog").fetchall())}

    usage = pack.get("usage") or {}
    statuses = []
    for status, count in (usage.get("formsByStatus") or {"draft": 5}).items():
        statuses += [status or "draft"] * int(count)
    statuses = statuses[:max_forms] or ["draft"]
    per_resource = usage.get("formsPerResource") or {}
    created = 0
    request_context = app_module.app.test_request_context()  # persist_form lit la session : un contexte de requete factice suffit
    request_context.push()
    for n, status in enumerate(statuses, 1):
        additional = []
        for code in per_resource:
            row = catalog.get(code)
            if not row or n % max(1, len(statuses) // max(1, min(per_resource[code], len(statuses)))) != 0:
                continue
            schema = json.loads(row["field_schema_json"] or "[]")
            additional.append({"id": row["id"], "code": code, "label": row["label"], "category": row["category"], "requiresReturn": True, "selected": True,
                               "fieldSchema": schema, "fields": {f["key"]: fictive_value(f, n) for f in schema}, "details": ""})
        try:
            persist_form({"dossier": {"type": "arrivee"}, "beneficiaire": {"nom": f"PERSONNE-{n:04d}", "prenom": "Fictif", "qualite": "agent", "service": "Service fictif"},
                          "resources": {"additional": additional}, "workflow": {"status": status if status in ("draft", "awaiting_signature", "active") else "draft"}, "meta": {}})
            created += 1
        except Exception as error:  # noqa: BLE001 - une combinaison impossible ne doit pas arreter la reconstruction
            print(f"dossier {n} ignore : {error}")

    request_context.pop()
    # anomalies observees chez le client : payloads illisibles, format ancien
    with get_db() as connection:
        for i in range(int(usage.get("unreadablePayloads") or 0)):
            connection.execute("INSERT INTO dotation_forms (id, title, status, nom, prenom, payload_json, created_at, updated_at) VALUES (?, 'ILLISIBLE', 'draft', 'X', 'X', '{illisible', ?, ?)",
                               (f"illisible-{i}", utc_now(), utc_now()))
    return {"resources": len(resources), "forms": created, "unreadable": int(usage.get("unreadablePayloads") or 0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pack", help="aquai_diagnostic.json ou aquai_diagnostic.zip")
    parser.add_argument("out_dir", help="dossier de données de la base squelette (créé)")
    parser.add_argument("--max-forms", type=int, default=500)
    args = parser.parse_args()
    print(build(load_pack(args.pack), args.out_dir, args.max_forms))


if __name__ == "__main__":
    main()
