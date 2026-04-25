from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import json
import os
import glob

bp = Blueprint("debug", __name__, url_prefix="/api/debug")

@bp.route("/test", methods=["GET"])
def lock_test():
    """Serve lock test page"""
    try:
        template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lock_test.html")
        with open(template_path, 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/test.js", methods=["GET"])
def lock_test_js():
    """Serve lock test JavaScript"""
    try:
        js_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lock_test.js")
        with open(js_path, 'r') as f:
            return f.read(), 200, {'Content-Type': 'application/javascript; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/last-lock-report", methods=["GET"])
def get_last_report():
    """Get the most recent lock report from frontend"""
    try:
        files = glob.glob("lock_report_*.json")
        if not files:
            return jsonify({"error": "No reports yet"}), 404

        latest = sorted(files)[-1]
        with open(latest, 'r') as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/check-lock/<form_id>", methods=["GET"])
def check_lock(form_id):
    """Check and log the lock state of a form"""
    from database import get_db
    try:
        with get_db() as conn:
            form = conn.execute(
                "SELECT id, status, payload_json FROM dotation_forms WHERE id = ?",
                (form_id,)
            ).fetchone()

            if not form:
                return jsonify({"error": "Form not found"}), 404

            payload = json.loads(form['payload_json']) if form['payload_json'] else {}
            locked_at = payload.get('meta', {}).get('lockedAt')

            result = {
                "formId": form_id,
                "status": form['status'],
                "workflowStatus": payload.get('workflow', {}).get('status'),
                "lockedAt": locked_at,
                "isLocked": bool(locked_at),
                "resources": len(payload.get('resources', {}).get('additional', []))
            }

            # Sauvegarder le diagnostic
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:15]
            filename = f"lock_check_{timestamp}.json"
            with open(filename, "w") as f:
                json.dump(result, f, indent=2)

            print(f"[LOCK CHECK] {filename}: {result}")
            return jsonify(result), 200
    except Exception as e:
        print(f"[LOCK CHECK ERROR] {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/report-lock", methods=["POST"])
def report_lock():
    """Receive lock state report from frontend"""
    try:
        data = request.get_json() or {}
        print(f"[LOCK REPORT] {data}")

        # Sauvegarder le rapport
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:15]
        filename = f"lock_report_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        return jsonify({"ok": True, "file": filename}), 200
    except Exception as e:
        print(f"[LOCK REPORT ERROR] {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/logs", methods=["POST"])
def receive_logs():
    """Receive console logs from frontend and save to file"""
    try:
        content_type = request.content_type
        print(f"[DEBUG] Received POST request, content-type: {content_type}")

        data = None
        if request.is_json:
            data = request.get_json() or {}
        else:
            raw_data = request.get_data(as_text=True)
            print(f"[DEBUG] Raw data: {raw_data[:200] if raw_data else 'empty'}")
            if raw_data:
                try:
                    data = json.loads(raw_data)
                except:
                    data = {"raw": raw_data}

        logs = data.get("logs", []) if data else []
        print(f"[DEBUG] Processing {len(logs)} logs")

        if not logs:
            return jsonify({"ok": True}), 200

        # Sauvegarder dans le répertoire courant
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:15]
        filename = f"debug_logs_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "logs": logs
            }, f, indent=2)

        print(f"[DEBUG] Logs saved to {os.path.abspath(filename)}")
        return jsonify({"ok": True, "file": filename}), 200
    except Exception as e:
        print(f"[DEBUG ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
