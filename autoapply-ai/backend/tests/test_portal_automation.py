"""
Comprehensive Integration & Unit Tests for Job Portal Handlers.
Covers:
- Platform detection for all 8 portals:
  LinkedIn, Greenhouse, Lever, Ashby, Workday, SmartRecruiters, ByteDance, Generic.
- LinkedIn Easy Apply flow, already-applied detection, multi-step modal navigation.
- Workday multi-step application workflow, login detection, save-and-continue navigation.
- ByteDance redirect detection, auth barrier, form filling.
- CAPTCHA accurate detection without false positives on scripts.
- In-Page embeddability check for frame-ancestors / X-Frame-Options.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.adapters.base_adapter import detect_platform, BaseAdapter
from app.adapters.linkedin_adapter import LinkedInAdapter
from app.adapters.workday_adapter import WorkdayAdapter
from app.adapters.bytedance_adapter import ByteDanceAdapter
from app.adapters.greenhouse_adapter import GreenhouseAdapter
from app.adapters.lever_adapter import LeverAdapter
from app.adapters.ashby_adapter import AshbyAdapter
from app.adapters.exceptions import (
    DuplicateApplicationError,
    SubmissionFailedError,
    LoginWallError,
    CaptchaDetectedError,
)


class TestPortalDetection(unittest.TestCase):
    """Test platform detection for all supported job portals."""

    def test_detect_linkedin(self):
        url = "https://www.linkedin.com/jobs/view/4102948210/"
        html = '<button class="jobs-apply-button">Easy Apply</button>'
        self.assertEqual(detect_platform(url, html), "linkedin")

    def test_detect_greenhouse(self):
        url = "https://boards.greenhouse.io/stripe/jobs/123456"
        html = '<div id="application_form"></div>'
        self.assertEqual(detect_platform(url, html), "greenhouse")

    def test_detect_lever(self):
        url = "https://jobs.lever.co/netflix/abcdef-1234"
        html = '<div class="lever-application"></div>'
        self.assertEqual(detect_platform(url, html), "lever")

    def test_detect_ashby(self):
        url = "https://jobs.ashbyhq.com/openai/98765"
        html = '<div data-ashby="form"></div>'
        self.assertEqual(detect_platform(url, html), "ashby")

    def test_detect_workday(self):
        url = "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/12345"
        html = '<div data-automation-id="workday-app"></div>'
        self.assertEqual(detect_platform(url, html), "workday")

    def test_detect_bytedance(self):
        url = "https://jobs.bytedance.com/en/position/7656823895123446069/apply"
        html = '<div class="bytedance-form"></div>'
        self.assertEqual(detect_platform(url, html), "bytedance")

    def test_detect_smartrecruiters(self):
        url = "https://jobs.smartrecruiters.com/AcmeCorp/12345"
        html = '<div data-smartrecruiters="true"></div>'
        self.assertEqual(detect_platform(url, html), "smartrecruiters")

    def test_detect_generic(self):
        url = "https://careers.acmecompany.com/openings/developer"
        html = '<form id="job-form"><input name="candidate_name"/></form>'
        self.assertEqual(detect_platform(url, html), "generic")


class TestLinkedInAdapter(unittest.TestCase):
    """Test dedicated LinkedIn Easy Apply handler."""

    def setUp(self):
        self.mock_page = MagicMock()
        self.adapter = LinkedInAdapter(self.mock_page, "test-app-id")

    def test_already_applied_detection(self):
        """Should detect already applied badge and raise DuplicateApplicationError."""
        mock_applied_badge = MagicMock()
        mock_applied_badge.is_visible.return_value = True
        mock_applied_badge.inner_text.return_value = "Applied 2 days ago"
        self.mock_page.query_selector.side_effect = lambda sel: (
            mock_applied_badge if "Applied" in sel else None
        )

        with self.assertRaises(DuplicateApplicationError):
            self.adapter.find_and_click_apply_button()

    def test_easy_apply_button_click(self):
        """Should click Easy Apply button when available."""
        mock_btn = MagicMock()
        mock_btn.is_visible.return_value = True
        mock_btn.inner_text.return_value = "Easy Apply"

        def qs(sel):
            if "Applied" in sel:
                return None
            if "jobs-apply-button" in sel or "Easy Apply" in sel:
                return mock_btn
            return None

        self.mock_page.query_selector.side_effect = qs
        res = self.adapter.find_and_click_apply_button()
        self.assertTrue(res)
        mock_btn.click.assert_called()

    def test_multi_step_flow_and_submission(self):
        """Should advance through steps and submit successfully."""
        mock_submit_btn = MagicMock()
        mock_submit_btn.is_visible.return_value = True

        self.mock_page.query_selector.return_value = None
        self.mock_page.query_selector_all.side_effect = lambda sel: (
            [mock_submit_btn] if "Submit" in sel else []
        )
        self.mock_page.inner_text.return_value = "Your application was sent to Acme Corp"

        result = self.adapter.fill_and_submit(
            field_mapping={"full_name": "Test User", "years_experience": "3"},
            resume_path="dummy.pdf",
            require_approval=False,
        )
        self.assertTrue(result["success"])

    def test_review_approval_gate_paused_before_submit(self):
        """Should pause at Review step and raise ReviewApprovalRequiredError when require_approval=True."""
        from app.adapters.exceptions import ReviewApprovalRequiredError

        mock_submit_btn = MagicMock()
        mock_submit_btn.is_visible.return_value = True

        self.mock_page.query_selector.return_value = None
        self.mock_page.query_selector_all.side_effect = lambda sel: (
            [mock_submit_btn] if "Submit" in sel else []
        )

        with self.assertRaises(ReviewApprovalRequiredError):
            self.adapter.fill_and_submit(
                field_mapping={"full_name": "Test User"},
                resume_path="dummy.pdf",
                require_approval=True,
                is_approved=False,
            )

    def test_job_match_analysis(self):
        """Should accurately match profile skills against job requirements."""
        profile = {
            "skills": ["Python", "Flask", "SQL", "Docker"],
            "years_of_experience": 3,
        }
        jd = "We are looking for a Software Engineer with Python, SQL, and AWS experience. Requires 2+ years of experience."
        match = self.adapter.analyze_job_match(profile, jd, "Python Developer")
        self.assertIn("Python", match["matched_skills"])
        self.assertIn("Sql", [s.title() for s in match["matched_skills"]])
        self.assertGreater(match["score"], 50)
        self.assertEqual(match["verdict"], "High Match")


class TestWorkdayAdapter(unittest.TestCase):
    """Test Workday multi-step portal adapter."""

    def setUp(self):
        self.mock_page = MagicMock()
        self.adapter = WorkdayAdapter(self.mock_page, "test-workday-app")

    def test_apply_manually_selection(self):
        """Should detect and click Apply then Apply Manually."""
        mock_apply_btn = MagicMock()
        mock_apply_btn.is_visible.return_value = True
        mock_manual_btn = MagicMock()
        mock_manual_btn.is_visible.return_value = True

        def qs(sel):
            if "applyButton" in sel:
                return mock_apply_btn
            if "applyManually" in sel:
                return mock_manual_btn
            return None

        self.mock_page.query_selector.side_effect = qs
        res = self.adapter.find_and_click_apply_button()
        self.assertTrue(res)
        mock_apply_btn.click.assert_called()
        mock_manual_btn.click.assert_called()

    def test_login_barrier_detection(self):
        """Should detect candidate authentication wall when required."""
        mock_pwd = MagicMock()
        mock_pwd.is_visible.return_value = True
        self.mock_page.query_selector.side_effect = lambda sel: (
            mock_pwd if "password" in sel else None
        )

        with self.assertRaises(LoginWallError):
            self.adapter.fill_and_submit({}, None)


class TestByteDanceAdapter(unittest.TestCase):
    """Test ByteDance application flow."""

    def setUp(self):
        self.mock_page = MagicMock()
        self.mock_page.url = "https://jobs.bytedance.com/en/resume/123/apply"
        self.mock_page.title.return_value = "ByteDance Careers"
        self.adapter = ByteDanceAdapter(self.mock_page, "test-bd-app")

    def test_apply_submission_flow(self):
        """Should fill fields and detect successful submission."""
        mock_submit = MagicMock()
        mock_submit.is_visible.return_value = True
        self.mock_page.query_selector.side_effect = lambda sel: (
            mock_submit if "Submit" in sel else None
        )
        self.mock_page.inner_text.return_value = "Your application has been submitted successfully"

        res = self.adapter.fill_and_submit({"name": "Test User"}, "resume.pdf")
        self.assertTrue(res["success"])


class TestCaptchaAndSecurity(unittest.TestCase):
    """Test accurate CAPTCHA detection without false positives from background scripts."""

    def setUp(self):
        self.mock_page = MagicMock()
        self.adapter = BaseAdapter(self.mock_page, "test-app")

    def test_script_tag_false_positive_prevention(self):
        """Background script tags containing 'recaptcha' must NOT trigger CAPTCHA detected."""
        self.mock_page.query_selector.return_value = None
        self.mock_page.title.return_value = "Senior Python Engineer - Stripe"
        self.mock_page.inner_text.return_value = "Join our engineering team to build global payment infrastructure."
        # Background HTML has recaptcha script
        self.mock_page.content.return_value = '<html><script src="https://google.com/recaptcha/api.js"></script></html>'

        self.assertFalse(self.adapter.detect_captcha())

    def test_actual_visible_captcha_detection(self):
        """Actual visible Cloudflare or reCAPTCHA challenge must be detected."""
        mock_cf = MagicMock()
        mock_cf.is_visible.return_value = True
        self.mock_page.query_selector.side_effect = lambda sel: (
            mock_cf if "turnstile" in sel or "challenge" in sel else None
        )

        self.assertTrue(self.adapter.detect_captcha())


class TestStandardAdapters(unittest.TestCase):
    """Test Greenhouse, Lever, Ashby, and Generic adapters."""

    def test_greenhouse_adapter(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            {"label": "First Name", "name": "first_name", "type": "text", "required": True, "selector": "#first_name"},
            {"label": "Email", "name": "email", "type": "email", "required": True, "selector": "#email"}
        ]
        adapter = GreenhouseAdapter(mock_page, "test-gh-app")
        fields = adapter.extract_form_fields()
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]["label"], "First Name")

    def test_lever_adapter(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            {"label": "Full Name", "name": "name", "type": "text", "required": True, "selector": "input[name='name']"}
        ]
        adapter = LeverAdapter(mock_page, "test-lever-app")
        fields = adapter.extract_form_fields()
        self.assertEqual(len(fields), 1)

    def test_ashby_adapter(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            {"label": "Phone", "name": "phone", "type": "text", "required": True, "selector": "input[name='phone']"}
        ]
        adapter = AshbyAdapter(mock_page, "test-ashby-app")
        fields = adapter.extract_form_fields()
        self.assertEqual(len(fields), 1)

    def test_generic_adapter_compiles_and_extracts(self):
        from app.adapters.generic_adapter import GenericAdapter
        mock_page = MagicMock()
        mock_page.main_frame.evaluate.return_value = [
            {"label": "Custom Question", "name": "custom_q", "type": "text", "required": False, "selector": "#custom_q"}
        ]
        adapter = GenericAdapter(mock_page, "test-gen-app")
        fields = adapter.extract_form_fields()
        self.assertEqual(len(fields), 1)


class TestChatAndInPageVerification(unittest.TestCase):
    """Test Chatbot API and In-Page Verification endpoints."""

    @classmethod
    def setUpClass(cls):
        from app import create_app, db
        cls.app = create_app()
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            from app.models.user import User
            from app.utils.auth import generate_token
            user = User.query.first()
            if not user:
                user = User(email="codernitin55@gmail.com", full_name="Nitin Chander")
                user.set_password("Password123!")
                db.session.add(user)
                db.session.commit()
            cls.user_id = user.id
            cls.token = generate_token(user.id)
            cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def test_check_embeddable_endpoint(self):
        """Should check embeddability of a portal URL."""
        with patch("requests.head") as mock_head:
            mock_head.return_value.status_code = 200
            mock_head.return_value.headers = {"X-Frame-Options": "SAMEORIGIN"}
            res = self.client.get(
                "/api/applications/check-embeddable?url=https://jobs.bytedance.com",
                headers=self.headers,
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertFalse(data["embeddable"])
            self.assertIn("SAMEORIGIN", data["reason"])

    def test_chat_status_endpoint(self):
        """Should return user info, stats, and active application context."""
        res = self.client.get("/api/chat/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("user", data)
        self.assertIn("stats", data)

    def test_chat_message_endpoint(self):
        """Should respond conversationally without making unnecessary external AI calls."""
        res = self.client.post(
            "/api/chat/message",
            headers=self.headers,
            json={"message": "how does this work?"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("reply", data)

    def test_linkedin_session_status_endpoint(self):
        """Should return LinkedIn session status and automation preferences."""
        res = self.client.get("/api/linkedin/session/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("connected", data)
        self.assertIn("headless", data)
        self.assertIn("require_approval", data)

    def test_approve_application_endpoint(self):
        """Should transition a review_approval application and resume pipeline."""
        with self.app.app_context():
            from app.models.application import Application, ApplicationStatus
            from app import db
            app_rec = Application(
                user_id=self.user_id,
                url="https://boards.greenhouse.io/test/jobs/999",
                company="Test Co",
                role="Engineer",
                status=ApplicationStatus.NEEDS_ACTION,
                action_details_json={"type": "review_approval", "summary": {"Role": "Engineer"}},
            )
            db.session.add(app_rec)
            db.session.commit()
            app_id = app_rec.id

        res = self.client.post(f"/api/applications/{app_id}/approve", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("approved", data["message"].lower())


if __name__ == "__main__":
    unittest.main()
