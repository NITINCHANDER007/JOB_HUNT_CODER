"""
Gemini AI service for field mapping, custom Q&A, and cover letter generation.
"""

import json
import logging
import os
import re
import time
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK initialisation
# ---------------------------------------------------------------------------

_API_KEY = os.getenv("GEMINI_API_KEY", "")
_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

if _API_KEY:
    genai.configure(api_key=_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not set – AI features will be unavailable.")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_model() -> genai.GenerativeModel:
    """Return a configured GenerativeModel instance."""
    return genai.GenerativeModel(
        model_name=_MODEL_NAME,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            top_p=0.95,
            max_output_tokens=4096,
        ),
    )


def _call_gemini_with_retry(
    prompt: str,
    max_retries: int = 4,
    base_delay: float = 2.0,
) -> str:
    """
    Call Gemini with exponential back-off on rate-limit / transient errors.
    Returns the raw text response.
    """
    model = _get_model()
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as exc:
            err_str = str(exc).lower()
            is_rate_limit = any(kw in err_str for kw in ("quota", "rate", "429", "resource_exhausted"))
            is_transient = any(kw in err_str for kw in ("503", "unavailable", "timeout", "deadline"))

            if (is_rate_limit or is_transient) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Gemini call failed (attempt %d/%d): %s – retrying in %.1fs",
                    attempt + 1, max_retries, exc, delay,
                )
                time.sleep(delay)
                last_exc = exc
            else:
                raise

    raise RuntimeError(f"Gemini call failed after {max_retries} retries") from last_exc


def _extract_json_from_text(text: str) -> Any:
    """
    Robustly parse JSON out of a Gemini response that may include markdown
    fences or surrounding prose.
    """
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Find the first { ... } block
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from Gemini response: {text[:500]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_fields_with_ai(
    form_fields: list,
    user_profile: dict,
    job_description: str,
    company: str,
    role: str,
) -> dict:
    """
    Use Gemini to map each form field to the correct value from user_profile.

    Parameters
    ----------
    form_fields   : list of dicts – each has keys: label, name, type, options, required
    user_profile  : dict with user's personal/professional info
    job_description: full JD text
    company       : company name
    role          : job title / role being applied to

    Returns
    -------
    dict  { "field_label_or_name": "value_to_enter", ... }
    """
    fields_json = json.dumps(form_fields, indent=2)
    profile_json = json.dumps(user_profile, indent=2)

    prompt = f"""
You are an expert job application assistant. Your task is to fill out a job application form
accurately using the applicant's profile data.

## Company
{company}

## Role
{role}

## Job Description
{job_description[:3000]}

## Applicant Profile
{profile_json}

## Form Fields to Fill
{fields_json}

## Instructions
1. For each form field, provide the exact value to enter based ONLY on the applicant's profile.
2. For custom open-ended questions (e.g. "Why do you want to work here?", "Tell us about yourself"),
   generate a concise, honest answer (2-4 sentences) grounded in the applicant's actual experience.
3. For EEO / diversity fields (gender, ethnicity, race, disability, veteran status):
   - Use the corresponding field in profile.eeo if present.
   - Otherwise use "Prefer not to answer" or the equivalent option available.
4. For salary / CTC / expected compensation fields, use profile.expected_ctc if present.
5. For notice period fields, use profile.notice_period if present.
6. For "years of experience" fields, calculate from profile.experience entries.
7. For select / radio / checkbox fields, pick the option from the provided list that best matches.
8. For file upload fields (resume), output the string "RESUME_FILE" as a placeholder.
9. NEVER invent facts, companies, degrees, or skills not present in the profile.
10. If a field cannot be answered from the profile, output an empty string "".

## Output Format
Return ONLY a valid JSON object with no markdown, no explanation, no surrounding text:
{{
  "field_label_or_name": "value_to_enter",
  ...
}}

Use the field's "label" as the key when available, otherwise use "name".
"""

    try:
        raw = _call_gemini_with_retry(prompt)
        mapping = _extract_json_from_text(raw)
        if isinstance(mapping, dict):
            logger.info("AI field mapping complete: %d fields mapped.", len(mapping))
            return mapping
    except Exception as exc:
        logger.warning("Gemini field mapping failed (%s), using rule-based mapping.", exc)

    return _heuristic_field_mapping(form_fields, user_profile)


def _heuristic_field_mapping(form_fields: list, user_profile: dict) -> dict:
    """Fallback rule-based field mapping when Gemini is unreachable."""
    mapping = {}
    full_name = user_profile.get("full_name", "")
    parts = full_name.split(" ", 1) if full_name else ["", ""]
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    for f in form_fields:
        label = (f.get("label") or f.get("name") or "").lower()
        key = f.get("label") or f.get("name") or ""
        if not key:
            continue

        if "first" in label and "name" in label:
            mapping[key] = first_name
        elif "last" in label and "name" in label:
            mapping[key] = last_name
        elif "full" in label or "name" in label:
            mapping[key] = full_name
        elif "email" in label:
            mapping[key] = user_profile.get("email", "")
        elif "phone" in label or "mobile" in label or "tel" in label:
            mapping[key] = user_profile.get("phone", "")
        elif "linkedin" in label:
            mapping[key] = user_profile.get("linkedin_url", "")
        elif "github" in label:
            mapping[key] = user_profile.get("github_url", "")
        elif "portfolio" in label or "website" in label:
            mapping[key] = user_profile.get("portfolio_url", "")
        elif "city" in label or "location" in label or "address" in label:
            mapping[key] = user_profile.get("location", "")
        elif "notice" in label:
            mapping[key] = user_profile.get("notice_period", "2 weeks")
        elif "salary" in label or "ctc" in label or "compensation" in label:
            mapping[key] = user_profile.get("expected_ctc", "")
        elif "resume" in label or "cv" in label:
            mapping[key] = "RESUME_FILE"
        elif "gender" in label:
            mapping[key] = user_profile.get("gender") or "Prefer not to answer"
        elif "veteran" in label:
            mapping[key] = user_profile.get("veteran_status") or "Prefer not to answer"
        elif "disability" in label:
            mapping[key] = user_profile.get("disability_status") or "Prefer not to answer"
        elif "authorized" in label or "sponsorship" in label:
            mapping[key] = "Yes" if "authorized" in label else "No"

    return mapping


def generate_cover_letter(
    user_profile: dict,
    job_description: str,
    company: str,
    role: str,
) -> str:
    """
    Generate a tailored 3-paragraph cover letter (300-400 words).

    Uses the applicant's real experience and skills; does not invent facts.
    """
    profile_json = json.dumps(user_profile, indent=2)

    prompt = f"""
You are a professional career coach and expert cover letter writer.
Write a compelling, personalized cover letter for the following job application.

## Target Role
{role} at {company}

## Job Description
{job_description[:3000]}

## Applicant Profile
{profile_json}

## Requirements
- Write EXACTLY 3 paragraphs.
- Total length: 300-400 words.
- Paragraph 1: Opening hook – express genuine interest in the role and company.
  Reference a specific aspect of the company's work if possible from context.
- Paragraph 2: Connect the applicant's most relevant experience (from profile.experience)
  and skills (from profile.skills) to the key requirements in the JD.
  Use concrete examples and quantifiable achievements where available in the profile.
- Paragraph 3: Forward-looking close – explain what the applicant can contribute,
  express enthusiasm for next steps, and thank the reader.
- Tone: professional yet personable; first-person; active voice.
- NEVER invent experience, skills, companies, or achievements not in the profile.
- Do NOT include placeholders like [Company Name] – use the actual company and role names.
- Do NOT include a header, salutation, or signature – just the three body paragraphs.

Return ONLY the cover letter text. No extra commentary.
"""

    try:
        cover_letter = _call_gemini_with_retry(prompt)
        cover_letter = re.sub(r"```[a-z]*\n?|```", "", cover_letter).strip()
        logger.info("Cover letter generated (%d chars).", len(cover_letter))
        return cover_letter
    except Exception as exc:
        logger.warning("Cover letter generation via Gemini failed (%s), using template.", exc)
        skills = ", ".join(user_profile.get("skills", [])[:5]) or "software engineering"
        name = user_profile.get("full_name", "Applicant")
        summary = user_profile.get("summary") or f"experienced professional specializing in {skills}"
        return (
            f"I am writing to express my strong enthusiasm for the {role} position at {company}. "
            f"With a proven background in {skills}, I am confident in my ability to deliver immediate value to your team.\n\n"
            f"Throughout my career, I have focused on building scalable, reliable software. As an {summary}, "
            f"my technical skill set directly aligns with the objectives of {company}.\n\n"
            f"I look forward to discussing how my experience and passion can contribute to {company}'s ongoing success. "
            f"Thank you for your time and consideration."
        )


def extract_job_info(page_text: str, page_url: str) -> dict:
    """
    Send job page text to Gemini and extract structured job information.

    Returns
    -------
    dict with keys:
      company_name, job_title, job_description, required_skills (list),
      location, employment_type, salary_range
    """
    # Truncate very long pages to avoid token limits
    truncated_text = page_text[:8000] if len(page_text) > 8000 else page_text

    prompt = f"""
You are a data extraction assistant. Extract structured information from the job posting below.

## Page URL
{page_url}

## Page Content
{truncated_text}

## Instructions
Extract the following fields from the page content:
- company_name: The hiring company's name
- job_title: The exact job title / role name
- job_description: A concise summary (200-300 words) of responsibilities and requirements
- required_skills: A JSON array of key skills explicitly mentioned (e.g. ["Python", "SQL", "AWS"])
- location: City/state/country or "Remote" or "Hybrid"
- employment_type: "Full-time", "Part-time", "Contract", "Internship", or "Unknown"
- salary_range: Salary or compensation range if mentioned, else empty string

Return ONLY a valid JSON object. No markdown, no explanation:
{{
  "company_name": "...",
  "job_title": "...",
  "job_description": "...",
  "required_skills": ["...", "..."],
  "location": "...",
  "employment_type": "...",
  "salary_range": "..."
}}
"""

    try:
        raw = _call_gemini_with_retry(prompt)
        info = _extract_json_from_text(raw)
        if not isinstance(info, dict):
            raise ValueError("Expected dict from extract_job_info")
        # Ensure required_skills is a list
        if not isinstance(info.get("required_skills"), list):
            info["required_skills"] = []
        logger.info(
            "Job info extracted: %s – %s",
            info.get("company_name", "?"),
            info.get("job_title", "?"),
        )
        return info
    except Exception as exc:
        logger.error("extract_job_info failed: %s", exc)
        return {
            "company_name": "",
            "job_title": "",
            "job_description": "",
            "required_skills": [],
            "location": "",
            "employment_type": "Unknown",
            "salary_range": "",
        }
