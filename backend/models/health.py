"""Controle de sante de la base : integrite SQLite, references cassees, version des migrations, valeurs de champs orphelines,
ecarts entre le dossier (source de verite) et sa copie a plat (dotation_items). Lecture seule."""
import json

from models.field_health import scan_orphan_fields


def drifted_form_ids(connection):
    """Dossiers dont une ressource porte des valeurs que la copie a plat (dotation_items.details_json) n'a pas."""
    drifted = []
    for row in connection.execute("SELECT id, payload_json FROM dotation_forms").fetchall():
        try:
            additional = ((json.loads(row["payload_json"] or "{}").get("resources") or {}).get("additional")) or []
        except (TypeError, ValueError):
            continue
        for entry in additional:
            fields = entry.get("fields") if isinstance(entry, dict) else None
            if not isinstance(fields, dict) or not any(str(v or "").strip() for v in fields.values()):
                continue
            item = connection.execute("SELECT details_json FROM dotation_items WHERE form_id = ? AND item_key = ?", (row["id"], entry.get("code"))).fetchone()
            if not item:
                continue
            try:
                details = json.loads(item["details_json"] or "{}")
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
    return {"status": "ok" if not problems else "attention", "problems": problems, "integrity": integrity, "brokenReferences": broken_refs,
            "schemaVersion": version, "orphanFields": len(orphans["orphans"]), "copyDrift": drift}


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
