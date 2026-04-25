from flask import Blueprint, request, jsonify
from datetime import datetime
import json
import os
import glob

from auth import admin_required

bp = Blueprint("debug", __name__, url_prefix="/api/debug")


@bp.route("/test", methods=["GET"])
@admin_required
def lock_test():
    try:
        template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lock_test.html")
        with open(template_path, "r") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/test.js", methods=["GET"])
@admin_required
def lock_test_js():
    try:
        js_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lock_test.js")
        with open(js_path, "r") as f:
            return f.read(), 200, {"Content-Type": "application/javascript; charset=utf-8"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/last-lock-report", methods=["GET"])
@admin_required
def get_last_report():
    try:
        files = glob.glob("lock_report_*.json")
        if not files:
            return jsonify({"error": "No reports yet"}), 404
        latest = sorted(files)[-1]
        with open(latest, "r") as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/check-lock/<form_id>", methods=["GET"])
@admin_required
def check_lock(form_id):
    from database import get_db
    try:
        with get_db() as conn:
            form = conn.execute(
                "SELECT id, status, payload_json FROM dotation_forms WHERE id = ?",
                (form_id,),
            ).fetchone()
            if not form:
                return jsonify({"error": "Form not found"}), 404
            payload = json.loads(form["payload_json"]) if form["payload_json"] else {}
            locked_at = payload.get("meta", {}).get("lockedAt")
            return jsonify({
                "formId": form_id,
                "status": form["status"],
                "workflowStatus": payload.get("workflow", {}).get("status"),
                "lockedAt": locked_at,
                "isLocked": bool(locked_at),
                "resources": len(payload.get("resources", {}).get("additional", [])),
            }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/report-lock", methods=["POST"])
@admin_required
def report_lock():
    try:
        data = request.get_json() or {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:15]
        filename = f"lock_report_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        return jsonify({"ok": True, "file": filename}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/logs", methods=["POST"])
@admin_required
def receive_logs():
    try:
        data = request.get_json(silent=True) or {}
        logs = data.get("logs", [])
        if not logs:
            return jsonify({"ok": True}), 200
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:15]
        filename = f"debug_logs_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "logs": logs}, f, indent=2)
        return jsonify({"ok": True, "file": filename}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
