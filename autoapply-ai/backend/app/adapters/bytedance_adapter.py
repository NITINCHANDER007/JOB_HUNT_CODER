"""
ByteDance ATS Adapter.
Handles applications on ByteDance career portals (jobs.bytedance.com, joinbytedance.com),
supporting:
- JD page detection & redirect navigation to application page (/apply)
- Dynamic form extraction & frame handling
- Candidate login / verification wall handling
- Form field auto-filling & resume upload
- Submission confirmation verification.
"""

import re
import time
import random
import logging
from app.adapters.base_adapter import BaseAdapter
from app.adapters.exceptions import (
    UnsupportedFormError,
    SubmissionFailedError,
    LoginWallError,
)

logger = logging.getLogger(__name__)


class ByteDanceAdapter(BaseAdapter):
    """Adapter for ByteDance and TikTok career portals."""

    PLATFORM = "bytedance"

    def find_and_click_apply_button(self):
        """
        Locate and click the 'Apply to this job' or 'Apply' CTA button.
        Waits for redirection to the application form page.
        """
        apply_selectors = [
            "button:has-text('Apply to this job')",
            "a:has-text('Apply to this job')",
            "button:has-text('Apply')",
            "a:has-text('Apply Now')",
            ".apply-btn",
            ".bytedance-apply-button",
        ]

        for sel in apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.page.wait_for_timeout(3000)
                    self.log("INFO", f"ByteDance: Clicked apply button: {sel}")
                    return True
            except Exception:
                continue

        return False

    def extract_form_fields(self) -> list:
        """Extract visible form fields from ByteDance application form."""
        # If still on JD page, click apply button
        if "/apply" not in self.page.url.lower():
            self.find_and_click_apply_button()

        fields = []
        js_extract = """
        () => {
            const results = [];
            const elements = document.querySelectorAll('input, select, textarea');

            for (const el of elements) {
                if (el.type === 'hidden') continue;
                if (!el.offsetParent && el.type !== 'file') continue;

                let label = '';
                const formItem = el.closest('.form-item, .item-wrap, [class*="form-item"], [class*="field"]');
                if (formItem) {
                    const lbl = formItem.querySelector('label, [class*="label"], [class*="title"]');
                    if (lbl) label = lbl.innerText.trim();
                }

                if (!label && el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) label = lbl.innerText.trim();
                }

                if (!label) {
                    label = el.getAttribute('placeholder') || el.name || '';
                }

                label = label.replace(/[\\n\\r\\t]+/g, ' ').replace(/\\s+/g, ' ').replace(/\\*$/, '').trim();

                let selector = '';
                if (el.id) {
                    selector = '#' + CSS.escape(el.id);
                } else if (el.name) {
                    selector = `input[name="${el.name}"]`;
                }

                results.push({
                    type: el.type || 'text',
                    name: el.name || '',
                    label: label,
                    required: el.required || el.getAttribute('aria-required') === 'true' || (formItem && formItem.innerText.includes('*')),
                    selector: selector,
                    options: [],
                });
            }

            return results;
        }
        """

        try:
            raw_fields = self.page.evaluate(js_extract)
            seen = set()
            for f in raw_fields:
                k = (f.get("name", ""), f.get("label", ""))
                if k in seen and k[0]:
                    continue
                seen.add(k)
                fields.append(f)
            self.log("INFO", f"ByteDance: Extracted {len(fields)} fields")
            return fields
        except Exception as e:
            self.log("WARNING", f"ByteDance field extraction warning: {e}")
            return []

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """
        Fill candidate details, upload resume, and submit ByteDance application.
        """
        self.log("INFO", "ByteDance: Filling application fields")

        # Check for candidate login requirement
        if self._is_login_required():
            self.log("WARNING", "ByteDance: Candidate login or verification required")
            raise LoginWallError(
                f"ByteDance requires candidate authentication. Please sign in via the in-page verification view, then click Resume."
            )

        # 1. Fill fields
        for field_key, value in field_mapping.items():
            if not value or value == "RESUME_FILE":
                continue
            selector = self._resolve_selector(field_key)
            if selector:
                try:
                    el = self.page.query_selector(selector)
                    if el and el.is_visible() and not el.input_value():
                        el.fill(str(value))
                        time.sleep(random.uniform(0.1, 0.2))
                except Exception:
                    continue

        # 2. Upload resume
        if resume_path:
            self._handle_resume_upload(resume_path)

        # 3. Check for Submit button
        submit_btn = self.page.query_selector(
            "button:has-text('Submit'), button:has-text('Submit Application'), button.submit-btn"
        )
        if submit_btn and submit_btn.is_visible():
            self.log("INFO", "ByteDance: Clicking Submit button")
            submit_btn.scroll_into_view_if_needed()
            submit_btn.click()
            self.page.wait_for_timeout(3500)

            if self._detect_submitted():
                return {"success": True, "confirmation_url": self.page.url}

        if self._detect_submitted():
            return {"success": True, "confirmation_url": self.page.url}

        raise SubmissionFailedError("ByteDance application submitted without confirmation receipt.")

    def _is_login_required(self) -> bool:
        """Detect if ByteDance login modal / verification is active."""
        login_selectors = [
            "input[type='password']",
            ".login-wrap",
            "[class*='login-modal']",
            "button:has-text('Send Code')",
            "button:has-text('Log In')",
        ]
        for sel in login_selectors:
            el = self.page.query_selector(sel)
            if el and el.is_visible():
                return True
        return False

    def _handle_resume_upload(self, resume_path: str):
        """Upload resume to ByteDance file input."""
        file_input = self.page.query_selector("input[type='file']")
        if file_input:
            try:
                self.log("INFO", f"ByteDance: Uploading resume file: {resume_path}")
                file_input.set_input_files(resume_path)
                self.page.wait_for_timeout(2000)
            except Exception as e:
                self.log("WARNING", f"ByteDance resume upload warning: {e}")

    def _detect_submitted(self) -> bool:
        """Detect submission success message on ByteDance."""
        success_signals = [
            "submitted successfully",
            "application submitted",
            "thank you for applying",
            "we have received your application",
        ]
        try:
            t = self.page.title() if callable(getattr(self.page, "title", None)) else ""
            t_str = str(t) if t else ""
            b = self.page.inner_text("body") if callable(getattr(self.page, "inner_text", None)) else ""
            b_str = str(b) if b else ""
            body = (t_str + " " + b_str).lower()
            return any(sig in body for sig in success_signals)
        except Exception:
            return False
