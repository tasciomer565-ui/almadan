from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import app.auth as auth
from app.main import normalize_phone


class SmsAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_key = auth.SUPABASE_PUBLISHABLE_KEY
        auth.SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test"

    def tearDown(self) -> None:
        auth.SUPABASE_PUBLISHABLE_KEY = self.original_key

    def test_normalize_phone(self) -> None:
        # Standard Turkish format
        self.assertEqual(normalize_phone("0555 123 4567"), "+905551234567")
        self.assertEqual(normalize_phone("5551234567"), "+905551234567")
        self.assertEqual(normalize_phone("+905551234567"), "+905551234567")
        self.assertEqual(normalize_phone("00905551234567"), "+905551234567")
        # International formats
        self.assertEqual(normalize_phone("+14155552671"), "+14155552671")

    @patch("app.auth.supabase_base_url", return_value="https://project.supabase.co")
    @patch("app.auth.requests.request")
    def test_send_otp_sends_phone_payload(
        self,
        request_mock: Mock,
        _base_url_mock: Mock,
    ) -> None:
        response = Mock(ok=True, content=b"{}")
        response.json.return_value = {}
        request_mock.return_value = response

        auth.send_otp("+905551234567")

        request_mock.assert_called_once()
        args, kwargs = request_mock.call_args
        self.assertEqual(args[0], "POST")
        self.assertIn("/auth/v1/otp", args[1])
        self.assertEqual(kwargs["json"], {"phone": "+905551234567"})

    @patch("app.auth.supabase_base_url", return_value="https://project.supabase.co")
    @patch("app.auth.requests.request")
    def test_verify_otp_sends_sms_payload(
        self,
        request_mock: Mock,
        _base_url_mock: Mock,
    ) -> None:
        response = Mock(ok=True, content=b'{"access_token":"token-123","user":{"id":"user-otp"}}')
        response.json.return_value = {"access_token": "token-123", "user": {"id": "user-otp"}}
        request_mock.return_value = response

        result = auth.verify_otp("+905551234567", "123456")

        request_mock.assert_called_once()
        args, kwargs = request_mock.call_args
        self.assertEqual(args[0], "POST")
        self.assertIn("/auth/v1/verify", args[1])
        self.assertEqual(kwargs["json"], {"phone": "+905551234567", "token": "123456", "type": "sms"})
        self.assertEqual(result["access_token"], "token-123")


if __name__ == "__main__":
    unittest.main()
