from flask import Blueprint, request, jsonify, session
import uuid
from auth import login_required, check_user, rate_limit
from utils import utc_now
from datetime import datetime, timezone

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_VERIFY_TTL_SECONDS = 900  # 15 minutes


def _verification_still_valid():
    ts = session.get("signature_verification_time")
    if not ts:
        return False
    try:
        verified_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - verified_at).total_seconds()
        return elapsed < _VERIFY_TTL_SECONDS
    except Exception:
        return False


@bp.route("/verify-session", methods=["POST"])
@login_required
@rate_limit(max_requests=10, window_seconds=300, scope="verify_session")
def verify_session():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json() or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "Password required"}), 400

    result = check_user(username, password)
    if result != "ok":
        if result == "pending":
            return jsonify({"error": "user_pending"}), 401
        elif result == "disabled":
            return jsonify({"error": "user_disabled"}), 401
        return jsonify({"error": "invalid_password"}), 401

    verification_token = str(uuid.uuid4())
    session["signature_verification_token"] = verification_token
    session["signature_verification_time"] = utc_now()
    session.modified = True

    return jsonify({"verified": True}), 200


@bp.route("/check-verification", methods=["GET"])
@login_required
def check_verification():
    token = session.get("signature_verification_token")
    if token and _verification_still_valid():
        return jsonify({"verified": True}), 200
    if token:
        session.pop("signature_verification_token", None)
        session.pop("signature_verification_time", None)
    return jsonify({"verified": False}), 200


@bp.route("/clear-verification", methods=["POST"])
@login_required
def clear_verification():
    session.pop("signature_verification_token", None)
    session.pop("signature_verification_time", None)
    return jsonify({"ok": True}), 200
