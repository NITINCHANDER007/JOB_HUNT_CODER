"""
Generic AI-driven adapter for career pages that don't match any known ATS.
Uses Playwright to extract ALL form fields dynamically, then uses Gemini
to interpret and map values. Handles multi-step forms.
"""

import re
import time
import random
import logging
from app.adapters.base_adapter import BaseAdapter
from app.adapters.exceptions import UnsupportedFormError

logger = logging.getLogger(__name__)


class GenericAdapter(BaseAdapter):
    """
    Fallback adapter: AI-driven form detection and filling for any career page.
    Works by extracting all visible form elements via JavaScript evaluation
    and using heuristics + Gemini for label–value matching.
    """

    PLATFORM = "generic"

    def find_and_click_apply_button(self):
        """Find and click the main Apply/CTA button if on a JD page."""
        return self.navigate_to_application_form()

    def extract_form_fields(self) -> list:
        """
        Extract ALL form elements from the page using JavaScript evaluation.
        This is the most thorough extraction—covers any HTML form structure.
        """
        fields = []
        target = self.get_active_frame()
        js_extract = """
        () => {
            const results = [];
            const allForms = document.querySelectorAll('form');
            const container = allForms.length > 0
                ? Array.from(allForms).reduce((a, b) =>
                    a.querySelectorAll('input,select,textarea').length >=
                    b.querySelectorAll('input,select,textarea').length ? a : b)
                : document.body;

            const elements = container.querySelectorAll('input, select, textarea');

            for (const el of elements) {
                if (el.type === 'hidden') continue;

                // Visibility check (skip truly hidden elements but keep file inputs)
                if (el.type !== 'file') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) continue;
                }

                let label = '';

                // Strategy 1: label[for="id"]
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) label = lbl.innerText.trim();
                }

                // Strategy 2: Closest ancestor label
                if (!label) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) {
                        label = parentLabel.innerText.trim();
                    }
                }

                // Strategy 3: Sibling or parent wrapper text
                if (!label) {
                    const wrapper = el.closest(
                        '.form-group, .form-field, .field, .form-row, ' +
                        '[class*="field"], [class*="question"], [class*="form-item"]'
                    );
                    if (wrapper) {
                        const lbl = wrapper.querySelector(
                            'label, .label, .field-label, [class*="label"], legend'
                        );
                        if (lbl) label = lbl.innerText.trim();
                    }
                }

                // Strategy 4: aria-label or placeholder
                if (!label) {
                    label = el.getAttribute('aria-label')
                         || el.getAttribute('aria-labelledby')
                         || el.placeholder
                         || el.name
                         || '';
                }

                // Clean up label
                label = label.replace(/[\\n\\r\\t]+/g, ' ').replace(/\\s+/g, ' ').replace(/\\*$/, '').trim();

                // Options for select elements
                const options = [];
                if (el.tagName === 'SELECT') {
                    for (const opt of el.options) {
                        if (opt.value && opt.value !== '') {
                            options.push({ value: opt.value, text: opt.innerText.trim() });
                        }
                    }
                }

                // Build a robust selector
                let selector = '';
                if (el.id) {
                    selector = '#' + CSS.escape(el.id);
                } else if (el.name) {
                    selector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                } else {
                    // Use nth-child as last resort
                    const parent = el.parentElement;
                    if (parent) {
                        const children = Array.from(parent.children);
                        const idx = children.indexOf(el);
                        selector = el.tagName.toLowerCase() + ':nth-child(' + (idx + 1) + ')';
                    }
                }

                results.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || (el.tagName === 'TEXTAREA' ? 'textarea' : 'text'),
                    name: el.name || '',
                    id: el.id || '',
                    label: label,
                    placeholder: el.placeholder || '',
                    required: el.required || el.getAttribute('aria-required') === 'true',
                    options: options,
                    selector: selector,
                    visible: true,
                });
            }

            // Also check for radio button groups
            const radioGroups = {};
            container.querySelectorAll('input[type="radio"]').forEach(radio => {
                const name = radio.name;
                if (!name) return;
                if (!radioGroups[name]) {
                    radioGroups[name] = {
                        type: 'radio',
                        name: name,
                        id: radio.id || '',
                        label: '',
                        options: [],
                        selector: `input[name="${name}"]`,
                        required: radio.required,
                    };
                    // Find label for the group
                    const fieldset = radio.closest('fieldset, [role="radiogroup"], .radio-group');
                    if (fieldset) {
                        const legend = fieldset.querySelector('legend, label, .label');
                        if (legend) radioGroups[name].label = legend.innerText.trim();
                    }
                }
                const radioLabel = radio.id
                    ? (document.querySelector('label[for="' + CSS.escape(radio.id) + '"]') || {}).innerText || radio.value
                    : radio.value;
                radioGroups[name].options.push({ value: radio.value, text: (radioLabel || '').trim() });
            });

            // Add radio groups that aren't already in results
            for (const rg of Object.values(radioGroups)) {
                const exists = results.some(r => r.name === rg.name && r.type === 'radio');
                if (!exists) results.push(rg);
            }

            return results;
        }
        """

        try:
            raw_fields = target.evaluate(js_extract)
            if not raw_fields:
                raise UnsupportedFormError("No form fields found on page")

            # Deduplicate by name+type
            seen = set()
            for f in raw_fields:
                key = (f.get("name", ""), f.get("type", ""), f.get("label", ""))
                if key in seen and key[0]:
                    continue
                seen.add(key)
                fields.append({
                    "label": f.get("label", ""),
                    "name": f.get("name", ""),
                    "type": f.get("type", "text"),
                    "options": [o["text"] for o in f.get("options", [])],
                    "required": f.get("required", False),
                    "selector": f.get("selector", ""),
                    "placeholder": f.get("placeholder", ""),
                })

            self.log("INFO", f"Generic: extracted {len(fields)} form fields")
            return fields

        except UnsupportedFormError:
            raise
        except Exception as e:
            raise UnsupportedFormError(f"Generic form extraction failed: {e}")

    def fill_and_submit(self, field_mapping: dict, resume_path: str, cover_letter: str = None) -> dict:
        """
        Fill the form using AI mapping, handling multi-step forms.
        """
        self.log("INFO", "Generic: filling form fields")
        target = self.get_active_frame()

        for field_key, value in field_mapping.items():
            if not value or value == "RESUME_FILE":
                continue

            selector = self._resolve_selector(field_key)
            if not selector:
                self.log("WARNING", f"Generic: no selector found for '{field_key}'")
                continue

            try:
                el = target.query_selector(selector)
                if not el:
                    continue

                tag = el.evaluate("e => e.tagName.toLowerCase()")
                ftype = el.evaluate("e => e.type || e.tagName.toLowerCase()")
                options = []
                if tag == "select":
                    options = el.evaluate(
                        "e => Array.from(e.options).map(o => o.innerText.trim())"
                    )

                self.fill_field(selector, ftype, str(value), options)
                time.sleep(random.uniform(0.1, 0.4))

            except Exception as e:
                self.log("WARNING", f"Generic fill failed for '{field_key}': {e}")

        # Upload resume
        if resume_path:
            self.log("INFO", "Generic: uploading resume")
            self.upload_resume(resume_path)
            time.sleep(random.uniform(0.5, 1.0))

        # Cover letter
        if cover_letter:
            cover_selectors = [
                "textarea[name*='cover']",
                "textarea[name*='letter']",
                "textarea[id*='cover']",
                "textarea[placeholder*='cover letter']",
                "textarea[placeholder*='Cover Letter']",
            ]
            for sel in cover_selectors:
                try:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.fill(sel, cover_letter)
                        self.log("INFO", "Generic: filled cover letter")
                        break
                except Exception:
                    continue

        # Handle multi-step: check for "Next" button before final submit
        max_steps = 5
        for step in range(max_steps):
            next_btn = self._find_next_button()
            if next_btn:
                try:
                    next_btn.click()
                    self.log("INFO", f"Generic: clicked Next (step {step + 1})")
                    time.sleep(random.uniform(1.0, 2.0))

                    # Extract and fill any new fields on the next step
                    new_fields = self.extract_form_fields()
                    if new_fields:
                        for f in new_fields:
                            fkey = f.get("label") or f.get("name", "")
                            if fkey in field_mapping:
                                sel = f.get("selector", "")
                                if sel:
                                    try:
                                        self.fill_field(sel, f["type"], str(field_mapping[fkey]), f.get("options", []))
                                    except Exception:
                                        pass
                except Exception:
                    break
            else:
                break

        # Final submit
        time.sleep(random.uniform(0.5, 1.5))
        self.log("INFO", "Generic: clicking submit")
        self.click_submit()

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)
        except Exception:
            pass

        success, confirmation_url = self.detect_success()
        return {"success": success, "confirmation_url": confirmation_url}

    def _find_next_button(self):
        """Find a Next / Continue button (for multi-step forms)."""
        next_selectors = [
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('next')",
            "a:has-text('Next')",
            "button.next-btn",
            "[data-testid='next']",
        ]
        for sel in next_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    # Make sure this isn't the submit button
                    text = (btn.inner_text() or "").lower()
                    if "submit" not in text and "apply" not in text:
                        return btn
            except Exception:
                continue
        return None

    def _resolve_selector(self, field_key: str) -> str:
        """Try multiple strategies to find a CSS selector for the field key."""
        target = self.get_active_frame()
        safe = re.sub(r'[^a-zA-Z0-9_\-]', '', field_key.replace(' ', '_').lower())

        # Direct match attempts
        for sel in [
            f"#{safe}",
            f"[name='{field_key}']",
            f"[name*='{safe}']",
            f"[id*='{safe}']",
            f"[placeholder*='{field_key}']",
        ]:
            try:
                if target.query_selector(sel):
                    return sel
            except Exception:
                continue

        # Label text matching
        try:
            # Escape single quotes in field_key
            escaped_key = field_key.replace("'", "\\'")
            label = target.query_selector(f"label:has-text('{escaped_key}')")
            if label:
                for_attr = label.get_attribute("for")
                if for_attr:
                    return f"#{for_attr}"
                # Find input inside the label
                inner = label.query_selector("input, select, textarea")
                if inner:
                    inner_id = inner.get_attribute("id")
                    inner_name = inner.get_attribute("name")
                    if inner_id:
                        return f"#{inner_id}"
                    if inner_name:
                        return f"[name='{inner_name}']"
        except Exception:
            pass

        return ""

