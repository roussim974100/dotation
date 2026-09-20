"""Sauvegarde planifiee : reglages, echeance, conservation, sante, execution.

Le declenchement est assure par le planificateur du systeme (cron, timer systemd, tache Windows) qui
lance `backup_cli.py tick` regulierement ; ce module decide s'il est temps de sauvegarder d'apres les
reglages saisis dans l'interface. Sans dependance Flask.
"""
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import backup
import backup_targets as targets
from config import BASE_DIR

PASSWORD_FILE = os.path.join(BASE_DIR, ".backup_password")
LOCK_PATH = os.path.join(backup.BACKUP_DIR, ".backup.lock")
LOCK_STALE_SECONDS = 3600
RETRY_AFTER_MINUTES = 60
MAX_RETRIES_PER_SLOT = 3
FREQUENCIES = ("daily", "weekly")
ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Reglages
# ---------------------------------------------------------------------------

def validate_settings(payload, current):
    """Valide les reglages recus et retourne la configuration mise a jour (sans l'enregistrer)."""
    config = {**current}
    schedule = {**current["schedule"], **(payload.get("schedule") or {})}
    if schedule.get("frequency") not in FREQUENCIES:
        raise ScheduleError("bad_frequency", "Fréquence invalide.")
    if not TIME_RE.match(str(schedule.get("time") or "")):
        raise ScheduleError("bad_time", "Heure invalide (format HH:MM).")
    try:
        schedule["weekday"] = int(schedule.get("weekday", 1))
    except (TypeError, ValueError):
        raise ScheduleError("bad_weekday", "Jour de semaine invalide.")
    if not 1 <= schedule["weekday"] <= 7:
        raise ScheduleError("bad_weekday", "Jour de semaine invalide.")
    schedule["enabled"] = bool(schedule.get("enabled"))
    config["schedule"] = {k: schedule[k] for k in ("enabled", "frequency", "time", "weekday")}

    retention = {**current["retention"], **(payload.get("retention") or {})}
    try:
        keep_days, keep_min = int(retention["keep_days"]), int(retention["keep_min"])
    except (TypeError, ValueError):
        raise ScheduleError("bad_retention", "Durée de conservation invalide.")
    if not (1 <= keep_days <= 3650 and 1 <= keep_min <= 1000):
        raise ScheduleError("bad_retention", "Durée de conservation hors limites.")
    config["retention"] = {"keep_days": keep_days, "keep_min": keep_min}

    env_var = str((payload.get("password_source") or {}).get("env_var", current["password_source"].get("env_var", "")) or "").strip()
    if env_var and not ENV_VAR_RE.match(env_var):
        raise ScheduleError("bad_env_var", "Nom de variable d'environnement invalide (majuscules, chiffres, _).")
    config["password_source"] = {"env_var": env_var, "file": current["password_source"].get("file", "")}
    config["allow_unencrypted"] = bool(payload.get("allow_unencrypted", current.get("allow_unencrypted", False)))
    return config


def write_password_file(password):
    """Enregistre le mot de passe des sauvegardes planifiees (ecriture seule, jamais relu par l'interface)."""
    password = backup.validate_password(password)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(PASSWORD_FILE, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(password)
    try:
        os.chmod(PASSWORD_FILE, 0o600)
    except OSError:
        pass


def clear_password_file():
    try:
        os.unlink(PASSWORD_FILE)
    except OSError:
        pass


def read_password(config):
    """Retourne (mot de passe, origine) : variable d'environnement d'abord, puis fichier serveur."""
    env_var = config["password_source"].get("env_var") or ""
    if env_var and os.environ.get(env_var):
        return os.environ[env_var], "env"
    path = config["password_source"].get("file") or PASSWORD_FILE
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip("\r\n")
        if value:
            return value, "file"
    except OSError:
        pass
    return None, None


# ---------------------------------------------------------------------------
# Echeance
# ---------------------------------------------------------------------------

def latest_slot(schedule, now):
    """Dernier horaire prevu qui est deja passe (heure locale du serveur)."""
    hour, minute = (int(part) for part in schedule["time"].split(":"))
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if schedule["frequency"] == "weekly":
        slot -= timedelta(days=(now.isoweekday() - schedule["weekday"]) % 7)
        if slot > now:
            slot -= timedelta(days=7)
    elif slot > now:
        slot -= timedelta(days=1)
    return slot


def next_slot(schedule, now):
    return latest_slot(schedule, now) + timedelta(days=7 if schedule["frequency"] == "weekly" else 1)


def _local(ts):
    return datetime.fromisoformat(ts).astimezone().replace(tzinfo=None)


def read_runs(limit=50):
    return [entry for entry in targets.read_history(500, include_runs=True) if entry.get("kind") == "run"][:limit]


def is_due(config, now=None):
    schedule = config["schedule"]
    if not schedule["enabled"]:
        return False
    now = now or datetime.now()
    slot = latest_slot(schedule, now)
    scheduled_runs = [run for run in read_runs() if run.get("trigger") == "scheduled"]
    if not scheduled_runs:
        return True
    last = _local(scheduled_runs[0]["ts"])
    if last < slot:
        return True
    # Meme creneau : nouvelle tentative espacee si la derniere a echoue, dans la limite fixee.
    if not scheduled_runs[0].get("ok"):
        attempts = sum(1 for run in scheduled_runs if _local(run["ts"]) >= slot)
        return attempts < MAX_RETRIES_PER_SLOT and now - last >= timedelta(minutes=RETRY_AFTER_MINUTES)
    return False


def health(config, now=None):
    """Etat de sante de la sauvegarde automatique, pour les bandeaux d'alerte de l'interface."""
    now = now or datetime.now()
    schedule = config["schedule"]
    if not schedule["enabled"]:
        return {"level": "info", "message": "La sauvegarde automatique est désactivée."}
    if not any(d.get("enabled") for d in config["destinations"]):
        return {"level": "warning", "message": "Sauvegarde automatique activée, mais aucune destination active."}
    runs = [run for run in read_runs() if run.get("trigger") == "scheduled"]
    if not runs:
        return {"level": "warning", "message": "Sauvegarde automatique activée : aucune exécution pour l'instant (vérifiez la tâche planifiée du serveur)."}
    if not runs[0].get("ok"):
        return {"level": "error", "message": f"Dernière sauvegarde automatique en échec : {(runs[0].get('error') or 'voir l’historique').rstrip('.')}."}
    last_ok = _local(runs[0]["ts"])
    tolerance = timedelta(days=8 if schedule["frequency"] == "weekly" else 2)
    if now - last_ok > tolerance:
        return {"level": "error", "message": f"Aucune sauvegarde automatique depuis le {last_ok.strftime('%d/%m/%Y %H:%M')} : la tâche planifiée ne s'exécute plus ?"}
    return {"level": "ok", "message": f"Dernière sauvegarde automatique réussie le {last_ok.strftime('%d/%m/%Y à %H:%M')}."}


# ---------------------------------------------------------------------------
# Conservation et execution
# ---------------------------------------------------------------------------

def apply_retention(destination, retention, now=None):
    """Supprime les archives plus anciennes que keep_days, en gardant toujours les keep_min plus recentes."""
    now_ts = (now or datetime.now()).timestamp()
    archives = targets.list_remote_archives(destination)  # plus recentes d'abord
    deleted = []
    for item in archives[retention["keep_min"]:]:
        if now_ts - item["mtime"] > retention["keep_days"] * 86400:
            try:
                os.unlink(os.path.join(destination["path"], item["name"]))
                deleted.append(item["name"])
            except OSError:
                continue
    return deleted


@contextmanager
def run_lock():
    os.makedirs(backup.BACKUP_DIR, exist_ok=True)
    try:
        if os.path.exists(LOCK_PATH) and time.time() - os.path.getmtime(LOCK_PATH) > LOCK_STALE_SECONDS:
            os.unlink(LOCK_PATH)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ScheduleError("already_running", "Une sauvegarde est déjà en cours.")
    try:
        os.close(fd)
        yield
    finally:
        try:
            os.unlink(LOCK_PATH)
        except OSError:
            pass


def run_scheduled(trigger="scheduled", dest_ids=None, app_version=""):
    """Envoie une sauvegarde a toutes les destinations actives avec le mot de passe du serveur, applique la
    conservation et journalise un resume. Retourne {ok, sent, failed, errors, deleted}."""
    config = targets.load_config()
    password, _origin = read_password(config)
    summary = {"ok": False, "sent": 0, "failed": 0, "errors": [], "deleted": []}
    with run_lock():
        if not password and not config.get("allow_unencrypted"):
            summary["errors"].append("Mot de passe de chiffrement introuvable (variable d'environnement ou fichier serveur).")
        destinations = [d for d in config["destinations"] if d.get("enabled") and (not dest_ids or d["id"] in dest_ids)]
        if not destinations:
            summary["errors"].append("Aucune destination active.")
        if not summary["errors"]:
            for destination in destinations:
                try:
                    targets.run_send(destination, password, trigger=trigger, app_version=app_version)
                    summary["sent"] += 1
                    summary["deleted"] += apply_retention(destination, config["retention"])
                except (targets.TargetError, backup.BackupError) as exc:
                    summary["failed"] += 1
                    summary["errors"].append(f"{destination['label']} : {exc.message}")
        summary["ok"] = not summary["errors"] and summary["sent"] > 0
        targets.append_history({
            "kind": "run", "trigger": trigger, "ok": summary["ok"], "sent": summary["sent"], "failed": summary["failed"],
            "error": " ; ".join(summary["errors"]) if summary["errors"] else None, "deleted": len(summary["deleted"]),
        })
    return summary
