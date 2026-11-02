"""
AutoApply AI - LinkedIn Easy Apply Dedicated Adapter.

Handles automated job applications for LinkedIn postings:
1. Validates authenticated LinkedIn session (detects expired sessions & login walls).
2. Extracts job title, company, location, and full job description.
3. Performs skill and requirement eligibility matching against candidate profile.
4. Detects already-applied status.
5. Locates and clicks Easy Apply button (or follows external apply redirects).
6. Handles multi-step modal dialogs:
   - Contact info (respecting codernitin55@gmail.com override)
   - Resume selection or upload
   - Work experience & education
   - Screening questions (radio, dropdown, combobox, number, text)
   - Accurately raises MissingInformationError for missing required questions
7. Pre-submission review & user approval gate.
8. Submission confirmation verification (Application sent / receipt detection).
"""

import re
import time
import random
import logging
from typing import Optional, Dict, List, Tuple, Any
from app.adapters.base_adapter import BaseAdapter
from app.adapters.exceptions import (
    UnsupportedFormError,
    DuplicateApplicationError,
    MissingInformationError,
    SubmissionFailedError,
    ResumeUploadError,
    LoginWallError,
    ReviewApprovalRequiredError,
)

logger = logging.getLogger(__name__)


class LinkedInAdapter(BaseAdapter):
    """
    Dedicated handler for LinkedIn Easy Apply postings.
    Interacts with .jobs-easy-apply-modal / [role='dialog'].
    """

    PLATFORM = "linkedin"

    def check_session_authentication(self):
        """
        Check if the current page indicates that the user is unauthenticated
        or redirected to a login wall.
        """
        current_url = self.page.url.lower()

        # Direct login / authwall paths
        if any(p in current_url for p in ["/login", "/authwall", "/checkpoint", "/uas/login"]):
            raise LoginWallError(
                "LinkedIn session expired or not logged in. Please connect your LinkedIn account in Settings to enable Easy Apply."
            )

        # Check for unauthenticated guest banner or modal
        guest_signals = [
            ".sign-in-modal",
            "button:has-text('Sign in to apply')",
            ".join-form",
            "a[data-tracking-control-name='public_jobs_nav-header-signin']",
        ]
        for sel in guest_signals:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    raise LoginWallError(
                        "LinkedIn login required: You are currently browsing as a guest. Please connect your LinkedIn account to access Easy Apply."
                    )
            except LoginWallError:
                raise
            except Exception:
                continue

    def extract_job_details(self) -> dict:
        """
        Extract title, company, location, and description directly from
        the LinkedIn job posting DOM, meta tags, JSON-LD, or public fallback.
        """
        details = {
            "title": "",
            "company": "",
            "location": "",
            "description": "",
        }

        # Ignore generic slogans on authwall or sign-in pages
        is_authwall = any(p in self.page.url.lower() for p in ["/authwall", "/checkpoint", "/uas/login"])

        if not is_authwall:
            # 1. Job Title
            title_selectors = [
                ".job-details-jobs-unified-top-card__job-title",
                ".jobs-unified-top-card__job-title",
                "h1.top-card-layout__title",
                "h1.t-24",
                "h1.jobs-details-top-card__job-title",
                "h1",
            ]
            for sel in title_selectors:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        txt = el.inner_text().strip()
                        if txt and not any(s in txt.lower() for s in ["find jobs", "sign in", "log in", "welcome back", "join linkedin"]):
                            details["title"] = txt
                            break
                except Exception:
                    continue

            # 2. Company Name
            company_selectors = [
                "a[data-tracking-control-name*='topcard-org-name']",
                "a[data-tracking-control-name='public_jobs_topcard-org-name']",
                ".topcard__org-name-link",
                ".topcard__flavor--black-link",
                ".topcard__flavor a",
                ".top-card-layout__first-sub-headline a",
                ".job-details-jobs-unified-top-card__company-name a",
                ".job-details-jobs-unified-top-card__company-name",
                ".jobs-unified-top-card__company-name a",
                ".jobs-unified-top-card__company-name",
                "a.jobs-details-top-card__company-url",
                ".jobs-unified-top-card__primary-description a",
                ".sub-nav-cta__sub-title",
            ]
            for sel in company_selectors:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        txt = el.inner_text().strip()
                        if txt:
                            details["company"] = txt
                            break
                except Exception:
                    continue

        # 3. Location
        loc_selectors = [
            ".topcard__flavor:not(.topcard__flavor--link)",
            ".top-card-layout__first-sub-headline span",
            ".job-details-jobs-unified-top-card__primary-description span",
            ".jobs-unified-top-card__bullet",
            ".jobs-details-top-card__bullet",
            ".topcard__flavor--bullet",
        ]
        for sel in loc_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    txt = el.inner_text().strip()
                    if txt:
                        details["location"] = txt
                        break
            except Exception:
                continue

        # 4. Job Description
        desc_selectors = [
            ".show-more-less-html__markup",
            ".jobs-description__content",
            ".jobs-box__html-content",
            "#job-details",
            ".jobs-description",
        ]
        for sel in desc_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    txt = el.inner_text().strip()
                    if txt:
                        details["description"] = txt
                        break
            except Exception:
                continue

        # 5. Check initial navigation title and HTML if available
        init_title = getattr(self, "initial_title", None) or ""
        if init_title and (not details["title"] or not details["company"]):
            pm = re.search(r"^(.*?)\s+at\s+(.*?)(?:\s+(?:in|·|•|-|\||\ufffd)|$)", init_title, re.I)
            if pm:
                if not details["title"]:
                    details["title"] = pm.group(1).strip()
                if not details["company"]:
                    details["company"] = pm.group(2).strip()

        init_html = getattr(self, "initial_html", None) or ""
        if init_html and (not details["title"] or not details["company"]):
            t_m = re.search(r"<title>(.*?)</title>", init_html, re.I)
            if t_m:
                pm = re.search(r"^(.*?)\s+at\s+(.*?)(?:\s+(?:in|·|•|-|\||\ufffd)|$)", t_m.group(1).strip(), re.I)
                if pm:
                    if not details["title"]:
                        details["title"] = pm.group(1).strip()
                    if not details["company"]:
                        details["company"] = pm.group(2).strip()
            h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", init_html, re.DOTALL)
            if h1_m and not details["title"]:
                h1_text = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip()
                if h1_text and not any(s in h1_text.lower() for s in ["find jobs", "sign in", "log in", "welcome back", "join linkedin"]):
                    details["title"] = h1_text

        # 6. Fallback regex on page title (e.g. "Role at Company · Location | LinkedIn Jobs")
        if not details["title"] or not details["company"]:
            try:
                page_title = (self.page.title() or "").strip()
                if not any(s in page_title.lower() for s in ["sign up", "sign in", "log in", "welcome back"]):
                    m = re.search(r"^(.*?)\s+at\s+(.*?)(?:\s+(?:in|·|•|-|\||\ufffd)|$)", page_title, re.I)
                    if m:
                        if not details["title"]:
                            details["title"] = m.group(1).strip()
                        if not details["company"]:
                            details["company"] = m.group(2).strip()
            except Exception:
                pass

        # 6. Fallback inspect JSON-LD
        if not details["title"] or not details["company"] or not details["description"]:
            try:
                import json
                scripts = self.page.query_selector_all("script[type='application/ld+json']")
                for s in scripts:
                    txt = s.inner_text() or ""
                    if "JobPosting" in txt:
                        data = json.loads(txt)
                        if not details["title"] and data.get("title"):
                            details["title"] = str(data["title"]).strip()
                        if not details["company"] and data.get("hiringOrganization"):
                            org = data["hiringOrganization"]
                            details["company"] = (org.get("name") if isinstance(org, dict) else str(org)).strip()
                        if not details["description"] and data.get("description"):
                            details["description"] = str(data["description"]).strip()
            except Exception:
                pass

        # 7. Public metadata fallback if redirected to authwall or company is still missing
        if not details["title"] or not details["company"]:
            target_url = self.page.url
            if "authwall" in target_url or "login" in target_url or not details["company"]:
                app_url = getattr(self, "application_url", "")
                jid_match = re.search(r"/jobs/view/(\d+)", app_url or target_url)
                if jid_match:
                    target_url = f"https://www.linkedin.com/jobs/view/{jid_match.group(1)}/"
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        target_url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        }
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        html = resp.read().decode("utf-8", errors="ignore")
                        h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
                        if h1_m and not details["title"]:
                            details["title"] = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()
                        org_m = re.search(r'data-tracking-control-name="public_jobs_topcard-org-name"[^>]*>(.*?)<', html, re.DOTALL)
                        if not org_m:
                            org_m = re.search(r'topcard__org-name-link[^>]*>(.*?)<', html, re.DOTALL)
                        if org_m and not details["company"]:
                            details["company"] = org_m.group(1).strip()
                        t_m = re.search(r'<title>(.*?)</title>', html, re.I)
                        if t_m:
                            pm = re.search(r"^(.*?)\s+at\s+(.*?)(?:\s+(?:in|·|•|-|\||\ufffd)|$)", t_m.group(1).strip(), re.I)
                            if pm:
                                if not details["title"]:
                                    details["title"] = pm.group(1).strip()
                                if not details["company"]:
                                    details["company"] = pm.group(2).strip()
                except Exception as ex:
                    self.log("WARNING", f"Public metadata fallback fetch error: {ex}")

        # 8. Clean up generic titles and provide fallback from job ID
        target_url = getattr(self, "application_url", "") or self.page.url
        jid_match = re.search(r"/jobs/view/(\d+)", target_url)
        job_id = jid_match.group(1) if jid_match else None

        if not details["title"] or any(s in details["title"].lower() for s in ["sign up", "sign in", "log in", "welcome back", "join linkedin"]):
            if job_id:
                details["title"] = f"LinkedIn Job Posting #{job_id}"
            else:
                details["title"] = "LinkedIn Job Opportunity"

        if not details["company"] or details["company"].lower() in ["company", "linkedin"]:
            details["company"] = "LinkedIn Employer"

        return details

    def analyze_job_match(self, user_profile: dict, job_description: str, job_title: str) -> dict:
        """
        Compare job requirements with the candidate's saved profile and skills
        to check eligibility and matching skills.
        """
        desc_lower = (job_description or "").lower()
        title_lower = (job_title or "").lower()

        candidate_skills = user_profile.get("skills") or []
        if isinstance(candidate_skills, str):
            candidate_skills = [s.strip() for s in candidate_skills.split(",") if s.strip()]

        # Common industry skills to detect in the JD
        common_keywords = [
            "python", "javascript", "typescript", "react", "node", "sql", "aws", "gcp",
            "docker", "kubernetes", "fastapi", "flask", "django", "java", "c++", "c#",
            "git", "linux", "html", "css", "mongodb", "postgresql", "data analysis",
            "machine learning", "rest api", "graphql", "agile", "scrum", "excel",
            "communication", "leadership", "problem solving"
        ]

        # Find skills mentioned in JD
        jd_skills = []
        for kw in common_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', desc_lower):
                jd_skills.append(kw)

        # Match with candidate skills
        matched_skills = []
        missing_skills = []

        cand_skills_lower = [str(s).lower().strip() for s in candidate_skills]

        for s in jd_skills:
            if any(s in cs or cs in s for cs in cand_skills_lower):
                matched_skills.append(s.title())
            else:
                missing_skills.append(s.title())

        # Also add candidate skills directly mentioned
        for cs in candidate_skills:
            cs_clean = str(cs).strip()
            if cs_clean.lower() in desc_lower and cs_clean.title() not in matched_skills:
                matched_skills.append(cs_clean.title())

        # Experience check
        candidate_years = user_profile.get("years_of_experience") or 0
        exp_match = re.search(r'(\d+)\+?\s*(?:-\s*(\d+))?\s*years?(?:\s*of)?\s*experience', desc_lower)
        req_years = int(exp_match.group(1)) if exp_match else None

        # Compatibility score
        total_signals = max(1, len(jd_skills))
        score = int(min(100, max(20, (len(matched_skills) / total_signals) * 100)))
        if req_years and candidate_years >= req_years:
            score = min(100, score + 15)

        verdict = "High Match" if score >= 75 else ("Moderate Match" if score >= 45 else "Growth Match")

        return {
            "score": score,
            "verdict": verdict,
            "matched_skills": matched_skills[:10],
            "missing_skills": missing_skills[:6],
            "required_years": req_years,
            "candidate_years": candidate_years,
            "job_title": job_title,
        }

    def find_and_click_apply_button(self) -> bool:
        """
        Locate and click the 'Easy Apply' button on LinkedIn job postings.
        If the job was already applied, raise DuplicateApplicationError.
        """
        self.check_session_authentication()

        # 1. Check if already applied
        if self._is_already_applied():
            self.log("WARNING", "LinkedIn: Job is already marked as Applied")
            raise DuplicateApplicationError("You have already applied for this job on LinkedIn.")

        # 2. Easy Apply button selectors
        easy_apply_selectors = [
            "button.jobs-apply-button",
            "button:has-text('Easy Apply')",
            "button[aria-label*='Easy Apply']",
            "[data-view-name*='job-apply-button']:has-text('Easy Apply')",
            ".jobs-s-apply button:has-text('Easy Apply')",
            "button:has-text('Apply now')",
        ]

        for sel in easy_apply_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    self.page.wait_for_timeout(2000)
                    self.log("INFO", f"Clicked LinkedIn Easy Apply button: {sel}")
                    return True
            except Exception:
                continue

        # Check for external apply button
        external_btn = self.page.query_selector("button:has-text('Apply'), a:has-text('Apply')")
        if external_btn and external_btn.is_visible():
            self.log("INFO", "LinkedIn: Found external apply button (redirects outside LinkedIn)")
            try:
                with self.page.context.expect_page(timeout=4000) as p_info:
                    external_btn.click()
                new_page = p_info.value
                if new_page:
                    self.page = new_page
                    self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                    return True
            except Exception:
                try:
                    external_btn.click()
                    self.page.wait_for_timeout(2000)
                    return True
                except Exception:
                    pass

        return False

    def _is_already_applied(self) -> bool:
        """Check if LinkedIn displays an 'Applied' status badge."""
        applied_selectors = [
            ".jobs-s-apply__application-link:has-text('Applied')",
            ".artdeco-inline-feedback:has-text('Applied')",
            "button:has-text('Applied')",
            "span:has-text('Applied')",
            "div:has-text('Application submitted')",
            ".jobs-apply-button:has-text('Applied')",
        ]
        for sel in applied_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    txt = (el.inner_text() or "").strip().lower()
                    if "applied" in txt or "application submitted" in txt:
                        return True
            except Exception:
                continue
        return False

    def _get_active_modal(self):
        """Return the active Easy Apply modal dialog element or fallback to page."""
        modal_selectors = [
            "div.jobs-easy-apply-modal",
            "div[role='dialog']:has-text('Easy Apply')",
            "div[role='dialog']",
            ".artdeco-modal",
        ]
        for sel in modal_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    return el
            except Exception:
                continue
        return self.page

    def extract_form_fields(self) -> list:
        """Extract visible form elements in the current Easy Apply step or page."""
        if not self.page.query_selector("div[role='dialog'], form, input"):
            self.find_and_click_apply_button()

        modal = self._get_active_modal()

        js_extract = """
        (container) => {
            const root = container || document;
            const results = [];
            const elements = root.querySelectorAll('input, select, textarea');

            for (const el of elements) {
                if (el.type === 'hidden') continue;
                if (!el.offsetParent && el.type !== 'file') continue;

                let label = '';
                if (el.id) {
                    const lbl = root.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) label = lbl.innerText.trim();
                }
                if (!label) {
                    const parent = el.closest('label, .fb-dash-form-element, .jobs-easy-apply-form-section__grouping');
                    if (parent) {
                        const lbl = parent.querySelector('label, .artdeco-text-input--label, span');
                        if (lbl) label = lbl.innerText.trim();
                    }
                }
                if (!label) {
                    label = el.getAttribute('aria-label') || el.placeholder || el.name || '';
                }

                label = label.replace(/[\\n\\r\\t]+/g, ' ').replace(/\\s+/g, ' ').replace(/\\*$/, '').trim();

                const options = [];
                if (el.tagName === 'SELECT') {
                    for (const opt of el.options) {
                        if (opt.value) options.push({ value: opt.value, text: opt.innerText.trim() });
                    }
                }

                let selector = '';
                if (el.id) {
                    selector = '#' + CSS.escape(el.id);
                } else if (el.name) {
                    selector = el.tagName.toLowerCase() + '[name="' + CSS.escape(el.name) + '"]';
                }

                results.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || (el.tagName === 'TEXTAREA' ? 'textarea' : 'text'),
                    name: el.name || '',
                    id: el.id || '',
                    label: label,
                    required: el.required || el.getAttribute('aria-required') === 'true',
                    options: options,
                    selector: selector,
                });
            }

            // Radio button groups (screening questions)
            const radioGroups = {};
            root.querySelectorAll('input[type="radio"]').forEach(radio => {
                const name = radio.name;
                if (!name) return;
                if (!radioGroups[name]) {
                    let groupLabel = '';
                    const fieldset = radio.closest('fieldset');
                    if (fieldset) {
                        const legend = fieldset.querySelector('legend');
                        if (legend) groupLabel = legend.innerText.trim();
                    }
                    radioGroups[name] = {
                        type: 'radio',
                        name: name,
                        label: groupLabel,
                        options: [],
                        required: radio.required,
                        selector: `input[name="${name}"]`,
                    };
                }
                const lbl = radio.closest('label') || root.querySelector(`label[for="${radio.id}"]`);
                const optText = lbl ? lbl.innerText.trim() : radio.value;
                radioGroups[name].options.push({ value: radio.value, text: optText });
            });

            for (const rg of Object.values(radioGroups)) {
                results.push(rg);
            }

            return results;
        }
        """

        try:
            raw_fields = self.page.evaluate(js_extract, modal)
            fields = []
            seen = set()
            for f in raw_fields:
                k = (f.get("name", ""), f.get("type", ""), f.get("label", ""))
                if k in seen and k[0]:
                    continue
                seen.add(k)
                fields.append({
                    "label": f.get("label", ""),
                    "name": f.get("name", ""),
                    "type": f.get("type", "text"),
                    "options": [o["text"] if isinstance(o, dict) else str(o) for o in f.get("options", [])],
                    "required": f.get("required", False),
                    "selector": f.get("selector", ""),
                })
            self.log("INFO", f"LinkedIn Easy Apply: Extracted {len(fields)} fields in current view")
            return fields
        except Exception as e:
            self.log("WARNING", f"LinkedIn field extraction note: {e}")
            return []

    def fill_and_submit(
        self,
        field_mapping: dict,
        resume_path: str,
        cover_letter: str = None,
        require_approval: bool = True,
        is_approved: bool = False,
    ) -> dict:
        """
        Drive through LinkedIn Easy Apply multi-step modal:
        1. Open Easy Apply modal if not open.
        2. Advance step-by-step through contact info, resume upload, screening questions.
        3. If approval is required and not yet given: pause at Review step, capture review summary.
        4. Submit application after approval.
        5. Verify submission confirmation.
        """
        self.log("INFO", "Starting LinkedIn Easy Apply multi-step flow")
        self.check_session_authentication()

        # Open modal if closed
        if not self.page.query_selector("div[role='dialog']"):
            self.find_and_click_apply_button()

        max_steps = 12
        current_step = 0
        filled_answers_summary = {}

        while current_step < max_steps:
            current_step += 1
            self.log("INFO", f"LinkedIn Easy Apply: Processing step {current_step}")
            self.page.wait_for_timeout(1200)

            # Check if modal already completed / submitted
            if self._detect_submitted():
                self.log("INFO", "LinkedIn: Application submission confirmed!")
                return {"success": True, "confirmation_url": self.page.url, "verified": True}

            modal = self._get_active_modal()

            # 1. Fill visible inputs in this step
            step_filled = self._fill_step_inputs(modal, field_mapping)
            filled_answers_summary.update(step_filled)

            # 2. Check for Resume upload on this step
            if resume_path:
                self._handle_step_resume_upload(modal, resume_path)

            # 3. Handle screening questions (radio buttons, select, combobox)
            q_filled, missing_qs = self._handle_step_screening_questions(modal, field_mapping)
            filled_answers_summary.update(q_filled)

            if missing_qs:
                self.log("WARNING", f"LinkedIn: Missing answers for required screening questions: {[q['label'] for q in missing_qs]}")
                raise MissingInformationError(
                    f"LinkedIn Easy Apply requires answering: {', '.join([q['label'] for q in missing_qs])}",
                    missing_fields=missing_qs,
                )

            # 4. Check navigation buttons: Submit -> Review -> Next
            submit_btn = self._find_button_by_text(["Submit application", "Submit"])
            review_btn = self._find_button_by_text(["Review", "Review application"])
            next_btn = self._find_button_by_text(["Next", "Continue to next step"])

            # A) Review or Submit Application step
            if submit_btn and submit_btn.is_visible():
                # Check User Approval Gate
                if require_approval and not is_approved:
                    self.log("INFO", "LinkedIn: Reached final Review step. Pausing for user approval.")
                    raise ReviewApprovalRequiredError(
                        "All fields filled and validated. Ready for your final review before submitting.",
                        review_details={
                            "summary": filled_answers_summary,
                            "url": self.page.url,
                            "step": current_step,
                        }
                    )

                self.log("INFO", "LinkedIn: Final Submit button ready. Submitting application!")
                submit_btn.scroll_into_view_if_needed()
                submit_btn.click()
                self.page.wait_for_timeout(3500)

                # Verify submission receipt
                if self._detect_submitted():
                    self._dismiss_post_submit_modal()
                    return {"success": True, "confirmation_url": self.page.url, "verified": True}
                break

            # B) Review button
            if review_btn and review_btn.is_visible():
                self.log("INFO", "LinkedIn: Clicking Review button")
                review_btn.click()
                self.page.wait_for_timeout(1500)

                # If approval is required before clicking final submit, pause at review
                if require_approval and not is_approved:
                    submit_now = self._find_button_by_text(["Submit application", "Submit"])
                    if submit_now and submit_now.is_visible():
                        raise ReviewApprovalRequiredError(
                            "Application review ready. Please inspect the review and approve to submit.",
                            review_details={
                                "summary": filled_answers_summary,
                                "url": self.page.url,
                                "step": current_step,
                            }
                        )
                continue

            # C) Next button
            if next_btn and next_btn.is_visible():
                self.log("INFO", "LinkedIn: Clicking Next button")
                next_btn.click()
                self.page.wait_for_timeout(1500)
                continue

            # If no forward button, check if submission succeeded
            if self._detect_submitted():
                return {"success": True, "confirmation_url": self.page.url, "verified": True}

            break

        # Final verification check
        if self._detect_submitted():
            return {"success": True, "confirmation_url": self.page.url, "verified": True}

        raise SubmissionFailedError("LinkedIn Easy Apply flow completed without submission confirmation.")

    def _fill_step_inputs(self, modal, field_mapping: dict) -> dict:
        """Fill standard text, phone, and email inputs on the active step."""
        filled = {}
        inputs = modal.query_selector_all("input[type='text'], input[type='tel'], input[type='email']")
        for inp in inputs:
            try:
                if not inp.is_visible():
                    continue
                current_val = inp.input_value()
                lbl = self._get_label_for_input(inp)

                # Strict email override rule
                if "email" in lbl.lower() or inp.get_attribute("type") == "email":
                    if "nitinchandra834@gmail.com" in current_val.lower() or not current_val:
                        inp.fill("codernitin55@gmail.com")
                        filled[lbl or "Email"] = "codernitin55@gmail.com"
                        continue

                if current_val:  # LinkedIn often pre-fills profile values
                    filled[lbl or "Field"] = current_val
                    continue

                matched_val = self._find_value_in_mapping(lbl, field_mapping)
                if matched_val:
                    # Double-check strict email override
                    if isinstance(matched_val, str) and "nitinchandra834@gmail.com" in matched_val.lower():
                        matched_val = "codernitin55@gmail.com"
                    inp.fill(str(matched_val))
                    filled[lbl] = str(matched_val)
                    time.sleep(random.uniform(0.1, 0.2))
            except Exception:
                continue
        return filled

    def _handle_step_resume_upload(self, modal, resume_path: str):
        """Upload resume if a file upload input is present on the current step."""
        file_input = modal.query_selector("input[type='file']")
        if file_input:
            try:
                self.log("INFO", f"LinkedIn Easy Apply: Uploading resume file: {resume_path}")
                file_input.set_input_files(resume_path)
                self.page.wait_for_timeout(1500)
            except Exception as e:
                self.log("WARNING", f"LinkedIn resume upload warning: {e}")

        # Check for radio selection of already-uploaded resumes
        resume_cards = modal.query_selector_all(".jobs-document-upload__file-name, input[type='radio'][id*='resume']")
        if resume_cards:
            try:
                # Pick the first available resume card
                first_card = modal.query_selector("input[type='radio'][id*='resume'], .jobs-document-upload__title-button")
                if first_card and not first_card.is_checked():
                    first_card.check()
            except Exception:
                pass

    def _handle_step_screening_questions(self, modal, field_mapping: dict) -> Tuple[dict, list]:
        """
        Answer radio groups, dropdowns, and text/number screening questions.
        Returns: (filled_dict, missing_required_questions_list)
        """
        filled = {}
        missing = []

        # 1. Radio groups (e.g. Yes/No, sponsorship, relocation)
        fieldsets = modal.query_selector_all("fieldset")
        for fs in fieldsets:
            try:
                legend = fs.query_selector("legend")
                question_text = (legend.inner_text() if legend else "").strip()
                if not question_text:
                    continue

                is_required = bool(fs.query_selector("[aria-required='true'], [required]")) or "*" in question_text
                question_clean = question_text.replace("*", "").strip()

                answer = self._find_value_in_mapping(question_clean, field_mapping)
                radios = fs.query_selector_all("input[type='radio']")
                any_checked = any(r.is_checked() for r in radios)

                if answer:
                    ans_lower = str(answer).strip().lower()
                    for r in radios:
                        lbl = modal.query_selector(f"label[for='{r.get_attribute('id')}']")
                        opt_text = (lbl.inner_text() if lbl else r.get_attribute("value") or "").lower()
                        if (ans_lower in ["yes", "true", "1"] and "yes" in opt_text) or \
                           (ans_lower in ["no", "false", "0"] and "no" in opt_text) or \
                           (ans_lower == opt_text):
                            r.check()
                            filled[question_clean] = opt_text.title()
                            any_checked = True
                            break

                if is_required and not any_checked:
                    options = []
                    for r in radios:
                        lbl = modal.query_selector(f"label[for='{r.get_attribute('id')}']")
                        opt_text = lbl.inner_text().strip() if lbl else r.get_attribute("value") or ""
                        options.append(opt_text)

                    missing.append({
                        "key": question_clean.lower().replace(" ", "_")[:30],
                        "label": question_clean,
                        "type": "yes_no" if len(options) == 2 and "yes" in options[0].lower() else "select",
                        "options": options,
                        "required": True,
                    })
            except Exception:
                continue

        # 2. Select dropdowns
        selects = modal.query_selector_all("select")
        for sel in selects:
            try:
                if not sel.is_visible():
                    continue
                current_val = sel.input_value()
                lbl = self._get_label_for_input(sel)
                is_req = sel.is_required() or sel.get_attribute("aria-required") == "true" or "*" in lbl

                answer = self._find_value_in_mapping(lbl, field_mapping)
                if answer:
                    sel.select_option(label=str(answer))
                    filled[lbl] = str(answer)
                elif is_req and not current_val:
                    opts = [opt.inner_text().strip() for opt in sel.query_selector_all("option") if opt.get_attribute("value")]
                    missing.append({
                        "key": lbl.lower().replace(" ", "_")[:30],
                        "label": lbl,
                        "type": "select",
                        "options": opts,
                        "required": True,
                    })
            except Exception:
                continue

        # 3. Numeric screening inputs (e.g. "How many years of experience do you have with Python?")
        number_inputs = modal.query_selector_all("input[type='number'], input[id*='numeric'], input[id*='experience']")
        for inp in number_inputs:
            try:
                if not inp.is_visible() or inp.input_value():
                    continue
                lbl = self._get_label_for_input(inp)
                ans = self._find_value_in_mapping(lbl, field_mapping)
                if ans is not None and str(ans).strip():
                    inp.fill(str(ans))
                    filled[lbl] = str(ans)
                elif inp.get_attribute("aria-required") == "true" or inp.is_required():
                    missing.append({
                        "key": lbl.lower().replace(" ", "_")[:30],
                        "label": lbl,
                        "type": "number",
                        "options": [],
                        "required": True,
                    })
            except Exception:
                continue

        return filled, missing

    def _find_button_by_text(self, text_candidates: list):
        """Find the first matching visible button among candidates."""
        for txt in text_candidates:
            for btn in self.page.query_selector_all(f"button:has-text('{txt}'), [role='button']:has-text('{txt}')"):
                try:
                    if btn and btn.is_visible():
                        return btn
                except Exception:
                    continue
        return None

    def _detect_submitted(self) -> bool:
        """Check if LinkedIn displays an application submitted confirmation message."""
        success_signals = [
            "application sent",
            "your application was sent",
            "applied on",
            "application submitted",
        ]
        try:
            body = (self.page.inner_text("body") or "").lower()
            return any(sig in body for sig in success_signals)
        except Exception:
            return False

    def _dismiss_post_submit_modal(self):
        """Close post-submission follow/notification modal if open."""
        try:
            dismiss_btn = self.page.query_selector("button[aria-label='Dismiss'], button:has-text('Done')")
            if dismiss_btn and dismiss_btn.is_visible():
                dismiss_btn.click()
        except Exception:
            pass

    def _get_label_for_input(self, el) -> str:
        """Helper to resolve human-readable label for an input."""
        try:
            el_id = el.get_attribute("id")
            if el_id:
                lbl = self.page.query_selector(f"label[for='{el_id}']")
                if lbl:
                    return lbl.inner_text().strip()
            parent = el.closest("label, .fb-dash-form-element, .jobs-easy-apply-form-section__grouping")
            if parent:
                lbl = parent.query_selector("label, span, .artdeco-text-input--label")
                if lbl:
                    return lbl.inner_text().strip()
            return el.get_attribute("aria-label") or el.get_attribute("placeholder") or el.get_attribute("name") or ""
        except Exception:
            return ""

    def _find_value_in_mapping(self, label: str, mapping: dict):
        """Match question/field label against dictionary mapping."""
        if not label or not mapping:
            return None
        lbl_norm = label.lower().strip()
        for k, v in mapping.items():
            k_norm = k.lower().strip()
            if k_norm == lbl_norm or k_norm in lbl_norm or lbl_norm in k_norm:
                return v
        return None
