"""
Gmail OAuth2 service for detecting job application confirmation emails.
Uses Google API Python Client with read-only Gmail scope.
"""

import base64
import json
import os
import re
from typing import Optional

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app import db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

FERNET_KEY = os.environ.get("FERNET_KEY", Fernet.generate_key().decode())
_fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)


def is_gmail_configured() -> bool:
    """Return True if Google OAuth client ID and secret are present in environment."""
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    csec = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    return bool(cid and csec)


def get_google_redirect_uri() -> str:
    """Return the configured OAuth redirect URI (defaulting to current backend port 5050)."""
    return os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:5050/api/gmail/callback"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_flow() -> Flow:
    if not is_gmail_configured():
        raise ValueError(
            "Google OAuth credentials are not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
        )

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = get_google_redirect_uri()

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect_uri,
    )


def _encrypt_tokens(token_dict: dict) -> str:
    payload = json.dumps(token_dict).encode()
    return _fernet.encrypt(payload).decode()


def _decrypt_tokens(encrypted: str) -> dict:
    payload = _fernet.decrypt(encrypted.encode())
    return json.loads(payload)


def _creds_from_token_dict(token_dict: dict) -> Credentials:
    return Credentials(
        token=token_dict.get("token"),
        refresh_token=token_dict.get("refresh_token"),
        token_uri=token_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        scopes=GMAIL_SCOPES,
    )


# ---------------------------------------------------------------------------
# 1. Build OAuth2 Authorization URL
# ---------------------------------------------------------------------------

def get_gmail_auth_url(user_id: str) -> str:
    """
    Build and return a Google OAuth2 authorization URL.

    The *state* parameter carries a base64-encoded user_id so we can
    identify the user during the callback.
    """
    flow = _build_flow()
    state = base64.urlsafe_b64encode(str(user_id).encode()).decode()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


# ---------------------------------------------------------------------------
# 2. Handle OAuth Callback
# ---------------------------------------------------------------------------

def handle_gmail_callback(code: str, state: str) -> dict:
    """
    Exchange the authorization code for tokens, encrypt them, and persist
    them to the user record.

    Returns {"success": True, "user_id": <id>} or raises on error.
    """
    from app.models.user import User  # lazy import to avoid circular deps  # noqa: PLC0415

    # Decode user_id from state
    try:
        user_id = base64.urlsafe_b64decode(state.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Invalid state parameter: {exc}") from exc

    user = User.query.get(str(user_id))
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Exchange code for tokens
    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    token_dict = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes) if creds.scopes else GMAIL_SCOPES,
    }

    # Retrieve Gmail address
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    gmail_email = profile.get("emailAddress", "")

    # Persist encrypted token + email
    user.gmail_token_encrypted = _encrypt_tokens(token_dict)
    user.gmail_email = gmail_email
    user.gmail_connected = True
    db.session.commit()

    return {"success": True, "user_id": user_id, "email": gmail_email}


# ---------------------------------------------------------------------------
# 3. Sync Confirmation Emails
# ---------------------------------------------------------------------------

def sync_confirmation_emails(user_or_id) -> list:
    """
    Decrypt the user's Gmail tokens, search for job-application confirmation
    emails, attempt to match them against pending applications, and persist
    EmailToken records.

    Returns a list of newly found email token dicts.
    """
    from app.models.user import User  # noqa: PLC0415
    from app.models.application import Application, ApplicationStatus  # noqa: PLC0415

    # Attempt to import EmailToken; skip gracefully if model isn't defined yet
    try:
        from app.models.email_token import EmailToken  # noqa: PLC0415
    except ImportError:
        EmailToken = None

    if isinstance(user_or_id, User):
        user = user_or_id
        user_id = str(user.id)
    else:
        user_id = str(user_or_id)
        user = User.query.get(user_id)

    if not user or not user.gmail_token_encrypted:
        raise ValueError("Gmail not connected for this user")

    token_dict = _decrypt_tokens(user.gmail_token_encrypted)
    creds = _creds_from_token_dict(token_dict)

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # --- Search query ---
    query = (
        "subject:(application OR confirmation OR received OR \"thank you\") "
        "newer_than:7d"
    )
    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=50)
        .execute()
    )
    messages = results.get("messages", [])

    # Fetch pending application domains for matching
    pending_apps = (
        Application.query.filter(
            Application.user_id == user_id,
            Application.status.in_(
                [ApplicationStatus.QUEUED, ApplicationStatus.APPLYING, ApplicationStatus.APPLIED]
            ),
        )
        .all()
    )

    def _extract_domain(url: str) -> str:
        match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
        return match.group(1).lower() if match else ""

    app_domains = {_extract_domain(a.url): a for a in pending_apps if a.url}

    new_tokens: list = []

    for msg_ref in messages:
        msg_id = msg_ref["id"]

        # Skip if already processed
        if EmailToken and EmailToken.query.filter_by(gmail_message_id=msg_id).first():
            continue

        # Fetch full message
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        snippet = msg.get("snippet", "")

        # Decode body
        body = _decode_body(msg.get("payload", {}))
        confirmation_link = extract_confirmation_link(body)

        # Match sender domain to a pending application
        sender_domain_match = re.search(r"@([\w.-]+)", sender)
        sender_domain = sender_domain_match.group(1).lower() if sender_domain_match else ""
        matched_app = None
        for domain, app in app_domains.items():
            if domain and sender_domain and (domain in sender_domain or sender_domain in domain):
                matched_app = app
                break

        if EmailToken:
            token = EmailToken(
                user_id=user_id,
                gmail_message_id=msg_id,
                subject=subject,
                sender=sender,
                body_snippet=snippet,
                confirmation_link=confirmation_link,
                matched_company=matched_app.company if matched_app else None,
                application_id=matched_app.id if matched_app else None,
            )
            db.session.add(token)
            db.session.flush()

            if matched_app and not matched_app.confirmation_email_id:
                matched_app.confirmation_email_id = token.id

            new_tokens.append(token.to_dict())

    db.session.commit()
    return new_tokens

    db.session.commit()
    return new_tokens


# ---------------------------------------------------------------------------
# 4. Extract Confirmation Link
# ---------------------------------------------------------------------------

def extract_confirmation_link(email_body: str) -> Optional[str]:
    """
    Use regex to find URLs in the email body and return the most likely
    confirmation / tracking link.
    """
    if not email_body:
        return None

    url_pattern = re.compile(
        r'https?://[^\s\'"<>()]+',
        re.IGNORECASE,
    )
    urls = url_pattern.findall(email_body)

    # Keywords that suggest a confirmation / tracking link
    priority_keywords = [
        "confirm", "track", "application", "status", "view", "portal",
        "redirect", "token", "verify",
    ]

    scored: list[tuple[int, str]] = []
    for url in urls:
        url_lower = url.lower()
        score = sum(1 for kw in priority_keywords if kw in url_lower)
        scored.append((score, url))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


# ---------------------------------------------------------------------------
# Internal helper: decode Gmail message body
# ---------------------------------------------------------------------------

def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text or HTML body from a Gmail payload."""
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        mime = part.get("mimeType", "")
        if mime in ("text/plain", "text/html"):
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        # Recurse into nested parts
        nested = _decode_body(part)
        if nested:
            return nested

    return ""
