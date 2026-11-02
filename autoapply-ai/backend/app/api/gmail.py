"""
Gmail API Blueprint
Handles Gmail OAuth2 connect/disconnect and email sync endpoints.
"""

import os
from urllib.parse import urljoin

from flask import Blueprint, request, jsonify, redirect, current_app

from app import db
from app.utils.auth import token_required
from app.services.gmail_service import (
    get_gmail_auth_url,
    handle_gmail_callback,
    sync_confirmation_emails,
)

gmail_bp = Blueprint("gmail", __name__)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ---------------------------------------------------------------------------
# GET /auth  — Return Gmail OAuth URL
# ---------------------------------------------------------------------------

@gmail_bp.route("/auth", methods=["GET"])
@token_required
def gmail_auth(current_user):
    """Return the Google OAuth2 URL that the frontend should redirect the user to."""
    try:
        auth_url = get_gmail_auth_url(str(current_user.id))
        return jsonify({"auth_url": auth_url})
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Gmail auth URL error: %s", exc)
        return jsonify({"error": "Failed to generate Gmail auth URL"}), 500


# ---------------------------------------------------------------------------
# GET /callback  — OAuth callback, exchange code, redirect to frontend
# ---------------------------------------------------------------------------

@gmail_bp.route("/callback", methods=["GET"])
def gmail_callback():
    """
    Google redirects here after the user grants permission.
    Exchange the code for tokens, save them, and redirect to the frontend
    settings page with a success/error query param.
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        current_app.logger.warning("Gmail OAuth error: %s", error)
        return redirect(f"{FRONTEND_URL}/#/settings?gmail=error&reason={error}")

    if not code or not state:
        return redirect(f"{FRONTEND_URL}/#/settings?gmail=error&reason=missing_params")

    try:
        result = handle_gmail_callback(code, state)
        email = result.get("email", "")
        return redirect(f"{FRONTEND_URL}/#/settings?gmail=success&email={email}")
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Gmail callback error: %s", exc)
        return redirect(
            f"{FRONTEND_URL}/#/settings?gmail=error&reason=token_exchange_failed"
        )


# ---------------------------------------------------------------------------
# DELETE /disconnect  — Remove Gmail token from user
# ---------------------------------------------------------------------------

@gmail_bp.route("/disconnect", methods=["DELETE"])
@token_required
def gmail_disconnect(current_user):
    current_user.gmail_token_encrypted = None
    current_user.gmail_email = None
    current_user.gmail_connected = False
    db.session.commit()
    return jsonify({"message": "Gmail disconnected successfully"})


# ---------------------------------------------------------------------------
# GET /status  — Return Gmail connection status
# ---------------------------------------------------------------------------

@gmail_bp.route("/status", methods=["GET"])
@token_required
def gmail_status(current_user):
    connected = bool(
        getattr(current_user, "gmail_token_encrypted", None)
    )
    email = getattr(current_user, "gmail_email", None) if connected else None
    return jsonify({"connected": connected, "email": email})


# ---------------------------------------------------------------------------
# POST /sync  — Manually trigger Gmail sync
# ---------------------------------------------------------------------------

@gmail_bp.route("/sync", methods=["POST"])
@token_required
def gmail_sync(current_user):
    if not getattr(current_user, "gmail_token_encrypted", None):
        return jsonify({"error": "Gmail is not connected"}), 400

    try:
        new_tokens = sync_confirmation_emails(str(current_user.id))
        return jsonify(
            {
                "message": f"Sync complete. Found {len(new_tokens)} new confirmation email(s).",
                "new_emails": new_tokens,
            }
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Gmail sync error for user %s: %s", current_user.id, exc)
        return jsonify({"error": "Gmail sync failed", "detail": str(exc)}), 500
