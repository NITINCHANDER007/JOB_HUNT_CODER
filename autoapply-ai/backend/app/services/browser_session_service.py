"""
AutoApply AI - Browser Session and LinkedIn Authentication Service.

Manages dedicated persistent Chrome profiles, manual LinkedIn login flow,
session state preservation (storage_state.json & cookies), session verification,
and Playwright persistent context creation for automation.
"""

import os
import json
import time
import shutil
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any
from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# In-memory tracking of active interactive login sessions
_active_interactive_sessions: Dict[str, Dict[str, Any]] = {}


def get_browser_profiles_base_dir() -> str:
    """Return the absolute path to the browser profiles root directory."""
    if has_app_context():
        configured = current_app.config.get("BROWSER_PROFILE_DIR", "browser_profiles")
    else:
        configured = os.getenv("BROWSER_PROFILE_DIR", "browser_profiles")

    if not os.path.isabs(configured):
        # Resolve relative to backend folder
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        configured = os.path.join(backend_dir, configured)

    os.makedirs(configured, exist_ok=True)
    return configured


def get_user_profile_dir(user_id: Optional[str]) -> str:
    """Return the persistent Chrome user data directory path for a specific user."""
    safe_uid = "".join(c for c in str(user_id or "default") if c.isalnum() or c in ("-", "_"))
    base_dir = get_browser_profiles_base_dir()
    profile_dir = os.path.join(base_dir, f"user_{safe_uid}")
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


def get_storage_state_path(user_id: Optional[str]) -> str:
    """Return the path to storage_state.json inside the user's persistent profile."""
    profile_dir = get_user_profile_dir(user_id)
    return os.path.join(profile_dir, "storage_state.json")


def get_linkedin_session_status(user_id: Optional[str]) -> dict:
    """
    Inspect the stored cookies/session for a user to determine if LinkedIn
    is currently authenticated.

    Returns:
        dict: {
            "connected": bool,
            "status": str,
            "cookie_expires": str,
            "days_remaining": int,
            "user_name": str,
            "has_profile_dir": bool
        }
    """
    profile_dir = get_user_profile_dir(user_id)
    state_file = get_storage_state_path(user_id)

    if not os.path.exists(state_file):
        return {
            "connected": False,
            "status": "Not Connected",
            "message": "No saved LinkedIn session found. Please click 'Connect LinkedIn' to log in.",
            "has_profile_dir": os.path.exists(profile_dir),
        }

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        cookies = state.get("cookies", [])
        li_at_cookie = None
        for c in cookies:
            if c.get("name") == "li_at" and "linkedin.com" in c.get("domain", ""):
                li_at_cookie = c
                break

        if not li_at_cookie:
            return {
                "connected": False,
                "status": "Session Expired",
                "message": "LinkedIn authentication cookie (li_at) missing. Please re-authenticate.",
                "has_profile_dir": True,
            }

        # Check expiration
        expires = li_at_cookie.get("expires", -1)
        now_ts = datetime.now(timezone.utc).timestamp()
        if expires != -1 and expires < now_ts:
            return {
                "connected": False,
                "status": "Session Expired",
                "message": "LinkedIn session has expired. Please log in again.",
                "has_profile_dir": True,
            }

        days_remaining = None
        if expires != -1:
            days_remaining = max(0, int((expires - now_ts) / 86400))

        # Check for optional cached metadata
        meta_file = os.path.join(profile_dir, "session_meta.json")
        user_name = None
        linkedin_email = None
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                    user_name = meta.get("user_name")
                    linkedin_email = meta.get("email")
            except Exception:
                pass

        return {
            "connected": True,
            "status": "Authenticated",
            "message": "LinkedIn session is active and ready for Easy Apply applications.",
            "user_name": user_name or "LinkedIn User",
            "linkedin_email": linkedin_email,
            "days_remaining": days_remaining,
            "cookie_expires": datetime.fromtimestamp(expires, timezone.utc).isoformat() if expires != -1 else None,
            "has_profile_dir": True,
        }

    except Exception as e:
        logger.warning(f"Error checking LinkedIn session status: {e}")
        return {
            "connected": False,
            "status": "Error",
            "message": f"Could not parse LinkedIn session: {e}",
            "has_profile_dir": True,
        }


def launch_manual_linkedin_login(user_id: str, timeout_seconds: int = 300) -> dict:
    """
    Launch a visible (headed) Chromium browser session using the user's persistent profile.
    Navigates to https://www.linkedin.com/login and waits for the user to manually log in,
    complete 2FA/OTP/CAPTCHA. Once logged in, exports storage_state.json and saves session.
    """
    from playwright.sync_api import sync_playwright

    profile_dir = get_user_profile_dir(user_id)
    state_file = get_storage_state_path(user_id)
    session_id = f"{user_id}_{int(time.time())}"

    _active_interactive_sessions[user_id] = {
        "session_id": session_id,
        "status": "launching",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "start_ts": time.time(),
        "message": "Opening browser window for LinkedIn login...",
    }

    try:
        with sync_playwright() as pw:
            # Launch persistent context headed so user can interact
            context = pw.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={"width": 1280, "height": 850},
                user_agent=_DEFAULT_USER_AGENT,
                locale="en-US",
                timezone_id="America/New_York",
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            # Mask automation flags
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = context.new_page() if not context.pages else context.pages[0]
            _active_interactive_sessions[user_id]["status"] = "waiting_for_user"
            _active_interactive_sessions[user_id]["message"] = "Browser opened. Please log into your LinkedIn account."

            logger.info(f"Navigating to LinkedIn login in headed browser for user {user_id}")
            try:
                page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
            except Exception as nav_e:
                logger.warning(f"Initial navigation note: {nav_e}")

            # Polling loop: wait for user to sign in
            start_time = time.time()
            logged_in = False
            user_name_found = None

            while time.time() - start_time < timeout_seconds:
                try:
                    # Check if page context was closed by user
                    if not context.pages or page.is_closed():
                        break

                    current_url = page.url.lower()

                    # 1. URL signal: redirected to feed, user profile, jobs, or mynetwork
                    auth_url_tokens = ["linkedin.com/feed", "linkedin.com/in/", "linkedin.com/mynetwork", "linkedin.com/jobs"]
                    if any(tok in current_url for tok in auth_url_tokens):
                        logged_in = True
                        break

                    # 2. Check for li_at cookie
                    try:
                        cookies = context.cookies(["https://www.linkedin.com"])
                        for c in cookies:
                            if c.get("name") == "li_at" and c.get("value"):
                                logged_in = True
                                break
                    except Exception:
                        pass

                    if logged_in:
                        break

                    # 3. Check for in-page feed nav element
                    try:
                        if page.query_selector("nav.global-nav, .feed-identity-module, [data-view-name*='profile']"):
                            logged_in = True
                            break
                    except Exception:
                        pass

                    # 4. Status hints for checkpoints / 2FA
                    if "checkpoint" in current_url or "challenge" in current_url:
                        _active_interactive_sessions[user_id]["message"] = "Security verification or 2FA detected. Please complete the verification in the opened browser window."

                    time.sleep(1.5)
                except Exception as loop_e:
                    err_str = str(loop_e).lower()
                    if not context.pages or page.is_closed() or "target closed" in err_str or "browser has been closed" in err_str:
                        logger.info(f"Interactive browser loop closed: {loop_e}")
                        break
                    # Transient error like context destroyed during page navigation
                    logger.debug(f"Transient interactive loop error (navigation in progress): {loop_e}")
                    time.sleep(1.5)
                    continue

            if logged_in:
                # Wait briefly to let session cookies settle
                time.sleep(2.0)
                try:
                    # Attempt to extract user's profile name from header/avatar
                    name_el = page.query_selector(
                        ".global-nav__me-photo, .feed-identity-module__actor-meta, h1.text-heading-xlarge"
                    )
                    if name_el:
                        user_name_found = name_el.get_attribute("alt") or name_el.inner_text().strip()
                except Exception:
                    pass

                # Save storage state snapshot
                context.storage_state(path=state_file)

                # Save session metadata
                meta_file = os.path.join(profile_dir, "session_meta.json")
                try:
                    with open(meta_file, "w", encoding="utf-8") as mf:
                        json.dump({
                            "user_name": user_name_found,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }, mf, indent=2)
                except Exception:
                    pass

                _active_interactive_sessions[user_id]["status"] = "success"
                _active_interactive_sessions[user_id]["message"] = "LinkedIn login detected! Session is saved."

                # Gracefully close
                try:
                    context.close()
                except Exception:
                    pass

                return {
                    "success": True,
                    "connected": True,
                    "message": "LinkedIn logged in and persistent session saved successfully! You can now use Easy Apply.",
                    "user_name": user_name_found or "LinkedIn User",
                }
            else:
                try:
                    context.close()
                except Exception:
                    pass
                _active_interactive_sessions[user_id]["status"] = "timed_out"
                _active_interactive_sessions[user_id]["message"] = "Login timed out or window was closed before completing."
                return {
                    "success": False,
                    "connected": False,
                    "message": "LinkedIn login timed out or the browser was closed before completing authentication.",
                }

    except Exception as e:
        logger.error(f"Error during interactive LinkedIn login: {e}")
        _active_interactive_sessions[user_id] = {
            "status": "error",
            "message": str(e),
        }
        return {
            "success": False,
            "connected": False,
            "error": str(e),
            "message": f"Could not launch browser login: {e}",
        }


def verify_linkedin_session(user_id: str) -> dict:
    """
    Perform a live, non-destructive check against LinkedIn using the persistent profile
    to confirm whether the session is genuinely authenticated and active.
    """
    from playwright.sync_api import sync_playwright

    profile_dir = get_user_profile_dir(user_id)
    state_file = get_storage_state_path(user_id)

    if not os.path.exists(state_file):
        return {
            "valid": False,
            "connected": False,
            "message": "No saved LinkedIn session found.",
        }

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=True,
                viewport={"width": 1280, "height": 800},
                user_agent=_DEFAULT_USER_AGENT,
                locale="en-US",
                timezone_id="America/New_York",
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = context.new_page() if not context.pages else context.pages[0]
            page.set_default_timeout(20000)

            try:
                page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=20000)
                time.sleep(2.0)
            except Exception as nav_e:
                context.close()
                return {
                    "valid": False,
                    "connected": False,
                    "message": f"Network error during verification: {nav_e}",
                }

            current_url = page.url.lower()

            # Check if redirected to login / authwall / checkpoint
            if any(p in current_url for p in ["/login", "/authwall", "/checkpoint", "/uas/login"]):
                context.close()
                return {
                    "valid": False,
                    "connected": False,
                    "message": "LinkedIn redirected to sign-in page. Your session has expired or requires re-authentication.",
                }

            # Check for logged-in navigation bar or feed elements
            nav_el = page.query_selector("nav.global-nav, .feed-identity-module, #global-nav")
            is_valid = bool(nav_el or "linkedin.com/feed" in current_url)

            # Refresh storage state snapshot if valid
            if is_valid:
                context.storage_state(path=state_file)

            context.close()

            return {
                "valid": is_valid,
                "connected": is_valid,
                "message": "LinkedIn session verified and active!" if is_valid else "Could not verify active session on LinkedIn feed.",
            }

    except Exception as e:
        logger.warning(f"Error during live LinkedIn verification: {e}")
        return {
            "valid": False,
            "connected": False,
            "error": str(e),
            "message": f"Verification error: {e}",
        }


def disconnect_linkedin_session(user_id: str) -> dict:
    """
    Disconnect LinkedIn by clearing storage_state.json and stored session metadata.
    Does not delete other browser profile data if any.
    """
    state_file = get_storage_state_path(user_id)
    profile_dir = get_user_profile_dir(user_id)
    meta_file = os.path.join(profile_dir, "session_meta.json")

    cleared = []
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
            cleared.append("storage_state.json")
        except Exception:
            pass

    if os.path.exists(meta_file):
        try:
            os.remove(meta_file)
            cleared.append("session_meta.json")
        except Exception:
            pass

    return {
        "success": True,
        "message": "LinkedIn session disconnected successfully.",
        "cleared_files": cleared,
    }


def get_persistent_context(pw, user_id: Optional[str], headless: Optional[bool] = None, timeout_ms: int = 30000):
    """
    Helper to launch a persistent Chromium BrowserContext with the user's saved profile,
    cookies, anti-bot evasion settings, and realistic browser configuration.
    """
    profile_dir = get_user_profile_dir(user_id)

    if headless is None:
        if has_app_context():
            headless = current_app.config.get("PLAYWRIGHT_HEADLESS", False)
        else:
            headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"

    context = pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        viewport={"width": 1280, "height": 850},
        user_agent=_DEFAULT_USER_AGENT,
        locale="en-US",
        timezone_id="America/New_York",
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    context.set_default_timeout(timeout_ms)

    return context

