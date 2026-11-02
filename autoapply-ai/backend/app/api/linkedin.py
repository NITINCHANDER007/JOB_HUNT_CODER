"""
AutoApply AI - LinkedIn Session Management API Blueprint.

Provides endpoints to:
1. Check LinkedIn authentication and session expiration status.
2. Launch a headed Chrome browser for manual LinkedIn login (with 2FA/CAPTCHA).
3. Poll live progress of manual login.
4. Verify session validity against LinkedIn live servers.
5. Disconnect / clear saved session cookies.
6. Configure automation preferences (browser visibility, review approval).
"""

import threading
from flask import Blueprint, request, jsonify, current_app
from app.utils.auth import token_required
from app.services.browser_session_service import (
    get_linkedin_session_status,
    launch_manual_linkedin_login,
    verify_linkedin_session,
    disconnect_linkedin_session,
    _active_interactive_sessions,
)

linkedin_bp = Blueprint("linkedin", __name__)


@linkedin_bp.route("/session/status", methods=["GET"])
@token_required
def session_status(current_user):
    """Return the current LinkedIn authentication and persistent session status."""
    status = get_linkedin_session_status(str(current_user.id))
    # Also include browser automation preferences
    status["headless"] = current_app.config.get("PLAYWRIGHT_HEADLESS", False)
    status["require_approval"] = current_app.config.get("REQUIRE_USER_APPROVAL", True)
    return jsonify(status)


@linkedin_bp.route("/session/connect", methods=["POST"])
@token_required
def session_connect(current_user):
    """
    Launch a visible (headed) Chrome browser window for manual LinkedIn login.
    Runs asynchronously in a background thread so the user can interact freely.
    """
    user_id = str(current_user.id)
    force = request.args.get("force") == "true" or (request.is_json and bool(request.json and request.json.get("force")))

    # Check if a login session is already running
    active = _active_interactive_sessions.get(user_id)
    if not force and active and active.get("status") in ["launching", "waiting_for_user"]:
        import time
        if time.time() - active.get("start_ts", 0) < 300:
            return jsonify({
                "message": "Interactive browser window is already open. Please complete your login.",
                "status": active.get("status"),
                "session": active,
            })

    def _run_login():
        launch_manual_linkedin_login(user_id=user_id, timeout_seconds=300)

    thread = threading.Thread(target=_run_login, daemon=True)
    thread.start()

    return jsonify({
        "message": "Chrome browser opened. Please log into your LinkedIn account in the newly opened window.",
        "status": "launching",
    })


@linkedin_bp.route("/session/connect-status", methods=["GET"])
@token_required
def session_connect_status(current_user):
    """Poll live progress of the interactive manual login window."""
    user_id = str(current_user.id)
    active = _active_interactive_sessions.get(user_id, {})
    current_status = get_linkedin_session_status(user_id)

    return jsonify({
        "interactive": active,
        "session": current_status,
    })


@linkedin_bp.route("/session/verify", methods=["POST"])
@token_required
def session_verify(current_user):
    """Run a live verification check against LinkedIn using the persistent profile."""
    result = verify_linkedin_session(str(current_user.id))
    return jsonify(result)


@linkedin_bp.route("/session/disconnect", methods=["POST"])
@token_required
def session_disconnect(current_user):
    """Disconnect LinkedIn session by clearing stored cookies and state."""
    result = disconnect_linkedin_session(str(current_user.id))
    return jsonify(result)


@linkedin_bp.route("/settings", methods=["POST"])
@token_required
def update_settings(current_user):
    """Update browser automation preferences (headless mode, require approval)."""
    data = request.get_json(silent=True) or {}

    if "headless" in data:
        current_app.config["PLAYWRIGHT_HEADLESS"] = bool(data["headless"])

    if "require_approval" in data:
        current_app.config["REQUIRE_USER_APPROVAL"] = bool(data["require_approval"])

    return jsonify({
        "message": "Automation settings updated successfully.",
        "headless": current_app.config.get("PLAYWRIGHT_HEADLESS", False),
        "require_approval": current_app.config.get("REQUIRE_USER_APPROVAL", True),
    })

