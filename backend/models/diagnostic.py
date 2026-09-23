"""Paquet de diagnostic : de quoi comprendre un problème chez un client SANS sa base et SANS aucune donnée personnelle.

Principe : LISTE BLANCHE. Chaque collecteur ne renvoie que des agrégats (comptages, distributions, tailles), des noms techniques
(codes de ressources, clés de champs, types) et des indicateurs de santé. Aucun libellé libre, aucune valeur saisie, aucun nom, e-mail,
numéro de série, chemin réseau, jeton, ni réglage d'identité de l'organisation. `assert_safe` vérifie le résultat final : au moindre
motif suspect (e-mail, chemin UNC, adresse IP, URL), le paquet n'est PAS produit."""
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import time

import environment
from config import DATA_DIR, DB_PATH
from models.health import database_health
from utils import safe_json

FORMAT = "aquai-diagnostic"
VERSION = 1

# réglages non identifiants (jamais nom d'organisation, e-mails, support, logo, domaines)
SAFE_SETTINGS = ("org_context", "theme_id", "dark_mode_policy", "restitution_phase1_unlock_days", "timing_warning_days", "parc_retention_years")
_TECHNICAL = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

_UNSAFE_PATTERNS = {
    "e-mail": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "chemin réseau": re.compile(r"\\\\[\w.$-]+\\|//[\w.$-]+/[\w.$-]+/"),
    "adresse IP": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "URL": re.compile(r"https?://", re.I),
    "chemin de fichier": re.compile(r"(?:[A-Za-z]:\\|/home/|/root/|/var/|/etc/)[\w .\\/-]*"),
}


def _tech(value):
    """Nom technique conservé seulement s'il en a la forme (sinon masqué) : un code de ressource ou une clé de champ ne contient jamais de texte libre."""
    text = str(value or "")
    return text if _TECHNICAL.match(text) else "(masqué)"


def _distribution(connection, table, column):
    return {str(r[0] or ""): r[1] for r in connection.execute(f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}").fetchall()}  # noqa: S608 (noms internes fixes)


def _versions():
    return {"app": environment.display_version(), "environment": environment.resolve_environment(), "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version, "os": f"{platform.system()} {platform.release()}", "machine": platform.machine()}


def _schema(connection):
    tables = {}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        columns = [{"name": c[1], "type": c[2], "notnull": bool(c[3]), "pk": bool(c[5])} for c in connection.execute(f"PRAGMA table_info({name})").fetchall()]  # noqa: S608
        tables[name] = {"columns": columns, "rows": connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]}  # noqa: S608
    indexes = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    return {"tables": tables, "indexes": indexes}


def _resources(connection):
    out = []
    for row in connection.execute("SELECT code, category, tracking_mode, is_active, is_builtin, requires_return, field_schema_json FROM resource_catalog ORDER BY code").fetchall():
        schema = safe_json(row["field_schema_json"], [])
        schema = schema if isinstance(schema, list) else []
        fields = [{"id": _tech(f.get("id")), "key": _tech(f.get("key")), "type": _tech(f.get("type")), "required": bool(f.get("required")),
                   "identifier": bool(f.get("identifier")), "hidden": bool(f.get("hidden")), "suggest": bool(f.get("suggest")),
                   "aliases": len(f.get("aliases") or []), "options": len(f.get("options") or [])} for f in schema if isinstance(f, dict)]
        out.append({"code": _tech(row["code"]), "category": _tech(row["category"]), "trackingMode": _tech(row["tracking_mode"]), "active": bool(row["is_active"]),
                    "builtin": bool(row["is_builtin"]), "requiresReturn": bool(row["requires_return"]), "fieldCount": len(fields), "fields": fields})
    return out


def _usage(connection):
    sizes = [len(r[0] or "") for r in connection.execute("SELECT payload_json FROM dotation_forms").fetchall()]
    unreadable = legacy = 0
    per_resource = {}
    for (payload_json,) in connection.execute("SELECT payload_json FROM dotation_forms").fetchall():
        payload = safe_json(payload_json, None)
        if not isinstance(payload, dict):
            unreadable += 1
            continue
        if payload.get("materiel") or payload.get("immateriel"):
            legacy += 1
        for entry in ((payload.get("resources") or {}).get("additional") or []):
            if isinstance(entry, dict) and (entry.get("selected") or entry.get("fields")):
                code = _tech(entry.get("code"))
                per_resource[code] = per_resource.get(code, 0) + 1
    return {"formsByStatus": _distribution(connection, "dotation_forms", "status"), "formsByDossierType": _distribution(connection, "dotation_forms", "dossier_type"),
            "formsByBeneficiaryType": {_tech(k): v for k, v in _distribution(connection, "dotation_forms", "beneficiary_type").items()},
            "payloadBytes": {"min": min(sizes, default=0), "avg": int(sum(sizes) / len(sizes)) if sizes else 0, "max": max(sizes, default=0)},
            "unreadablePayloads": unreadable, "legacyFormatForms": legacy, "formsPerResource": per_resource}


def _system():
    def size(path):
        return os.path.getsize(path) if os.path.exists(path) else 0
    try:
        free = shutil.disk_usage(DATA_DIR).free
    except OSError:
        free = None
    backups_dir = os.path.join(DATA_DIR, "db_backups")
    return {"diskFreeMB": None if free is None else free // (1024 * 1024), "dbBytes": size(DB_PATH), "walBytes": size(DB_PATH + "-wal"),
            "dataDirWritable": os.access(DATA_DIR, os.W_OK), "safetyCopies": len(os.listdir(backups_dir)) if os.path.isdir(backups_dir) else 0,
            "timezone": list(time.tzname), "filesystemEncoding": sys.getfilesystemencoding()}


def _performance(connection):
    timings = {}
    for name, sql in (("countForms", "SELECT COUNT(*) FROM dotation_forms"), ("listForms", "SELECT id, status, updated_at FROM dotation_forms ORDER BY updated_at DESC LIMIT 200"),
                      ("countItems", "SELECT COUNT(*) FROM dotation_items")):
        started = time.perf_counter()
        connection.execute(sql).fetchall()
        timings[name + "Ms"] = round((time.perf_counter() - started) * 1000, 2)
    return timings


def _settings(connection):
    from models.settings import get_app_settings
    settings = get_app_settings(connection)
    result = {k: settings.get(k, "") for k in SAFE_SETTINGS}
    result["beneficiaryTypeValues"] = [_tech(t.split(":", 1)[0]) for t in (settings.get("beneficiary_types") or "").split(",") if t.strip()]
    return result


def collect_diagnostic(connection):
    from observability import recent_events
    migrations = [{"version": r[0], "name": _tech(r[1])} for r in connection.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()] \
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'schema_migrations'").fetchone() else []
    # événements : seuls des champs techniques sont conservés (type, code, route, statut, positions de code)
    events = [{k: e.get(k) for k in ("t", "kind", "code", "type", "method", "route", "status", "ms", "frames") if k in e} for e in recent_events(50)]
    return {"format": FORMAT, "version": VERSION, "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "versions": _versions(), "migrations": migrations,
            "pragmas": {"userVersion": connection.execute("PRAGMA user_version").fetchone()[0], "journalMode": connection.execute("PRAGMA journal_mode").fetchone()[0],
                        "pageCount": connection.execute("PRAGMA page_count").fetchone()[0], "freelistCount": connection.execute("PRAGMA freelist_count").fetchone()[0]},
            "schema": _schema(connection), "health": database_health(connection), "resources": _resources(connection), "usage": _usage(connection),
            "settings": _settings(connection), "system": _system(), "performance": _performance(connection), "recentEvents": events}


class UnsafeDiagnosticError(RuntimeError):
    pass


def assert_safe(pack):
    """Dernier verrou : refuse de produire le paquet si le contenu ressemble à une donnée personnelle."""
    text = json.dumps(pack, ensure_ascii=False)
    for label, pattern in _UNSAFE_PATTERNS.items():
        match = pattern.search(text)
        if match:
            raise UnsafeDiagnosticError(f"Le paquet contient un motif de type « {label} » : il n'est pas produit.")
    return True
