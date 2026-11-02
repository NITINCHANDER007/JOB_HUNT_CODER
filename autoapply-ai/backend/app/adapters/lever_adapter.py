"""
Lever ATS adapter.
URL patterns: jobs.lever.co/company/uuid
Lever uses React-based SPA forms with specific class patterns.
"""

import re
import time
import random
from app.adapters.base_adapter import BaseAdapter
from app.adapters.exceptions import UnsupportedFormError


class LeverAdapter(BaseAdapter):
    """Adapter for Lever (jobs.lever.co) application forms."""

    PLATFORM = "lever"

    def find_and_click_apply_button(self):
        """Lever JD pages have an 'Apply for this job' link at top."""
        apply_selectors = [
            "a.postings-btn",
            "a:has-text('Apply for this job')",
            ".posting-btn-submit",
            "[data-qa='btn-apply']",
            "a.template-btn-submit",
        ]
        for sel in apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    time.sleep(random.uniform(1.0, 2.0))
                    self.log("INFO", f"Lever: clicked apply button via {sel}")
                    return
            except Exception:
                continue

    def extract_form_fields(self) -> list:
        """Extract all fields from a Lever application form."""
        fields = []

        js_extract = """
        () => {
            const form = document.querySelector('.application-form, form[action*="lever"], form');
            if (!form) return [];

            const results = [];
            const elements = form.querySelectorAll('input, select, textarea');

            for (const el of elements) {
                if (el.type === 'hidden') continue;
                if (!el.offsetParent && el.type !== 'file') continue;

                let label = '';
                // Lever labels are in .application-label or label[for]
                if (el.id) {
                    const labelEl = document.querySelector(`label[for="${el.id}"]`);
                    if (labelEl) label = labelEl.innerText.trim();
                }
                if (!label) {
                    const fieldContainer = el.closest('.application-field, .field');
                    if (fieldContainer) {
                        const labelEl = fieldContainer.querySelector('.application-label, label, .field-label');
                        if (labelEl) label = labelEl.innerText.trim();
                    }
                }
                if (!label) label = el.getAttribute('aria-label') || el.placeholder || el.name || '';

                const options = [];
                if (el.tagName === 'SELECT') {
                    for (const opt of el.options) {
                        if (opt.value) options.push({ value: opt.value, text: opt.innerText.trim() });
                    }
                }

                results.push({
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    label: label.replace(/[\\*\\n]/g, '').trim(),
                    placeholder: el.placeholder || '',
                    required: el.required,
                    options: options,
                    selector: el.id ? '#' + el.id : (el.name ? `[name="${el.name}"]` : ''),
                });
            }
            return results;
        }
        """

        try:
            raw_fields = self.page.evaluate(js_extract)
            if not raw_fields:
                raise UnsupportedFormError("No fields found on Lever page")

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

            self.log("INFO", f"Lever: extracted {len(fields)} form fields")
            return fields

        except UnsupportedFormError:
            raise
        except Exception as e:
            raise UnsupportedFormError(f"Lever form extraction failed: {e}")

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """Fill and submit the Lever form."""
        self.log("INFO", "Lever: filling form fields")

        for field_key, value in field_mapping.items():
            if not value or value == "RESUME_FILE":
                continue
            selector = self._resolve_selector(field_key)
            if not selector:
                continue
            try:
                el = self.page.query_selector(selector)
                if not el:
                    continue
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                ftype = el.evaluate("e => e.type || e.tagName.toLowerCase()")
                options = []
                if tag == "select":
                    options = el.evaluate("e => Array.from(e.options).map(o => o.innerText.trim())")
                self.fill_field(selector, ftype, str(value), options)
                time.sleep(random.uniform(0.1, 0.3))
            except Exception as e:
                self.log("WARNING", f"Lever fill failed for '{field_key}': {e}")

        # Upload resume
        if resume_path:
            self.upload_resume(resume_path)
            time.sleep(random.uniform(0.5, 1.0))

        # Cover letter
        if cover_letter:
            for sel in ["textarea[name*='cover']", "#additional-information", "textarea[name*='comments']"]:
                try:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.fill(sel, cover_letter)
                        break
                except Exception:
                    continue

        # Submit
        time.sleep(random.uniform(0.5, 1.5))
        submit_selectors = [
            "button.template-btn-submit",
            "button:has-text('Submit application')",
            "button[type='submit']",
            "input[type='submit']",
        ]
        for sel in submit_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.log("INFO", f"Lever: clicked submit via {sel}")
                    break
            except Exception:
                continue

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)
        except Exception:
            pass

        success, confirmation_url = self.detect_success()
        return {"success": success, "confirmation_url": confirmation_url}

    def _resolve_selector(self, field_key: str) -> str:
        """Resolve a field key to a CSS selector."""
        safe = re.sub(r'[^a-zA-Z0-9_\-]', '', field_key.replace(' ', '_'))
        for sel in [f"#{safe}", f"[name='{field_key}']", f"[name*='{safe}']", f"[id*='{safe}']"]:
            try:
                if self.page.query_selector(sel):
                    return sel
            except Exception:
                continue
        try:
            label = self.page.query_selector(f"label:has-text('{field_key}')")
            if label:
                for_attr = label.get_attribute("for")
                if for_attr:
                    return f"#{for_attr}"
        except Exception:
            pass
        return ""

