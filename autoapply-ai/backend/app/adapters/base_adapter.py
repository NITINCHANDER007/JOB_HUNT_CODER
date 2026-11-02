"""
Base adapter with common Playwright helpers and platform detection.
"""

import logging
import os
import random
import re
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-agent pool for rotation
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.6261.57 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
]

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform(url: str, page_html: str) -> str:
    """
    Identify the ATS platform from URL patterns and HTML signatures.

    Returns one of:
      "linkedin", "greenhouse", "lever", "ashby", "workday", "smartrecruiters", "bytedance", "workable", "generic"
    """
    url_lower = url.lower()
    html_lower = page_html.lower() if page_html else ""

    # LinkedIn Easy Apply & Job pages
    if (
        "linkedin.com/jobs" in url_lower
        or "linkedin.cn/jobs" in url_lower
        or "jobs-easy-apply-modal" in html_lower
        or "jobs-apply-button" in html_lower
        or "easy apply" in html_lower and "linkedin.com" in url_lower
    ):
        return "linkedin"

    # Greenhouse
    if (
        "greenhouse.io" in url_lower
        or "boards.greenhouse.io" in url_lower
        or 'data-gh-form' in html_lower
        or "grnh.se" in url_lower
        or "id=\"gh_" in html_lower
    ):
        return "greenhouse"

    # Lever
    if (
        "jobs.lever.co" in url_lower
        or "lever.co/api" in url_lower
        or "lever.co/apply" in url_lower
        or 'class="lever-' in html_lower
    ):
        return "lever"

    # Ashby
    if (
        "ashbyhq.com" in url_lower
        or "jobs.ashbyhq.com" in url_lower
        or 'data-ashby' in html_lower
        or "ashby-job-posting" in html_lower
    ):
        return "ashby"

    # Workday
    if (
        "myworkdayjobs.com" in url_lower
        or "myworkday.com" in url_lower
        or "workday.com" in url_lower
        or "data-automation-id" in html_lower and ("workday" in html_lower or "wd-" in html_lower)
    ):
        return "workday"

    # ByteDance
    if (
        "jobs.bytedance.com" in url_lower
        or "joinbytedance.com" in url_lower
        or "bytedance.feishu.cn" in url_lower
    ):
        return "bytedance"

    # Workable
    if (
        "workable.com" in url_lower
        or "apply.workable.com" in url_lower
        or "wkablt.com" in url_lower
        or 'data-ui="workable"' in html_lower
    ):
        return "workable"

    # SmartRecruiters
    if (
        "smartrecruiters.com" in url_lower
        or "jobs.smartrecruiters.com" in url_lower
        or 'data-smartrecruiters' in html_lower
        or "smartrecruiters" in html_lower
    ):
        return "smartrecruiters"

    return "generic"


# ---------------------------------------------------------------------------
# scrape_job_page
# ---------------------------------------------------------------------------

def scrape_job_page(url: str) -> dict:
    """
    Open the job URL with Playwright, extract raw HTML, detect platform,
    and call the AI service to parse structured job info.

    Returns
    -------
    dict:
      html, text, title, platform, company, role, job_description
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from app.services.ai_service import extract_job_info
    from app.adapters.exceptions import CaptchaDetectedError, LoginWallError

    nav_timeout = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))
    debug_screenshot_dir = os.getenv("SCREENSHOT_FOLDER", "/tmp/autoapply_screenshots")
    os.makedirs(debug_screenshot_dir, exist_ok=True)

    user_agent = random.choice(_USER_AGENTS)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Mask automation signals
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout)
            # Extra wait to let JS-heavy SPAs render
            page.wait_for_timeout(2500)

            temp = BaseAdapter(page, "scrape")
            if temp.detect_expired_job():
                from app.adapters.exceptions import ExpiredJobError
                raise ExpiredJobError("Job posting has closed or expired.")
            if temp.detect_captcha():
                from app.adapters.exceptions import CaptchaDetectedError
                raise CaptchaDetectedError("CAPTCHA challenge detected on job page.")
            if temp.detect_login_wall():
                from app.adapters.exceptions import LoginWallError
                raise LoginWallError("Login wall detected on job page.")

            html = page.content()
            title = page.title()
            text = page.inner_text("body")

            # Debug screenshot
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_url = re.sub(r"[^\w]", "_", url)[:80]
            screenshot_path = os.path.join(
                debug_screenshot_dir, f"scrape_{safe_url}_{ts}.png"
            )
            page.screenshot(path=screenshot_path, full_page=True)
            logger.info("Scrape screenshot saved: %s", screenshot_path)

            platform = detect_platform(url, html)

            # AI-powered structured extraction
            job_info = extract_job_info(text, url)

            return {
                "html": html,
                "text": text,
                "title": title,
                "platform": platform,
                "company": job_info.get("company_name", ""),
                "role": job_info.get("job_title", ""),
                "job_description": job_info.get("job_description", ""),
                "required_skills": job_info.get("required_skills", []),
                "location": job_info.get("location", ""),
                "employment_type": job_info.get("employment_type", ""),
                "screenshot_path": screenshot_path,
            }

        except PlaywrightTimeout as exc:
            logger.error("Navigation timeout scraping %s: %s", url, exc)
            raise
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# BaseAdapter
# ---------------------------------------------------------------------------

class BaseAdapter:
    """
    Abstract base class providing shared Playwright helpers for all ATS adapters.
    Concrete adapters must override extract_form_fields() and fill_and_submit().
    """

    # Selectors for common submit buttons
    _SUBMIT_SELECTORS = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Apply')",
        "button:has-text('Send Application')",
        "button:has-text('Submit Application')",
        "[data-testid='submit']",
        ".submit-btn",
        "#submit-app",
    ]

    def __init__(self, page, application_id: str):
        self.page = page
        self.application_id = application_id
        self.last_submission_error = None

    def get_active_frame(self):
        """
        Returns the Frame containing the application form.
        Checks page.main_frame first; if it has no form fields, inspects child iframes.
        """
        try:
            main_frame = self.page.main_frame
            # Check if main frame has form fields
            if main_frame.query_selector("input, select, textarea"):
                return main_frame

            # Check child frames
            for frame in self.page.frames:
                if frame == main_frame:
                    continue
                try:
                    if frame.query_selector("input, select, textarea"):
                        self.log("INFO", f"Detected application form inside iframe: {frame.url}")
                        return frame
                except Exception:
                    continue
        except Exception:
            pass
        return self.page.main_frame

    def is_job_detail_page(self) -> bool:
        """
        Check if the current page is a job description/detail page rather than an active application form.
        Returns True if an Apply CTA button exists and standard application form fields are absent.
        """
        try:
            # 1. Check if an application form already exists on the page (main frame or child frames)
            frames = [self.page.main_frame] + [f for f in self.page.frames if f != self.page.main_frame]
            for frame in frames:
                try:
                    # If there is a file input (resume upload), this is already an application form
                    if frame.query_selector("input[type='file']"):
                        return False

                    # Check for standard applicant inputs
                    applicant_selectors = [
                        "input[name*='first_name' i]", "input[name*='last_name' i]",
                        "input[name*='email' i]", "input[name*='phone' i]",
                        "input[id*='first_name' i]", "input[id*='last_name' i]",
                        "input[id*='email' i]", "input[id*='phone' i]",
                        "input[autocomplete='email']", "input[autocomplete='tel']",
                        "textarea[name*='summary' i]", "textarea[name*='cover' i]"
                    ]
                    vis_count = 0
                    for sel in applicant_selectors:
                        el = frame.query_selector(sel)
                        if el and el.is_visible():
                            vis_count += 1
                            if vis_count >= 2:
                                return False
                except Exception:
                    continue

            # 2. Check if an Apply CTA button/link is present
            apply_btn, _ = self.find_apply_button()
            return apply_btn is not None
        except Exception:
            return False

    def find_apply_button(self):
        """
        Locates the specific job application CTA button/link across any job portal.
        Uses prioritized heuristics to distinguish job apply CTAs from generic navigation menus.
        Returns: (element, href) or (None, None)
        """
        try:
            candidates = self.page.query_selector_all(
                "button, a, [role='button'], input[type='button'], input[type='submit']"
            )

            tier1 = []  # Specific phrase match: "apply to this job", "apply for this job", "apply now", etc.
            tier2 = []  # Direct application href: href containing /apply, /resume/, /application
            tier3 = []  # Apply attributes: [data-qa*='apply'], [data-testid*='apply'], etc.
            tier4 = []  # Generic text: "apply" (outside header/nav)

            specific_phrases = [
                "apply to this job",
                "apply for this job",
                "apply for this position",
                "apply to position",
                "apply now",
                "apply online",
                "start application",
                "submit application",
                "easy apply",
                "i'm interested",
                "apply here",
                "apply to role",
            ]

            for el in candidates:
                try:
                    if not el.is_visible():
                        continue

                    txt = (el.inner_text() or "").strip().lower()
                    aria_lbl = (el.get_attribute("aria-label") or "").strip().lower()
                    href = (el.get_attribute("href") or "").strip()
                    full_txt = f"{txt} {aria_lbl}".strip()

                    # Check if element is inside header / nav / footer menu
                    is_in_nav = el.evaluate("""
                        e => Boolean(e.closest('header, nav, .navbar, .site-header, .nav-menu, footer, .footer'))
                    """)

                    # Tier 1: Matches specific phrases
                    if any(phrase in full_txt for phrase in specific_phrases):
                        tier1.append((el, href, is_in_nav))
                        continue

                    # Tier 2: Link href points specifically to an application URL
                    if href:
                        href_lower = href.lower()
                        if any(sub in href_lower for sub in ["/apply", "/resume/", "/application/", "apply=true", "#apply", "/jobs/apply/"]):
                            tier2.append((el, href, is_in_nav))
                            continue

                    # Tier 3: Apply-specific testing / QA attributes
                    test_id = (el.get_attribute("data-testid") or el.get_attribute("data-qa") or el.get_attribute("id") or "").lower()
                    if any(t in test_id for t in ["apply", "job-apply", "btn-apply"]) and not is_in_nav:
                        tier3.append((el, href, is_in_nav))
                        continue

                    # Tier 4: Plain "apply" text outside header/nav
                    if full_txt == "apply" and not is_in_nav:
                        tier4.append((el, href, is_in_nav))
                        continue

                except Exception:
                    continue

            # Prefer elements outside nav/header
            for bucket in [tier1, tier2, tier3, tier4]:
                non_nav = [item for item in bucket if not item[2]]
                if non_nav:
                    return non_nav[0][0], non_nav[0][1]
                if bucket:
                    return bucket[0][0], bucket[0][1]

            return None, None
        except Exception:
            return None, None

    def navigate_to_application_form(self):
        """
        Finds and clicks the Apply button on a job-detail page, handles popups/redirects,
        and waits for the application page to load completely. Returns the active page.
        """
        btn, href = self.find_apply_button()
        if not btn:
            self.log("INFO", "No separate Apply CTA button detected; current page may already be the form.")
            return self.page

        initial_url = self.page.url
        self.log("INFO", f"Clicking Apply CTA button (initial URL: {initial_url}, href: {href})")

        new_page = None
        try:
            # Check if clicking spawns a new popup tab
            with self.page.context.expect_page(timeout=4000) as p_info:
                btn.click(timeout=5000)
            new_page = p_info.value
        except Exception:
            pass

        if new_page:
            active_page = new_page
            self.log("INFO", f"Apply CTA opened new browser page: {active_page.url}")
        else:
            active_page = self.page
            # Wait for in-page navigation or URL update
            try:
                active_page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass

            # If URL did not change and button has an explicit application href, navigate directly
            if href and href.startswith(("http://", "https://")) and active_page.url == initial_url:
                self.log("INFO", f"Click did not trigger navigation; navigating directly to CTA href: {href}")
                try:
                    active_page.goto(href, wait_until="domcontentloaded", timeout=30000)
                except Exception as nav_e:
                    self.log("WARNING", f"Direct navigation to CTA href failed: {nav_e}")

        # Wait for redirected application page to load and stabilize
        try:
            active_page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(2.5)  # Dynamic framework (React/Vue/Next) hydration delay

        self.page = active_page
        return active_page

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def log(self, level: str, message: str, extra: dict = None):
        """Persist a log entry to ApplicationLog; falls back to Python logger."""
        try:
            from app import db
            from app.models.application import ApplicationLog
            entry = ApplicationLog(
                application_id=self.application_id,
                level=level.upper(),
                message=message,
                extra_data=extra or {},
            )
            db.session.add(entry)
            db.session.commit()
        except Exception:
            pass  # Don't let logging failures break the pipeline

        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn("[%s] %s", self.application_id, message)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    def extract_form_fields(self) -> list:
        """
        Extract all form fields from the page.

        Returns list of dicts:
          {label, name, type, options (list), required (bool), selector}
        """
        raise NotImplementedError("Subclasses must implement extract_form_fields()")

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """Fill the form with the given mapping and submit it."""
        raise NotImplementedError("Subclasses must implement fill_and_submit()")

    # ------------------------------------------------------------------
    # Single-field filler
    # ------------------------------------------------------------------

    def fill_field(
        self,
        selector: str,
        field_type: str,
        value: str,
        options: list = None,
    ):
        """
        Fill a single form field based on its type with dynamic DOM stabilization.

        Parameters
        ----------
        selector   : CSS/XPath selector for the element
        field_type : "text", "email", "tel", "url", "number", "textarea",
                     "select", "radio", "checkbox", "file"
        value      : value to fill / select / check
        options    : list of option labels (for select/radio fields)
        """
        if not value:
            return

        target = self.get_active_frame()

        # Attempt to wait for element to be visible/interactive (dynamic forms)
        try:
            target.wait_for_selector(selector, state="visible", timeout=3000)
        except Exception:
            pass  # Fall back to immediate interaction if wait times out

        for attempt in (1, 2):
            try:
                field_type_norm = (field_type or "text").lower()

                if field_type_norm in ("text", "email", "tel", "url", "number", "search", "hidden"):
                    target.fill(selector, str(value))

                elif field_type_norm == "textarea":
                    target.fill(selector, str(value))

                elif field_type_norm == "select":
                    self._fill_select(selector, value, options)
                    # Allow dynamic cascading selects (e.g. Country -> State) to update
                    time.sleep(0.3)

                elif field_type_norm == "radio":
                    self._fill_radio(selector, value, options)

                elif field_type_norm == "checkbox":
                    truthy = str(value).lower() in ("true", "yes", "1", "on", "x")
                    element = target.query_selector(selector)
                    if element:
                        checked = element.is_checked()
                        if truthy and not checked:
                            element.click()
                        elif not truthy and checked:
                            element.click()

                elif field_type_norm == "file":
                    if os.path.isfile(str(value)):
                        target.set_input_files(selector, str(value))

                else:
                    target.fill(selector, str(value))

                return  # Success
            except Exception as exc:
                if attempt == 1:
                    time.sleep(0.5)
                    continue
                logger.warning(
                    "fill_field failed for selector=%s type=%s value=%s: %s",
                    selector, field_type, value, exc,
                )

    def _fill_select(self, selector: str, value: str, options: list = None):
        """Select the best matching <select> option."""
        try:
            # Try exact value / label match first
            self.page.select_option(selector, label=str(value))
            return
        except Exception:
            pass

        try:
            self.page.select_option(selector, value=str(value))
            return
        except Exception:
            pass

        # Fuzzy match against provided option list
        if options:
            value_lower = value.lower()
            best: Optional[str] = None
            best_score = 0
            for opt in options:
                opt_lower = str(opt).lower()
                if opt_lower == value_lower:
                    best = opt
                    best_score = 100
                    break
                # Simple overlap score
                score = sum(1 for word in value_lower.split() if word in opt_lower)
                if score > best_score:
                    best_score = score
                    best = opt
            if best and best_score > 0:
                try:
                    self.page.select_option(selector, label=str(best))
                    return
                except Exception:
                    pass

        logger.warning("Could not select option '%s' for %s", value, selector)

    def _fill_radio(self, selector: str, value: str, options: list = None):
        """Click the radio button whose label best matches value."""
        value_lower = value.lower()
        # Try locating all radio buttons near this selector's container
        try:
            clean_name = selector.lstrip("#")
            radios = self.page.query_selector_all(f"input[type='radio'][name='{clean_name}']")
            if not radios:
                radios = self.page.query_selector_all(selector)
            for radio in radios:
                radio_value = (radio.get_attribute("value") or "").lower()
                radio_label = ""
                radio_id = radio.get_attribute("id") or ""
                if radio_id:
                    label_el = self.page.query_selector(f"label[for='{radio_id}']")
                    if label_el:
                        radio_label = (label_el.inner_text() or "").lower()
                if radio_value == value_lower or radio_label == value_lower:
                    radio.click()
                    return
        except Exception as exc:
            logger.warning("_fill_radio failed: %s", exc)

    # ------------------------------------------------------------------
    # Resume upload
    # ------------------------------------------------------------------

    def upload_resume(self, resume_path: str) -> bool:
        """
        Find the file input on the page and upload the resume.
        Retries once on error, then raises ResumeUploadError if failure persists.
        """
        import time
        from app.adapters.exceptions import ResumeUploadError

        if not resume_path or not os.path.isfile(resume_path):
            raise ResumeUploadError(f"Resume file not found at path: {resume_path}")

        file_selectors = [
            "input[type='file']",
            "input[accept*='pdf']",
            "input[accept*='.doc']",
            "[data-testid*='resume']",
            "#resume",
            "#resume_file",
            "input[name*='resume']",
            "input[name*='cv']",
            "input[id*='cv']",
            "input[id*='resume']",
        ]

        last_error = None
        for attempt in (1, 2):
            try:
                for sel in file_selectors:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.set_input_files(sel, resume_path)
                        # Verify that the input element actually received the file
                        try:
                            attached = el.evaluate(
                                "e => Boolean(e.files && e.files.length > 0) || Boolean(e.value)"
                            )
                        except Exception:
                            attached = True  # Fallback if evaluation is blocked
                        if attached:
                            self.log("INFO", f"Resume successfully uploaded via selector '{sel}' (attempt {attempt})")
                            return True

                raise Exception("No matching visible file input accepted the resume file.")
            except Exception as exc:
                last_error = exc
                if attempt == 1:
                    self.log("WARNING", f"Resume upload attempt 1 failed: {exc}. Retrying once...")
                    time.sleep(1.5)
                else:
                    self.log("ERROR", f"Resume upload attempt 2 failed: {exc}")

        raise ResumeUploadError(f"Failed to upload resume after retry: {last_error}")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def click_submit(self):
        """Find and click the submit / apply button."""
        for sel in self._SUBMIT_SELECTORS:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.log("INFO", f"Clicked submit button: {sel}")
                    return
            except Exception:
                continue

        logger.warning("click_submit: no submit button found.")

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def detect_captcha(self) -> bool:
        """
        Check whether the current page shows a CAPTCHA challenge or bot verification.
        Accurately identifies visible challenges without false positives on background scripts.
        """
        # 1. Check for visible CAPTCHA iframes and DOM challenge containers
        captcha_selectors = [
            "iframe[src*='recaptcha']:not([aria-hidden='true'])",
            "iframe[src*='turnstile']",
            "iframe[src*='challenges.cloudflare']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='arkoselabs']",
            "#challenge-stage",
            "#challenge-running",
            ".cf-browser-verification",
            "#cf-please-wait",
            "#px-captcha",
            "[id*='datadome']",
            ".g-recaptcha:not([aria-hidden='true'])",
            ".h-captcha:not([aria-hidden='true'])",
            "[data-testid*='captcha']",
        ]
        for sel in captcha_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    return True
            except Exception:
                continue

        # 2. Check visible page text and title (not raw script contents)
        try:
            title_text = (self.page.title() or "").lower()
            body_text = (self.page.inner_text("body") or "").lower()
            visible_content = f"{title_text} {body_text}"
        except Exception:
            return False

        visible_challenge_signatures = [
            "are you a robot",
            "verify you are human",
            "press & hold",
            "complete the security check",
            "security challenge",
            "bot detection",
            "attention required! | cloudflare",
            "checking your browser before accessing",
            "unusual traffic from your computer",
            "verify that you are human",
            "just a moment...",
            "access denied - cloudflare",
        ]
        return any(sig in visible_content for sig in visible_challenge_signatures)

    def detect_login_wall(self) -> bool:
        """
        Check if the page is blocking access behind a login/auth wall.
        Handles actual login paths, password prompts, and auth barriers while
        avoiding false positives on normal job description pages.
        """
        try:
            import urllib.parse
            current_url = self.page.url.lower()
            parsed_path = urllib.parse.urlparse(current_url).path.lower()
            page_title = (self.page.title() or "").strip().lower()
            body_text = (self.page.inner_text("body") or "").lower()
        except Exception:
            return False

        # Exemption: If page has an active Easy Apply button or application form, it's not blocked
        try:
            if self.page.query_selector("button:has-text('Easy Apply'), button.jobs-apply-button, form.application-form"):
                return False
        except Exception:
            pass

        # Strict auth path matching
        auth_paths = ["/login", "/signin", "/sign-in", "/auth/login", "/account/login", "/session/new", "/uas/login", "/authwall", "/checkpoint"]
        if "/authwall" in current_url or "/checkpoint" in current_url:
            return True
        is_url_login = any(pat == parsed_path or parsed_path.endswith(pat) or f"{pat}/" in parsed_path for pat in auth_paths)
        is_title_login = any(t in page_title for t in ["sign in", "log in", "login", "signin"] if not "apply" in t)

        # Check for visible password input
        has_password_input = False
        try:
            pwd_el = self.page.query_selector("input[type='password']")
            if pwd_el and pwd_el.is_visible():
                has_password_input = True
        except Exception:
            pass

        # Check for visible login/sign-in button
        has_login_button = False
        try:
            for btn in self.page.query_selector_all("button, a, [role='button']"):
                txt = (btn.inner_text() or "").strip().lower()
                if txt in ["sign in", "log in", "login", "signin"]:
                    if btn.is_visible():
                        has_login_button = True
                        break
        except Exception:
            pass

        login_text_signatures = [
            "please sign in to continue",
            "sign in to your account",
            "log in to your account",
            "enter your email and password to sign in",
            "login required",
            "sign in with google",
            "sign in with linkedin",
            "already have an account? sign in",
            "please log in to view this job",
        ]
        has_login_signature = any(sig in body_text for sig in login_text_signatures)

        return bool(
            (is_url_login and (has_password_input or has_login_button))
            or (has_password_input and has_login_signature)
            or (has_password_input and is_title_login)
            or (is_url_login and has_login_signature)
        )

    def detect_registration_wall(self) -> tuple[bool, list]:
        """
        Check if the portal requires candidate account creation/registration.
        Returns: (is_registration_required, missing_registration_fields)
        """
        try:
            page_text = (self.page.title() + " " + (self.page.inner_text("body") or "")).lower()
            reg_signatures = [
                "create an account to apply",
                "create account to continue",
                "create your candidate account",
                "create a password",
                "register to apply",
                "new candidate registration",
            ]
            has_reg_sig = any(sig in page_text for sig in reg_signatures)

            has_create_btn = False
            for btn in self.page.query_selector_all("button, a, [role='button']"):
                txt = (btn.inner_text() or "").strip().lower()
                if txt in ["create account", "create an account", "register", "sign up"]:
                    if btn.is_visible():
                        has_create_btn = True
                        break

            if has_reg_sig or has_create_btn:
                fields = []
                if self.page.query_selector("input[type='password']"):
                    fields.append({
                        "key": "candidate_password",
                        "label": "Desired Password for Candidate Account",
                        "type": "text",
                        "required": True,
                    })
                return True, fields
            return False, []
        except Exception:
            return False, []

    def detect_verification_prompt(self) -> tuple[bool, str]:
        """
        Detect if an SMS OTP, email verification code, or 2FA prompt is blocking the application.
        Returns: (is_verification_required, reason)
        """
        try:
            page_text = self.page.inner_text("body").lower()
            signals = [
                "enter verification code",
                "verification code sent",
                "enter the 6-digit code",
                "enter the code we sent",
                "one-time password",
                "enter otp",
                "sms code",
                "enter security code",
            ]
            for sig in signals:
                if sig in page_text:
                    return True, sig
            return False, ""
        except Exception:
            return False, ""

    def detect_expired_job(self) -> bool:
        """
        Check if the job posting has closed, expired, or is no longer accepting applications.
        """
        try:
            page_content = (self.page.title() + " " + self.page.content()).lower()
        except Exception:
            return False

        expired_signatures = [
            "this job has expired",
            "this position is closed",
            "this job is no longer available",
            "position has been filled",
            "no longer accepting applications",
            "this job posting is no longer active",
            "job closed",
            "requisition closed",
            "this opening has been filled",
            "the job you are looking for is closed",
            "the job you are looking for is no longer open",
            "posting has ended",
            "job not found",
            "404 - not found",
            "page not found",
        ]
        return any(sig in page_content for sig in expired_signatures)

    def detect_unsupported_layout(self) -> tuple[bool, str]:
        """
        Detect unsupported iframe barriers, biometric video requirements, or proprietary widgets.
        Returns (is_unsupported: bool, reason: str).
        """
        try:
            content_lower = self.page.content().lower()

            # Check for video interview requirements
            if any(term in content_lower for term in ["record a video", "video interview required", "camera access required", "record your response"]):
                return True, "Job application requires an interactive video/audio recording."

            # Check for sandboxed / inaccessible cross-origin iframes holding the form
            frames = self.page.frames
            if len(frames) > 1:
                form_in_main = self.page.query_selector("form")
                if not form_in_main:
                    for f in frames[1:]:
                        try:
                            if f.query_selector("input, select, textarea"):
                                # If we can access it, it's supported
                                return False, ""
                        except Exception:
                            return True, "Application form is isolated inside a restricted cross-origin iframe."

            return False, ""
        except Exception as exc:
            return False, ""

    def detect_success(self) -> tuple[bool, str]:
        """
        Confirm successful submission and check for post-submission validation errors.
        Sets self.last_submission_error if validation errors or submission failures are detected.

        Returns:
            (success: bool, confirmation_url: str)
        """
        self.last_submission_error = None
        try:
            page_content = self.page.content().lower()
            current_url = self.page.url
        except Exception:
            self.last_submission_error = "Could not read page content after submission."
            return False, ""

        # 1. Negative Check: Inspect for visible form validation errors on the page
        error_selectors = [
            "[aria-invalid='true']",
            ".field-error",
            ".error-message",
            ".has-error",
            ".form-error",
            ".errors",
            "[class*='error-message']",
            "[class*='field-error']",
            "[class*='form-error']",
        ]
        detected_errors = []
        for sel in error_selectors:
            try:
                err_els = self.page.query_selector_all(sel)
                for el in err_els:
                    if el.is_visible():
                        txt = (el.inner_text() or "").strip()
                        if txt and len(txt) < 150 and txt not in detected_errors:
                            detected_errors.append(txt)
            except Exception:
                pass

        if detected_errors:
            self.last_submission_error = f"Form validation error(s) detected: {'; '.join(detected_errors[:3])}"
            return False, ""

        # 2. Positive Check: Confirm success via URL or receipt messages
        success_phrases = [
            "thank you for applying",
            "thank you for your application",
            "application submitted",
            "application received",
            "application complete",
            "we received your application",
            "you have successfully applied",
            "your application has been submitted",
            "successfully submitted",
            "confirmation",
            "we'll be in touch",
            "we will be in touch",
            "application is complete",
            "thanks for applying",
        ]

        success_url_patterns = [
            "/confirmation",
            "/success",
            "/thank-you",
            "/thankyou",
            "/applied",
            "submitted=true",
            "success=true",
        ]

        content_match = any(phrase in page_content for phrase in success_phrases)
        url_match = any(pat in current_url.lower() for pat in success_url_patterns)

        if content_match or url_match:
            return True, current_url

        self.last_submission_error = "No confirmation message or receipt URL detected after submit."
        return False, ""

    def _resolve_selector(self, field_key: str) -> str:
        """Try multiple robust strategies to find a CSS selector for the field key."""
        if not field_key:
            return ""
        safe_key = re.sub(r'[^a-zA-Z0-9_\-]', '', field_key.replace(' ', '_'))
        candidates = [
            f"#{safe_key}",
            f"[name='{field_key}']",
            f"[name*='{safe_key}']",
            f"[id*='{safe_key}']",
            f"[placeholder*='{field_key}']",
            f"[aria-label*='{field_key}']",
            f"[data-automation-id*='{safe_key}']",
        ]
        for sel in candidates:
            try:
                el = self.page.query_selector(sel)
                if el:
                    return sel
            except Exception:
                continue

        # Try finding by label text
        try:
            lbl = self.page.query_selector(f"label:has-text('{field_key}')")
            if lbl:
                for_id = lbl.get_attribute("for")
                if for_id:
                    return f"#{for_id}"
                inp = lbl.query_selector("input, select, textarea")
                if inp:
                    inp_id = inp.get_attribute("id")
                    if inp_id:
                        return f"#{inp_id}"
                    inp_name = inp.get_attribute("name")
                    if inp_name:
                        return f"[name='{inp_name}']"
        except Exception:
            pass

        return ""
