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
    focus_interactive_browser,
    cancel_interactive_login,
    get_interactive_session_info,
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
    Cleans up stale locks, starts the interactive session, verifies launch,
    and returns verified launch status.
    If an interactive session is already open and running, returns already_running: True.
    """
    user_id = str(current_user.id)
    force = request.args.get("force") == "true" or (request.is_json and bool(request.json and request.json.get("force")))

    # Check if a login session is already running
    active = _active_interactive_sessions.get(user_id)
    if not force and active and active.get("status") in ["launching", "waiting_for_user"]:
        proc = active.get("proc")
        # If the process is still running, return already_running status
        if proc is None or proc.poll() is None:
            return jsonify({
                "already_running": True,
                "message": active.get("message", "Chrome browser is already open on your desktop. Please complete your LinkedIn login."),
                "status": "waiting_for_user",
                "browser_verified": True,
                "session": get_interactive_session_info(user_id),
            })

    ready_event = threading.Event()

    def _run_login():
        launch_manual_linkedin_login(user_id=user_id, timeout_seconds=300, ready_event=ready_event)

    thread = threading.Thread(target=_run_login, daemon=True)
    thread.start()

    # Wait up to 8 seconds for launch verification
    ready_event.wait(timeout=8.0)

    active_now = _active_interactive_sessions.get(user_id, {})
    if active_now.get("status") == "error":
        err_msg = active_now.get("error") or active_now.get("message") or "Failed to launch Chrome on desktop."
        return jsonify({
            "error": err_msg,
            "message": err_msg,
            "status": "error",
            "browser_verified": False,
        }), 500

    info = get_interactive_session_info(user_id)
    return jsonify({
        "message": active_now.get("message", "Chrome browser is opening. Please log into your LinkedIn account."),
        "status": active_now.get("status", "launching"),
        "browser_verified": active_now.get("browser_verified", False),
        "session": info,
    })


@linkedin_bp.route("/session/open-browser", methods=["POST"])
@token_required
def session_open_browser(current_user):
    """Bring the running interactive Chrome window to the foreground on desktop."""
    user_id = str(current_user.id)
    result = focus_interactive_browser(user_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@linkedin_bp.route("/session/cancel-login", methods=["POST"])
@token_required
def cancel_login(current_user):
    """Cancel any active interactive login session and clean up browser processes."""
    user_id = str(current_user.id)
    result = cancel_interactive_login(user_id)
    return jsonify(result)


@linkedin_bp.route("/session/connect-status", methods=["GET"])
@token_required
def session_connect_status(current_user):
    """Poll live progress of the interactive manual login window."""
    user_id = str(current_user.id)
    active = get_interactive_session_info(user_id)
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

