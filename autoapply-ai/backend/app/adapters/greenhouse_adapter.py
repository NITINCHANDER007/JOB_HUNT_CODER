"""
Greenhouse ATS adapter.
Greenhouse uses standardized forms, often with data-gh-* attributes.
URL patterns: boards.greenhouse.io/company/jobs/12345
"""

import re
import time
import random
from app.adapters.base_adapter import BaseAdapter
from app.adapters.exceptions import UnsupportedFormError


class GreenhouseAdapter(BaseAdapter):
    """Adapter for Greenhouse (boards.greenhouse.io) application forms."""

    PLATFORM = "greenhouse"

    def find_and_click_apply_button(self):
        """Click the 'Apply for this job' button if on the JD page."""
        apply_selectors = [
            "a:has-text('Apply for this job')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply')",
            "#apply_button",
            ".btn--apply",
            "[data-test='apply-button']",
        ]
        for sel in apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    time.sleep(random.uniform(1.0, 2.0))
                    self.log("INFO", f"Clicked apply button: {sel}")
                    return
            except Exception:
                continue

    def extract_form_fields(self) -> list:
        """
        Extract all form fields from a Greenhouse application form.
        Greenhouse forms are inside #application_form or form#application.
        """
        fields = []

        js_extract = """
        () => {
            const form = document.querySelector('#application_form, form#application, form.application-form, form');
            if (!form) return [];

            const results = [];
            const elements = form.querySelectorAll('input, select, textarea');

            for (const el of elements) {
                if (el.type === 'hidden' && el.name !== 'job_application[resume]') continue;
                if (!el.offsetParent && el.type !== 'file') continue; // skip invisible

                let label = '';
                // Try label[for]
                if (el.id) {
                    const labelEl = document.querySelector(`label[for="${el.id}"]`);
                    if (labelEl) label = labelEl.innerText.trim();
                }
                // Fallback: parent label
                if (!label) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) label = parentLabel.innerText.trim();
                }
                // Fallback: preceding text or aria-label
                if (!label) label = el.getAttribute('aria-label') || el.placeholder || el.name || '';

                const options = [];
                if (el.tagName === 'SELECT') {
                    for (const opt of el.options) {
                        if (opt.value) options.push({ value: opt.value, text: opt.innerText.trim() });
                    }
                }

                results.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    label: label.replace(/\\*$/, '').trim(),
                    placeholder: el.placeholder || '',
                    required: el.required || el.getAttribute('aria-required') === 'true',
                    options: options,
                    selector: el.id ? '#' + el.id : (el.name ? `[name="${el.name}"]` : ''),
                    value: el.value || '',
                });
            }
            return results;
        }
        """

        try:
            raw_fields = self.page.evaluate(js_extract)
            if not raw_fields:
                raise UnsupportedFormError("No form fields found on Greenhouse page")

            for f in raw_fields:
                fields.append({
                    "label": f.get("label", ""),
                    "name": f.get("name", ""),
                    "type": f.get("type", "text"),
                    "options": [o["text"] for o in f.get("options", [])],
                    "required": f.get("required", False),
                    "selector": f.get("selector", ""),
                    "placeholder": f.get("placeholder", ""),
                })

            self.log("INFO", f"Greenhouse: extracted {len(fields)} form fields")
            return fields

        except UnsupportedFormError:
            raise
        except Exception as e:
            raise UnsupportedFormError(f"Greenhouse form extraction failed: {e}")

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """Fill the Greenhouse form using the AI-generated mapping and submit."""
        self.log("INFO", "Greenhouse: filling form fields")

        for field_key, value in field_mapping.items():
            if not value or value == "RESUME_FILE":
                continue

            # Try to find the matching field selector
            selector = self._resolve_selector(field_key)
            if not selector:
                self.log("WARNING", f"Could not find selector for field: {field_key}")
                continue

            try:
                el = self.page.query_selector(selector)
                if not el:
                    continue
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                field_type = el.evaluate("e => e.type || e.tagName.toLowerCase()")
                options = []
                if tag == "select":
                    options = el.evaluate(
                        "e => Array.from(e.options).map(o => o.innerText.trim())"
                    )
                self.fill_field(selector, field_type, str(value), options)
                time.sleep(random.uniform(0.1, 0.3))
            except Exception as e:
                self.log("WARNING", f"Failed to fill '{field_key}': {e}")

        # Upload resume
        if resume_path:
            self.log("INFO", "Greenhouse: uploading resume")
            self.upload_resume(resume_path)
            time.sleep(random.uniform(0.5, 1.0))

        # Fill cover letter if present
        if cover_letter:
            cover_selectors = [
                "#cover_letter", "textarea[name*='cover']",
                "#job_application_cover_letter",
                "textarea[data-field='cover_letter']",
            ]
            for sel in cover_selectors:
                try:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.fill(sel, cover_letter)
                        self.log("INFO", "Greenhouse: filled cover letter")
                        break
                except Exception:
                    continue

        # Submit
        time.sleep(random.uniform(0.5, 1.5))
        self.log("INFO", "Greenhouse: clicking submit")
        self.click_submit()

        # Wait for navigation / confirmation
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)
        except Exception:
            pass

        success, confirmation_url = self.detect_success()
        return {"success": success, "confirmation_url": confirmation_url}

    def _resolve_selector(self, field_key: str) -> str:
        """Try multiple strategies to find a CSS selector for the field key."""
        # Direct ID match
        safe_key = re.sub(r'[^a-zA-Z0-9_\-]', '', field_key.replace(' ', '_'))
        candidates = [
            f"#{safe_key}",
            f"[name='{field_key}']",
            f"[name*='{safe_key}']",
            f"[id*='{safe_key}']",
            f"[placeholder*='{field_key}']",
        ]
        for sel in candidates:
            try:
                el = self.page.query_selector(sel)
                if el:
                    return sel
            except Exception:
                continue

        # Try label text matching
        try:
            label = self.page.query_selector(f"label:has-text('{field_key}')")
            if label:
                for_attr = label.get_attribute("for")
                if for_attr:
                    return f"#{for_attr}"
        except Exception:
            pass

        return ""

