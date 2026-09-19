"""Detection d'une nouvelle version et etat de la mise a jour depuis le navigateur.

- La version installee est lue dans frontend/js/branding.js (APP_BUILD_VERSION), la meme que celle affichee a l'ecran.
- La version disponible est lue dans le meme fichier sur la branche de l'environnement de l'instance (dev, preprod ou prod : voir environment.py) de GitHub.
  Le resultat est mis en cache dans <DATA_DIR>/update/check.json (partage entre les processus gunicorn, 6 h).
- Aucun blocage : une verification automatique tourne dans un thread, un echec (reseau coupe, intranet sans sortie
  Internet) est silencieux. Desactivable : APP_UPDATE_CHECK=0. Adresse : APP_UPDATE_CHECK_URL.
- La mise a jour depuis le navigateur ne lance AUCUNE commande : l'application depose un fichier de demande que
  surveille une unite systemd (voir setup/install-web-update.sh). Desactivee par defaut : APP_ALLOW_WEB_UPDATE=1.
"""
import json
import os
import re
import threading
import time
import urllib.request

import environment
from config import DATA_DIR, FRONTEND_DIR

UPDATE_DIR = os.path.join(DATA_DIR, "update")
CHECK_FILE = os.path.join(UPDATE_DIR, "check.json")
REQUEST_FILE = os.path.join(UPDATE_DIR, "request.json")
STATUS_FILE = os.path.join(UPDATE_DIR, "status.json")
CHECK_TTL_SECONDS = 6 * 3600
FETCH_TIMEOUT_SECONDS = 5
DEFAULT_REPOSITORY = "roussim974100/dotation"
PATH_UNIT = os.environ.get("APP_UPDATE_UNIT_PATH") or "/etc/systemd/system/dotation-update.path"

_VERSION_RE = re.compile(r'APP_BUILD_VERSION\s*=\s*"([^"]+)"')
_NUMERIC_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
_refresh_lock = threading.Lock()
_refreshing = False


def current_version():
    """Version installee (APP_BUILD_VERSION de branding.js, avec ou sans suffixe), ou chaine vide si illisible."""
    return environment.raw_version()


def channel_for(version=None):
    """Canal de mise a jour = environnement de l'instance (dev, preprod ou prod) : voir environment.resolve_environment
    (fichier ecrit par le script de deploiement, APP_ENVIRONMENT, suffixe de la version, sinon prod)."""
    return environment.resolve_environment(version)


def parse_version(version):
    match = _NUMERIC_RE.match(str(version or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(latest, current):
    """Vrai si `latest` est strictement plus recente que `current` (numeros majeur.mineur.correctif)."""
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def enabled():
    return os.environ.get("APP_UPDATE_CHECK", "1").strip() != "0"


def source_url(version=None):
    override = os.environ.get("APP_UPDATE_CHECK_URL", "").strip()
    if override:
        return override
    channel = channel_for(version if version is not None else current_version())
    return f"https://raw.githubusercontent.com/{DEFAULT_REPOSITORY}/{channel}/frontend/js/branding.js"


def can_update():
    """La mise a jour depuis le navigateur exige : l'activation explicite ET l'unite systemd de surveillance installee
    (sa presence implique Linux + systemd : sous Windows elle n'existe jamais)."""
    return (
        os.environ.get("APP_ALLOW_WEB_UPDATE", "0").strip() == "1"
        and os.path.exists(PATH_UNIT)
        and os.path.isdir(UPDATE_DIR)
        and os.access(UPDATE_DIR, os.W_OK)
    )


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(temporary, path)


def fetch_latest_version(url, timeout=FETCH_TIMEOUT_SECONDS):
    """Lit APP_BUILD_VERSION dans le fichier distant. Leve OSError / ValueError en cas d'echec."""
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("adresse de verification invalide")
    request = urllib.request.Request(url, headers={"User-Agent": "aquai-update-check", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read(512 * 1024).decode("utf-8", errors="replace")
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError("version introuvable dans le fichier distant")
    return match.group(1)


def refresh(url=None, fetch=fetch_latest_version):
    """Interroge la source et ecrit le resultat dans le cache. Ne leve jamais : un echec est enregistre (`error`)."""
    url = url or source_url()
    result = {"checked_at": time.time(), "url": url}
    try:
        result["latest"] = fetch(url)
        result["error"] = None
    except Exception as error:  # noqa: BLE001 - reseau, DNS, TLS, format : tout echec est silencieux
        previous = _read_json(CHECK_FILE)
        result["latest"] = previous.get("latest")
        result["error"] = str(error)[:200] or error.__class__.__name__
    try:
        _write_json_atomic(CHECK_FILE, result)
    except OSError:
        pass
    return result


def _refresh_in_background():
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return
        _refreshing = True

    def run():
        global _refreshing
        try:
            refresh()
        finally:
            _refreshing = False

    threading.Thread(target=run, name="update-check", daemon=True).start()


def progress():
    """Etat de la derniere mise a jour lancee (ecrit par deploy.sh) : {state, step, message, ...} ou {}."""
    return _read_json(STATUS_FILE)


def status(force=False, now=None):
    """Etat complet pour l'administration. `force` = verification synchrone (bouton « Verifier maintenant »)."""
    now = time.time() if now is None else now
    installed = current_version()
    channel = channel_for(installed)
    result = {
        "enabled": enabled(), "current": environment.display_version(installed, channel), "channel": channel, "latest": None,
        "available": False, "checked_at": None, "error": None, "can_update": can_update(), "progress": progress(),
        "release_notes_url": f"https://github.com/{DEFAULT_REPOSITORY}/blob/{channel}/CHANGELOG.md",
    }
    if not result["enabled"]:
        return result
    cached = _read_json(CHECK_FILE)
    if force:
        cached = refresh()
    elif not cached:
        cached = refresh()  # toute premiere verification : synchrone (5 s max), sinon la page n'afficherait rien avant le rechargement
    elif now - float(cached.get("checked_at") or 0) > CHECK_TTL_SECONDS:
        _refresh_in_background()
    result["latest"] = cached.get("latest")
    result["checked_at"] = cached.get("checked_at")
    result["error"] = cached.get("error")
    result["available"] = is_newer(result["latest"], installed)
    return result


def request_update(requested_by, target_version, now=None):
    """Depose la demande de mise a jour. Le CONTENU n'est jamais interprete par le script : il ne sert qu'a la trace."""
    _write_json_atomic(REQUEST_FILE, {
        "requested_by": requested_by, "requested_at": time.time() if now is None else now, "target_version": target_version,
    })


def update_in_progress():
    state = progress().get("state")
    return state == "running" or os.path.exists(REQUEST_FILE)
