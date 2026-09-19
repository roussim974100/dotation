"""Destinations de sauvegarde (dossiers locaux, partages SMB/NFS montes), envoi, historique.

Un partage reseau est atteint comme un dossier : montage du systeme (point de montage cifs/NFS sous
Linux, chemin UNC ou lecteur reseau sous Windows). L'application ne stocke JAMAIS d'identifiants de
partage : ils restent dans la configuration du systeme. Aucune dependance Flask (utilise aussi par
backup_cli.py).
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime, timezone

import backup
from config import BASE_DIR, FRONTEND_DIR

CONFIG_PATH = os.path.join(BASE_DIR, "backup_config.json")
HISTORY_PATH = os.path.join(backup.BACKUP_DIR, "history.jsonl")
PROTOCOLS = {"smb": "Partage SMB / CIFS", "nfs": "Partage NFS", "local": "Dossier local"}
ARCHIVE_NAME_RE = re.compile(r"^aquai_sauvegarde_\d{8}_\d{6}\.(aqbak|zip)$")

DEFAULT_CONFIG = {
    "destinations": [],
    "schedule": {"enabled": False, "frequency": "daily", "time": "02:00", "weekday": 1},
    "retention": {"keep_days": 30, "keep_min": 5},
    "password_source": {"env_var": "AQUAI_BACKUP_PASSWORD", "file": ""},
}


class TargetError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return config
    for key in DEFAULT_CONFIG:
        if key in stored:
            if isinstance(DEFAULT_CONFIG[key], dict):
                config[key].update(stored[key] or {})
            else:
                config[key] = stored[key]
    return config


def save_config(config):
    staging = CONFIG_PATH + ".tmp"
    with open(staging, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
    os.replace(staging, CONFIG_PATH)


def _is_inside(path, parent):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(parent)]) == os.path.abspath(parent)
    except ValueError:  # lecteurs differents sous Windows
        return False


def validate_destination(raw, existing_ids=()):
    """Nettoie et valide une destination saisie ; retourne un dict propre ou leve TargetError."""
    label = str(raw.get("label") or "").strip()
    path = str(raw.get("path") or "").strip()
    protocol = raw.get("protocol") if raw.get("protocol") in PROTOCOLS else "local"
    if not label:
        raise TargetError("label_required", "Le nom de la destination est obligatoire.")
    if not path:
        raise TargetError("path_required", "Le chemin de destination est obligatoire.")
    if not os.path.isabs(path) and not path.startswith("\\\\"):
        raise TargetError("path_not_absolute", "Le chemin doit être absolu (ex. /mnt/sauvegardes ou \\\\serveur\\partage\\aquai).")
    # Ne jamais ecrire les sauvegardes dans le code de l'application ni dans le dossier servi au navigateur.
    if _is_inside(path, FRONTEND_DIR) or _is_inside(path, BASE_DIR):
        raise TargetError("path_forbidden", "Ce dossier est réservé à l'application : choisissez un dossier extérieur.")
    dest_id = str(raw.get("id") or "").strip()
    if not re.fullmatch(r"[a-z0-9_-]{4,40}", dest_id or ""):
        dest_id = "dest_" + secrets.token_hex(4)
    if dest_id in existing_ids:
        dest_id = "dest_" + secrets.token_hex(4)
    return {"id": dest_id, "label": label[:80], "protocol": protocol, "path": path, "enabled": bool(raw.get("enabled", True))}


def get_destination(dest_id):
    for destination in load_config()["destinations"]:
        if destination["id"] == dest_id:
            return destination
    raise TargetError("destination_not_found", "Destination introuvable.")


def save_destinations(raw_list):
    cleaned, seen = [], set()
    for raw in raw_list or []:
        destination = validate_destination(raw, seen)
        seen.add(destination["id"])
        cleaned.append(destination)
    config = load_config()
    config["destinations"] = cleaned
    save_config(config)
    return cleaned


# ---------------------------------------------------------------------------
# Test et envoi
# ---------------------------------------------------------------------------

def test_destination(destination):
    """Verifie que le dossier existe, est inscriptible et donne l'espace libre."""
    path = destination["path"]
    started = time.monotonic()
    if not os.path.isdir(path):
        raise TargetError("path_unreachable", "Dossier introuvable ou partage non monté.")
    probe = os.path.join(path, f".aquai_test_{secrets.token_hex(4)}")
    try:
        with open(probe, "wb") as handle:
            handle.write(b"ok")
        os.unlink(probe)
    except OSError as exc:
        raise TargetError("path_not_writable", f"Écriture impossible dans ce dossier : {exc}")
    try:
        free = shutil.disk_usage(path).free
    except OSError:
        free = None
    return {"ok": True, "free_bytes": free, "latency_ms": round((time.monotonic() - started) * 1000)}


def send_archive(destination, blob, filename):
    """Ecrit l'archive dans la destination (fichier temporaire puis renommage) et verifie l'ecriture."""
    if not ARCHIVE_NAME_RE.match(filename):
        raise TargetError("bad_filename", "Nom de fichier invalide.")
    test_destination(destination)
    final_path = os.path.join(destination["path"], filename)
    if os.path.exists(final_path):
        raise TargetError("already_exists", "Un fichier de même nom existe déjà : aucun écrasement.")
    partial = final_path + ".part"
    try:
        with open(partial, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        with open(partial, "rb") as check:
            if hashlib.sha256(check.read()).hexdigest() != hashlib.sha256(blob).hexdigest():
                raise TargetError("verify_failed", "Vérification de l'écriture échouée : copie corrompue.")
        os.replace(partial, final_path)
    except OSError as exc:
        raise TargetError("write_failed", f"Envoi impossible : {exc}")
    finally:
        if os.path.exists(partial):
            try:
                os.unlink(partial)
            except OSError:
                pass
    return final_path


def list_remote_archives(destination):
    try:
        names = [n for n in os.listdir(destination["path"]) if ARCHIVE_NAME_RE.match(n)]
    except OSError:
        return []
    items = []
    for name in names:
        full = os.path.join(destination["path"], name)
        try:
            items.append({"name": name, "size": os.path.getsize(full), "mtime": os.path.getmtime(full)})
        except OSError:
            continue
    return sorted(items, key=lambda item: item["mtime"], reverse=True)


# ---------------------------------------------------------------------------
# Historique
# ---------------------------------------------------------------------------

def append_history(entry):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    with open(HISTORY_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_history(limit=30):
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    entries = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
        if len(entries) >= limit:
            break
    return entries


def run_send(destination, password=None, trigger="manual", app_version=""):
    """Cree une archive et l'envoie a une destination ; journalise le resultat (succes ou echec)."""
    started = time.monotonic()
    filename = None
    try:
        blob, manifest = backup.create_archive(password, app_version)
        filename = backup.archive_filename(bool(password))
        send_archive(destination, blob, filename)
        entry = {"trigger": trigger, "destination_id": destination["id"], "destination": destination["label"],
                 "filename": filename, "size": len(blob), "encrypted": bool(password), "ok": True,
                 "duration_ms": round((time.monotonic() - started) * 1000)}
        append_history(entry)
        return entry
    except (TargetError, backup.BackupError) as exc:
        entry = {"trigger": trigger, "destination_id": destination["id"], "destination": destination["label"],
                 "filename": filename, "ok": False, "error": exc.message, "code": exc.code,
                 "duration_ms": round((time.monotonic() - started) * 1000)}
        append_history(entry)
        raise
