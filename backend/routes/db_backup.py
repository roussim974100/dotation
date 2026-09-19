"""Routes de sauvegarde / restauration multi-bases (archive unique, chiffrement optionnel)."""
import os

from flask import Blueprint, jsonify, make_response, request

import backup
import backup_targets
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
    "destination_not_found": 404,
    "path_unreachable": 502,
    "path_not_writable": 502,
    "write_failed": 502,
    "verify_failed": 502,
    "already_exists": 409,
}


def _destinations_view():
    """Destinations + dernier resultat d'envoi de chacune (lu dans l'historique)."""
    last = {}
    for entry in backup_targets.read_history(200):
        last.setdefault(entry.get("destination_id"), entry)
    return [{**dest, "last": last.get(dest["id"])} for dest in backup_targets.load_config()["destinations"]]


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


@bp.route("/api/admin/backup/destinations", methods=["GET"])
@login_required
@permission_required("db.manage")
def backup_destinations_list():
    return jsonify({"destinations": _destinations_view(), "protocols": backup_targets.PROTOCOLS})


@bp.route("/api/admin/backup/destinations", methods=["PUT"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=30, window_seconds=60, scope="backup_destinations")
def backup_destinations_save():
    payload = request.get_json(silent=True) or {}
    try:
        backup_targets.save_destinations(payload.get("destinations"))
    except backup_targets.TargetError as error:
        return _error_response(error)
    _log("backup_destinations_saved", "Destinations de sauvegarde modifiées", {"count": len(payload.get("destinations") or [])})
    return jsonify({"destinations": _destinations_view()})


@bp.route("/api/admin/backup/destinations/<dest_id>/test", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=20, window_seconds=60, scope="backup_dest_test")
def backup_destination_test(dest_id):
    try:
        result = backup_targets.test_destination(backup_targets.get_destination(dest_id))
    except backup_targets.TargetError as error:
        return _error_response(error)
    return jsonify(result)


@bp.route("/api/admin/backup/destinations/<dest_id>/send", methods=["POST"])
@login_required
@permission_required("db.manage")
@rate_limit(max_requests=10, window_seconds=60, scope="backup_dest_send")
def backup_destination_send(dest_id):
    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or None
    try:
        destination = backup_targets.get_destination(dest_id)
        entry = backup_targets.run_send(destination, password, trigger="manual")
    except (backup_targets.TargetError, backup.BackupError) as error:
        _log("backup_sent_failed", "Envoi de sauvegarde échoué", {"destination": dest_id, "code": error.code})
        return _error_response(error)
    _log("backup_sent", "Sauvegarde envoyée", {"destination": entry["destination"], "filename": entry["filename"], "encrypted": entry["encrypted"]})
    return jsonify(entry)


@bp.route("/api/admin/backup/history", methods=["GET"])
@login_required
@permission_required("db.manage")
def backup_history():
    return jsonify({"history": backup_targets.read_history(30)})
