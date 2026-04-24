import json
import sqlite3

from config import DB_PATH, DB_USERS_PATH


_KNOWN_TABLES = {
    "dotation_forms", "dotation_items", "onboarding_dossiers",
    "resource_catalog", "service_catalog", "signature_links",
    "app_settings", "app_logs", "deleted_items",
    "shared_pools", "shared_pool_members", "shared_pool_items",
    "users", "groups", "user_groups",
}


def get_db():
    # timeout=10 : attendre 10 secondes avant de lever une erreur de verrouillage
    # check_same_thread=False : permettre l'accès cross-thread (gunicorn workers)
    connection = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def get_users_db():
    # BDD séparée pour users/groupes (ignore par git)
    connection = sqlite3.connect(DB_USERS_PATH, timeout=10, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def table_columns(connection, table_name):
    if table_name not in _KNOWN_TABLES:
        raise ValueError(f"Table inconnue : {table_name!r}")
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def ensure_column(connection, table_name, column_name, column_sql):
    if table_name not in _KNOWN_TABLES:
        raise ValueError(f"Table inconnue : {table_name!r}")
    if column_name not in table_columns(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def normalize_reference_row(row):
    if not row:
        return None
    data = {key: row[key] for key in row.keys()}
    try:
        data["field_schema"] = json.loads(data.get("field_schema_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        data["field_schema"] = []
    data["requires_return"] = bool(data.get("requires_return"))
    data["has_assignment_date"] = bool(data.get("has_assignment_date", True))
    data["has_assignment_condition"] = bool(data.get("has_assignment_condition", False))
    data["has_assignment_notes"] = bool(data.get("has_assignment_notes", True))
    data["is_active"] = bool(data.get("is_active", True))
    data["is_builtin"] = bool(data.get("is_builtin", False))
    data["display_order"] = int(data.get("display_order") or 100)
    return data


def normalize_service_row(row):
    if not row:
        return None
    return {key: row[key] for key in row.keys()}
