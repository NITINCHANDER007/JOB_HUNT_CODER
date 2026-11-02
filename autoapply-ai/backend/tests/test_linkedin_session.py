"""
Unit and Integration Tests for LinkedIn Session Management and Strict Rules.
"""

import os
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.services.browser_session_service import (
    get_user_profile_dir,
    get_storage_state_path,
    get_linkedin_session_status,
    disconnect_linkedin_session,
)
from app.adapters.linkedin_adapter import LinkedInAdapter


class TestLinkedInSessionService(unittest.TestCase):
    """Test dedicated Chrome persistent profile and session verification."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.user_id = "test-user-session-123"

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_user_profile_dir(self):
        """Should create a dedicated profile directory for the user."""
        profile_dir = get_user_profile_dir(self.user_id)
        self.assertTrue(os.path.exists(profile_dir))
        self.assertIn(self.user_id, profile_dir)

    def test_session_status_not_connected(self):
        """Should report Not Connected when no storage_state exists."""
        status = get_linkedin_session_status("non-existent-user-999")
        self.assertFalse(status["connected"])
        self.assertEqual(status["status"], "Not Connected")

    def test_session_status_valid_cookie(self):
        """Should detect valid, non-expired li_at cookie."""
        uid = "user-valid-cookie-test"
        state_file = get_storage_state_path(uid)
        os.makedirs(os.path.dirname(state_file), exist_ok=True)

        future_exp = (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        fake_state = {
            "cookies": [
                {
                    "name": "li_at",
                    "value": "fake_linkedin_token_xyz",
                    "domain": ".linkedin.com",
                    "path": "/",
                    "expires": future_exp,
                }
            ]
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(fake_state, f)

        status = get_linkedin_session_status(uid)
        self.assertTrue(status["connected"])
        self.assertEqual(status["status"], "Authenticated")
        self.assertGreater(status["days_remaining"], 0)

        # Disconnect test
        disc = disconnect_linkedin_session(uid)
        self.assertTrue(disc["success"])
        status_after = get_linkedin_session_status(uid)
        self.assertFalse(status_after["connected"])

    def test_focus_and_cancel_interactive_browser(self):
        """Test focus_interactive_browser and cancel_interactive_login behaviors."""
        from app.services.browser_session_service import (
            _active_interactive_sessions,
            focus_interactive_browser,
            cancel_interactive_login,
            get_interactive_session_info,
        )

        uid = "test-focus-user-1"
        # 1. When no active session exists
        res = focus_interactive_browser(uid)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "closed")

        # 2. When active session exists and waiting for user
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 99999

        _active_interactive_sessions[uid] = {
            "session_id": "sess_1",
            "status": "waiting_for_user",
            "browser_verified": True,
            "proc": mock_proc,
            "pid": 99999,
            "cdp_port": 9222,
            "cdp_url": "http://127.0.0.1:9222",
            "message": "Chrome browser window is open on your desktop!",
        }

        with patch("app.services.browser_session_service.bring_window_to_front", return_value=True):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps([{"id": "tab1"}]).encode()
                mock_resp.__enter__.return_value = mock_resp
                mock_urlopen.return_value = mock_resp

                focus_res = focus_interactive_browser(uid)
                self.assertTrue(focus_res["success"])
                self.assertEqual(focus_res["status"], "waiting_for_user")

        # 3. get_interactive_session_info should not include raw proc
        info = get_interactive_session_info(uid)
        self.assertNotIn("proc", info)
        self.assertEqual(info["status"], "waiting_for_user")

        # 4. cancel_interactive_login terminates process and cleans up
        cancel_res = cancel_interactive_login(uid)
        self.assertTrue(cancel_res["success"])
        mock_proc.terminate.assert_called_once()
        self.assertEqual(_active_interactive_sessions[uid]["status"], "cancelled")

    def test_strict_email_rule_enforcement(self):
        """Strict instruction: never use nitinchandra834@gmail.com, use codernitin55@gmail.com."""
        mock_page = MagicMock()
        adapter = LinkedInAdapter(mock_page, "strict-email-test")

        mock_email_input = MagicMock()
        mock_email_input.is_visible.return_value = True
        mock_email_input.get_attribute.return_value = "email"
        mock_email_input.input_value.return_value = "nitinchandra834@gmail.com"

        mock_modal = MagicMock()
        mock_modal.query_selector_all.return_value = [mock_email_input]

        with patch.object(adapter, "_get_label_for_input", return_value="Email Address"):
            filled = adapter._fill_step_inputs(
                mock_modal,
                field_mapping={"Email Address": "nitinchandra834@gmail.com"}
            )
            mock_email_input.fill.assert_called_with("codernitin55@gmail.com")
            self.assertEqual(filled.get("Email Address"), "codernitin55@gmail.com")
            self.assertNotIn("nitinchandra834@gmail.com", str(filled))


if __name__ == "__main__":
    unittest.main()

