"""Sauvegarde et restauration de toutes les bases de l'application.

Une sauvegarde est une archive unique (zip) contenant un manifeste et un instantane coherent
de chaque base (API de sauvegarde SQLite, jamais une copie brute : les bases sont en mode WAL).
Elle peut etre chiffree par mot de passe (scrypt + AES-256-GCM, bibliotheque `cryptography`).

Ce module n'a aucune dependance Flask : il est utilise par les routes d'administration et par
le script de sauvegarde planifiee (backup_cli.py).
"""
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone

from config import BASE_DIR, DB_PATH, DB_USERS_PATH

ARCHIVE_FORMAT = 1
ENCRYPTED_MAGIC = b"AQBK-ENC1"
SALT_SIZE = 16
NONCE_SIZE = 12
SCRYPT_N = 2 ** 15
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_DATABASE_BYTES = 400 * 1024 * 1024
SQLITE_MAGIC = b"SQLite format 3\x00"
BACKUP_DIR = os.path.join(BASE_DIR, "db_backups")
MIN_PASSWORD_LENGTH = 8

# Bases sauvegardees : cle stable (nom de fichier dans l'archive), libelle, chemin, tables attendues.
DATABASES = [
    {
        "key": "dotation",
        "label": "Dossiers, ressources et paramètres",
        "path": DB_PATH,
        "required_tables": {"dotation_forms", "dotation_items", "resource_catalog", "service_catalog", "app_settings", "app_logs"},
    },
    {
        "key": "users",
        "label": "Comptes et groupes",
        "path": DB_USERS_PATH,
        "required_tables": {"users", "groups", "user_groups"},
    },
]


class BackupError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def archive_filename(encrypted):
    return f"aquai_sauvegarde_{_utc_stamp()}.{'aqbak' if encrypted else 'zip'}"


def validate_password(password):
    if password is None or password == "":
        return None
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BackupError("password_too_short", f"Le mot de passe doit comporter au moins {MIN_PASSWORD_LENGTH} caractères.")
    return password


# ---------------------------------------------------------------------------
# Instantane et diagnostic d'une base SQLite
# ---------------------------------------------------------------------------

def snapshot_sqlite(source_path, target_path):
    """Copie coherente d'une base en cours d'utilisation (sauvegarde en ligne SQLite)."""
    source = sqlite3.connect(source_path, timeout=30)
    try:
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def diagnose_sqlite(path, key):
    """Controle un fichier de base : signature, integrite, tables attendues, quelques statistiques."""
    spec = next((db for db in DATABASES if db["key"] == key), None)
    issues, warnings, stats = [], [], {}
    try:
        with open(path, "rb") as handle:
            if handle.read(16) != SQLITE_MAGIC:
                return {"level": "error", "issues": ["Fichier non reconnu comme base SQLite valide."], "warnings": [], "stats": {}}
    except OSError as exc:
        return {"level": "error", "issues": [f"Impossible de lire le fichier : {exc}"], "warnings": [], "stats": {}}
    try:
        conn = sqlite3.connect(path)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                issues.append(f"Échec du contrôle d'intégrité SQLite : {integrity}")
            existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if spec:
                missing = spec["required_tables"] - existing
                if missing:
                    issues.append(f"Tables manquantes : {', '.join(sorted(missing))}")
            if key == "dotation" and "dotation_forms" in existing:
                stats["dossiers"] = conn.execute("SELECT COUNT(*) FROM dotation_forms").fetchone()[0]
            if key == "users" and "users" in existing:
                stats["comptes"] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                if stats["comptes"] == 0:
                    warnings.append("Aucun compte dans cette base : personne ne pourrait se connecter après restauration.")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        issues.append(f"Erreur SQLite : {exc}")
    level = "error" if issues else ("warning" if warnings else "ok")
    return {"level": level, "issues": issues, "warnings": warnings, "stats": stats}


# ---------------------------------------------------------------------------
# Chiffrement
# ---------------------------------------------------------------------------

def _crypto():
    """Importe `cryptography` a la demande. Le module n'est utile que pour les archives chiffrees : s'il manque
    (mise a jour du code sans `pip install`), l'application demarre quand meme et seules les sauvegardes
    chiffrees sont indisponibles, avec un message clair."""
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError:
        raise BackupError(
            "crypto_unavailable",
            "Le chiffrement des sauvegardes est indisponible : le module Python « cryptography » n'est pas installé. "
            "Lancez la mise à jour complète (sudo bash deploy.sh) ou : <venv>/bin/pip install -r backend/requirements.txt, "
            "puis redémarrez le service.",
        ) from None
    return InvalidTag, AESGCM, Scrypt


def _derive_key(password, salt):
    Scrypt = _crypto()[2]
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=8, p=1).derive(password.encode("utf-8"))


def encrypt_bytes(data, password):
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    header = ENCRYPTED_MAGIC + salt
    AESGCM = _crypto()[1]
    return header + nonce + AESGCM(_derive_key(password, salt)).encrypt(nonce, data, header)


def decrypt_bytes(blob, password):
    header_size = len(ENCRYPTED_MAGIC) + SALT_SIZE
    if len(blob) < header_size + NONCE_SIZE + 16:
        raise BackupError("invalid_archive", "Archive tronquée ou illisible.")
    header = blob[:header_size]
    nonce = blob[header_size:header_size + NONCE_SIZE]
    InvalidTag, AESGCM, _ = _crypto()
    try:
        return AESGCM(_derive_key(password, header[len(ENCRYPTED_MAGIC):])).decrypt(nonce, blob[header_size + NONCE_SIZE:], header)
    except InvalidTag:
        # Mot de passe incorrect ou archive alteree : impossible de les distinguer.
        raise BackupError("wrong_password", "Mot de passe incorrect ou archive altérée.")


def is_encrypted(blob):
    return blob.startswith(ENCRYPTED_MAGIC)


# ---------------------------------------------------------------------------
# Creation d'une archive
# ---------------------------------------------------------------------------

def create_archive(password=None, app_version=""):
    """Retourne (octets de l'archive, manifeste). Chiffre si un mot de passe est fourni."""
    password = validate_password(password)
    manifest = {
        "format": ARCHIVE_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app_version": app_version,
        "databases": [],
    }
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as workdir, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for spec in DATABASES:
            if not os.path.exists(spec["path"]) or os.path.getsize(spec["path"]) == 0:
                continue
            snapshot_path = os.path.join(workdir, f"{spec['key']}.db")
            snapshot_sqlite(spec["path"], snapshot_path)
            with open(snapshot_path, "rb") as handle:
                content = handle.read()
            archive.writestr(f"{spec['key']}.db", content)
            manifest["databases"].append({
                "key": spec["key"], "label": spec["label"], "file": f"{spec['key']}.db",
                "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            })
        if not manifest["databases"]:
            raise BackupError("nothing_to_backup", "Aucune base à sauvegarder.")
        manifest["encrypted"] = bool(password)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    data = buffer.getvalue()
    return (encrypt_bytes(data, password) if password else data), manifest


# ---------------------------------------------------------------------------
# Lecture, diagnostic et restauration
# ---------------------------------------------------------------------------

def open_archive(blob, password=None):
    """Ouvre une archive (dechiffre au besoin) et retourne (manifeste, {cle: octets}). Verifie les empreintes."""
    if len(blob) > MAX_ARCHIVE_BYTES:
        raise BackupError("file_too_large", "Archive trop volumineuse.")
    if is_encrypted(blob):
        if not password:
            raise BackupError("password_required", "Cette sauvegarde est protégée : le mot de passe est requis.")
        blob = decrypt_bytes(blob, password)
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != ARCHIVE_FORMAT:
                raise BackupError("unsupported_format", "Format de sauvegarde non pris en charge.")
            contents = {}
            for entry in manifest.get("databases", []):
                key = entry.get("key")
                if key not in {db["key"] for db in DATABASES}:
                    raise BackupError("invalid_archive", f"Base inconnue dans l'archive : {key}")
                # Protection contre une archive "bombe" : taille decompressee annoncee bornee avant lecture.
                if archive.getinfo(entry["file"]).file_size > MAX_DATABASE_BYTES:
                    raise BackupError("file_too_large", f"Base {key} trop volumineuse.")
                content = archive.read(entry["file"])
                if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
                    raise BackupError("corrupted_archive", f"Empreinte invalide pour {key} : archive corrompue.")
                contents[key] = content
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise BackupError("invalid_archive", f"Archive illisible : {exc}")
    return manifest, contents


def diagnose_archive(blob, password=None):
    manifest, contents = open_archive(blob, password)
    reports = []
    with tempfile.TemporaryDirectory() as workdir:
        for entry in manifest["databases"]:
            path = os.path.join(workdir, entry["file"])
            with open(path, "wb") as handle:
                handle.write(contents[entry["key"]])
            report = diagnose_sqlite(path, entry["key"])
            reports.append({"key": entry["key"], "label": entry["label"], "size": entry["size"], **report})
    level = "error" if any(r["level"] == "error" for r in reports) else ("warning" if any(r["level"] == "warning" for r in reports) else "ok")
    return {"level": level, "created_at": manifest.get("created_at"), "encrypted": bool(manifest.get("encrypted")), "databases": reports}


def restore_sqlite(source_path, target_path):
    """Remplace le contenu de la base cible par celui du fichier source, en place, via l'API de
    sauvegarde SQLite. Pas de remplacement de fichier : fonctionne meme si la base est ouverte par
    le serveur (Windows refuse de remplacer un fichier ouvert) et sans casser les autres connexions."""
    source = sqlite3.connect(source_path)
    try:
        target = sqlite3.connect(target_path, timeout=30)
        try:
            source.backup(target)
            target.execute("PRAGMA journal_mode = WAL")
        finally:
            target.close()
    finally:
        source.close()


def restore_archive(blob, password=None, keys=None):
    """Restaure les bases de l'archive (toutes, ou celles de `keys`). Les bases actuelles sont d'abord
    sauvegardees dans db_backups/. Refuse l'operation si une base de l'archive est en erreur."""
    report = diagnose_archive(blob, password)
    if report["level"] == "error":
        raise BackupError("diagnose_failed", "L'archive contient une base invalide : restauration refusée.")
    manifest, contents = open_archive(blob, password)
    selected = [entry for entry in manifest["databases"] if not keys or entry["key"] in keys]
    if not selected:
        raise BackupError("nothing_to_restore", "Aucune base à restaurer.")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = _utc_stamp()
    safety_copies = []
    for entry in selected:
        spec = next(db for db in DATABASES if db["key"] == entry["key"])
        if os.path.exists(spec["path"]) and os.path.getsize(spec["path"]) > 0:
            safety_path = os.path.join(BACKUP_DIR, f"avant_restauration_{stamp}_{entry['key']}.db")
            snapshot_sqlite(spec["path"], safety_path)
            safety_copies.append(os.path.basename(safety_path))
    try:
        with tempfile.TemporaryDirectory() as workdir:
            for entry in selected:
                spec = next(db for db in DATABASES if db["key"] == entry["key"])
                staging = os.path.join(workdir, entry["file"])
                with open(staging, "wb") as handle:
                    handle.write(contents[entry["key"]])
                restore_sqlite(staging, spec["path"])
    except sqlite3.Error as exc:
        raise BackupError("import_failed", f"Échec du remplacement : {exc}")
    return {"restored": [entry["key"] for entry in selected], "safety_copies": safety_copies, "report": report}


def list_safety_copies():
    if not os.path.isdir(BACKUP_DIR):
        return []
    items = []
    names = sorted(os.listdir(BACKUP_DIR), key=lambda n: os.path.getmtime(os.path.join(BACKUP_DIR, n)), reverse=True)
    for name in names:
        full = os.path.join(BACKUP_DIR, name)
        if os.path.isfile(full):
            items.append({"name": name, "size": os.path.getsize(full), "modified": datetime.fromtimestamp(os.path.getmtime(full), timezone.utc).isoformat()})
    return items
