"""
AutoApply AI - Celery task definitions.
Background jobs for running job applications and Gmail sync.
"""

import logging
from datetime import datetime

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lazily load or reuse Flask app context across tasks
_cached_app = None

def _get_app():
    global _cached_app
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            return current_app._get_current_object()
    except Exception:
        pass
    if _cached_app is None:
        from app import create_app
        _cached_app = create_app()
    return _cached_app


# ---------------------------------------------------------------------------
# Helper: write an ApplicationLog entry inside an active app context
# ---------------------------------------------------------------------------

def _log_step(application_id: str, level: str, message: str, extra: dict = None):
    """Persist a log row to ApplicationLog. Must be called within app context."""
    try:
        from app import db
        from app.models.application import ApplicationLog
        log_entry = ApplicationLog(
            application_id=application_id,
            level=level,
            message=message,
            extra_data=extra or {},
            created_at=datetime.utcnow(),
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as exc:
        logger.warning("Failed to write ApplicationLog: %s", exc)


# ---------------------------------------------------------------------------
# Task 1: run_application / execute_application_pipeline
# ---------------------------------------------------------------------------

def execute_application_pipeline(application_id: str, celery_task=None):
    """
    Executes the end-to-end application pipeline with robust error handling.
    Can be invoked from Celery worker OR directly in a background thread if Celery is offline.
    """
    with _get_app().app_context():
        from app import db
        from app.models.application import Application, ApplicationStatus
        from app.services.application_orchestrator import run_application_pipeline
        from app.adapters.exceptions import (
            CaptchaDetectedError,
            LoginWallError,
            MissingInformationError,
            ExpiredJobError,
            ResumeUploadError,
            DuplicateApplicationError,
            UnsupportedFormError,
            SubmissionFailedError,
            NavigationError,
            ReviewApprovalRequiredError,
        )

        # 1. Load application record
        application = Application.query.get(application_id)
        if application is None:
            logger.error("Application %s not found – aborting task.", application_id)
            return {"error": "application_not_found"}

        # 2. Transition to APPLYING
        application.status = ApplicationStatus.APPLYING
        application.updated_at = datetime.utcnow()
        db.session.commit()
        _log_step(application_id, "INFO", "Task started – status set to APPLYING")

        try:
            # 3. Run the orchestrator pipeline
            _log_step(application_id, "INFO", "Invoking application_orchestrator pipeline")
            result = run_application_pipeline(application_id)

            # 4. Process orchestrator result
            application = Application.query.get(application_id)
            application.updated_at = datetime.utcnow()
            application.retry_count = (application.retry_count or 0) + 1

            if result.get("success"):
                application.status = ApplicationStatus.APPLIED
                application.error_message = None
                application.action_details_json = None
                db.session.commit()
                _log_step(application_id, "INFO", "Application submitted successfully and verified", result)
                logger.info("Application %s completed successfully.", application_id)
            elif result.get("unverified") or result.get("status") == "SUBMITTED":
                application.status = ApplicationStatus.SUBMITTED
                application.error_message = f"Submission Unverified: {result.get('error', 'No confirmation receipt detected')}. Please check portal status."
                db.session.commit()
                _log_step(application_id, "WARNING", "Application submitted but confirmation unverified", result)
            elif result.get("needs_action"):
                application.status = ApplicationStatus.NEEDS_ACTION
                db.session.commit()
                _log_step(application_id, "INFO", "Application action required", result)
            else:
                db.session.commit()

            return result

        except ReviewApprovalRequiredError as exc:
            logger.info("Review approval required for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = "Review Ready: All fields filled. Please review and click 'Approve & Submit' to submit."
            application.action_details_json = {
                "type": "review_approval",
                "company": application.company or "the job",
                "role": application.role or "",
                "message": "All fields filled and validated. Ready for your final review before submitting.",
                "summary": exc.review_details.get("summary", {}),
                "url": application.url,
                "screenshot_url": application.screenshot_url,
            }
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "INFO", f"Application review ready – marked NEEDS_ACTION: {exc}")
            return {"status": "needs_approval", "message": str(exc)}

        except CaptchaDetectedError as exc:
            # Problem 1: CAPTCHA / Bot detection – pause automation, ask user to solve manually
            logger.warning("CAPTCHA detected for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = f"CAPTCHA Challenge: Automation paused. Please open the job link ({application.url}) to solve the verification challenge manually, then click Resume."
            if not application.action_details_json:
                application.action_details_json = {
                    "type": "captcha",
                    "company": application.company or "the job",
                    "role": application.role or "",
                    "message": "CAPTCHA challenge detected. Please open the job page and solve it manually.",
                    "url": application.url,
                }
            application.retry_count = (application.retry_count or 0) + 1
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "WARNING", f"CAPTCHA detected – marked NEEDS_ACTION: {exc}")
            return {"error": "captcha_detected", "message": str(exc)}

        except LoginWallError as exc:
            # Problem 2: Login required – ask user to log in
            logger.warning("Login wall detected for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = f"Login Required: The employer requires an account to apply. Please visit the job link ({application.url}), sign in, and click Resume."
            if not application.action_details_json:
                application.action_details_json = {
                    "type": "login",
                    "company": application.company or "the job",
                    "role": application.role or "",
                    "message": "Candidate login or registration is required to apply.",
                    "url": application.url,
                }
            application.retry_count = (application.retry_count or 0) + 1
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "WARNING", f"Login wall – marked NEEDS_ACTION: {exc}")
            return {"error": "login_wall", "message": str(exc)}

        except MissingInformationError as exc:
            # Problem 3: Missing information – ask user for answers not available in profile
            logger.warning("Missing information for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = f"Missing Information: {exc}"
            application.retry_count = (application.retry_count or 0) + 1
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "WARNING", f"Missing information – marked NEEDS_ACTION: {exc}")
            return {"error": "missing_information", "message": str(exc)}

        except ExpiredJobError as exc:
            # Problem 6: Expired or closed job postings
            logger.warning("Job closed/expired for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.FAILED
            application.error_message = f"Job Closed/Expired: {exc}"
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "ERROR", f"Job expired – marked FAILED: {exc}")
            return {"error": "job_expired", "message": str(exc)}

        except ResumeUploadError as exc:
            # Problem 7: Resume upload failed after retry
            logger.error("Resume upload failed for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = f"Resume Upload Error: {exc}. Please verify your uploaded resume or apply directly."
            application.retry_count = (application.retry_count or 0) + 1
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "ERROR", f"Resume upload failed after retry: {exc}")
            return {"error": "resume_upload_error", "message": str(exc)}

        except DuplicateApplicationError as exc:
            # Problem 8: Duplicate application history check
            logger.warning("Duplicate application detected for %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = str(exc)
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "WARNING", f"Duplicate application: {exc}")
            return {"error": "duplicate_application", "message": str(exc)}

        except UnsupportedFormError as exc:
            # Problem 5: Unsupported fields or iframe layouts – stop safely
            logger.warning("Unsupported form layout for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = f"Unsupported Form Layout: {exc}. Please apply directly via the job link."
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "WARNING", f"Unsupported form – marked NEEDS_ACTION: {exc}")
            return {"error": "unsupported_form", "message": str(exc)}

        except SubmissionFailedError as exc:
            # Problem 9: Submission unconfirmed – check for errors, do not mark Applied
            logger.warning("Submission verification failed for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.NEEDS_ACTION
            application.error_message = f"Submission Unverified: {exc}. Please check your application status on the job portal."
            application.retry_count = (application.retry_count or 0) + 1
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "WARNING", f"Submission unverified – marked NEEDS_ACTION: {exc}")
            return {"error": "submission_failed", "message": str(exc)}

        except NavigationError as exc:
            # Network/navigation timeout
            logger.error("Navigation error for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.FAILED
            application.error_message = f"Navigation Error: Could not reach job page ({exc}). Please check the link."
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "ERROR", f"Navigation error – marked FAILED: {exc}")
            return {"error": "navigation_error", "message": str(exc)}

        except Exception as exc:
            # Unexpected terminal error – log clearly, mark FAILED, do not loop
            logger.exception("Unexpected pipeline failure for application %s: %s", application_id, exc)
            application = Application.query.get(application_id)
            application.status = ApplicationStatus.FAILED
            application.error_message = f"Application error: {str(exc)}"
            application.updated_at = datetime.utcnow()
            db.session.commit()
            _log_step(application_id, "ERROR", f"Application failed: {exc}")
            return {"error": "pipeline_error", "message": str(exc)}


@celery_app.task(
    bind=True,
    name="app.worker.tasks.run_application",
    max_retries=1,
    default_retry_delay=30,
    acks_late=True,
)
def run_application(self, application_id: str):
    """Celery task entry point."""
    return execute_application_pipeline(application_id, celery_task=self)


# ---------------------------------------------------------------------------
# Task 2: sync_gmail_for_user
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.worker.tasks.sync_gmail_for_user",
    bind=False,
    acks_late=True,
)
def sync_gmail_for_user(user_id: str):
    """
    Pull confirmation/rejection emails from Gmail for a single user and
    match them against existing Application records.
    """
    with _get_app().app_context():
        from app import db
        from app.models.user import User
        from app.services.gmail_service import sync_confirmation_emails

        user = User.query.get(str(user_id))
        if user is None:
            logger.error("sync_gmail_for_user: user %s not found.", user_id)
            return {"error": "user_not_found"}

        if not user.gmail_connected:
            logger.info("sync_gmail_for_user: user %s has no Gmail connection.", user_id)
            return {"skipped": True, "reason": "gmail_not_connected"}

        try:
            logger.info("Syncing Gmail for user %s", user_id)
            new_tokens = sync_confirmation_emails(user)
            logger.info(
                "Gmail sync for user %s: %d confirmation emails processed.",
                user_id, len(new_tokens),
            )
            return {"emails_synced": len(new_tokens)}

        except Exception as exc:
            logger.exception("Gmail sync failed for user %s: %s", user_id, exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Task 3: schedule_gmail_sync  (triggered by Celery Beat every 15 minutes)
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.worker.tasks.schedule_gmail_sync",
    bind=False,
)
def schedule_gmail_sync():
    """
    Beat-driven task. Iterates all users with gmail_connected=True and
    enqueues an individual sync task for each.
    """
    with _get_app().app_context():
        from app.models import User

        users = User.query.filter_by(gmail_connected=True).all()
        queued = 0
        for user in users:
            sync_gmail_for_user.apply_async(
                args=[str(user.id)],
                queue="gmail",
            )
            queued += 1

        logger.info("schedule_gmail_sync: queued %d Gmail sync tasks.", queued)
        return {"queued": queued}


# ---------------------------------------------------------------------------
# Register beat schedule (done here so the task names are already defined)
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    "schedule-gmail-sync-every-15-min": {
        "task": "app.worker.tasks.schedule_gmail_sync",
        "schedule": 900,  # 15 minutes in seconds
    },
}
