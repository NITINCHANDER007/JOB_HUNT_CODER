"""
Workday ATS Adapter.
Handles automated applications for Workday career portals (*.myworkdayjobs.com),
supporting:
- JD page detection & clicking "Apply" / "Apply Manually"
- Account creation / login detection
- Multi-step form progression via standard Workday data-automation-id attributes
- Resume upload & questionnaire screening questions
- Review and final submission verification.
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
    MissingInformationError,
)

logger = logging.getLogger(__name__)


class WorkdayAdapter(BaseAdapter):
    """Adapter for Workday application portals (*.myworkdayjobs.com)."""

    PLATFORM = "workday"

    def find_and_click_apply_button(self):
        """
        Locate and click the primary Apply button on a Workday job description page.
        Selects 'Apply Manually' if a sub-menu appears.
        """
        apply_selectors = [
            "a[data-automation-id='applyButton']",
            "button[data-automation-id='applyButton']",
            "a:has-text('Apply')",
            "button:has-text('Apply')",
            "[data-automation-id='adventureButton']",
        ]

        for sel in apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.page.wait_for_timeout(2000)
                    self.log("INFO", f"Workday: Clicked apply button: {sel}")

                    # Check for "Apply Manually" sub-option
                    manual_btn = self.page.query_selector(
                        "a[data-automation-id='applyManually'], button:has-text('Apply Manually'), a:has-text('Apply Manually')"
                    )
                    if manual_btn and manual_btn.is_visible():
                        manual_btn.click()
                        self.page.wait_for_timeout(2500)
                        self.log("INFO", "Workday: Selected 'Apply Manually'")
                    return True
            except Exception:
                continue

        return False

    def extract_form_fields(self) -> list:
        """Extract all form fields visible on the active Workday step."""
        fields = []

        js_extract = """
        () => {
            const results = [];
            const elements = document.querySelectorAll('input, select, textarea, button[data-automation-id*="dropdown"]');

            for (const el of elements) {
                if (el.type === 'hidden') continue;
                if (!el.offsetParent && el.type !== 'file') continue;

                let label = '';
                // Workday label strategy
                const container = el.closest('[data-automation-id*="formField"], .css-1, div');
                if (container) {
                    const lbl = container.querySelector('label, [data-automation-id*="label"], .css-label');
                    if (lbl) label = lbl.innerText.trim();
                }

                if (!label && el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) label = lbl.innerText.trim();
                }

                if (!label) {
                    label = el.getAttribute('aria-label') || el.placeholder || el.getAttribute('data-automation-id') || '';
                }

                label = label.replace(/[\\n\\r\\t]+/g, ' ').replace(/\\s+/g, ' ').replace(/\\*$/, '').trim();

                let selector = '';
                const autoId = el.getAttribute('data-automation-id');
                if (autoId) {
                    selector = `[data-automation-id="${autoId}"]`;
                } else if (el.id) {
                    selector = '#' + CSS.escape(el.id);
                } else if (el.name) {
                    selector = `input[name="${el.name}"]`;
                }

                results.push({
                    type: el.type || 'text',
                    name: el.name || autoId || '',
                    label: label,
                    required: el.required || el.getAttribute('aria-required') === 'true' || el.getAttribute('aria-invalid') !== null,
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
            self.log("INFO", f"Workday: Extracted {len(fields)} fields on current step")
            return fields
        except Exception as e:
            self.log("WARNING", f"Workday field extraction warning: {e}")
            return []

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """
        Advance through Workday's multi-step application workflow:
        1. Handle candidate account if prompted.
        2. Progress through steps ('Save and Continue' / Next).
        3. Fill fields & upload resume at appropriate steps.
        4. Submit and verify confirmation.
        """
        self.log("INFO", "Starting Workday multi-step application workflow")

        # Open application form if needed
        if not self.page.query_selector("[data-automation-id*='bottom-navigation']"):
            self.find_and_click_apply_button()

        # Check for candidate login/account barrier
        if self._is_workday_auth_required():
            self.log("WARNING", "Workday: Candidate sign-in or account registration required")
            raise LoginWallError(
                f"Workday requires a candidate account to apply. Please sign in or create an account via the in-page verification view, then click Resume."
            )

        max_steps = 12
        current_step = 0

        while current_step < max_steps:
            current_step += 1
            self.log("INFO", f"Workday: Processing application step {current_step}")
            self.page.wait_for_timeout(1500)

            # Check if submission is already finished
            if self._detect_submitted():
                return {"success": True, "confirmation_url": self.page.url}

            # 1. Fill visible inputs on this step
            self._fill_step_inputs(field_mapping)

            # 2. Upload resume if file input is present
            if resume_path:
                self._handle_step_resume_upload(resume_path)

            # 3. Handle questionnaires (Workday radio & dropdowns)
            self._handle_step_questions(field_mapping)

            # 4. Check for Submit button
            submit_btn = self.page.query_selector(
                "button[data-automation-id='bottom-navigation-submit-button'], button:has-text('Submit')"
            )
            if submit_btn and submit_btn.is_visible():
                self.log("INFO", "Workday: Found final Submit button. Clicking submit!")
                submit_btn.scroll_into_view_if_needed()
                submit_btn.click()
                self.page.wait_for_timeout(4000)

                if self._detect_submitted():
                    return {"success": True, "confirmation_url": self.page.url}
                break

            # 5. Check for Next / Save and Continue button
            next_btn = self.page.query_selector(
                "button[data-automation-id='bottom-navigation-next-button'], button:has-text('Save and Continue'), button:has-text('Next')"
            )
            if next_btn and next_btn.is_visible():
                self.log("INFO", "Workday: Clicking 'Save and Continue'")
                next_btn.click()
                self.page.wait_for_timeout(2000)
                continue

            # Fallback check
            if self._detect_submitted():
                return {"success": True, "confirmation_url": self.page.url}

            break

        if self._detect_submitted():
            return {"success": True, "confirmation_url": self.page.url}

        raise SubmissionFailedError("Workday application completed without confirmation receipt.")

    def _is_workday_auth_required(self) -> bool:
        """Check if Workday is presenting an account login or creation modal."""
        auth_selectors = [
            "input[data-automation-id='password']",
            "button[data-automation-id='signInSubmitButton']",
            "div:has-text('Create Account')",
            "div:has-text('Sign In')",
        ]
        has_pwd = False
        for sel in auth_selectors:
            el = self.page.query_selector(sel)
            if el and el.is_visible():
                has_pwd = True
                break
        return has_pwd and not self.page.query_selector("[data-automation-id='bottom-navigation-next-button']")

    def _fill_step_inputs(self, field_mapping: dict):
        """Fill all standard text inputs on the current step."""
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

    def _handle_step_resume_upload(self, resume_path: str):
        """Upload resume if a file upload drop zone is present on this step."""
        file_input = self.page.query_selector(
            "input[type='file'][data-automation-id*='file-upload'], input[type='file']"
        )
        if file_input:
            try:
                self.log("INFO", f"Workday: Uploading resume file: {resume_path}")
                file_input.set_input_files(resume_path)
                self.page.wait_for_timeout(2000)
            except Exception as e:
                self.log("WARNING", f"Workday resume upload warning: {e}")

    def _handle_step_questions(self, field_mapping: dict):
        """Answer Workday questionnaire radio buttons and select options."""
        # Radio buttons
        for radio in self.page.query_selector_all("input[type='radio']"):
            try:
                if not radio.is_visible():
                    continue
                lbl_el = self.page.query_selector(f"label[for='{radio.get_attribute('id')}']")
                opt_text = (lbl_el.inner_text() if lbl_el else radio.get_attribute("value") or "").lower()

                # Find associated question
                container = radio.closest("fieldset, [data-automation-id*='formField']")
                legend = container.query_selector("legend, label, span") if container else None
                q_text = (legend.inner_text() if legend else "").strip().lower()

                for k, v in field_mapping.items():
                    if k.lower() in q_text or q_text in k.lower():
                        v_lower = str(v).strip().lower()
                        if (v_lower in ["yes", "true", "1"] and "yes" in opt_text) or \
                           (v_lower in ["no", "false", "0"] and "no" in opt_text) or \
                           (v_lower == opt_text):
                            radio.check()
                            break
            except Exception:
                continue

    def _detect_submitted(self) -> bool:
        """Check if Workday shows confirmation message or receipt URL."""
        success_signals = [
            "congratulations",
            "thank you for applying",
            "your application has been submitted",
            "application submitted",
            "application-submitted",
        ]
        try:
            body = (self.page.title() + " " + self.page.inner_text("body")).lower()
            return any(sig in body for sig in success_signals)
        except Exception:
            return False

