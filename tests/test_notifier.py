"""
Notifier Testleri

Gerçek HTTP/SMTP göndermeden kanalları test eder.
"""
from __future__ import annotations

import unittest
import unittest.mock as mock

import app.notifier as notifier_mod
from app.notifier import (
    notify_failure,
    notify_recovery,
    notify_health_result,
    notifier_status,
    _build_message,
    _strip_html_tags,
)


class TestMessageBuilder(unittest.TestCase):
    def test_build_message_contains_title(self):
        msg = _build_message("TEST BAŞLIK", "detay", test_name="x", ts="2026-01-01", level="error")
        self.assertIn("TEST BAŞLIK", msg)

    def test_build_message_contains_body(self):
        msg = _build_message("t", "bu bir hata detayı", test_name="x", ts="2026-01-01", level="error")
        self.assertIn("bu bir hata detayı", msg)

    def test_build_message_body_truncated_at_800(self):
        long_body = "x" * 1000
        msg = _build_message("t", long_body, test_name="TESTNAME", ts="ts", level="error")
        # body[:800] uygulandığından 1000 x yerine 800 x olmalı
        self.assertLessEqual(msg.count("x"), 800)

    def test_strip_html_tags(self):
        self.assertEqual(_strip_html_tags("<b>merhaba</b> <i>dünya</i>"), "merhaba dünya")

    def test_strip_html_tags_empty(self):
        self.assertEqual(_strip_html_tags(""), "")


class TestNotifierStatus(unittest.TestCase):
    def test_status_both_unconfigured(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", ""):
            with mock.patch.object(notifier_mod, "_TG_CHAT", ""):
                with mock.patch.object(notifier_mod, "_SMTP_HOST", ""):
                    with mock.patch.object(notifier_mod, "_NOTIFY_EMAIL", ""):
                        s = notifier_status()
        self.assertFalse(s["telegram_configured"])
        self.assertFalse(s["email_configured"])

    def test_status_telegram_configured(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "abc123"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "-100123"):
                s = notifier_status()
        self.assertTrue(s["telegram_configured"])

    def test_status_email_configured(self):
        with mock.patch.object(notifier_mod, "_SMTP_HOST", "smtp.gmail.com"):
            with mock.patch.object(notifier_mod, "_NOTIFY_EMAIL", "admin@example.com"):
                s = notifier_status()
        self.assertTrue(s["email_configured"])
        self.assertEqual(s["notify_email"], "admin@example.com")


class TestTelegramChannel(unittest.TestCase):
    def _patched_send(self, ok=True):
        resp = mock.MagicMock()
        resp.ok = ok
        resp.status_code = 200 if ok else 400
        resp.text = ""
        return resp

    def test_telegram_sends_when_configured(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "fake_token"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "12345"):
                with mock.patch("requests.post", return_value=self._patched_send(True)) as m:
                    result = notify_failure("test hata", test_name="t1")
        self.assertTrue(result["telegram"])
        m.assert_called_once()

    def test_telegram_skipped_when_unconfigured(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", ""):
            with mock.patch.object(notifier_mod, "_TG_CHAT", ""):
                with mock.patch("requests.post") as m:
                    result = notify_failure("test")
        m.assert_not_called()
        self.assertFalse(result["telegram"])

    def test_telegram_returns_false_on_api_error(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "bad_token"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "123"):
                with mock.patch("requests.post", return_value=self._patched_send(False)):
                    result = notify_failure("test")
        self.assertFalse(result["telegram"])

    def test_telegram_returns_false_on_exception(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "tok"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "123"):
                with mock.patch("requests.post", side_effect=ConnectionError("timeout")):
                    result = notify_failure("test")
        self.assertFalse(result["telegram"])


class TestEmailChannel(unittest.TestCase):
    def test_email_skipped_when_unconfigured(self):
        with mock.patch.object(notifier_mod, "_SMTP_HOST", ""):
            with mock.patch.object(notifier_mod, "_NOTIFY_EMAIL", ""):
                with mock.patch("smtplib.SMTP") as m:
                    result = notify_failure("test")
        m.assert_not_called()
        self.assertFalse(result["email"])

    def test_email_sends_when_configured(self):
        smtp_mock = mock.MagicMock()
        smtp_mock.__enter__ = mock.MagicMock(return_value=smtp_mock)
        smtp_mock.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch.object(notifier_mod, "_SMTP_HOST", "smtp.example.com"):
            with mock.patch.object(notifier_mod, "_SMTP_USER", "user@example.com"):
                with mock.patch.object(notifier_mod, "_SMTP_PASS", "pass"):
                    with mock.patch.object(notifier_mod, "_NOTIFY_EMAIL", "admin@example.com"):
                        with mock.patch.object(notifier_mod, "_TG_TOKEN", ""):
                            with mock.patch("smtplib.SMTP", return_value=smtp_mock):
                                result = notify_failure("test hata")
        self.assertTrue(result["email"])

    def test_email_returns_false_on_smtp_error(self):
        with mock.patch.object(notifier_mod, "_SMTP_HOST", "smtp.example.com"):
            with mock.patch.object(notifier_mod, "_NOTIFY_EMAIL", "admin@example.com"):
                with mock.patch.object(notifier_mod, "_TG_TOKEN", ""):
                    with mock.patch("smtplib.SMTP", side_effect=OSError("connection refused")):
                        result = notify_failure("test")
        self.assertFalse(result["email"])


class TestHealthResultLogic(unittest.TestCase):
    def test_failure_always_notifies(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "tok"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "123"):
                with mock.patch("requests.post", return_value=mock.MagicMock(ok=True)):
                    result = notify_health_result("failure", error="API timeout", prev_result="success")
        self.assertTrue(result["telegram"])

    def test_success_after_failure_sends_recovery(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "tok"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "123"):
                with mock.patch("requests.post", return_value=mock.MagicMock(ok=True)) as m:
                    result = notify_health_result("success", prev_result="failure")
        self.assertTrue(result["telegram"])
        # Recovery mesajı gönderildi mi?
        call_json = m.call_args[1]["json"]
        self.assertIn("Normale", call_json["text"])

    def test_success_after_success_is_silent(self):
        with mock.patch("requests.post") as m:
            result = notify_health_result("success", prev_result="success")
        m.assert_not_called()
        self.assertFalse(result["telegram"])
        self.assertFalse(result["email"])

    def test_success_first_run_is_silent(self):
        with mock.patch("requests.post") as m:
            result = notify_health_result("success", prev_result=None)
        m.assert_not_called()

    def test_notify_recovery_message(self):
        with mock.patch.object(notifier_mod, "_TG_TOKEN", "tok"):
            with mock.patch.object(notifier_mod, "_TG_CHAT", "123"):
                with mock.patch("requests.post", return_value=mock.MagicMock(ok=True)) as m:
                    notify_recovery("health_check")
        call_json = m.call_args[1]["json"]
        self.assertIn("Normale", call_json["text"])


if __name__ == "__main__":
    unittest.main()
