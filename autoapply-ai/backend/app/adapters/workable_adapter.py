"""
Workable ATS adapter.
URL patterns: apply.workable.com/company/j/UUID/
"""

import re
import time
import random
from app.adapters.base_adapter import BaseAdapter
from app.adapters.exceptions import UnsupportedFormError


class WorkableAdapter(BaseAdapter):
    """Adapter for Workable (apply.workable.com) application forms."""

    PLATFORM = "workable"

    def find_and_click_apply_button(self):
        """Click the apply button on a Workable JD page."""
        apply_selectors = [
            "button:has-text('Apply for this job')",
            "a:has-text('Apply')",
            "[data-ui='apply-button']",
            ".careers-apply-button",
            "button.apply-btn",
        ]
        for sel in apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    time.sleep(random.uniform(1.0, 2.0))
                    self.log("INFO", f"Workable: clicked apply via {sel}")
                    return
            except Exception:
                continue

    def extract_form_fields(self) -> list:
        """Extract form fields from a Workable application form."""
        fields = []

        js_extract = """
        () => {
            const form = document.querySelector('form[data-ui="application-form"], form[class*="application"], form');
            if (!form) return [];

            const results = [];
            const elements = form.querySelectorAll('input, select, textarea');

            for (const el of elements) {
                if (el.type === 'hidden') continue;
                if (!el.offsetParent && el.type !== 'file') continue;

                let label = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim();
                }
                if (!label) {
                    const wrapper = el.closest('.form-group, .field-group, [class*="field"]');
                    if (wrapper) {
                        const lbl = wrapper.querySelector('label, .label');
                        if (lbl) label = lbl.innerText.trim();
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
                raise UnsupportedFormError("No fields found on Workable page")

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

            self.log("INFO", f"Workable: extracted {len(fields)} fields")
            return fields

        except UnsupportedFormError:
            raise
        except Exception as e:
            raise UnsupportedFormError(f"Workable form extraction failed: {e}")

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """Fill and submit the Workable form."""
        self.log("INFO", "Workable: filling form")

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
                self.log("WARNING", f"Workable fill failed for '{field_key}': {e}")

        if resume_path:
            self.upload_resume(resume_path)
            time.sleep(random.uniform(0.5, 1.0))

        if cover_letter:
            for sel in ["textarea[name*='cover']", "textarea[name*='letter']", "textarea#cover_letter"]:
                try:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.fill(sel, cover_letter)
                        break
                except Exception:
                    continue

        time.sleep(random.uniform(0.5, 1.5))
        self.click_submit()

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)
        except Exception:
            pass

        success, confirmation_url = self.detect_success()
        return {"success": success, "confirmation_url": confirmation_url}

    def _resolve_selector(self, field_key: str) -> str:
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

