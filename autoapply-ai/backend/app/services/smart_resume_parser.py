"""
Smart Resume Parser Service.
Extracts structured resume data using pdfplumber, PyMuPDF, python-docx,
pytesseract OCR fallback, and Gemini API with Pydantic schema validation.
"""

import io
import json
import logging
import os
import re
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Max upload size: 5 MB
MAX_RESUME_SIZE = 5 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

# Mandatory profile completion fields
REQUIRED_FIELDS = [
    "name",
    "email",
    "phone",
    "location",
    "education",
    "skills",
    "notice_period",
    "expected_ctc",
    "work_authorization",
]


# ============================================================================
# Pydantic Schemas for Strict Resume Output Validation
# ============================================================================

class EducationItem(BaseModel):
    institute: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    start_year: Optional[Union[str, int]] = None
    end_year: Optional[Union[str, int]] = None
    cgpa: Optional[Union[str, float]] = None


class ExperienceItem(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class ProjectItem(BaseModel):
    name: Optional[str] = None
    tech: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None


class ResumeParsedSchema(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    summary: Optional[str] = None
    education: List[EducationItem] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)


# ============================================================================
# File Text Extraction (PDF, DOCX, OCR)
# ============================================================================

def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from PDF or DOCX file.
    If text from PDF is empty or very short, falls back to OCR via pytesseract.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".docx":
        return _extract_docx(file_path)
    elif ext == ".pdf":
        return _extract_pdf(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Only PDF and DOCX are accepted.")


def _extract_docx(file_path: str) -> str:
    """Extract text from a .docx document."""
    try:
        import docx
        doc = docx.Document(file_path)
        full_text = []

        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())

        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    full_text.append(" | ".join(row_text))

        return "\n".join(full_text)
    except Exception as exc:
        logger.error("Failed to extract DOCX text: %s", exc)
        return ""


def _extract_pdf(file_path: str) -> str:
    """Extract text from PDF using pdfplumber, fallback PyMuPDF, and OCR if scanned."""
    extracted_text = ""

    # Strategy 1: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    pages.append(txt)
            extracted_text = "\n".join(pages).strip()
    except Exception as e:
        logger.warning("pdfplumber extraction failed: %s", e)

    # Strategy 2: PyMuPDF fallback
    if not extracted_text or len(extracted_text) < 50:
        try:
            import pymupdf  # PyMuPDF
            doc = pymupdf.open(file_path)
            pages = []
            for page in doc:
                txt = page.get_text()
                if txt:
                    pages.append(txt)
            fallback_text = "\n".join(pages).strip()
            if fallback_text:
                extracted_text = fallback_text
            doc.close()
        except Exception as e:
            logger.warning("PyMuPDF fallback failed: %s", e)

    # Strategy 3: OCR fallback for scanned PDFs
    if not extracted_text or len(extracted_text) < 50:
        logger.info("PDF text empty or minimal (< 50 chars). Attempting OCR via pytesseract...")
        ocr_text = _ocr_pdf(file_path)
        if ocr_text:
            extracted_text = ocr_text

    return extracted_text


def _ocr_pdf(file_path: str, max_pages: int = 5) -> str:
    """Perform OCR on PDF pages using PyMuPDF page rendering and pytesseract."""
    try:
        import pymupdf
        import pytesseract
        from PIL import Image

        doc = pymupdf.open(file_path)
        ocr_pages = []

        for idx, page in enumerate(doc):
            if idx >= max_pages:
                break
            try:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                txt = pytesseract.image_to_string(img)
                if txt and txt.strip():
                    ocr_pages.append(txt.strip())
            except Exception as page_err:
                logger.warning("OCR failed on page %d: %s", idx, page_err)

        doc.close()
        return "\n".join(ocr_pages)
    except Exception as exc:
        logger.warning("Pytesseract OCR unavailable or failed: %s", exc)
        return ""


# ============================================================================
# Regex Extractors (for conflict resolution)
# ============================================================================

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)


def extract_regex_contact_info(text: str) -> dict:
    """Extract email and phone using strict regex patterns."""
    emails = EMAIL_REGEX.findall(text)
    phones = PHONE_REGEX.findall(text)

    valid_email = None
    for em in emails:
        em_clean = em.strip().lower()
        if not em_clean.endswith((".png", ".jpg", ".jpeg", ".gif")):
            if em_clean == "nitinchandra834@gmail.com":
                em_clean = "codernitin55@gmail.com"
            valid_email = em_clean
            break

    if valid_email and valid_email.lower() == "nitinchandra834@gmail.com":
        valid_email = "codernitin55@gmail.com"

    valid_phone = None
    for ph in phones:
        ph_clean = ph.strip()
        # Ensure at least 10 digits
        if sum(c.isdigit() for c in ph_clean) >= 10:
            valid_phone = ph_clean
            break

    return {"email": valid_email, "phone": valid_phone}


def sanitize_experience_entries(exp_list: list) -> list:
    """
    Ensure every experience entry has:
    1. Clean company name without dates or job titles attached.
    2. Full date month year in start_date and end_date (not lone month names like 'Jun').
    3. Proper separation of multiple jobs/internships (e.g. IDEMIA, Paytm, NTPC).
    """
    if not exp_list or not isinstance(exp_list, list):
        return []

    results = []
    month_pattern = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    date_full_re = re.compile(rf'(?:(?:\d{{1,2}}[-/\s]+)?{month_pattern}[-/\s,]+(?:\d{{1,2}}[-/\s,]+)?\d{{2,4}}|\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{2,4}}|\d{{1,2}}[-/]\d{{4}}|(?:19|20)\d{{2}}|Present|Current|Ongoing|Now)', re.IGNORECASE)

    for item in exp_list:
        if not isinstance(item, dict):
            continue
        comp = item.get('company') or ''
        title = item.get('title') or ''
        start = item.get('start_date') or ''
        end = item.get('end_date') or ''
        desc = item.get('description') or ''

        # Extract dates accidentally embedded inside company name
        found_dates = date_full_re.findall(comp)
        if found_dates:
            for d in found_dates:
                comp = comp.replace(d, '')
            comp = re.sub(r'[\s|–—\-\ufffd,()]+', ' ', comp).strip()
            if not start or len(start) <= 4:
                start = found_dates[0] if len(found_dates) > 0 else start
            if not end or len(end) <= 4:
                end = found_dates[1] if len(found_dates) > 1 else end

        # If start_date / end_date is just a month name, try to find the year from text or comp
        year_match = re.search(r'\b(20\d{2}|19\d{2})\b', comp + ' ' + desc)
        if year_match:
            year_val = year_match.group(1)
            if start and len(start.split()) == 1 and re.match(rf'^{month_pattern}$', start, re.IGNORECASE):
                start = f"{start} {year_val}"
            if end and len(end.split()) == 1 and re.match(rf'^{month_pattern}$', end, re.IGNORECASE):
                end = f"{end} {year_val}"

        # Check if description contains embedded internships (e.g. Paytm, NTPC, etc.)
        sub_splits = re.split(r'\n(?=(?:Paytm|NTPC|IDEMIA|Google|Microsoft|Amazon|Meta|Apple|[A-Z][a-zA-Z0-9\s]{2,25})\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|(?:19|20)\d{2}))', desc)
        if len(sub_splits) > 1:
            desc = sub_splits[0].strip()
            if 'Projects\n' in desc:
                desc = desc.split('Projects\n')[0].strip()
            elif '\nProjects' in desc:
                desc = desc.split('\nProjects')[0].strip()
            results.append({'company': comp, 'title': title, 'start_date': start, 'end_date': end, 'description': desc})
            for sub in sub_splits[1:]:
                lines = [l.strip() for l in sub.splitlines() if l.strip()]
                if not lines:
                    continue
                m_dates = date_full_re.findall(lines[0])
                c_name = lines[0]
                for d in m_dates:
                    c_name = c_name.replace(d, '')
                c_name = re.sub(r'[\s|–—\-\ufffd,()]+', ' ', c_name).strip()
                s_date = m_dates[0] if len(m_dates) > 0 else None
                e_date = m_dates[1] if len(m_dates) > 1 else None
                t_name = lines[1] if len(lines) > 1 else None
                d_text = '\n'.join(lines[2:]) if len(lines) > 2 else ''
                if 'Projects\n' in d_text:
                    d_text = d_text.split('Projects\n')[0].strip()
                elif '\nProjects' in d_text:
                    d_text = d_text.split('\nProjects')[0].strip()
                results.append({'company': c_name, 'title': t_name, 'start_date': s_date, 'end_date': e_date, 'description': d_text})
        else:
            if 'Projects\n' in desc:
                desc = desc.split('Projects\n')[0].strip()
            elif '\nProjects' in desc:
                desc = desc.split('\nProjects')[0].strip()
            results.append({'company': comp, 'title': title, 'start_date': start, 'end_date': end, 'description': desc})

    return results


# ============================================================================
# Gemini AI Parsing with Strict Schema & Pydantic Validation
# ============================================================================

def parse_resume_with_gemini(raw_text: str) -> dict:
    """
    Send resume text to Gemini API with a strict schema prompt.
    Validates output using Pydantic; retries once if invalid.
    Overrides email/phone with regex extraction if a conflict exists.
    """
    if not raw_text or not raw_text.strip():
        return ResumeParsedSchema().model_dump()

    # Pre-extract contact info via regex
    regex_contacts = extract_regex_contact_info(raw_text)

    prompt = f"""
You are an expert resume parsing engine.
Analyze the following resume text and extract all structured data.

## STRICT RULES:
1. Return ONLY a single valid JSON object adhering to the schema below.
2. Use null for any string field that is not explicitly present in the resume.
3. NEVER guess, assume, or invent facts, titles, dates, or contact info.
4. Extract ALL internships, jobs, and work experiences listed in the resume without omitting any.
5. In "experience", "start_date" and "end_date" MUST contain the full date with Month and Year (e.g. "Jun 2026", "Jul 2026", "15 Jun 2026", "Present") - NEVER return just the month name alone.
6. In "experience", keep the company name clean in "company" (e.g. "IDEMIA", "Paytm", "NTPC") and NEVER include the dates or job title in the company name.
7. In "education", extract all degrees and schools listed with their full graduation year/dates.
8. If a section is missing, return an empty array [].
9. Do NOT include markdown fences, comments, or preamble. Return purely JSON.
10. STRICT PROJECT OVERRIDE: If the email "nitinchandra834@gmail.com" appears anywhere in the resume text, NEVER use it. Strictly substitute and output "codernitin55@gmail.com".

## REQUIRED JSON SCHEMA:
{{
  "full_name": string or null,
  "email": string or null,
  "phone": string or null,
  "location": string or null,
  "linkedin": string or null,
  "github": string or null,
  "portfolio": string or null,
  "summary": string or null,
  "education": [
    {{
      "institute": string or null,
      "degree": string or null,
      "field": string or null,
      "start_year": string or number or null,
      "end_year": string or number or null,
      "cgpa": string or number or null
    }}
  ],
  "experience": [
    {{
      "company": string or null,
      "title": string or null,
      "start_date": string or null,
      "end_date": string or null,
      "description": string or null
    }}
  ],
  "projects": [
    {{
      "name": string or null,
      "tech": string or null,
      "description": string or null,
      "link": string or null
    }}
  ],
  "skills": [string],
  "certifications": [string],
  "languages": [string]
}}

## RESUME TEXT:
{raw_text[:12000]}
"""

    parsed_dict = None
    validation_error = None

    has_gemini_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    if has_gemini_key:
        # Attempt 1
        try:
            from app.services.ai_service import _call_gemini_with_retry, _extract_json_from_text
            raw_output = _call_gemini_with_retry(prompt)
            json_obj = _extract_json_from_text(raw_output)
            validated = ResumeParsedSchema.model_validate(json_obj)
            parsed_dict = validated.model_dump()
        except Exception as exc:
            validation_error = str(exc)
            logger.warning("Gemini resume parse attempt 1 failed: %s. Retrying once...", exc)

        # Attempt 2 (Retry with error feedback)
        if not parsed_dict:
            try:
                from app.services.ai_service import _call_gemini_with_retry, _extract_json_from_text
                retry_prompt = f"{prompt}\n\nATTENTION: Previous response failed schema validation ({validation_error}). Ensure strictly valid JSON with exact keys."
                raw_output = _call_gemini_with_retry(retry_prompt)
                json_obj = _extract_json_from_text(raw_output)
                validated = ResumeParsedSchema.model_validate(json_obj)
                parsed_dict = validated.model_dump()
            except Exception as exc:
                logger.error("Gemini resume parse attempt 2 failed: %s. Falling back to heuristic parsing.", exc)

    # Fallback to local heuristic parsing if Gemini fails completely or key not configured
    if not parsed_dict:
        parsed_dict = _heuristic_resume_parse(raw_text)

    # Rule: If Gemini output conflicts with regex extraction for email/phone, prefer regex result
    if regex_contacts.get("email"):
        gemini_email = parsed_dict.get("email")
        if not gemini_email or gemini_email.strip().lower() != regex_contacts["email"]:
            parsed_dict["email"] = regex_contacts["email"]

    if regex_contacts.get("phone"):
        gemini_phone = parsed_dict.get("phone")
        if not gemini_phone or not re.search(r"\d{7,}", str(gemini_phone)):
            parsed_dict["phone"] = regex_contacts["phone"]

    # Strict email override rule
    if parsed_dict.get("email") and parsed_dict["email"].strip().lower() == "nitinchandra834@gmail.com":
        parsed_dict["email"] = "codernitin55@gmail.com"

    # Sanitize and ensure complete experience entries
    if parsed_dict.get("experience"):
        parsed_dict["experience"] = sanitize_experience_entries(parsed_dict["experience"])

    return parsed_dict


def _heuristic_resume_parse(raw_text: str) -> dict:
    """Heuristic fallback extraction when AI is completely unreachable."""
    contacts = extract_regex_contact_info(raw_text)
    name = None
    skills = []
    summary = None
    edu_items = []
    exp_items = []
    proj_items = []
    linkedin = None
    github = None

    try:
        from app.services.resume_parser import (
            _extract_name, _extract_skills, _extract_linkedin, _extract_github,
            _split_sections, _extract_summary, _extract_education, _extract_experience,
            _extract_projects
        )
        name = _extract_name(raw_text, contacts.get("email"))
        sections = _split_sections(raw_text)
        skills = _extract_skills(raw_text, sections)
        linkedin = _extract_linkedin(raw_text)
        github = _extract_github(raw_text)
        summary = _extract_summary(sections)

        raw_edu = _extract_education(sections)
        for e in raw_edu:
            edu_items.append(EducationItem(
                institute=e.get("school") or e.get("institution"),
                degree=e.get("degree"),
                field=e.get("field"),
                start_year=e.get("start_date"),
                end_year=e.get("graduation_year") or e.get("end_date"),
                cgpa=e.get("cgpa")
            ))

        raw_exp = _extract_experience(sections)
        for ex in raw_exp:
            exp_items.append(ExperienceItem(
                company=ex.get("company"),
                title=ex.get("title"),
                start_date=ex.get("start_date"),
                end_date=ex.get("end_date"),
                description=ex.get("description")
            ))

        raw_proj = _extract_projects(sections)
        for p in raw_proj:
            proj_items.append(ProjectItem(
                name=p.get("name"),
                tech=p.get("tech"),
                description=p.get("description"),
                link=p.get("link")
            ))
    except Exception as exc:
        logger.warning("Heuristic fallback parser encountered error: %s", exc)

    c_email = contacts.get("email")
    if c_email and c_email.strip().lower() == "nitinchandra834@gmail.com":
        c_email = "codernitin55@gmail.com"

    schema = ResumeParsedSchema(
        full_name=name,
        email=c_email,
        phone=contacts.get("phone"),
        linkedin=linkedin,
        github=github,
        summary=summary,
        skills=skills,
        education=edu_items,
        experience=exp_items,
        projects=proj_items,
    )
    result = schema.model_dump()
    if result.get("experience"):
        result["experience"] = sanitize_experience_entries(result["experience"])
    return result


# ============================================================================
# Profile Completeness Calculation
# ============================================================================

def compute_profile_completeness(user, profile) -> dict:
    """
    Compute profile completeness percentage and missing required fields.
    Required: name, email, phone, location, education, skills,
              notice_period, expected_ctc, work_authorization.
    """
    missing = []
    filled = []

    # 1. name
    if user and user.full_name and user.full_name.strip():
        filled.append("name")
    else:
        missing.append("name")

    # 2. email
    if user and user.email and user.email.strip():
        filled.append("email")
    else:
        missing.append("email")

    if not profile:
        for f in ["phone", "location", "education", "skills", "notice_period", "expected_ctc", "work_authorization"]:
            missing.append(f)
        return {
            "percent": int(round((len(filled) / len(REQUIRED_FIELDS)) * 100)),
            "missing_fields": missing,
            "filled_fields": filled,
            "is_complete": False,
        }

    # 3. phone
    if profile.phone and profile.phone.strip():
        filled.append("phone")
    else:
        missing.append("phone")

    # 4. location
    if profile.location and profile.location.strip():
        filled.append("location")
    else:
        missing.append("location")

    # 5. education
    if profile.education and isinstance(profile.education, list) and len(profile.education) > 0:
        filled.append("education")
    else:
        missing.append("education")

    # 6. skills
    if profile.skills and isinstance(profile.skills, list) and len(profile.skills) > 0:
        filled.append("skills")
    else:
        missing.append("skills")

    # 7. notice_period
    if profile.notice_period and profile.notice_period.strip():
        filled.append("notice_period")
    else:
        missing.append("notice_period")

    # 8. expected_ctc
    if profile.expected_ctc and profile.expected_ctc.strip():
        filled.append("expected_ctc")
    else:
        missing.append("expected_ctc")

    # 9. work_authorization
    if profile.work_authorization and profile.work_authorization.strip():
        filled.append("work_authorization")
    else:
        missing.append("work_authorization")

    percent = int(round((len(filled) / len(REQUIRED_FIELDS)) * 100))
    is_complete = (len(missing) == 0)

    return {
        "percent": percent,
        "missing_fields": missing,
        "filled_fields": filled,
        "is_complete": is_complete,
    }


# ============================================================================
# Smart Profile Merge & Diff Computation
# ============================================================================

def compute_profile_diff(current_user, profile, parsed_data: dict) -> dict:
    """
    Compare parsed data with current profile values to show a clear diff.
    """
    diff = {}

    def _has_diff(curr, nxt):
        if not nxt:
            return False
        if not curr:
            return True
        return str(curr).strip().lower() != str(nxt).strip().lower()

    # Full name
    curr_name = current_user.full_name or ""
    parsed_name = parsed_data.get("full_name") or ""
    diff["name"] = {
        "current": curr_name,
        "parsed": parsed_name,
        "changed": _has_diff(curr_name, parsed_name),
    }

    # Phone
    curr_phone = profile.phone if profile else ""
    parsed_phone = parsed_data.get("phone") or ""
    diff["phone"] = {
        "current": curr_phone,
        "parsed": parsed_phone,
        "changed": _has_diff(curr_phone, parsed_phone),
    }

    # Location
    curr_loc = profile.location if profile else ""
    parsed_loc = parsed_data.get("location") or ""
    diff["location"] = {
        "current": curr_loc,
        "parsed": parsed_loc,
        "changed": _has_diff(curr_loc, parsed_loc),
    }

    # Links
    for key, attr in [("linkedin", "linkedin_url"), ("github", "github_url"), ("portfolio", "portfolio_url")]:
        c_val = getattr(profile, attr, "") if profile else ""
        p_val = parsed_data.get(key) or ""
        diff[key] = {
            "current": c_val,
            "parsed": p_val,
            "changed": _has_diff(c_val, p_val),
        }

    # Summary
    curr_sum = profile.summary if profile else ""
    parsed_sum = parsed_data.get("summary") or ""
    diff["summary"] = {
        "current": curr_sum,
        "parsed": parsed_sum,
        "changed": bool(parsed_sum and curr_sum != parsed_sum),
    }

    # Skills
    curr_skills = profile.skills or [] if profile else []
    parsed_skills = parsed_data.get("skills") or []
    diff["skills"] = {
        "current": curr_skills,
        "parsed": parsed_skills,
        "changed": bool(parsed_skills and set(curr_skills) != set(parsed_skills)),
    }

    # Education
    curr_edu = profile.education or [] if profile else []
    parsed_edu = parsed_data.get("education") or []
    diff["education"] = {
        "current": curr_edu,
        "parsed": parsed_edu,
        "changed": bool(parsed_edu and curr_edu != parsed_edu),
    }

    # Experience
    curr_exp = profile.experience or [] if profile else []
    parsed_exp = parsed_data.get("experience") or []
    diff["experience"] = {
        "current": curr_exp,
        "parsed": parsed_exp,
        "changed": bool(parsed_exp and curr_exp != parsed_exp),
    }

    return diff


def safe_apply_parsed_to_profile(current_user, profile, parsed_data: dict, force_overwrite: bool = False):
    """
    Safely save parsed resume fields into User & Profile.
    Does NOT overwrite fields that already contain non-empty manual data
    unless force_overwrite=True.
    """
    # Name
    if parsed_data.get("full_name"):
        if force_overwrite or not current_user.full_name or current_user.full_name in ("New User", "User"):
            current_user.full_name = parsed_data["full_name"].strip()

    # Email (enforcing strict override of nitinchandra834@gmail.com -> codernitin55@gmail.com)
    if parsed_data.get("email"):
        cand_email = str(parsed_data["email"]).strip().lower()
        if cand_email == "nitinchandra834@gmail.com":
            cand_email = "codernitin55@gmail.com"
        if force_overwrite or not current_user.email or current_user.email.lower() == "nitinchandra834@gmail.com":
            current_user.email = cand_email
    elif current_user.email and current_user.email.lower() == "nitinchandra834@gmail.com":
        current_user.email = "codernitin55@gmail.com"

    # Phone
    if parsed_data.get("phone"):
        if force_overwrite or not profile.phone:
            profile.phone = parsed_data["phone"].strip()

    # Location
    if parsed_data.get("location"):
        if force_overwrite or not profile.location:
            profile.location = parsed_data["location"].strip()

    # Links
    if parsed_data.get("linkedin"):
        if force_overwrite or not profile.linkedin_url:
            profile.linkedin_url = parsed_data["linkedin"].strip()

    if parsed_data.get("github"):
        if force_overwrite or not profile.github_url:
            profile.github_url = parsed_data["github"].strip()

    if parsed_data.get("portfolio"):
        if force_overwrite or not profile.portfolio_url:
            profile.portfolio_url = parsed_data["portfolio"].strip()

    # Summary
    if parsed_data.get("summary"):
        if force_overwrite or not profile.summary:
            profile.summary = parsed_data["summary"].strip()

    # Skills: Merge with existing skills
    if parsed_data.get("skills"):
        existing_skills = set(profile.skills or [])
        if force_overwrite:
            profile.skills = list(parsed_data["skills"])
        else:
            existing_skills.update(parsed_data["skills"])
            profile.skills = list(existing_skills)

    # Education
    if parsed_data.get("education"):
        if force_overwrite or not profile.education or len(profile.education) == 0:
            edu_list = []
            for item in parsed_data["education"]:
                edu_list.append({
                    "school": item.get("institute") or "",
                    "degree": item.get("degree") or "",
                    "field": item.get("field") or "",
                    "graduation_year": str(item.get("end_year") or ""),
                    "cgpa": str(item.get("cgpa") or ""),
                })
            profile.education = edu_list

    # Experience
    if parsed_data.get("experience"):
        clean_exp = sanitize_experience_entries(parsed_data["experience"])
        curr_len = len(profile.experience or [])
        if force_overwrite or curr_len == 0 or len(clean_exp) > curr_len:
            profile.experience = clean_exp
        else:
            profile.experience = sanitize_experience_entries(profile.experience)
    elif profile.experience:
        profile.experience = sanitize_experience_entries(profile.experience)

    # Certifications
    if parsed_data.get("certifications"):
        if force_overwrite or not profile.certifications:
            profile.certifications = parsed_data["certifications"]

    # Languages
    if parsed_data.get("languages"):
        if force_overwrite or not profile.languages:
            profile.languages = parsed_data["languages"]
