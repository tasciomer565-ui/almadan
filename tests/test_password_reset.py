from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import app.auth as auth
from app.main import (
    PASSWORD_RESET_LIMIT,
    password_reset_key,
    password_reset_retry_after,
    record_password_reset,
)


class PasswordResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_key = auth.SUPABASE_PUBLISHABLE_KEY
        auth.SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test"

    def tearDown(self) -> None:
        auth.SUPABASE_PUBLISHABLE_KEY = self.original_key

    @patch("app.auth.supabase_base_url", return_value="https://project.supabase.co")
    @patch("app.auth.requests.request")
    def test_reset_email_uses_recovery_endpoint(
        self,
        request_mock: Mock,
        _base_url_mock: Mock,
    ) -> None:
        response = Mock(ok=True, content=b"{}")
        response.json.return_value = {}
        request_mock.return_value = response

        auth.request_password_reset(
            "user@example.com",
            "https://almadan.vercel.app",
        )

        request_mock.assert_called_once()
        args, kwargs = request_mock.call_args
        self.assertEqual(args[0], "POST")
        self.assertIn("/auth/v1/recover?redirect_to=https://almadan.vercel.app", args[1])
        self.assertEqual(kwargs["json"], {"email": "user@example.com"})

    @patch("app.auth.supabase_base_url", return_value="https://project.supabase.co")
    @patch("app.auth.requests.request")
    def test_password_update_uses_user_token(
        self,
        request_mock: Mock,
        _base_url_mock: Mock,
    ) -> None:
        response = Mock(ok=True, content=b'{"id":"user-1"}')
        response.json.return_value = {"id": "user-1"}
        request_mock.return_value = response

        result = auth.update_password("access-token", "new-password")

        args, kwargs = request_mock.call_args
        self.assertEqual(args[0], "PUT")
        self.assertTrue(args[1].endswith("/auth/v1/user"))
        self.assertEqual(kwargs["json"], {"password": "new-password"})
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer access-token",
        )
        self.assertEqual(result["id"], "user-1")

    def test_third_reset_request_is_rate_limited(self) -> None:
        db = {"password_reset_attempts": {}}

        for _ in range(PASSWORD_RESET_LIMIT):
            self.assertEqual(
                password_reset_retry_after(db, "User@Example.com"),
                0,
            )
            record_password_reset(db, "user@example.com")

        self.assertGreater(
            password_reset_retry_after(db, "USER@example.com"),
            0,
        )

    def test_old_reset_requests_expire(self) -> None:
        old_timestamp = (
            datetime.now(timezone.utc) - timedelta(minutes=16)
        ).isoformat()
        db = {
            "password_reset_attempts": {
                password_reset_key("user@example.com"): [
                    old_timestamp,
                    old_timestamp,
                ]
            }
        }

        self.assertEqual(
            password_reset_retry_after(db, "user@example.com"),
            0,
        )


if __name__ == "__main__":
    unittest.main()
