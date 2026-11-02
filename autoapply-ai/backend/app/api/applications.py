"""
AutoApply AI - Applications API Blueprint
Handles job application submission, listing, retry, and screenshots.
"""

import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app, send_file
from app import db
from app.models.application import Application, ApplicationStatus, ApplicationLog
from app.utils.auth import token_required
from app.utils.validators import is_valid_url, sanitize_url, normalize_job_url

applications_bp = Blueprint("applications", __name__)


def _get_daily_count(user_id: str) -> int:
    """Return count of applications submitted by user today (UTC)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return Application.query.filter(
        Application.user_id == user_id,
        Application.created_at >= today_start,
    ).count()


@applications_bp.route("/", methods=["POST"])
@token_required
def submit_application(current_user):
    """
    Submit a new job application URL for automated processing.
    Body: { "url": "https://boards.greenhouse.io/company/jobs/12345" }
    """
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url", "").strip()
    url = sanitize_url(raw_url)

    # Validation
    if not url:
        return jsonify({"error": "Job application URL is required"}), 400

    if not is_valid_url(url):
        return jsonify({"error": "Invalid URL format. Please provide a valid job application link."}), 400

    # Duplicate detection (same user + normalized URL, check if already applied or in progress)
    norm_url = normalize_job_url(url)
    existing_user_apps = Application.query.filter_by(user_id=current_user.id).all()
    for existing in existing_user_apps:
        if existing.status not in [ApplicationStatus.FAILED, ApplicationStatus.NEEDS_ACTION]:
            if normalize_job_url(existing.url) == norm_url:
                return jsonify({
                    "error": f"You have already applied or submitted this job application (Status: {existing.status.value})",
                    "application": existing.to_dict(),
                }), 409

    # Daily rate limit
    max_per_day = current_app.config.get("MAX_APPLICATIONS_PER_DAY", 50)
    count_today = _get_daily_count(current_user.id)
    if count_today >= max_per_day:
        return jsonify({
            "error": f"Daily limit reached. Maximum {max_per_day} applications per day.",
            "count_today": count_today,
            "limit": max_per_day,
        }), 429

    # Profile completeness check (Block apply until profile is 100% complete)
    from app.services.smart_resume_parser import compute_profile_completeness
    completeness = compute_profile_completeness(current_user, current_user.profile)
    if not completeness.get("is_complete"):
        return jsonify({
            "error": "Profile must be 100% complete before applying. Please complete the missing required fields.",
            "percent": completeness.get("percent", 0),
            "missing_fields": completeness.get("missing_fields", []),
            "is_complete": False,
        }), 403

    # Create Application record
    application = Application(
        user_id=current_user.id,
        url=url,
        status=ApplicationStatus.QUEUED,
    )
    db.session.add(application)
    db.session.flush()

    # Initial log
    log_entry = ApplicationLog(
        application_id=application.id,
        level="INFO",
        message="Application queued",
        extra_data={"url": url, "submitted_by": current_user.email},
    )
    db.session.add(log_entry)
    db.session.commit()

    # Dispatch execution (Celery worker or background daemon thread fallback)
    dispatched_celery = False
    try:
        from app.worker.tasks import run_application, celery_app
        inspector = celery_app.control.inspect(timeout=1.0)
        active_workers = inspector.ping() if inspector else None
        if active_workers:
            task = run_application.apply_async(args=[application.id], retry=False)
            application.celery_task_id = task.id
            db.session.commit()
            dispatched_celery = True
    except Exception as e:
        current_app.logger.warning(f"Celery dispatch check failed: {e}")

    if not dispatched_celery:
        # Fallback to local background daemon thread so application executes immediately
        import threading
        from app.worker.tasks import execute_application_pipeline
        current_app.logger.info(f"Running application {application.id} in background thread")
        thread = threading.Thread(
            target=execute_application_pipeline,
            args=[application.id],
            daemon=True
        )
        thread.start()

    return jsonify({
        "message": "Application submitted successfully",
        "application": application.to_dict(),
        "count_today": count_today + 1,
        "limit": max_per_day,
    }), 201


@applications_bp.route("/", methods=["GET"])
@token_required
def list_applications(current_user):
    """
    List all applications for the current user.
    Query params: status, page, per_page
    """
    status_filter = (request.args.get("status") or "").strip().upper()
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 20))))

    query = Application.query.filter_by(user_id=current_user.id)

    if status_filter and status_filter in ApplicationStatus.__members__:
        query = query.filter_by(status=ApplicationStatus[status_filter])

    query = query.order_by(Application.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    count_today = _get_daily_count(current_user.id)
    limit = current_app.config.get("MAX_APPLICATIONS_PER_DAY", 50)

    return jsonify({
        "applications": [app.to_dict() for app in pagination.items],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
        "count_today": count_today,
        "limit": limit,
    })


@applications_bp.route("/<string:app_id>", methods=["GET"])
@token_required
def get_application(current_user, app_id):
    """Get single application details including execution logs."""
    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    logs = ApplicationLog.query.filter_by(
        application_id=app_id
    ).order_by(ApplicationLog.created_at.asc()).all()

    result = application.to_dict()
    result["logs"] = [log.to_dict() for log in logs]
    return jsonify(result)


@applications_bp.route("/<string:app_id>", methods=["DELETE"])
@token_required
def delete_application(current_user, app_id):
    """Delete an application and its screenshot."""
    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    if application.screenshot_path and os.path.exists(application.screenshot_path):
        try:
            os.remove(application.screenshot_path)
        except OSError:
            pass

    db.session.delete(application)
    db.session.commit()
    return jsonify({"message": "Application deleted successfully"})


@applications_bp.route("/<string:app_id>/retry", methods=["POST"])
@token_required
def retry_application(current_user, app_id):
    """Retry a FAILED or NEEDS_ACTION application."""
    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    retryable = [ApplicationStatus.FAILED, ApplicationStatus.NEEDS_ACTION]
    if application.status not in retryable:
        return jsonify({
            "error": f"Cannot retry application with status '{application.status.value}'. Only FAILED and NEEDS_ACTION can be retried."
        }), 400

    MAX_RETRIES = 10
    if (application.retry_count or 0) >= MAX_RETRIES:
        return jsonify({
            "error": f"Maximum retry limit ({MAX_RETRIES}) reached for this application."
        }), 400

    application.status = ApplicationStatus.QUEUED
    application.error_message = None
    application.celery_task_id = None

    log_entry = ApplicationLog(
        application_id=application.id,
        level="INFO",
        message=f"Manual retry initiated (attempt {(application.retry_count or 0) + 1}/3)",
        extra_data={"retried_by": current_user.email},
    )
    db.session.add(log_entry)
    db.session.commit()

    dispatched_celery = False
    try:
        from app.worker.tasks import run_application, celery_app
        inspector = celery_app.control.inspect(timeout=1.0)
        active_workers = inspector.ping() if inspector else None
        if active_workers:
            task = run_application.delay(application.id)
            application.celery_task_id = task.id
            db.session.commit()
            dispatched_celery = True
    except Exception as e:
        current_app.logger.warning(f"Could not queue retry task with Celery: {e}")

    if not dispatched_celery:
        import threading
        from app.worker.tasks import execute_application_pipeline
        current_app.logger.info(f"Retrying application {application.id} in background thread")
        thread = threading.Thread(
            target=execute_application_pipeline,
            args=[application.id],
            daemon=True
        )
        thread.start()

    return jsonify({
        "message": "Application queued for retry",
        "application": application.to_dict(),
    })


@applications_bp.route("/<string:app_id>/approve", methods=["POST"])
@token_required
def approve_application(current_user, app_id):
    """
    Approve an application that is awaiting user review approval,
    and trigger final submission.
    """
    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    action_details = dict(application.action_details_json or {})
    action_details["approved"] = True
    application.action_details_json = action_details
    application.status = ApplicationStatus.QUEUED
    application.error_message = None

    log_entry = ApplicationLog(
        application_id=application.id,
        level="INFO",
        message="User approved application review. Submitting final application.",
        extra_data={"approved_by": current_user.email},
    )
    db.session.add(log_entry)
    db.session.commit()

    import threading
    from app.worker.tasks import execute_application_pipeline
    current_app.logger.info("Executing approved application %s in background thread", application.id)
    thread = threading.Thread(
        target=execute_application_pipeline,
        args=[application.id],
        daemon=True
    )
    thread.start()

    return jsonify({
        "message": "Application approved! Proceeding with final submission 🚀",
        "application": application.to_dict(),
    })


@applications_bp.route("/check-embeddable", methods=["GET"])
@token_required
def check_embeddable(current_user):
    """
    Check if a portal URL can be embedded in an in-page iframe,
    or if X-Frame-Options / CSP frame-ancestors blocks framing.
    """
    import urllib.parse
    import requests

    target_url = request.args.get("url", "").strip()
    if not target_url:
        return jsonify({"error": "url parameter is required"}), 400

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    x_frame = None
    csp = None
    embeddable = True
    reason = "Portal allows in-page embedding."

    try:
        resp = requests.head(target_url, headers=headers, timeout=4, allow_redirects=True)
        if resp.status_code in [403, 405]:
            resp = requests.get(target_url, headers=headers, timeout=4, stream=True)

        for k, v in resp.headers.items():
            k_lower = k.lower()
            if k_lower == "x-frame-options":
                x_frame = v.strip().lower()
            elif k_lower == "content-security-policy":
                csp = v.strip().lower()

        if x_frame in ["deny", "sameorigin"]:
            embeddable = False
            reason = f"Employer portal enforces security header X-Frame-Options: {x_frame.upper()} to prevent embedding on third-party websites."
        elif csp and ("frame-ancestors 'none'" in csp or "frame-ancestors 'self'" in csp):
            embeddable = False
            reason = "Employer portal enforces Content-Security-Policy (CSP) frame-ancestors which blocks embedded frames."

    except Exception as e:
        reason = f"Embed check notice: {str(e)}"

    return jsonify({
        "url": target_url,
        "embeddable": embeddable,
        "reason": reason,
        "x_frame_options": x_frame,
        "csp": csp,
    })


@applications_bp.route("/<string:app_id>/screenshot", methods=["GET"])
@token_required
def get_screenshot(current_user, app_id):
    """Serve the final submission page screenshot image."""
    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    if not application.screenshot_path:
        return jsonify({"error": "No screenshot available for this application"}), 404

    if not os.path.exists(application.screenshot_path):
        return jsonify({"error": "Screenshot file not found on disk"}), 404

    return send_file(
        application.screenshot_path,
        mimetype="image/png",
        as_attachment=False,
    )
