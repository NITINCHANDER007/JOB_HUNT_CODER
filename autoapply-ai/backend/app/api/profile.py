"""
Profile Blueprint — /api/profile
Handles user profile management and resume upload/parsing.
"""

import os
import uuid
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from app import db
from app.models.profile import Profile
from app.models.resume import Resume
from app.utils.auth import token_required
from app.services.resume_parser import parse_resume

profile_bp = Blueprint("profile", __name__)

# PDF magic bytes (first 4 bytes: %PDF)
PDF_MAGIC = b"%PDF"


def _is_pdf(file_storage) -> bool:
    """Return True if the uploaded file is a valid PDF."""
    filename = file_storage.filename or ""
    if not filename.lower().endswith(".pdf"):
        return False
    header = file_storage.read(4)
    file_storage.seek(0)  # rewind for later saving
    return header == PDF_MAGIC


# ---------------------------------------------------------------------------
# GET /api/profile/
# ---------------------------------------------------------------------------
@profile_bp.route("/", methods=["GET"])
@token_required
def get_profile(current_user):
    """Return the authenticated user's profile and all their resumes."""
    # Strict project email override
    if current_user.email and current_user.email.lower() == "nitinchandra834@gmail.com":
        current_user.email = "codernitin55@gmail.com"
        db.session.commit()

    profile = Profile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    if profile.experience:
        from app.services.smart_resume_parser import sanitize_experience_entries
        sanitized = sanitize_experience_entries(profile.experience)
        if sanitized != profile.experience:
            profile.experience = sanitized
            db.session.commit()

    resumes = (
        Resume.query.filter_by(user_id=current_user.id)
        .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
        .all()
    )

    return jsonify(
        {
            "profile": profile.to_dict(),
            "resumes": [r.to_dict() for r in resumes],
            "user": current_user.to_dict(),
        }
    )


# ---------------------------------------------------------------------------
# GET /api/profile/resumes
# ---------------------------------------------------------------------------
@profile_bp.route("/resumes", methods=["GET"])
@token_required
def list_resumes(current_user):
    """List all resumes for the user."""
    resumes = (
        Resume.query.filter_by(user_id=current_user.id)
        .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
        .all()
    )
    return jsonify({"resumes": [r.to_dict() for r in resumes]})


# ---------------------------------------------------------------------------
# GET /api/profile/completeness
# ---------------------------------------------------------------------------
@profile_bp.route("/completeness", methods=["GET"])
@token_required
def get_completeness(current_user):
    """Return profile completeness percentage and missing required fields."""
    from app.services.smart_resume_parser import compute_profile_completeness
    profile = Profile.query.filter_by(user_id=current_user.id).first()
    completeness = compute_profile_completeness(current_user, profile)
    return jsonify({
        "percent": completeness["percent"],
        "missing_fields": completeness["missing_fields"],
        "is_complete": completeness["is_complete"],
        "filled_fields": completeness["filled_fields"],
    })


# ---------------------------------------------------------------------------
# PUT /api/profile/complete
# ---------------------------------------------------------------------------
@profile_bp.route("/complete", methods=["PUT", "POST"])
@token_required
def complete_profile(current_user):
    """Save manual inputs to complete profile fields."""
    data = request.get_json(silent=True) or {}
    profile = Profile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)

    # Name & Email on User (with strict override of nitinchandra834@gmail.com)
    if "email" in data and data["email"]:
        new_email = str(data["email"]).strip().lower()
        if new_email == "nitinchandra834@gmail.com":
            new_email = "codernitin55@gmail.com"
        from app.models.user import User
        existing = User.query.filter_by(email=new_email).first()
        if not existing or existing.id == current_user.id:
            current_user.email = new_email
    elif current_user.email and current_user.email.lower() == "nitinchandra834@gmail.com":
        current_user.email = "codernitin55@gmail.com"

    if "name" in data or "full_name" in data:
        name_val = data.get("name") or data.get("full_name")
        if name_val:
            current_user.full_name = str(name_val).strip()

    # Map manual inputs
    field_mappings = {
        "phone": "phone",
        "location": "location",
        "notice_period": "notice_period",
        "expected_ctc": "expected_ctc",
        "work_authorization": "work_authorization",
        "current_title": "current_title",
        "remote_preference": "remote_preference",
        "summary": "summary",
        "linkedin": "linkedin_url",
        "linkedin_url": "linkedin_url",
        "github": "github_url",
        "github_url": "github_url",
        "portfolio": "portfolio_url",
        "portfolio_url": "portfolio_url",
    }
    for req_key, model_attr in field_mappings.items():
        if req_key in data and data[req_key] is not None:
            setattr(profile, model_attr, str(data[req_key]).strip())

    # Collections
    if "education" in data and isinstance(data["education"], list):
        profile.education = data["education"]
    if "skills" in data and isinstance(data["skills"], list):
        profile.skills = data["skills"]
    if "experience" in data and isinstance(data["experience"], list):
        from app.services.smart_resume_parser import sanitize_experience_entries
        profile.experience = sanitize_experience_entries(data["experience"])

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Failed to save profile completion", "detail": str(exc)}), 500

    from app.services.smart_resume_parser import compute_profile_completeness
    completeness = compute_profile_completeness(current_user, profile)

    return jsonify({
        "message": "Profile completion saved successfully",
        "percent": completeness["percent"],
        "missing_fields": completeness["missing_fields"],
        "is_complete": completeness["is_complete"],
        "profile": profile.to_dict(),
    })


# ---------------------------------------------------------------------------
# PUT /api/profile/
# ---------------------------------------------------------------------------
@profile_bp.route("/", methods=["PUT", "POST"])
@token_required
def update_profile(current_user):
    """Update the authenticated user's profile."""
    data = request.get_json(silent=True) or {}

    profile = Profile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)

    # String / Text fields
    string_fields = [
        "phone",
        "location",
        "linkedin_url",
        "github_url",
        "portfolio_url",
        "current_title",
        "notice_period",
        "expected_ctc",
        "current_ctc",
        "work_authorization",
        "remote_preference",
        "gender",
        "ethnicity",
        "veteran_status",
        "disability_status",
        "pronouns",
        "summary",
    ]
    for field in string_fields:
        if field in data:
            val = data[field]
            setattr(profile, field, str(val).strip() if val is not None else None)

    # Numeric fields
    if "years_of_experience" in data:
        try:
            val = data["years_of_experience"]
            profile.years_of_experience = int(val) if val is not None and str(val).strip() != "" else None
        except (TypeError, ValueError):
            pass

    # Boolean fields
    if "willing_to_relocate" in data:
        val = data["willing_to_relocate"]
        if isinstance(val, bool):
            profile.willing_to_relocate = val
        elif isinstance(val, str) and val.lower() in ("true", "false"):
            profile.willing_to_relocate = val.lower() == "true"
        elif val is None:
            profile.willing_to_relocate = None

    # JSON fields
    json_fields = ["education", "skills", "experience", "certifications", "languages"]
    for field in json_fields:
        if field in data:
            setattr(profile, field, data[field])

    # Allow updating full_name and email on User model (with strict override)
    if "email" in data and data["email"]:
        new_email = str(data["email"]).strip().lower()
        if new_email == "nitinchandra834@gmail.com":
            new_email = "codernitin55@gmail.com"
        from app.models.user import User
        existing = User.query.filter_by(email=new_email).first()
        if not existing or existing.id == current_user.id:
            current_user.email = new_email
    elif current_user.email and current_user.email.lower() == "nitinchandra834@gmail.com":
        current_user.email = "codernitin55@gmail.com"

    if "full_name" in data and data["full_name"]:
        current_user.full_name = str(data["full_name"]).strip()
    elif "name" in data and data["name"]:
        current_user.full_name = str(data["name"]).strip()

    if profile.experience:
        from app.services.smart_resume_parser import sanitize_experience_entries
        profile.experience = sanitize_experience_entries(profile.experience)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Could not update profile", "detail": str(exc)}), 500

    return jsonify({"message": "Profile updated", "profile": profile.to_dict()})


# ---------------------------------------------------------------------------
# POST /api/profile/resume
# ---------------------------------------------------------------------------
@profile_bp.route("/resume", methods=["POST"])
@token_required
def upload_resume(current_user):
    """
    Upload a PDF resume (multipart/form-data, field name: 'resume').
    Auto-parses resume text and structured info, and pre-populates profile.
    """
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded. Use field name 'resume'"}), 400

    file = request.files["resume"]
    if not file or file.filename == "":
        return jsonify({"error": "Empty file"}), 400

    if not _is_pdf(file):
        return jsonify({"error": "Only PDF files are accepted"}), 415

    # Storage paths
    resume_folder = current_app.config.get("RESUME_FOLDER", "uploads/resumes")
    os.makedirs(resume_folder, exist_ok=True)

    original_filename = secure_filename(file.filename) or "resume.pdf"
    stored_filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(resume_folder, stored_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except Exception as exc:
        return jsonify({"error": "Could not save file", "detail": str(exc)}), 500

    # Parse resume
    try:
        parsed = parse_resume(file_path)
    except Exception as exc:
        parsed = {"text": "", "error": str(exc)}

    # Save Resume record
    try:
        existing_count = Resume.query.filter_by(user_id=current_user.id).count()
        is_primary = (existing_count == 0)

        resume = Resume(
            user_id=current_user.id,
            filename=stored_filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            parsed_text=parsed.get("text", ""),
            parsed_data=parsed,
            is_primary=is_primary,
        )
        db.session.add(resume)

        # Auto-prefill user profile with parsed resume data
        profile = Profile.query.filter_by(user_id=current_user.id).first()
        if not profile:
            profile = Profile(user_id=current_user.id)
            db.session.add(profile)

        if parsed.get("skills"):
            existing_skills = set(profile.skills or [])
            existing_skills.update(parsed["skills"])
            profile.skills = list(existing_skills)

        if parsed.get("summary") and not profile.summary:
            profile.summary = parsed["summary"]
        if parsed.get("linkedin") and not profile.linkedin_url:
            profile.linkedin_url = parsed["linkedin"]
        if parsed.get("github") and not profile.github_url:
            profile.github_url = parsed["github"]
        if parsed.get("phone") and not profile.phone:
            profile.phone = parsed["phone"]
        if parsed.get("education") and not profile.education:
            profile.education = parsed["education"]
        if parsed.get("experience") and not profile.experience:
            profile.experience = parsed["experience"]

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
        return jsonify({"error": "Could not save resume record", "detail": str(exc)}), 500

    return (
        jsonify(
            {
                "message": "Resume uploaded and parsed successfully",
                "resume": resume.to_dict(),
                "profile": profile.to_dict(),
                "parsed": parsed,
            }
        ),
        201,
    )


# ---------------------------------------------------------------------------
# GET /api/profile/resume/<resume_id>
# ---------------------------------------------------------------------------
@profile_bp.route("/resume/<resume_id>", methods=["GET"])
@token_required
def get_resume(current_user, resume_id):
    """Return details for a single resume."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()
    if not resume:
        return jsonify({"error": "Resume not found"}), 404

    return jsonify({"resume": resume.to_dict()})


# ---------------------------------------------------------------------------
# DELETE /api/profile/resume/<resume_id>
# ---------------------------------------------------------------------------
@profile_bp.route("/resume/<resume_id>", methods=["DELETE"])
@token_required
def delete_resume(current_user, resume_id):
    """Delete a resume record and its stored file."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()
    if not resume:
        return jsonify({"error": "Resume not found"}), 404

    was_primary = resume.is_primary
    file_path = resume.file_path

    try:
        db.session.delete(resume)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Could not delete resume", "detail": str(exc)}), 500

    # Remove file from disk
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass

    # If deleted resume was primary, assign primary to the next most recent one
    if was_primary:
        remaining = (
            Resume.query.filter_by(user_id=current_user.id)
            .order_by(Resume.created_at.desc())
            .first()
        )
        if remaining:
            remaining.is_primary = True
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    return jsonify({"message": "Resume deleted successfully"})


# ---------------------------------------------------------------------------
# PUT/POST /api/profile/resume/<resume_id>/primary
# ---------------------------------------------------------------------------
@profile_bp.route("/resume/<resume_id>/primary", methods=["PUT", "POST"])
@token_required
def set_primary_resume(current_user, resume_id):
    """Set a resume as the primary one (clears primary flag on all others)."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()
    if not resume:
        return jsonify({"error": "Resume not found"}), 404

    try:
        Resume.query.filter_by(user_id=current_user.id, is_primary=True).update(
            {"is_primary": False}
        )
        resume.is_primary = True
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Could not update primary resume", "detail": str(exc)}), 500

    return jsonify(
        {"message": "Primary resume updated", "resume": resume.to_dict()}
    )
