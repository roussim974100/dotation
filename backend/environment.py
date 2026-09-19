"""Environnement de l'instance (dev / preprod / prod) et version affichee.

Le meme code est promu de dev vers preprod puis prod : l'environnement n'est donc PAS ecrit dans les fichiers (sinon chaque
promotion creerait des conflits sur le numero de version) mais decide par le SERVEUR. Ordre de resolution :
  1. le fichier <dossier de donnees>/environment, ecrit par deploy.sh / deploy-preprod.sh / deploy-dev.sh ;
  2. la variable d'environnement APP_ENVIRONMENT ;
  3. le suffixe eventuel de la version (anciennes installations : « 3.18.5-prod ») ;
  4. « prod ».
La version affichee est « X.Y.Z-<environnement> », par exemple « 3.49.0-preprod ».
"""
import os
import re

from config import DATA_DIR, FRONTEND_DIR

ENVIRONMENTS = ("dev", "preprod", "prod")
ENV_FILE = os.path.join(DATA_DIR, "environment")
_VERSION_RE = re.compile(r'APP_BUILD_VERSION\s*=\s*"([^"]+)"')


def raw_version():
    """Contenu de APP_BUILD_VERSION dans frontend/js/branding.js (avec ou sans suffixe), ou chaine vide."""
    try:
        with open(os.path.join(FRONTEND_DIR, "js", "branding.js"), encoding="utf-8") as handle:
            match = _VERSION_RE.search(handle.read())
        return match.group(1) if match else ""
    except OSError:
        return ""


def base_version(version):
    """« 3.49.0-dev » -> « 3.49.0 »."""
    return str(version or "").split("-")[0]


def suffix_environment(version):
    """Environnement indique par le suffixe de la version (« 3.18.5-prod » -> prod), ou None."""
    suffix = (str(version or "").split("-")[1:2] or [""])[0].lower()
    return suffix if suffix in ENVIRONMENTS else None


def _clean(value):
    value = str(value or "").strip().lower()
    return value if value in ENVIRONMENTS else None


def _file_environment():
    try:
        with open(ENV_FILE, encoding="utf-8") as handle:
            return _clean(handle.readline())
    except OSError:
        return None


def resolve_environment(version=None):
    """Environnement de l'instance : fichier, puis APP_ENVIRONMENT, puis suffixe de `version` (par defaut celle de
    branding.js), puis « prod »."""
    return (_file_environment() or _clean(os.environ.get("APP_ENVIRONMENT"))
            or suffix_environment(raw_version() if version is None else version) or "prod")


def display_version(version=None, environment=None):
    """Version telle qu'affichee : « X.Y.Z-<environnement> »."""
    raw = raw_version() if version is None else version
    return f"{base_version(raw)}-{environment or resolve_environment(raw)}"
