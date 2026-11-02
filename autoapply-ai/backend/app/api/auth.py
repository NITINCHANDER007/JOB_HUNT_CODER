"""
Auth Blueprint — /api/auth
Handles user registration, login, profile retrieval, logout, and password changes.
"""

import bcrypt
from flask import Blueprint, request, jsonify
from app import db
from app.models.user import User
from app.models.profile import Profile
from app.utils.auth import generate_token, token_required
from app.utils.validators import is_valid_email, is_valid_password

auth_bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
def register():
    """Create a new account. Returns a JWT on success."""
    data = request.get_json(silent=True) or {}

    # ── Validate required fields ──────────────────────────────────────────
    email = (data.get("email") or "").strip().lower()
    if email == "nitinchandra834@gmail.com":
        email = "codernitin55@gmail.com"
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()

    errors = {}
    if not full_name:
        errors["full_name"] = "Full name is required"
    if not email:
        errors["email"] = "Email is required"
    elif not is_valid_email(email):
        errors["email"] = "Invalid email format"
    if not password:
        errors["password"] = "Password is required"
    else:
        valid, msg = is_valid_password(password)
        if not valid:
            errors["password"] = msg

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    # ── Check uniqueness ──────────────────────────────────────────────────
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with that email already exists"}), 409

    # ── Create user + profile ─────────────────────────────────────────────
    try:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, password_hash=hashed, full_name=full_name)
        db.session.add(user)
        db.session.flush()  # get user.id before creating profile

        profile = Profile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Could not create account", "detail": str(exc)}), 500

    token = generate_token(str(user.id))
    return (
        jsonify(
            {
                "token": token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                },
            }
        ),
        201,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate an existing user and return a JWT."""
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    if email == "nitinchandra834@gmail.com":
        email = "codernitin55@gmail.com"
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_active:
        return jsonify({"error": "Account is deactivated"}), 403

    # Verify password
    try:
        password_matches = bcrypt.checkpw(
            password.encode(), user.password_hash.encode()
        )
    except Exception:
        password_matches = False

    if not password_matches:
        return jsonify({"error": "Invalid email or password"}), 401

    token = generate_token(str(user.id))
    return jsonify(
        {
            "token": token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
        }
    )


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------
@auth_bp.route("/me", methods=["GET"])
@token_required
def me(current_user):
    """Return the authenticated user's info and profile."""
    profile = Profile.query.filter_by(user_id=current_user.id).first()

    return jsonify(
        {
            "user": current_user.to_dict(),
            "profile": profile.to_dict() if profile else {},
        }
    )


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------
@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout(current_user):
    """
    Stateless JWT logout — the client simply drops the token.
    """
    return jsonify({"message": "Logged out successfully"})


# ---------------------------------------------------------------------------
# POST / PUT /api/auth/change-password
# ---------------------------------------------------------------------------
@auth_bp.route("/change-password", methods=["POST", "PUT"])
@token_required
def change_password(current_user):
    """Change the authenticated user's password."""
    data = request.get_json(silent=True) or {}

    old_password = data.get("current_password") or data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        return jsonify({"error": "current_password and new_password are required"}), 400

    # Verify old password
    try:
        old_matches = bcrypt.checkpw(
            old_password.encode(), current_user.password_hash.encode()
        )
    except Exception:
        old_matches = False

    if not old_matches:
        return jsonify({"error": "Current password is incorrect"}), 401

    # Validate new password strength
    valid, msg = is_valid_password(new_password)
    if not valid:
        return jsonify({"error": msg}), 422

    if old_password == new_password:
        return jsonify({"error": "New password must differ from the current password"}), 422

    # Hash and save
    try:
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        current_user.password_hash = new_hash
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Could not update password", "detail": str(exc)}), 500

    return jsonify({"message": "Password changed successfully"})


# ---------------------------------------------------------------------------
# DELETE /api/auth/account
# ---------------------------------------------------------------------------
@auth_bp.route("/account", methods=["DELETE"])
@token_required
def delete_account(current_user):
    """Permanently delete user account and associated profile, resumes, applications."""
    try:
        db.session.delete(current_user)
        db.session.commit()
        return jsonify({"message": "Account deleted successfully"})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Could not delete account", "detail": str(exc)}), 500
