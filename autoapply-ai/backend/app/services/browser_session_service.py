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


def find_chrome_executable() -> Optional[str]:
    """Find installed Google Chrome binary on host."""
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
    ]
    for p in chrome_paths:
        if p and os.path.isfile(p):
            return p
    return None


def is_running_in_docker() -> bool:
    """Detect whether backend is executing inside a Docker container."""
    return os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"


def find_free_port(start_port: int = 9222) -> int:
    """Find an available TCP port for Chrome remote debugging."""
    import socket
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def _get_chrome_launch_kwargs() -> dict:
    """
    Detect whether Google Chrome is installed on the host system to launch real Chrome,
    otherwise fallback to Playwright's bundled Chromium.
    """
    if find_chrome_executable():
        return {"channel": "chrome"}
    return {}


def cleanup_profile_locks(profile_dir: str):
    """
    Clean up any orphaned chrome/chromium processes locking the user-data-dir
    and remove leftover lockfile / SingletonLock to prevent ProcessSingleton errors.
    """
    import psutil

    abs_profile_dir = os.path.abspath(profile_dir).lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            name = (proc.info.get("name") or "").lower()
            if abs_profile_dir in cmdline and "chrome" in name:
                try:
                    proc.kill()
                    logger.info("Killed orphaned chrome process %s locking profile dir", proc.info.get("pid"))
                except Exception:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Give Windows OS a moment to release handles
    time.sleep(0.3)

    # Remove stale lock files
    for lock_name in ["lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(profile_dir, lock_name)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                logger.info("Removed stale lock file: %s", lock_path)
            except Exception as e:
                logger.warning("Could not remove lock file %s: %s", lock_path, e)



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


def launch_manual_linkedin_login(user_id: str, timeout_seconds: int = 300, ready_event=None) -> dict:
    """
    Launch a visible Google Chrome browser window on the user's desktop using
    their persistent Chrome profile directory.
    - If running on Windows directly: launches native Chrome via subprocess with CDP remote debugging,
      verifies actual process running and CDP responsiveness, then attaches Playwright.
    - If running inside Docker: calls the local Windows browser bridge on host.docker.internal,
      or returns clear actionable instructions.
    - Waits for manual LinkedIn login (2FA/OTP/CAPTCHA supported).
    - Detects login via li_at cookie and URL changes, saves storage_state.json and metadata.
    """
    import subprocess
    import urllib.request
    from playwright.sync_api import sync_playwright

    profile_dir = get_user_profile_dir(user_id)
    state_file = get_storage_state_path(user_id)
    session_id = f"{user_id}_{int(time.time())}"

    _active_interactive_sessions[user_id] = {
        "session_id": session_id,
        "status": "launching",
        "browser_verified": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "start_ts": time.time(),
        "message": "Preparing persistent profile and launching visible Chrome window...",
    }

    # 1. Clean up stale profile locks / orphaned processes
    try:
        cleanup_profile_locks(profile_dir)
    except Exception as lock_err:
        logger.warning("Note during profile lock cleanup: %s", lock_err)

    proc = None
    cdp_port = 9222
    cdp_url = None

    try:
        # Check if inside Docker
        if is_running_in_docker():
            logger.info("Backend detected running inside Docker container")
            bridge_hosts = ["host.docker.internal", "172.17.0.1", "localhost"]
            bridge_working = False
            for bh in bridge_hosts:
                try:
                    with urllib.request.urlopen(f"http://{bh}:9225/status", timeout=1.5) as resp:
                        if resp.status == 200:
                            bridge_working = True
                            # Launch through bridge
                            launch_req = urllib.request.Request(
                                f"http://{bh}:9225/launch",
                                data=json.dumps({"profile_dir": profile_dir, "url": "https://www.linkedin.com/login"}).encode("utf-8"),
                                headers={"Content-Type": "application/json"}
                            )
                            with urllib.request.urlopen(launch_req, timeout=10) as lresp:
                                ldata = json.loads(lresp.read().decode("utf-8"))
                                cdp_port = ldata.get("cdp_port", 9222)
                                cdp_url = f"http://{bh}:{cdp_port}"
                                break
                except Exception:
                    continue

            if not bridge_working or not cdp_url:
                err_msg = (
                    "Backend is running inside a Docker container without desktop display access. "
                    "To launch visible Chrome on your desktop, run 'start_windows_browser_bridge.bat' "
                    "on your Windows host, or run the backend natively using 'python autoapply-ai\\backend\\run.py'."
                )
                _active_interactive_sessions[user_id] = {
                    "session_id": session_id,
                    "status": "error",
                    "browser_verified": False,
                    "error": err_msg,
                    "message": err_msg,
                }
                if ready_event:
                    ready_event.set()
                return {"success": False, "connected": False, "error": err_msg, "message": err_msg}

        else:
            # Running natively on Windows
            chrome_exe = find_chrome_executable()
            if not chrome_exe:
                err_msg = (
                    "Google Chrome executable not found on Windows at standard installation locations. "
                    "Please install Google Chrome (https://www.google.com/chrome) to enable interactive Easy Apply."
                )
                _active_interactive_sessions[user_id] = {
                    "session_id": session_id,
                    "status": "error",
                    "browser_verified": False,
                    "error": err_msg,
                    "message": err_msg,
                }
                if ready_event:
                    ready_event.set()
                return {"success": False, "connected": False, "error": err_msg, "message": err_msg}

            cdp_port = find_free_port(9222)
            cdp_url = f"http://127.0.0.1:{cdp_port}"

            cmd = [
                chrome_exe,
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={cdp_port}",
                "--new-window",
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "https://www.linkedin.com/login"
            ]

            logger.info("Launching native Chrome on desktop: %s", " ".join(cmd))
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )

            # Verify that process started and CDP endpoint responds
            verified = False
            for _ in range(16):
                time.sleep(0.5)
                if proc.poll() is not None:
                    _, err_text = proc.communicate()
                    err_msg = f"Chrome process exited immediately (code {proc.returncode}): {err_text or 'Profile locked or incompatible flags'}"
                    _active_interactive_sessions[user_id] = {
                        "session_id": session_id,
                        "status": "error",
                        "browser_verified": False,
                        "error": err_msg,
                        "message": err_msg,
                    }
                    if ready_event:
                        ready_event.set()
                    return {"success": False, "connected": False, "error": err_msg, "message": err_msg}

                try:
                    with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1) as resp:
                        if resp.status == 200:
                            verified = True
                            break
                except Exception:
                    pass

            if not verified:
                err_msg = f"Chrome launched (PID {proc.pid}) but debugging port {cdp_port} did not respond within timeout."
                try:
                    proc.terminate()
                except Exception:
                    pass
                _active_interactive_sessions[user_id] = {
                    "session_id": session_id,
                    "status": "error",
                    "browser_verified": False,
                    "error": err_msg,
                    "message": err_msg,
                }
                if ready_event:
                    ready_event.set()
                return {"success": False, "connected": False, "error": err_msg, "message": err_msg}

        # BROWSER IS GENUINELY VERIFIED OPEN ON DESKTOP
        logger.info("Chrome desktop window verified open at CDP %s", cdp_url)
        _active_interactive_sessions[user_id]["status"] = "waiting_for_user"
        _active_interactive_sessions[user_id]["browser_verified"] = True
        pid_info = f" (PID {proc.pid})" if proc else ""
        _active_interactive_sessions[user_id]["message"] = f"Chrome browser window is open on your desktop{pid_info}! Please log into your LinkedIn account."
        if ready_event:
            ready_event.set()

        # Connect Playwright to the live Chrome session over CDP
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.bring_to_front()
            except Exception:
                pass

            start_time = time.time()
            logged_in = False
            user_name_found = None

            while time.time() - start_time < timeout_seconds:
                try:
                    if proc and proc.poll() is not None:
                        logger.info("Chrome process terminated by user.")
                        break
                    if not browser.is_connected() or not context.pages or page.is_closed():
                        logger.info("Browser window or tab closed by user.")
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

                    # Status hints for checkpoints / 2FA
                    if "checkpoint" in current_url or "challenge" in current_url:
                        _active_interactive_sessions[user_id]["message"] = "Security verification or 2FA detected. Please complete the verification in the opened Chrome window."
                    elif "checkpoint/lg/login-submit" in current_url:
                        _active_interactive_sessions[user_id]["message"] = "Submitting credentials... Please complete any 2FA challenge if prompted."

                    time.sleep(1.5)

                except Exception as loop_e:
                    err_str = str(loop_e).lower()
                    if "closed" in err_str or "target closed" in err_str:
                        break
                    time.sleep(1.5)

            # Check if login succeeded right before closing
            if not logged_in:
                try:
                    cookies = context.cookies(["https://www.linkedin.com"])
                    for c in cookies:
                        if c.get("name") == "li_at" and c.get("value"):
                            logged_in = True
                            break
                except Exception:
                    pass

            if logged_in:
                time.sleep(2.0)
                try:
                    name_el = page.query_selector(".global-nav__me-photo, .feed-identity-module__actor-meta, h1.text-heading-xlarge")
                    if name_el:
                        user_name_found = name_el.get_attribute("alt") or name_el.inner_text().strip()
                except Exception:
                    pass

                # Save storage state snapshot
                context.storage_state(path=state_file)

                # Save metadata
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

                try:
                    browser.close()
                except Exception:
                    pass
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

                return {
                    "success": True,
                    "connected": True,
                    "message": "LinkedIn logged in and persistent session saved successfully! You can now use Easy Apply.",
                    "user_name": user_name_found or "LinkedIn Member",
                }
            else:
                try:
                    browser.close()
                except Exception:
                    pass
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

                _active_interactive_sessions[user_id]["status"] = "timed_out"
                _active_interactive_sessions[user_id]["message"] = "Login timed out or window was closed before completing."
                return {
                    "success": False,
                    "connected": False,
                    "message": "LinkedIn login timed out or browser window was closed before completing authentication.",
                }

    except Exception as e:
        logger.error(f"Error during interactive LinkedIn login: {e}")
        _active_interactive_sessions[user_id] = {
            "session_id": session_id,
            "status": "error",
            "browser_verified": False,
            "error": str(e),
            "message": f"Could not launch Chrome: {e}",
        }
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        if ready_event:
            ready_event.set()
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
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=state_file,
                viewport={"width": 1280, "height": 800},
                user_agent=_DEFAULT_USER_AGENT,
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = context.new_page()
            try:
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            except Exception as nav_e:
                logger.warning("Navigation during verify: %s", nav_e)

            current_url = page.url.lower()

            # Check if redirected to login / authwall / checkpoint
            if any(p in current_url for p in ["/login", "/authwall", "/checkpoint", "/uas/login"]):
                browser.close()
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

            browser.close()

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

    # Clean stale locks
    try:
        cleanup_profile_locks(profile_dir)
    except Exception:
        pass

    if headless is None:
        if has_app_context():
            headless = current_app.config.get("PLAYWRIGHT_HEADLESS", False)
        else:
            headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"

    launch_kwargs = _get_chrome_launch_kwargs()
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
        **launch_kwargs
    )

    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    context.set_default_timeout(timeout_ms)

    return context

