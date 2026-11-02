"""
AutoApply AI - Application Pipeline Orchestrator.
Coordinates: page scraping → platform detection → AI field mapping
             → form filling → resume upload → submission → verification.
"""

import os
import re
import time
import random
import traceback
from datetime import datetime

from flask import current_app, has_app_context

from app import db
from app.models.application import Application, ApplicationStatus, ApplicationLog
from app.adapters.exceptions import (
    CaptchaDetectedError,
    LoginWallError,
    UnsupportedFormError,
    SubmissionFailedError,
    NavigationError,
    ExpiredJobError,
    MissingInformationError,
    ResumeUploadError,
    DuplicateApplicationError,
    ReviewApprovalRequiredError,
)


def _log(application_id: str, level: str, message: str, extra: dict = None):
    """Persist a log entry for the given application."""
    try:
        entry = ApplicationLog(
            application_id=application_id,
            level=level,
            message=message,
            extra_data=extra or {},
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass  # Never let logging crash the pipeline


def run_application_pipeline(application_id: str) -> dict:
    """
    Main pipeline: opens the job URL, fills and submits the application.

    Returns:
        dict with keys: success (bool), confirmation_url (str|None),
                        screenshot_path (str|None), error (str|None)

    Raises:
        CaptchaDetectedError / LoginWallError / UnsupportedFormError
        on non-retryable terminal failures (caller marks NEEDS_ACTION).
    """
    from playwright.sync_api import sync_playwright

    application = Application.query.get(application_id)
    if not application:
        raise ValueError(f"Application {application_id} not found in DB")

    user = application.user
    if not user:
        raise ValueError("Application has no associated user")

    # --- Load profile + resume ---
    profile = user.profile
    if not profile:
        raise ValueError("User has no profile set up")

    primary_resume = next(
        (r for r in user.resumes if r.is_primary),
        user.resumes[0] if user.resumes else None,
    )
    if not primary_resume:
        raise ValueError("User has no resume uploaded")

    from app.utils.validators import resolve_resume_path
    resume_path = resolve_resume_path(primary_resume.file_path)
    if not resume_path or not os.path.isfile(resume_path):
        raise ValueError(f"Resume file not found at {primary_resume.file_path or 'unspecified location'}")

    if primary_resume.file_path != resume_path:
        primary_resume.file_path = resume_path
        db.session.commit()

    profile_dict = profile.to_dict()
    profile_dict["full_name"] = user.full_name
    user_email = user.email or ""
    if "nitinchandra834@gmail.com" in user_email.lower():
        user_email = "codernitin55@gmail.com"
    profile_dict["email"] = user_email

    # Record resume used
    application.resume_used = getattr(primary_resume, "original_filename", None) or os.path.basename(resume_path)
    db.session.commit()

    _log(application_id, "INFO", "Pipeline started", {"url": application.url, "resume_used": application.resume_used})

    from app.services.browser_session_service import get_persistent_context
    if has_app_context():
        headless_pref = current_app.config.get("PLAYWRIGHT_HEADLESS", False)
    else:
        headless_pref = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
    timeout = int(os.getenv("PLAYWRIGHT_TIMEOUT", 30000))

    with sync_playwright() as pw:
        # Launch dedicated persistent browser profile (reusing authenticated LinkedIn sessions)
        context = get_persistent_context(pw, user_id=str(user.id), headless=headless_pref, timeout_ms=timeout)
        page = context.new_page() if not context.pages else context.pages[0]
        page.set_default_timeout(timeout)

        try:
            # --- 1. Navigate to job URL ---
            _log(application_id, "INFO", f"Navigating to {application.url}")
            try:
                page.goto(application.url, wait_until="domcontentloaded", timeout=timeout)
                try:
                    page.wait_for_load_state("load", timeout=3000)
                except Exception:
                    pass
            except Exception as nav_err:
                raise NavigationError(f"Could not load page: {nav_err}")

            # --- 2. Extract job information (Title, Company, Platform) EARLY ---
            page_html = ""
            page_text = ""
            page_title = ""
            for _ in range(3):
                try:
                    page_html = page.content()
                    page_text = page.inner_text("body")
                    page_title = (page.title() or "").strip()
                    break
                except Exception:
                    time.sleep(1.0)

            from app.adapters.base_adapter import detect_platform, BaseAdapter
            platform = detect_platform(application.url, page_html)
            _log(application_id, "INFO", f"Detected platform: {platform}")

            adapter = _get_adapter(platform, page, application_id)
            adapter.page = page
            adapter.application_url = application.url

            company = ""
            role = ""
            job_description = ""

            # Dedicated adapter DOM extraction (e.g. LinkedIn dedicated DOM)
            if hasattr(adapter, "extract_job_details"):
                try:
                    dom_details = adapter.extract_job_details() or {}
                    company = dom_details.get("company") or ""
                    role = dom_details.get("title") or ""
                    job_description = dom_details.get("description") or ""
                except Exception as ex:
                    _log(application_id, "WARNING", f"DOM job details extraction failed: {ex}")

            # If still missing company or role, extract via Gemini AI
            if not company or not role or not job_description:
                from app.services.ai_service import extract_job_info
                try:
                    job_info = extract_job_info(page_text[:8000], application.url)
                    company = company or job_info.get("company_name") or ""
                    role = role or job_info.get("job_title") or page_title
                    job_description = job_description or job_info.get("job_description") or page_text[:5000]
                except Exception as ai_err:
                    _log(application_id, "WARNING", f"AI job info extraction failed: {ai_err}")

            # Fallback regex on page_title (e.g. "Title at Company")
            if not company or not role:
                m = re.search(r"^(.*?)\s+at\s+(.*?)(?:\s+(?:in|·|•|-|\||\ufffd)|$)", page_title, re.I)
                if m:
                    role = role or m.group(1).strip()
                    company = company or m.group(2).strip()

            role = role or page_title or "Job Application"
            company = company or "Company"

            # Persist scraped info immediately so all subsequent actions and logs have exact details
            application.company = company
            application.role = role
            application.job_description = job_description or page_text[:5000]
            application.platform = platform
            db.session.commit()
            _log(application_id, "INFO", f"Identified job: '{role}' at '{company}'")

            # --- 3. Duplicate Application Check ---
            if company and role and company.lower() != "company":
                existing_applied = Application.query.filter(
                    Application.user_id == user.id,
                    Application.id != application_id,
                    Application.status == ApplicationStatus.APPLIED,
                    db.func.lower(Application.company) == company.strip().lower(),
                    db.func.lower(Application.role) == role.strip().lower(),
                ).first()
                if existing_applied:
                    _log(application_id, "WARNING", f"Duplicate application detected: Already applied to {company} - {role}")
                    raise DuplicateApplicationError(
                        f"Duplicate application: You have already applied for '{role}' at '{company}' (Application #{existing_applied.id[:8]})."
                    )

            # --- 4. Check for Expired Job / CAPTCHA / Login Wall / Unsupported Layout ---
            temp_adapter = BaseAdapter(page, application_id)

            if temp_adapter.detect_expired_job():
                _log(application_id, "WARNING", f"Job posting is closed or expired for {company} - {role}")
                raise ExpiredJobError(f"Job posting for '{role}' at '{company}' has closed or is no longer accepting applications.")

            if temp_adapter.detect_captcha():
                _log(application_id, "WARNING", f"CAPTCHA detected on page for {company}")
                application.action_details_json = {
                    "type": "captcha",
                    "company": company,
                    "role": role,
                    "message": "A CAPTCHA challenge was detected. Automation paused so you can solve it manually.",
                    "url": page.url,
                }
                db.session.commit()
                raise CaptchaDetectedError(
                    f"CAPTCHA / Bot detection challenge encountered. Automation paused: Please open the job link to solve the challenge manually, then click Retry."
                )

            if platform == "linkedin":
                adapter.check_session_authentication()
            elif temp_adapter.detect_login_wall():
                _log(application_id, "WARNING", f"Login wall detected for {company}")
                application.action_details_json = {
                    "type": "login",
                    "company": company,
                    "role": role,
                    "message": "Candidate sign-in or account registration is required to apply.",
                    "url": page.url,
                }
                db.session.commit()
                raise LoginWallError(
                    f"Login required: The employer requires an account to apply. Please sign in via the in-page verification view, then click Resume."
                )

            is_reg, reg_fields = temp_adapter.detect_registration_wall()
            if is_reg and reg_fields:
                _log(application_id, "WARNING", f"Candidate registration required for {company}")
                application.action_details_json = {
                    "type": "registration",
                    "company": company,
                    "role": role,
                    "missing_fields": reg_fields,
                    "url": page.url,
                }
                db.session.commit()
                raise LoginWallError(f"Candidate registration required: The employer requires creating an account. Please complete registration via the in-page verification view, then click Resume.")

            is_unsupported, layout_reason = temp_adapter.detect_unsupported_layout()
            if is_unsupported:
                _log(application_id, "WARNING", f"Unsupported layout: {layout_reason}")
                raise UnsupportedFormError(f"Unsupported form layout: {layout_reason}")

            # --- 5. Detect Job-Detail Page vs Application Form & Click Apply ---
            if temp_adapter.is_job_detail_page():
                _log(application_id, "INFO", "Detected job-detail page – searching for and clicking actual Apply button")
                page = temp_adapter.navigate_to_application_form()

                # If redirected to a new URL, update application record
                if page.url != application.url:
                    _log(application_id, "INFO", f"Redirected to application URL: {page.url}")
                    application.url = page.url
                    db.session.commit()

                # Re-check Expired / CAPTCHA / Login Wall on the newly loaded page
                temp_adapter.page = page

                if temp_adapter.detect_expired_job():
                    _log(application_id, "WARNING", "Job posting is closed or expired on application page")
                    raise ExpiredJobError("Job posting has closed or is no longer accepting applications.")

                if temp_adapter.detect_captcha():
                    _log(application_id, "WARNING", "CAPTCHA detected on application page")
                    application.action_details_json = {
                        "type": "captcha",
                        "company": company,
                        "role": role,
                        "message": "A CAPTCHA challenge was detected. Automation paused so you can solve it manually.",
                        "url": page.url,
                    }
                    db.session.commit()
                    raise CaptchaDetectedError(
                        f"CAPTCHA challenge encountered on application page ({page.url}). Automation paused: Please open the link to solve manually, then click Retry."
                    )

                if platform == "linkedin":
                    adapter.page = page
                    adapter.check_session_authentication()
                elif temp_adapter.detect_login_wall():
                    _log(application_id, "WARNING", f"Login wall detected on application page: {page.url}")
                    application.action_details_json = {
                        "type": "login",
                        "company": company,
                        "role": role,
                        "message": "Candidate sign-in or account registration is required to apply.",
                        "url": page.url,
                    }
                    db.session.commit()
                    raise LoginWallError(
                        f"Login required: The employer requires an account to apply. Please visit the application link ({page.url}), sign in, and click Retry."
                    )

                is_unsupported, layout_reason = temp_adapter.detect_unsupported_layout()
                if is_unsupported:
                    _log(application_id, "WARNING", f"Unsupported layout on application page: {layout_reason}")
                    raise UnsupportedFormError(f"Unsupported form layout: {layout_reason}")

                # Re-detect platform if it redirected to a known ATS (e.g. greenhouse/lever/ashby)
                new_html = page.content()
                new_platform = detect_platform(page.url, new_html)
                if new_platform != platform:
                    _log(application_id, "INFO", f"Platform updated after redirect: {new_platform}")
                    platform = new_platform
                    application.platform = platform
                    db.session.commit()

            # --- 6. Select platform adapter ---
            adapter = _get_adapter(platform, page, application_id)
            adapter.page = page
            adapter.application_url = application.url

            # --- 6. Extract form fields (handling dynamic loading & iframes) ---
            _log(application_id, "INFO", "Inspecting form fields and supported iframes")
            # Wait briefly for dynamic elements or iframe to render
            try:
                page.wait_for_selector("input, select, textarea, iframe", timeout=5000, state="attached")
            except Exception:
                pass

            try:
                form_fields = adapter.extract_form_fields()
                if not form_fields:
                    # Double-check if login wall or captcha appeared after wait
                    if platform == "linkedin":
                        adapter.check_session_authentication()
                    if temp_adapter.detect_login_wall():
                        raise LoginWallError(
                            f"Login required: The employer requires an account to apply. Please visit the application link ({page.url}), sign in, and click Retry."
                        )
                    if temp_adapter.detect_captcha():
                        raise CaptchaDetectedError(
                            f"CAPTCHA challenge encountered on application page ({page.url}). Automation paused: Please open the link to solve manually, then click Retry."
                        )
                    raise UnsupportedFormError("No form fields found on page")

                application.form_fields_json = [f for f in form_fields]
                db.session.commit()
                _log(application_id, "INFO", f"Found {len(form_fields)} form fields")
            except (LoginWallError, CaptchaDetectedError, UnsupportedFormError):
                raise
            except Exception as e:
                raise UnsupportedFormError(f"Form field extraction failed: {e}")

            # --- 7. AI field mapping ---
            _log(application_id, "INFO", "Sending fields to Gemini for mapping")
            from app.services.ai_service import map_fields_with_ai, generate_cover_letter
            try:
                field_mapping = map_fields_with_ai(
                    form_fields=form_fields,
                    user_profile=profile_dict,
                    job_description=job_description,
                    company=company,
                    role=role,
                )
                # Strict email override
                for k, v in list(field_mapping.items()):
                    if isinstance(v, str) and "nitinchandra834@gmail.com" in v.lower():
                        field_mapping[k] = "codernitin55@gmail.com"

                application.ai_mapping_json = field_mapping
                db.session.commit()
                _log(application_id, "INFO", f"AI mapped {len(field_mapping)} fields")
            except Exception as e:
                _log(application_id, "WARNING", f"AI mapping partial failure: {e}")
                field_mapping = {}

            # --- 7b. Check for Verification Prompts (SMS OTP, Email code) ---
            has_verif, verif_sig = temp_adapter.detect_verification_prompt()
            if has_verif:
                _log(application_id, "WARNING", f"Verification prompt detected: {verif_sig}")
                application.action_details_json = {
                    "type": "otp",
                    "company": company or "the company",
                    "role": role or "the role",
                    "message": f"Verification code or OTP prompt detected ({verif_sig}). Please enter the verification code or complete it on the portal.",
                    "url": page.url,
                }
                db.session.commit()
                raise MissingInformationError(
                    f"Verification required: Employer requires entering a verification code ({verif_sig}). Please complete verification on the portal and retry.",
                    missing_fields=[{"label": "Verification Code", "name": "verification_code", "required": True}],
                )

            # --- 7c. Check for Missing Required Information (Never submit incomplete) ---
            missing_required = []
            for f in form_fields:
                if f.get("required") and f.get("type") != "file":
                    lbl = f.get("label") or f.get("name") or ""
                    val = field_mapping.get(lbl)
                    if not val and f.get("name"):
                        val = field_mapping.get(f.get("name"))
                    if not val or not str(val).strip():
                        missing_required.append(f)

            if missing_required:
                missing_labels = [f.get("label") or f.get("name") for f in missing_required]
                _log(application_id, "WARNING", f"Missing required information for fields: {missing_labels}")

                # Format missing fields for chatbot interaction
                chatbot_fields = []
                for f in missing_required:
                    lbl = (f.get("label") or f.get("name") or "").strip()
                    key = f.get("name") or f.get("label") or lbl
                    ftype = (f.get("type") or "text").lower()
                    opts = [o["text"] if isinstance(o, dict) else str(o) for o in (f.get("options") or [])]

                    if ftype in ["checkbox", "radio"] and len(opts) <= 2:
                        q_type = "yes_no"
                    elif opts and len(opts) > 1:
                        q_type = "select"
                    elif "experience" in lbl.lower() or "years" in lbl.lower() or ftype == "number":
                        q_type = "number"
                    else:
                        q_type = "text"

                    chatbot_fields.append({
                        "key": key,
                        "label": lbl,
                        "type": q_type,
                        "options": opts,
                        "required": True,
                    })

                application.action_details_json = {
                    "type": "missing_info",
                    "company": company or "the company",
                    "role": role or "the role",
                    "missing_fields": chatbot_fields,
                    "url": application.url,
                }
                db.session.commit()

                raise MissingInformationError(
                    f"Missing required information: Answers needed for: {', '.join(missing_labels)}. Please update your profile or answer these questions to apply.",
                    missing_fields=missing_required,
                )

            # --- 8. Generate cover letter if needed ---
            has_cover_letter_field = any(
                "cover" in (f.get("label", "") + f.get("name", "")).lower()
                for f in form_fields
            )
            cover_letter = None
            if has_cover_letter_field:
                try:
                    cover_letter = generate_cover_letter(profile_dict, job_description, company, role)
                    _log(application_id, "INFO", "Cover letter generated")
                except Exception as e:
                    _log(application_id, "WARNING", f"Cover letter generation failed: {e}")

            # --- 9. Fill and submit form ---
            _log(application_id, "INFO", "Filling form fields")
            is_approved = bool((application.action_details_json or {}).get("approved"))
            if has_app_context():
                require_approval = current_app.config.get("REQUIRE_USER_APPROVAL", True)
            else:
                require_approval = os.getenv("REQUIRE_USER_APPROVAL", "true").lower() == "true"
            try:
                if platform == "linkedin":
                    result = adapter.fill_and_submit(
                        field_mapping=field_mapping,
                        resume_path=resume_path,
                        cover_letter=cover_letter,
                        require_approval=require_approval,
                        is_approved=is_approved,
                    )
                else:
                    result = adapter.fill_and_submit(
                        field_mapping=field_mapping,
                        resume_path=resume_path,
                        cover_letter=cover_letter,
                    )
            except (CaptchaDetectedError, LoginWallError, ResumeUploadError, UnsupportedFormError, MissingInformationError, ReviewApprovalRequiredError):
                raise
            except Exception as e:
                raise SubmissionFailedError(f"Form fill/submit failed: {e}")

            # --- 10. Verify success ---
            _log(application_id, "INFO", "Verifying submission confirmation")
            time.sleep(3.0)  # Wait for submission redirects / server response
            temp_adapter.page = page
            success, confirmation_url = temp_adapter.detect_success()
            if not success and result.get("confirmation_url"):
                # Adapter explicitly captured a confirmation receipt URL
                success = True
                confirmation_url = result.get("confirmation_url")

            # --- 11. Screenshot ---
            screenshot_folder = os.getenv("SCREENSHOT_FOLDER", "uploads/screenshots")
            os.makedirs(screenshot_folder, exist_ok=True)
            screenshot_filename = f"{application_id}_{int(datetime.utcnow().timestamp())}.png"
            screenshot_path = os.path.join(screenshot_folder, screenshot_filename)
            try:
                page.screenshot(path=screenshot_path, full_page=False)
                _log(application_id, "INFO", f"Screenshot saved: {screenshot_filename}")
            except Exception as ss_err:
                _log(application_id, "WARNING", f"Screenshot failed: {ss_err}")
                screenshot_path = None

            # --- 12. Update application record ---
            application.screenshot_path = screenshot_path
            application.screenshot_url = f"/api/applications/{application_id}/screenshot"
            if confirmation_url:
                application.confirmation_url = confirmation_url

            db.session.commit()

            if success:
                _log(application_id, "INFO", "Application submitted successfully and verified",
                     {"confirmation_url": confirmation_url})
                return {
                    "success": True,
                    "confirmation_url": confirmation_url,
                    "screenshot_path": screenshot_path,
                }
            else:
                err_detail = getattr(temp_adapter, "last_submission_error", None) or "No confirmation message or receipt URL detected after submit"
                _log(application_id, "WARNING", f"Submission unverified: {err_detail}")
                return {
                    "success": False,
                    "unverified": True,
                    "status": "SUBMITTED",
                    "confirmation_url": confirmation_url,
                    "screenshot_path": screenshot_path,
                    "error": err_detail,
                }

        except (CaptchaDetectedError, LoginWallError, UnsupportedFormError, ExpiredJobError,
                MissingInformationError, ResumeUploadError, DuplicateApplicationError,
                ReviewApprovalRequiredError):
            _take_debug_screenshot(page, application_id)
            raise

        except SubmissionFailedError:
            _take_debug_screenshot(page, application_id)
            raise

        except Exception as e:
            _log(application_id, "ERROR", f"Unexpected error: {e}",
                 {"traceback": traceback.format_exc()})
            _take_debug_screenshot(page, application_id)
            raise

        finally:
            try:
                context.close()
            except Exception:
                pass


def _get_adapter(platform: str, page, application_id: str):
    """Factory: return the correct adapter for the detected platform."""
    if platform == "linkedin":
        from app.adapters.linkedin_adapter import LinkedInAdapter
        return LinkedInAdapter(page, application_id)
    elif platform == "workday":
        from app.adapters.workday_adapter import WorkdayAdapter
        return WorkdayAdapter(page, application_id)
    elif platform == "bytedance":
        from app.adapters.bytedance_adapter import ByteDanceAdapter
        return ByteDanceAdapter(page, application_id)
    elif platform == "greenhouse":
        from app.adapters.greenhouse_adapter import GreenhouseAdapter
        return GreenhouseAdapter(page, application_id)
    elif platform == "lever":
        from app.adapters.lever_adapter import LeverAdapter
        return LeverAdapter(page, application_id)
    elif platform == "ashby":
        from app.adapters.ashby_adapter import AshbyAdapter
        return AshbyAdapter(page, application_id)
    elif platform == "workable":
        from app.adapters.workable_adapter import WorkableAdapter
        return WorkableAdapter(page, application_id)
    elif platform == "smartrecruiters":
        from app.adapters.smartrecruiters_adapter import SmartRecruitersAdapter
        return SmartRecruitersAdapter(page, application_id)
    else:
        from app.adapters.generic_adapter import GenericAdapter
        return GenericAdapter(page, application_id)


def _take_debug_screenshot(page, application_id: str):
    """Attempt to take a debug screenshot on error and associate with application record."""
    try:
        folder = os.getenv("SCREENSHOT_FOLDER", "uploads/screenshots")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{application_id}_error_{int(time.time())}.png")
        page.screenshot(path=path, full_page=False)
        app_rec = Application.query.get(application_id)
        if app_rec:
            app_rec.screenshot_path = path
            app_rec.screenshot_url = f"/api/applications/{application_id}/screenshot"
            db.session.commit()
    except Exception:
        pass

