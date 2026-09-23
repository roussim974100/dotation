"""Controle de sante de la base : integrite SQLite, references cassees, version des migrations, valeurs de champs orphelines,
ecarts entre le dossier (source de verite) et sa copie a plat (dotation_items). Lecture seule."""
import json

from models.field_health import scan_orphan_fields


def drifted_form_ids(connection):
    """Dossiers dont une ressource porte des valeurs que la copie a plat (dotation_items.details_json) n'a pas."""
    drifted = []
    items = {}
    for item in connection.execute("SELECT form_id, item_key, details_json FROM dotation_items").fetchall():
        items.setdefault((item["form_id"], item["item_key"]), item["details_json"])
    for row in connection.execute("SELECT id, payload_json FROM dotation_forms").fetchall():
        try:
            additional = ((json.loads(row["payload_json"] or "{}").get("resources") or {}).get("additional")) or []
        except (TypeError, ValueError):
            continue
        for entry in additional:
            fields = entry.get("fields") if isinstance(entry, dict) else None
            if not isinstance(fields, dict) or not any(str(v or "").strip() for v in fields.values()):
                continue
            key = (row["id"], entry.get("code"))
            if key not in items:
                continue
            try:
                details = json.loads(items[key] or "{}")
                # deux formats : details["fields"] (actuel) ou champs a plat dans details (ancien)
                copied = details.get("fields") if isinstance(details.get("fields"), dict) and details.get("fields") else details
            except (TypeError, ValueError):
                copied = {}
            # une copie sans aucune valeur n'est pas comparable (certaines ressources integrees n'y portent pas leurs champs)
            if any(str(v or "").strip() for v in copied.values()) and any(str(v or "").strip() and str(copied.get(k) or "").strip() != str(v).strip() for k, v in fields.items()):
                drifted.append(row["id"])
                break
    return drifted


def _copy_drift(connection):
    return len(drifted_form_ids(connection))


def resync_flat_copies(connection):
    """Recalcule la copie a plat des dossiers en ecart (le dossier fait foi)."""
    from models.forms import resync_items_for_form
    ids = drifted_form_ids(connection)
    for form_id in ids:
        resync_items_for_form(connection, form_id)
    return len(ids)


def stock_and_unit_invariants(connection):
    """Invariants des stocks et du parc (comptages seulement) : soldes négatifs, mouvements d'une ressource inconnue, objets sans
    identifiant, ressources de stock saisies sur plusieurs lignes dans un même dossier."""
    def count(sql):
        try:
            return connection.execute(sql).fetchone()[0]
        except Exception:  # noqa: BLE001 - table absente (base ancienne) : rien a controler
            return 0
    return {
        "stockNegativeBalances": count("SELECT COUNT(*) FROM (SELECT 1 FROM resource_stock_movements GROUP BY resource_code, variant HAVING SUM(quantity) < 0)"),
        "stockMovementsUnknownResource": count("SELECT COUNT(*) FROM resource_stock_movements WHERE resource_code NOT IN (SELECT code FROM resource_catalog)"),
        "unitsWithoutIdentifier": count("SELECT COUNT(*) FROM resource_units WHERE TRIM(COALESCE(identifier, '')) = ''"),
        "unitsUnknownResource": count("SELECT COUNT(*) FROM resource_units WHERE resource_code NOT IN (SELECT code FROM resource_catalog)"),
        "duplicateItemLines": count("SELECT COUNT(*) FROM (SELECT 1 FROM dotation_items WHERE assigned = 1 GROUP BY form_id, item_key HAVING COUNT(*) > 1)"),
    }


def database_health(connection):
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    broken_refs = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    try:
        version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    except Exception:
        version = None
    orphans = scan_orphan_fields(connection)
    drift = _copy_drift(connection)
    problems = []
    if integrity != "ok":
        problems.append("Contrôle d'intégrité SQLite en échec.")
    if broken_refs:
        problems.append(f"{broken_refs} référence(s) cassée(s) entre tables.")
    if orphans["orphans"]:
        problems.append(f"{len(orphans['orphans'])} nom(s) de champ à examiner dans les dossiers ({orphans['repairable']} rattachable(s)).")
    if drift:
        problems.append(f"{drift} dossier(s) dont la copie à plat diffère du dossier.")
    invariants = stock_and_unit_invariants(connection)
    labels = {"stockNegativeBalances": "solde(s) de stock négatif(s)", "stockMovementsUnknownResource": "mouvement(s) de stock d'une ressource inconnue",
              "unitsWithoutIdentifier": "objet(s) du parc sans identifiant", "unitsUnknownResource": "objet(s) du parc d'une ressource inconnue",
              "duplicateItemLines": "ressource(s) saisie(s) sur plusieurs lignes dans un même dossier (risque de calcul de stock faussé)"}
    for key, label in labels.items():
        if invariants[key]:
            problems.append(f"{invariants[key]} {label}.")
    return {"status": "ok" if not problems else "attention", "problems": problems, "integrity": integrity, "brokenReferences": broken_refs,
            "schemaVersion": version, "orphanFields": len(orphans["orphans"]), "copyDrift": drift, "invariants": invariants}


_HEALTH_LOCK = None


def run_health_check_and_log():
    """Un controle : consigne au journal (app_logs) seulement quand quelque chose est a examiner."""
    from database import get_db
    from models.audit import insert_app_log
    with get_db() as connection:
        report = database_health(connection)
        if report["status"] != "ok":
            insert_app_log(connection, "system", "database_health", "Contrôle de santé : " + " ".join(report["problems"]), details=report)
    return report


def start_daily_health_check(interval_hours=24, first_delay_seconds=600):
    """Controle de sante quotidien en arriere-plan (fil daemon, ne bloque ni le demarrage ni l'arret). Desactivable :
    APP_HEALTH_INTERVAL_HOURS=0. Un premier passage a lieu apres `first_delay_seconds`, puis toutes les `interval_hours`."""
    import logging
    import threading
    import time

    if not interval_hours or interval_hours <= 0:
        return None
    from utils import single_instance_lock
    global _HEALTH_LOCK
    _HEALTH_LOCK = single_instance_lock("health")  # un seul worker lance le controle (pas 4 fois la charge ni 4 lignes de journal)
    if _HEALTH_LOCK is None:
        return None

    def loop():
        time.sleep(first_delay_seconds)
        while True:
            try:
                run_health_check_and_log()
            except Exception:  # noqa: BLE001 - un controle ne doit jamais faire tomber l'application
                logging.getLogger(__name__).warning("Controle de sante quotidien impossible", exc_info=True)
            time.sleep(interval_hours * 3600)

    thread = threading.Thread(target=loop, name="health-check", daemon=True)
    thread.start()
    return thread
