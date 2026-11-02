"""
Resume Blueprint — /api/resume
Handles resume uploads (PDF/DOCX), smart parsing with Gemini,
and profile pre-filling.
"""

import os
import uuid
import logging
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from app import db
from app.models.profile import Profile
from app.models.resume import Resume
from app.utils.auth import token_required
from app.services.smart_resume_parser import (
    MAX_RESUME_SIZE,
    ALLOWED_EXTENSIONS,
    extract_text_from_file,
    parse_resume_with_gemini,
    compute_profile_completeness,
    compute_profile_diff,
    safe_apply_parsed_to_profile,
)

logger = logging.getLogger(__name__)

resume_bp = Blueprint("resume", __name__)


# ---------------------------------------------------------------------------
# POST /api/resume/upload
# ---------------------------------------------------------------------------
@resume_bp.route("/upload", methods=["POST"])
@token_required
def upload_resume(current_user):
    """
    Upload and parse resume file (PDF or DOCX, max 5MB).
    Returns {parsed, missing_fields, percent, is_complete, diff, resume}.
    """
    if "resume" not in request.files and "file" not in request.files:
        return jsonify({"error": "No resume file uploaded. Use field name 'resume'"}), 400

    file = request.files.get("resume") or request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Empty file provided"}), 400

    original_filename = secure_filename(file.filename) or "resume.pdf"
    ext = os.path.splitext(original_filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"Invalid file format: '{ext}'. Only PDF and DOCX documents are accepted."
        }), 415

    # Check file size (max 5 MB)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_RESUME_SIZE:
        return jsonify({
            "error": f"File exceeds maximum allowed size of 5 MB ({round(file_size / (1024 * 1024), 2)} MB provided)."
        }), 413

    # Storage paths
    resume_folder = current_app.config.get("RESUME_FOLDER", "uploads/resumes")
    os.makedirs(resume_folder, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.abspath(os.path.join(resume_folder, stored_filename))

    try:
        file.save(file_path)
    except Exception as exc:
        logger.error("Failed to save resume file to disk: %s", exc)
        return jsonify({"error": "Could not save resume file to disk", "detail": str(exc)}), 500

    # Ensure Profile exists for user
    profile = current_user.profile
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)
        db.session.flush()

    # Step 1: Extract text (PDF/DOCX/OCR)
    raw_text = ""
    parse_error = None
    try:
        raw_text = extract_text_from_file(file_path)
    except Exception as exc:
        parse_error = str(exc)
        logger.error("Text extraction failed for %s: %s", original_filename, exc)

    # Step 2: Send text to Gemini API with strict schema & validation
    parsed_data = {}
    try:
        parsed_data = parse_resume_with_gemini(raw_text)
    except Exception as exc:
        parse_error = str(exc)
        logger.error("AI parsing failed: %s", exc)

    # Step 3: Compute diff against current profile
    diff = compute_profile_diff(current_user, profile, parsed_data)

    # Step 4: Safely apply parsed fields into user & profile without overwriting existing data
    force_overwrite = request.form.get("force_overwrite", "false").lower() == "true"
    try:
        safe_apply_parsed_to_profile(current_user, profile, parsed_data, force_overwrite=force_overwrite)
    except Exception as exc:
        logger.error("Error applying parsed fields to profile: %s", exc)

    # Step 5: Save Resume DB record (do not store raw text longer than needed)
    try:
        existing_count = Resume.query.filter_by(user_id=current_user.id).count()
        resume_record = Resume(
            user_id=current_user.id,
            filename=stored_filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            parsed_text=None,  # Do not persist raw resume text longer than needed
            parsed_data=parsed_data,
            is_primary=(existing_count == 0),
        )
        db.session.add(resume_record)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Error persisting Resume record: %s", exc)
        resume_record = None

    # Step 6: Compute profile completeness and missing fields
    completeness = compute_profile_completeness(current_user, profile)

    return jsonify({
        "message": "Resume uploaded and processed successfully",
        "parsed": parsed_data,
        "missing_fields": completeness["missing_fields"],
        "percent": completeness["percent"],
        "is_complete": completeness["is_complete"],
        "diff": diff,
        "parse_error": parse_error,
        "resume": resume_record.to_dict() if resume_record else {
            "original_filename": original_filename,
            "file_size": file_size,
        },
    }), 201

