"""
Input validation helpers.
"""

import re
from urllib.parse import urlparse


def is_valid_email(email: str) -> bool:
    """Return True if email is valid format."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def is_valid_url(url: str) -> bool:
    """Return True if URL is valid."""
    try:
        res = urlparse(url)
        return bool(res.scheme in ("http", "https") and res.netloc)
    except Exception:
        return False


def is_valid_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength.
    Returns (is_valid, error_message).
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    return True, ""


def sanitize_url(url: str) -> str:
    """Strip whitespace and ensure URL has a scheme."""
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def normalize_job_url(url: str) -> str:
    """
    Normalize a job application URL for accurate duplicate detection.
    Strips UTM parameters, referrer tracking tags, trailing slashes, and fragments.
    """
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

    sanitized = sanitize_url(url)
    try:
        parsed = urlparse(sanitized)
        # Filter tracking parameters
        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "source", "ref", "gh_src", "lever-origin", "lever-source", "mode",
            "fbclid", "gclid", "msclkid", "mc_eid", "trk", "trkinfo"
        }
        filtered_queries = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in tracking_keys and not k.lower().startswith("utm_")
        ]
        # Rebuild query
        new_query = urlencode(sorted(filtered_queries))
        # Strip trailing slash from path
        clean_path = parsed.path.rstrip("/")
        if not clean_path:
            clean_path = "/"

        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            new_query,
            "",  # Strip fragment
        ))
        return normalized
    except Exception:
        return sanitized.rstrip("/")


def resolve_resume_path(resume_path: str) -> str:
    """
    Resolve a resume file path across project and upload directories to an absolute path that exists.
    Returns the absolute path if found, or the original path.
    """
    import os

    if not resume_path:
        return ""
    if os.path.isabs(resume_path) and os.path.isfile(resume_path):
        return os.path.abspath(resume_path)

    basename = os.path.basename(resume_path)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root_dir = os.path.dirname(backend_dir)

    candidates = [
        resume_path,
        os.path.abspath(resume_path),
        os.path.join(os.getcwd(), resume_path),
        os.path.join(backend_dir, "uploads", "resumes", basename),
        os.path.join(root_dir, "uploads", "resumes", basename),
        os.path.join(os.getcwd(), "autoapply-ai", "backend", "uploads", "resumes", basename),
        os.path.join(os.getcwd(), "autoapply-ai", "uploads", "resumes", basename),
        os.path.join(os.getcwd(), "uploads", "resumes", basename),
    ]

    try:
        from flask import current_app, has_app_context
        if has_app_context() and "RESUME_FOLDER" in current_app.config:
            candidates.insert(0, os.path.join(current_app.config["RESUME_FOLDER"], basename))
    except Exception:
        pass

    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)

    return os.path.abspath(resume_path) if os.path.isabs(resume_path) else resume_path

