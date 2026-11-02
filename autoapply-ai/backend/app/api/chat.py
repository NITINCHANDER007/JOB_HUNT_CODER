"""
AutoApply AI - Chatbot Assistant Blueprint
Coordinates conversational Q&A for missing application questions,
CAPTCHA/OTP manual verification alerts, and application resumption.
"""

import os
import re
import threading
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.application import Application, ApplicationStatus, ApplicationLog
from app.models.profile import Profile
from app.utils.auth import token_required
from app.utils.validators import is_valid_url, sanitize_url, normalize_job_url

chat_bp = Blueprint("chat", __name__)


def _get_active_application(user_id: str):
    """
    Find the most urgent or active application for the user:
    1. Status in NEEDS_ACTION (needing input/captcha/login)
    2. Status in APPLYING or QUEUED
    3. Most recent application today
    """
    # 1. Needs action first
    app_needs_action = Application.query.filter_by(
        user_id=user_id, status=ApplicationStatus.NEEDS_ACTION
    ).order_by(Application.updated_at.desc()).first()
    if app_needs_action:
        return app_needs_action

    # 2. In progress
    app_in_progress = Application.query.filter_by(user_id=user_id).filter(
        Application.status.in_([ApplicationStatus.APPLYING, ApplicationStatus.QUEUED])
    ).order_by(Application.updated_at.desc()).first()
    if app_in_progress:
        return app_in_progress

    # 3. Most recent
    return Application.query.filter_by(user_id=user_id).order_by(Application.created_at.desc()).first()


@chat_bp.route("/status", methods=["GET"])
@token_required
def get_chat_status(current_user):
    """
    Returns the real-time context for the floating chatbot:
    - Active application (if any)
    - Pending missing questions or action required (CAPTCHA, Login, OTP)
    - Quick statistics
    """
    app = _get_active_application(current_user.id)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    applied_count = Application.query.filter(
        Application.user_id == current_user.id,
        Application.status == ApplicationStatus.APPLIED,
    ).count()
    today_count = Application.query.filter(
        Application.user_id == current_user.id,
        Application.created_at >= today_start,
    ).count()
    limit = current_app.config.get("MAX_APPLICATIONS_PER_DAY", 50)

    app_data = None
    if app:
        is_active = app.status in [ApplicationStatus.APPLYING, ApplicationStatus.QUEUED, ApplicationStatus.NEEDS_ACTION]
        is_terminal = app.status in [ApplicationStatus.APPLIED, ApplicationStatus.FAILED]

        # Fetch recent audit logs for live progress streaming in the chatbot
        logs = ApplicationLog.query.filter_by(
            application_id=app.id
        ).order_by(ApplicationLog.created_at.asc()).all()
        recent_logs = [log.to_dict() for log in logs[-8:]]

        app_data = {
            "id": app.id,
            "company": app.company or "Unknown Company",
            "role": app.role or "Job Application",
            "url": app.url,
            "status": app.status.value,
            "error_message": app.error_message,
            "action_details": app.action_details_json,
            "is_active": is_active,
            "is_terminal": is_terminal,
            "retry_count": app.retry_count or 0,
            "screenshot_url": app.screenshot_url,
            "confirmation_url": app.confirmation_url,
            "updated_at": app.updated_at.isoformat() if app.updated_at else None,
            "recent_logs": recent_logs,
        }

    return jsonify({
        "active_application": app_data,
        "user": {
            "name": current_user.full_name or current_user.email.split("@")[0],
            "email": current_user.email,
        },
        "stats": {
            "applied_count": applied_count,
            "today_count": today_count,
            "remaining_today": max(0, limit - today_count),
            "limit": limit,
        },
    })


@chat_bp.route("/answer", methods=["POST"])
@token_required
def submit_answer(current_user):
    """
    Receives an answer for a missing application question from the chatbot.
    Saves the answer to the application's AI mapping and user's profile.
    If all missing questions are answered, automatically resumes the automation.
    Body:
    {
        "application_id": "...",
        "field_key": "notice_period",
        "answer": "15 days",
        "save_to_profile": true
    }
    """
    data = request.get_json(silent=True) or {}
    app_id = data.get("application_id")
    field_key = (data.get("field_key") or "").strip()
    raw_answer = data.get("answer")
    save_to_profile = bool(data.get("save_to_profile", True))

    if not app_id or not field_key or raw_answer is None:
        return jsonify({"error": "application_id, field_key, and answer are required"}), 400

    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    answer_str = str(raw_answer).strip()

    # 1. Update Application AI mapping
    mapping = dict(application.ai_mapping_json or {})
    mapping[field_key] = answer_str
    application.ai_mapping_json = mapping

    # 2. Save to user Profile so it is remembered and never asked again
    profile = current_user.profile
    if profile and save_to_profile:
        norm_key = field_key.lower().replace(" ", "_").replace("-", "_")
        # Direct profile fields mapping
        profile_fields = {
            "notice_period": "notice_period",
            "notice": "notice_period",
            "expected_ctc": "expected_ctc",
            "ctc": "expected_ctc",
            "salary": "expected_ctc",
            "work_authorization": "work_authorization",
            "visa": "work_authorization",
            "sponsorship": "work_authorization",
            "years_of_experience": "years_of_experience",
            "experience_years": "years_of_experience",
            "linkedin": "linkedin_url",
            "github": "github_url",
            "portfolio": "portfolio_url",
            "city": "location",
            "location": "location",
            "phone": "phone",
            "summary": "summary",
            "gender": "gender",
            "ethnicity": "ethnicity",
            "relocate": "willing_to_relocate",
        }
        matched_attr = None
        for k, attr in profile_fields.items():
            if k in norm_key:
                matched_attr = attr
                break

        if not matched_attr and hasattr(profile, norm_key):
            matched_attr = norm_key

        if matched_attr and hasattr(profile, matched_attr):
            try:
                col_type = getattr(Profile, matched_attr).type
                if isinstance(col_type, db.Integer):
                    import re
                    digits = re.findall(r"\d+", answer_str)
                    if digits:
                        setattr(profile, matched_attr, int(digits[0]))
                elif isinstance(col_type, db.Boolean):
                    setattr(profile, matched_attr, answer_str.lower() in ("yes", "true", "1"))
                else:
                    setattr(profile, matched_attr, answer_str)
                current_app.logger.info("Saved answer for '%s' to profile.%s", field_key, matched_attr)
            except Exception as e:
                current_app.logger.warning("Could not set profile.%s: %s", matched_attr, e)

    # 3. Update pending missing fields in action_details_json
    action_details = dict(application.action_details_json or {})
    missing_fields = action_details.get("missing_fields") or []

    # Filter out answered field (by key or label)
    remaining_fields = []
    for f in missing_fields:
        f_key = f.get("key") or f.get("name") or f.get("label") or ""
        f_lbl = f.get("label") or ""
        if f_key != field_key and f_lbl != field_key:
            remaining_fields.append(f)

    action_details["missing_fields"] = remaining_fields
    application.action_details_json = action_details
    db.session.commit()

    # 4. If all missing fields are answered (or this is OTP verification or review approval), automatically resume automation!
    is_otp = action_details.get("type") == "otp" or field_key in ["otp", "verification_code", "code"]
    is_approval = action_details.get("type") == "review_approval" and field_key in ["approval", "approve", "submit", "confirm"]
    if is_approval:
        action_details["approved"] = True
        application.action_details_json = action_details

    all_answered = (len(remaining_fields) == 0) or is_otp or is_approval
    if all_answered:
        application.status = ApplicationStatus.QUEUED
        application.error_message = None
        if not is_approval:
            application.action_details_json = None
        db.session.commit()

        # Log resumption
        log_entry = ApplicationLog(
            application_id=application.id,
            level="INFO",
            message="All pending questions answered via chatbot. Resuming application.",
            extra_data={"resumed_via": "chatbot"},
        )
        db.session.add(log_entry)
        db.session.commit()

        # Launch worker pipeline in background
        from app.worker.tasks import execute_application_pipeline
        current_app.logger.info("Auto-resuming application %s in background thread", application.id)
        thread = threading.Thread(
            target=execute_application_pipeline,
            args=[application.id],
            daemon=True,
        )
        thread.start()

        return jsonify({
            "success": True,
            "resumed": True,
            "message": f"Perfect! All missing questions for {application.company or 'the job'} have been answered. Resuming your application now 🚀",
            "application": application.to_dict(),
        })

    next_field = remaining_fields[0]
    return jsonify({
        "success": True,
        "resumed": False,
        "message": f"Saved answer for {field_key}.",
        "remaining_count": len(remaining_fields),
        "next_question": next_field,
        "application": application.to_dict(),
    })


@chat_bp.route("/resume", methods=["POST"])
@token_required
def resume_application(current_user):
    """
    Resumes an application after the user has manually completed
    CAPTCHA, login, or OTP verification on the portal.
    Body: { "application_id": "..." }
    """
    data = request.get_json(silent=True) or {}
    app_id = data.get("application_id")

    if not app_id:
        return jsonify({"error": "application_id is required"}), 400

    application = Application.query.filter_by(
        id=app_id, user_id=current_user.id
    ).first_or_404(description="Application not found")

    action_details = dict(application.action_details_json or {})
    if action_details.get("type") == "review_approval":
        action_details["approved"] = True
        application.action_details_json = action_details
    else:
        application.action_details_json = None

    application.status = ApplicationStatus.QUEUED
    application.error_message = None

    log_entry = ApplicationLog(
        application_id=application.id,
        level="INFO",
        message="Manual verification completed by user. Automation resumed via chatbot.",
        extra_data={"resumed_via": "chatbot_action_button"},
    )
    db.session.add(log_entry)
    db.session.commit()

    # Launch worker in background thread
    from app.worker.tasks import execute_application_pipeline
    current_app.logger.info("Resuming application %s in background thread after manual verification", application.id)
    thread = threading.Thread(
        target=execute_application_pipeline,
        args=[application.id],
        daemon=True,
    )
    thread.start()

    return jsonify({
        "success": True,
        "resumed": True,
        "message": f"Resuming automation for {application.company or 'the job'}! I'm monitoring the process...",
        "application": application.to_dict(),
    })


@chat_bp.route("/message", methods=["POST"])
@token_required
def send_chat_message(current_user):
    """
    Conversational chat message endpoint.
    Handles URL submissions, status inquiries, and general job assistance without wasting AI API calls.
    Body: { "message": "..." }
    """
    data = request.get_json(silent=True) or {}
    raw_msg = (data.get("message") or "").strip()

    if not raw_msg:
        return jsonify({"reply": "How can I help you today? You can paste a job URL to apply or ask for your application status!"})

    msg_lower = raw_msg.lower()

    # Intent 0a: Approval command for review_approval
    if any(kw in msg_lower for kw in ["approve", "submit application", "confirm submission"]):
        app_to_approve = Application.query.filter_by(
            user_id=current_user.id, status=ApplicationStatus.NEEDS_ACTION
        ).order_by(Application.updated_at.desc()).first()
        if app_to_approve and (app_to_approve.action_details_json or {}).get("type") == "review_approval":
            action_details = dict(app_to_approve.action_details_json or {})
            action_details["approved"] = True
            app_to_approve.action_details_json = action_details
            app_to_approve.status = ApplicationStatus.QUEUED
            app_to_approve.error_message = None
            db.session.commit()

            from app.worker.tasks import execute_application_pipeline
            thread = threading.Thread(
                target=execute_application_pipeline,
                args=[app_to_approve.id],
                daemon=True,
            )
            thread.start()
            return jsonify({
                "reply": f"🚀 Application for **{app_to_approve.company or 'the job'}** approved! Submitting now in your persistent browser session.",
                "action": "application_started",
            })

    # Intent 0b: LinkedIn session inquiries
    if "linkedin" in msg_lower and any(w in msg_lower for w in ["login", "connect", "session", "status", "cookie", "auth"]):
        from app.services.browser_session_service import get_linkedin_session_status
        li_stat = get_linkedin_session_status(str(current_user.id))
        if li_stat.get("connected"):
            return jsonify({
                "reply": f"Your LinkedIn session is **Connected** as **{li_stat.get('user_name', 'Candidate')}**! You are ready for 1-click Easy Apply applications.",
            })
        else:
            return jsonify({
                "reply": "Your LinkedIn session is **Not Connected**. Go to [Settings](#/settings) and click **'Connect LinkedIn'** to log in using your browser once. Your authenticated session will be saved and reused for all Easy Apply jobs!",
            })

    # Intent 1: Check if message contains a Job Application URL
    url_match = re.search(r"https?://[^\s]+", raw_msg)
    if url_match:
        extracted_url = url_match.group(0).rstrip(".,)")
        clean_url = sanitize_url(extracted_url)
        if is_valid_url(clean_url):
            # Check profile completeness first
            from app.services.smart_resume_parser import compute_profile_completeness
            completeness = compute_profile_completeness(current_user, current_user.profile)
            if not completeness.get("is_complete"):
                missing = [m.replace("_", " ").title() for m in completeness.get("missing_fields", [])]
                return jsonify({
                    "reply": f"I found the job URL, but your profile is currently {completeness.get('percent', 0)}% complete. Please complete the following required fields in your Profile first: **{', '.join(missing)}**.",
                    "action": "complete_profile",
                })

            # Check duplicate
            norm_url = normalize_job_url(clean_url)
            existing = Application.query.filter_by(user_id=current_user.id).all()
            for ex in existing:
                if ex.status not in [ApplicationStatus.FAILED, ApplicationStatus.NEEDS_ACTION]:
                    if normalize_job_url(ex.url) == norm_url:
                        return jsonify({
                            "reply": f"You have already submitted this application ({ex.company or 'the job'}). Current status: **{ex.status.value}**.",
                            "application": ex.to_dict(),
                        })

            # Submit application
            new_app = Application(
                user_id=current_user.id,
                url=clean_url,
                status=ApplicationStatus.QUEUED,
            )
            db.session.add(new_app)
            db.session.flush()

            log_entry = ApplicationLog(
                application_id=new_app.id,
                level="INFO",
                message="Application queued via chatbot",
                extra_data={"url": clean_url},
            )
            db.session.add(log_entry)
            db.session.commit()

            # Start background thread
            from app.worker.tasks import execute_application_pipeline
            thread = threading.Thread(
                target=execute_application_pipeline,
                args=[new_app.id],
                daemon=True,
            )
            thread.start()

            return jsonify({
                "reply": f"🚀 I've started applying to that job! I'll analyze the page and handle form filling for you. I'll alert you here if any questions or verification steps arise.",
                "application": new_app.to_dict(),
                "action": "application_started",
            })

    # Intent 2: Status check
    if any(w in msg_lower for w in ["status", "how is", "progress", "what happened", "update", "check"]):
        active_app = _get_active_application(current_user.id)
        if not active_app:
            return jsonify({
                "reply": "You have no active applications right now. Paste a job link here or on the Apply page to get started!",
            })

        company = active_app.company or "the job"
        role = f" ({active_app.role})" if active_app.role else ""
        status = active_app.status.value

        if status == "APPLYING":
            reply = f"⏳ Your application for **{company}{role}** is currently being processed by the automation worker."
        elif status == "QUEUED":
            reply = f"📋 Your application for **{company}{role}** is queued and will begin processing shortly."
        elif status == "NEEDS_ACTION":
            reply = f"⚠️ Your application for **{company}{role}** needs attention: {active_app.error_message or 'Action required'}."
        elif status == "APPLIED":
            reply = f"✅ Success! Your application for **{company}{role}** was successfully submitted!"
        elif status == "FAILED":
            reply = f"❌ Your application for **{company}{role}** encountered an issue: {active_app.error_message}."
        else:
            reply = f"Your latest application for **{company}** is in status **{status}**."

        return jsonify({
            "reply": reply,
            "application": active_app.to_dict(),
        })

    # Intent 2b: Retry
    if any(w in msg_lower for w in ["retry", "try again", "re-apply", "reapply"]):
        retryable_app = Application.query.filter(
            Application.user_id == current_user.id,
            Application.status.in_([ApplicationStatus.FAILED, ApplicationStatus.NEEDS_ACTION])
        ).order_by(Application.updated_at.desc()).first()

        if retryable_app:
            if (retryable_app.retry_count or 0) >= 3:
                return jsonify({
                    "reply": f"⚠️ Maximum retry limit (3) reached for **{retryable_app.company or 'the job'}**.",
                })

            retryable_app.status = ApplicationStatus.QUEUED
            retryable_app.error_message = None
            retryable_app.action_details_json = None
            db.session.commit()

            from app.worker.tasks import execute_application_pipeline
            thread = threading.Thread(
                target=execute_application_pipeline,
                args=[retryable_app.id],
                daemon=True,
            )
            thread.start()

            return jsonify({
                "reply": f"🔄 Retrying your application for **{retryable_app.company or 'the job'}** right now! I'll monitor progress and let you know if any action is needed.",
                "application": retryable_app.to_dict(),
            })
        else:
            return jsonify({
                "reply": "No recently failed application found to retry. Paste a new job link to get started!",
            })

    # Intent 3: Help / Capabilities
    if any(w in msg_lower for w in ["help", "what can you do", "features", "how do you work", "hi", "hello", "hey"]):
        name = current_user.full_name or "there"
        return jsonify({
            "reply": f"Hi {name}! 👋 I'm your **AutoApply AI Co-Pilot**.\n\nHere is what I can do for you:\n• **1-Click Apply**: Paste any job URL here and I'll start the application for you.\n• **Fill Missing Questions**: If an employer asks questions not in your profile, I'll ask you here and remember your answers.\n• **Assist with Verification**: If a CAPTCHA, login, or OTP appears, I'll pause and guide you with direct links to solve it and resume.",
        })

    # Intent 4: Profile / Completeness
    if any(w in msg_lower for w in ["profile", "complete", "completeness", "resume"]):
        from app.services.smart_resume_parser import compute_profile_completeness
        completeness = compute_profile_completeness(current_user, current_user.profile)
        pct = completeness.get("percent", 0)
        if completeness.get("is_complete"):
            return jsonify({
                "reply": f"Your profile is **100% complete**! 🎉 Automated 1-click apply is fully enabled for all job portals.",
            })
        missing = [m.replace("_", " ").title() for m in completeness.get("missing_fields", [])]
        return jsonify({
            "reply": f"Your profile is **{pct}% complete**. Missing required fields: **{', '.join(missing)}**. You can update them in the [Profile page](#/profile)!",
        })

    # Fallback response
    return jsonify({
        "reply": f"I'm here to help with your job applications! You can paste a job link directly here to apply, ask for the status of your applications, or answer any pending questions.",
    })
