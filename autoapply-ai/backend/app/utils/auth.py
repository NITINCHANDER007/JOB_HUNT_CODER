"""
JWT authentication utilities.
"""

import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app


def generate_token(user_id: str) -> str:
    """Generate a JWT access token for the given user_id."""
    secret = current_app.config.get("JWT_SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
    expires_in = int(current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 86400))
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Returns payload or raises jwt.InvalidTokenError."""
    try:
        secret = current_app.config.get("JWT_SECRET_KEY") or os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")
    except Exception:
        secret = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")
    return jwt.decode(token, secret, algorithms=["HS256"])


def token_required(f):
    """Decorator to protect routes with JWT authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

        if not token:
            return jsonify({"error": "Authorization token required"}), 401

        try:
            payload = decode_token(token)
            user_id = payload["sub"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        # Import here to avoid circular imports
        from app.models.user import User

        user = User.query.get(user_id)
        if not user or not user.is_active:
            return jsonify({"error": "User not found or inactive"}), 401

        return f(user, *args, **kwargs)

    return decorated
