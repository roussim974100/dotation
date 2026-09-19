"""Parc : liste des unites et historique d'une unite (lecture)."""
from flask import Blueprint, jsonify, redirect, request, send_from_directory

from auth import current_user, has_permission, login_required, permission_required, rate_limit
from config import FRONTEND_DIR
from database import get_db
from models.audit import insert_app_log
import time

from models.settings import DEFAULT_APP_SETTINGS, get_app_settings
from models.units import UnitActionError, apply_manual_action, count_units_by_status, get_unit, list_units, release_stale_reservations
from models.units_extra import (
    DEFAULT_RETENTION_YEARS, anonymize_old_holders, compute_indicators, find_duplicate_candidates, find_incomplete_lines, import_units,
)

bp = Blueprint("units", __name__)


_HOUSEKEEPING_EVERY = 600  # secondes
_last_housekeeping = 0.0


def run_parc_housekeeping(connection, force=False):
    """Entretien periodique (au plus toutes les 10 min) : reservations perimees et anonymisation RGPD des anciens detenteurs."""
    global _last_housekeeping
    if not force and time.time() - _last_housekeeping < _HOUSEKEEPING_EVERY:
        return
    _last_housekeeping = time.time()
    release_stale_reservations(connection)
    try:
        years = int(get_app_settings(connection).get("parc_retention_years") or DEFAULT_RETENTION_YEARS)
    except (TypeError, ValueError):
        years = DEFAULT_RETENTION_YEARS
    anonymize_old_holders(connection, years)


def _masked():
    user = current_user() or {}
    return user.get("data_scope") == "masked"


@bp.route("/parc.html")
@login_required
def parc_page():
    if not has_permission("forms.read_list"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "parc.html")


@bp.route("/api/units", methods=["GET"])
@login_required
def units_list():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        run_parc_housekeeping(connection)  # requete legere : pas de tache planifiee a installer
        units = list_units(
            connection, request.args.get("resource") or None, (request.args.get("q") or "").strip(),
            request.args.get("status") or None, request.args.get("limit", 200), _masked(),
        )
        counts = count_units_by_status(connection, request.args.get("resource") or None)
    return jsonify({"units": units, "counts": counts})


@bp.route("/api/units/<unit_id>", methods=["GET"])
@login_required
def unit_detail(unit_id):
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        unit = get_unit(connection, unit_id, _masked())
    if not unit:
        return jsonify({"error": "not_found"}), 404
    return jsonify(unit)


_ACTION_STATUS = {"holder_required": 400, "unknown_unit": 404, "invalid_state": 409, "identifier_exists": 409, "different_resource": 409}


@bp.route("/api/units/<unit_id>/actions", methods=["POST"])
@login_required
@permission_required("parc.manage")
@rate_limit(max_requests=60, window_seconds=60, scope="units_actions")
def unit_action(unit_id):
    payload = request.get_json(silent=True) or {}
    actor = (current_user() or {}).get("username")
    with get_db() as connection:
        try:
            unit = apply_manual_action(connection, unit_id, payload.get("action"), payload.get("notes"), actor, payload)
        except UnitActionError as error:
            return jsonify({"error": error.code, "message": error.message}), _ACTION_STATUS.get(error.code, 400)
        insert_app_log(connection, "admin", "unit_action", "Action sur une unité du parc", "unit", unit_id,
                       {"action": payload.get("action")}, actor=actor)
    return jsonify(unit)


@bp.route("/api/units/stats", methods=["GET"])
@login_required
def units_stats():
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        return jsonify(compute_indicators(connection, request.args.get("resource") or None))


@bp.route("/api/units/import", methods=["POST"])
@login_required
@permission_required("parc.manage")
@rate_limit(max_requests=10, window_seconds=600, scope="units_import")
def units_import():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no_file", "message": "Aucun fichier reçu."}), 400
    raw = file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        return jsonify({"error": "file_too_large", "message": "Fichier trop volumineux (2 Mo maximum)."}), 413
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # export Excel classique
    dry_run = (request.form.get("dry_run") or "1") != "0"
    actor = (current_user() or {}).get("username")
    with get_db() as connection:
        report = import_units(connection, text, actor, dry_run=dry_run)
        if not dry_run:
            insert_app_log(connection, "admin", "units_imported", "Import du parc", None, None,
                           {"created": report["created"], "skipped": report["skipped"], "errors": len(report["errors"])}, actor=actor)
    return jsonify(report)


@bp.route("/api/units/to-check", methods=["GET"])
@login_required
def units_to_check():
    """Donnees a verifier : lignes attribuees sans identifiant (absentes du parc) et doublons probables d'identifiants."""
    if not has_permission("forms.read_list"):
        return jsonify({"error": "forbidden"}), 403
    with get_db() as connection:
        return jsonify({
            "incomplete": find_incomplete_lines(connection, _masked()),
            "duplicates": find_duplicate_candidates(connection, _masked()),
        })
