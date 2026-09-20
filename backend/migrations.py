"""Migrations numerotees de la base principale.

Chaque migration est appliquee UNE fois, dans l'ordre, et enregistree dans `schema_migrations` (et `PRAGMA user_version`).
Avant d'appliquer des migrations en attente sur une base qui contient deja des dossiers, une copie de securite coherente
(API de sauvegarde SQLite, fiable en mode WAL) est faite dans <DATA_DIR>/db_backups. Les migrations sont idempotentes.
Les anciennes migrations « migrate_* » d'app.py restent en place (elles sont deja idempotentes) ; les nouvelles evolutions
de schema passent ici."""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from config import DATA_DIR, DB_PATH


def field_id_for(resource_code, key):
    """Identifiant deterministe d'un champ existant (le meme partout, meme apres restauration d'une sauvegarde)."""
    return "fld_" + hashlib.sha1(f"{resource_code}:{key}".encode("utf-8")).hexdigest()[:12]


def _m_baseline(connection):
    """Etat de depart : rien a faire, pose le point de reference du numero de version."""


def _m_field_ids(connection):
    """Chaque champ de chaque ressource recoit un identifiant interne immuable (`id`), independant de sa cle et de son libelle."""
    for row in connection.execute("SELECT id, code, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(schema, list):
            continue
        changed = False
        for field in schema:
            if isinstance(field, dict) and field.get("key") and not field.get("id"):
                field["id"] = field_id_for(row["code"], field["key"])
                changed = True
        if changed:
            connection.execute("UPDATE resource_catalog SET field_schema_json = ? WHERE id = ?", (json.dumps(schema, ensure_ascii=False), row["id"]))


def _m_field_roles(connection):
    """Pose explicitement le role (identifiant / quantite / variante) que le code deduisait jusqu'ici des NOMS de cle : le comportement
    existant est ffige, puis ne depend plus des noms (renommer un champ ne change plus le calcul des stocks)."""
    from models.inventory import resolve_identifier_key
    from models.resource_rules import effective_tracking_mode
    from models.stock import QUANTITY_KEYS, VARIANT_KEYS
    columns = {r[1] for r in connection.execute("PRAGMA table_info(resource_catalog)").fetchall()}
    if not {"category", "tracking_mode", "field_schema_json"} <= columns:
        return  # base tres ancienne / incomplete : rien a figer
    for row in connection.execute("SELECT id, category, tracking_mode, field_schema_json FROM resource_catalog").fetchall():
        try:
            schema = json.loads(row["field_schema_json"] or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(schema, list):
            continue
        mode = effective_tracking_mode(row["tracking_mode"], row["category"], schema)
        changed = False

        def assign(key, role):
            nonlocal changed
            if not key or any(isinstance(f, dict) and f.get("role") == role for f in schema):
                return
            for field in schema:
                if isinstance(field, dict) and field.get("key") == key and not field.get("role"):
                    field["role"] = role
                    field[role] = True
                    changed = True

        if mode == "unit":
            assign(resolve_identifier_key(schema), "identifier")
        elif mode == "quantity":
            keys = [f.get("key") for f in schema if isinstance(f, dict)]
            assign(next((k for k in keys if k in QUANTITY_KEYS), None), "quantity")
            assign(next((k for k in keys if k in VARIANT_KEYS), None), "variant")
        if changed:
            connection.execute("UPDATE resource_catalog SET field_schema_json = ? WHERE id = ?", (json.dumps(schema, ensure_ascii=False), row["id"]))


MIGRATIONS = [
    (1, "baseline", _m_baseline),
    (2, "identifiants_de_champs", _m_field_ids),
    (3, "roles_de_champs", _m_field_roles),
]


def _has_data(connection):
    try:
        return connection.execute("SELECT COUNT(*) FROM dotation_forms").fetchone()[0] > 0
    except sqlite3.Error:
        return False


class DatabaseTooNewError(RuntimeError):
    """La base a ete migree par une version PLUS RECENTE de l'application : demarrer risquerait de l'abimer."""


def purge_old_safety_copies(directory, keep=5):
    """Ne garde que les `keep` copies de securite les plus recentes de chaque famille (evite le disque plein a terme)."""
    import glob
    for pattern in ("dotation_avant_migration_*.db", "dotation_avant_reparation_champs_*.db"):
        files = sorted(glob.glob(os.path.join(directory, pattern)), key=os.path.getmtime, reverse=True)
        for old in files[keep:]:
            try:
                os.unlink(old)
            except OSError:
                pass


def _safety_copy(connection, version):
    try:
        return _safety_copy_unchecked(connection, version)
    except (OSError, sqlite3.Error) as error:
        # Pas de copie possible (droits, disque plein) : on le dit tres clairement, mais la migration, additive et idempotente, continue.
        import logging
        logging.getLogger(__name__).error("Copie de securite avant migration IMPOSSIBLE (%s) : migration poursuivie sans copie", error)
        return None


def _safety_copy_unchecked(connection, version):
    file_path = next((row[2] for row in connection.execute("PRAGMA database_list").fetchall() if row[1] == "main"), "") or DB_PATH
    if not file_path or not os.path.exists(file_path):
        return None
    directory = os.path.join(os.path.dirname(file_path) or DATA_DIR, "db_backups")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"dotation_avant_migration_{version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db")
    import shutil
    free = shutil.disk_usage(directory).free
    if free < 2 * os.path.getsize(file_path):
        raise OSError(f"espace disque insuffisant ({free // (1024 * 1024)} Mo libres)")
    source = sqlite3.connect(file_path)
    target = sqlite3.connect(path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    purge_old_safety_copies(directory)
    return path


def run_pending_migrations(connection):
    """Applique les migrations en attente. Renvoie la liste des numeros appliques."""
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    done = {row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}
    newest_known = max(m[0] for m in MIGRATIONS)
    if done and max(done) > newest_known:
        raise DatabaseTooNewError(
            f"Cette base a ete migree par une version plus recente de l'application (schema {max(done)}, cette version connait {newest_known}). "
            "Mettez l'application a jour, ou restaurez une sauvegarde compatible : demarrer avec cette version risquerait d'abimer les donnees.")
    pending = [m for m in MIGRATIONS if m[0] not in done]
    if not pending:
        return []
    if _has_data(connection):
        connection.commit()
        _safety_copy(connection, pending[0][0])
    applied = []
    for version, name, function in pending:
        function(connection)
        connection.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)", (version, name, datetime.now(timezone.utc).isoformat()))
        applied.append(version)
    connection.execute(f"PRAGMA user_version = {max(m[0] for m in MIGRATIONS)}")
    return applied


def upgrade_after_restore():
    """Apres une restauration ou un import de base (souvent plus ancienne) : remet le schema a niveau (tables, colonnes,
    migrations numerotees) en rejouant l'initialisation idempotente de l'application. Sans cela, une base d'une version
    anterieure resterait en l'etat jusqu'au prochain redemarrage."""
    import sys
    for name in ("app", "__main__"):
        init = getattr(sys.modules.get(name), "init_db", None)
        if callable(init):
            init()
            return True
    return False
