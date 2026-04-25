from flask import Blueprint, request, jsonify, session
import uuid
from auth import login_required, check_user
from utils import utc_now

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.route("/verify-session", methods=["POST"])
@login_required
def verify_session():
    """Verify current user's password for sensitive operations (RGPD compliance)"""
    try:
        username = session.get("user")
        print(f"[AUTH] Verify session for user: {username}")
        if not username:
            print(f"[AUTH] ERROR: No username in session")
            return jsonify({"error": "Not authenticated"}), 401

        data = request.get_json() or {}
        password = data.get("password", "")

        if not password:
            print(f"[AUTH] ERROR: No password provided")
            return jsonify({"error": "Password required"}), 400

        # Utilise la même logique de vérification que le login
        print(f"[AUTH] Calling check_user for username={username}, password_len={len(password)}")
        result = check_user(username, password)
        print(f"[AUTH] check_user result: {result}")
        if result != "ok":
            if result == "pending":
                return jsonify({"error": "user_pending"}), 401
            elif result == "disabled":
                return jsonify({"error": "user_disabled"}), 401
            else:
                return jsonify({"error": "invalid_password"}), 401

        # Stocker le token de vérification dans la session
        verification_token = str(uuid.uuid4())
        session["signature_verification_token"] = verification_token
        session["signature_verification_time"] = utc_now()
        session.modified = True
        print(f"[AUTH] Password verified for {username}, token={verification_token[:8]}...")

        return jsonify({
            "verified": True,
            "token": verification_token
        }), 200
    except Exception as e:
        print(f"[AUTH] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@bp.route("/check-verification", methods=["GET"])
@login_required
def check_verification():
    """Check if user has verified their password in this session"""
    from flask import session

    verification_token = session.get("signature_verification_token")
    if verification_token:
        return jsonify({"verified": True}), 200
    return jsonify({"verified": False}), 200


@bp.route("/clear-verification", methods=["POST"])
@login_required
def clear_verification():
    """Clear verification token (for security after showing signature)"""
    from flask import session

    session.pop("signature_verification_token", None)
    session.pop("signature_verification_time", None)
    return jsonify({"ok": True}), 200
