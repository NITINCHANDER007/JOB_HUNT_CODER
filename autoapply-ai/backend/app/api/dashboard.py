"""
Dashboard API Blueprint
Provides summary statistics and a feed of recent applications.
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify
from sqlalchemy import func

from app import db
from app.models.application import Application, ApplicationStatus
from app.utils.auth import token_required

dashboard_bp = Blueprint("dashboard", __name__)


def _utc_now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# GET /stats  — Aggregated statistics for the current user
# ---------------------------------------------------------------------------

@dashboard_bp.route("/stats", methods=["GET"])
@token_required
def get_stats(current_user):
    uid = current_user.id

    # --- Total counts by status ---
    counts = (
        db.session.query(Application.status, func.count(Application.id))
        .filter(Application.user_id == uid)
        .group_by(Application.status)
        .all()
    )
    status_map = {row[0]: row[1] for row in counts}

    total_applications = sum(status_map.values())
    applied_count = status_map.get(ApplicationStatus.APPLIED, 0)
    queued_count = status_map.get(ApplicationStatus.QUEUED, 0)
    failed_count = status_map.get(ApplicationStatus.FAILED, 0)
    needs_action_count = status_map.get(ApplicationStatus.NEEDS_ACTION, 0)
    applying_count = status_map.get(ApplicationStatus.APPLYING, 0)

    # Success rate: applied / (total - queued - applying)  * 100
    denominator = total_applications - queued_count - applying_count
    success_rate = round((applied_count / denominator * 100), 1) if denominator > 0 else 0.0

    # --- Applications in the last 7 days ---
    week_ago = _utc_now() - timedelta(days=7)
    applications_this_week = (
        db.session.query(func.count(Application.id))
        .filter(
            Application.user_id == uid,
            Application.created_at >= week_ago,
        )
        .scalar()
        or 0
    )

    # --- Recent confirmation emails (last 5) ---
    recent_confirmations = []
    try:
        from app.models.email_token import EmailToken  # noqa: PLC0415

        tokens = (
            EmailToken.query.filter_by(user_id=uid)
            .order_by(EmailToken.created_at.desc())
            .limit(5)
            .all()
        )
        recent_confirmations = [t.to_dict() for t in tokens]
    except Exception:  # noqa: BLE001
        # EmailToken model may not exist yet; return empty list gracefully
        recent_confirmations = []

    return jsonify(
        {
            "total_applications": total_applications,
            "applied_count": applied_count,
            "queued_count": queued_count,
            "failed_count": failed_count,
            "needs_action_count": needs_action_count,
            "applying_count": applying_count,
            "success_rate": success_rate,
            "applications_this_week": applications_this_week,
            "recent_confirmations": recent_confirmations,
        }
    )


# ---------------------------------------------------------------------------
# GET /feed  — Last 20 applications with full details
# ---------------------------------------------------------------------------

@dashboard_bp.route("/feed", methods=["GET"])
@token_required
def get_feed(current_user):
    applications = (
        Application.query.filter_by(user_id=current_user.id)
        .order_by(Application.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify({"applications": [a.to_dict() for a in applications]})
