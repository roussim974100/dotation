"""Routes de sauvegarde / restauration multi-bases (archive unique, chiffrement optionnel)."""
import os

from flask import Blueprint, jsonify, make_response, request

import backup
from auth import login_required, permission_required, rate_limit, current_user
from database import get_db
from models.audit import insert_app_log

bp = Blueprint("db_backup", __name__)

# Codes d'erreur metier -> statut HTTP
_ERROR_STATUS = {
    "import_failed": 500,
    "password_required": 422,
    "wrong_password": 422,
    "password_too_short": 400,
    "diagnose_failed": 422,
    "file_too_large": 413,
}


def _error_response(error):
    return jsonify({"error": error.code, "message": error.message}), _ERROR_STATUS.get(error.code, 400)


def _log(action_type, label, details=None):
    try:
        with get_db() as connection:
            insert_app_log(
                connection, "admin", action_type, label, details=details or {},
                actor=(current_user() or {}).get("username"),
            )
    except Exception:  # la journalisation ne doit jamais bloquer une sauvegarde
        pass


def _uploaded_archive():
    file = request.files.get("file")
    if not file:
        return None, (jsonify({"error": "no_file", "message": "Aucun fichier reçu."}), 400)
    blob = file.read(backup.MAX_ARCHIVE_BYTES + 1)
    if len(blob) > backup.MAX_ARCHIVE_BYTES:
        return None, (jsonify({"error": "file_too_large", "message": "Archive trop volumineuse."}), 413)
    return blob, None


@bp.route("/api/admin/backup/info", methods=["GET"])
@login_required
@permission_required("db.manage")
def backup_info():
    databases = []
    for spec in backup.DATABASES:
        exists = os.path.exists(spec["path"]) and os.path.getsize(spec["path"]) > 0
        databases.append({
            "key": spec["key"], "label": spec["label"], "exists": exists,
            "size": os.path.getsize(spec["path"]) if exists else 0,
        })
    return jsonify({"databases": databases, "safety_copies": backup.list_safety_copies(), "min_password_length": backup.MIN_PASSWORD_LENGTH})


@bp.route("/api/admin/backup/export", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=20, window_seconds=60, scope="backup_export")
def backup_export():
    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or None
    try:
        blob, manifest = backup.create_archive(password)
    except backup.BackupError as error:
        return _error_response(error)
    filename = backup.archive_filename(bool(password))
    _log("backup_exported", "Export sauvegarde", {"filename": filename, "encrypted": bool(password), "databases": [d["key"] for d in manifest["databases"]]})
    response = make_response(blob)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@bp.route("/api/admin/backup/diagnose", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=10, window_seconds=60, scope="backup_diagnose")
def backup_diagnose():
    blob, error_response = _uploaded_archive()
    if error_response:
        return error_response
    try:
        report = backup.diagnose_archive(blob, request.form.get("password") or None)
    except backup.BackupError as error:
        return _error_response(error)
    _log("backup_diagnosed", "Diagnostic sauvegarde", {"level": report["level"]})
    return jsonify(report)


@bp.route("/api/admin/backup/import", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=3, window_seconds=600, scope="backup_import")
def backup_import():
    blob, error_response = _uploaded_archive()
    if error_response:
        return error_response
    keys = [key for key in (request.form.get("keys") or "").split(",") if key] or None
    try:
        result = backup.restore_archive(blob, request.form.get("password") or None, keys)
    except backup.BackupError as error:
        return _error_response(error)
    except OSError as error:
        return jsonify({"error": "import_failed", "message": f"Échec du remplacement : {error}"}), 500
    _log("backup_imported", "Import sauvegarde", {"restored": result["restored"], "safety_copies": result["safety_copies"]})
    return jsonify({"imported": True, "restored": result["restored"], "safety_copies": result["safety_copies"], "report": result["report"]})
