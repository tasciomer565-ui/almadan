"""
Notifier Testleri

Gerçek HTTP/SMTP göndermeden kanalları test eder.
_cfg() fonksiyonu mock'lanır — os.getenv yerine kontrollü değer döner.
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


# ── Yardımcı: _cfg() için hazır şablonlar ──────────────────────

def _cfg_empty():
    return {
        "tg_token": "", "tg_chat": "", "notify_email": "",
        "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
    }

def _cfg_telegram(token="fake_token", chat="12345"):
    return {**_cfg_empty(), "tg_token": token, "tg_chat": chat}

def _cfg_email(host="smtp.example.com", user="u@x.com", notify="admin@x.com", passwd="pass"):
    return {**_cfg_empty(), "smtp_host": host, "smtp_user": user,
            "notify_email": notify, "smtp_pass": passwd}

def _cfg_both():
    return {**_cfg_telegram(), **_cfg_email()}


# ── Mesaj Yapıcı ────────────────────────────────────────────────

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
        self.assertLessEqual(msg.count("x"), 800)

    def test_strip_html_tags(self):
        self.assertEqual(_strip_html_tags("<b>merhaba</b> <i>dünya</i>"), "merhaba dünya")

    def test_strip_html_tags_empty(self):
        self.assertEqual(_strip_html_tags(""), "")


# ── Yapılandırma Durumu ─────────────────────────────────────────

class TestNotifierStatus(unittest.TestCase):
    def test_status_both_unconfigured(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_empty()):
            s = notifier_status()
        self.assertFalse(s["telegram_configured"])
        self.assertFalse(s["email_configured"])

    def test_status_telegram_configured(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_telegram()):
            s = notifier_status()
        self.assertTrue(s["telegram_configured"])

    def test_status_email_configured(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_email()):
            s = notifier_status()
        self.assertTrue(s["email_configured"])
        self.assertEqual(s["notify_email"], "admin@x.com")
        self.assertEqual(s["smtp_host"], "smtp.example.com")


# ── Telegram Kanalı ─────────────────────────────────────────────

class TestTelegramChannel(unittest.TestCase):
    def _ok_resp(self):
        r = mock.MagicMock(); r.ok = True; r.status_code = 200; r.text = ""; return r

    def _fail_resp(self):
        r = mock.MagicMock(); r.ok = False; r.status_code = 400; r.text = "bad"; return r

    def test_telegram_sends_when_configured(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_telegram()):
            with mock.patch("requests.post", return_value=self._ok_resp()) as m:
                result = notify_failure("test hata", test_name="t1")
        self.assertTrue(result["telegram"])
        m.assert_called_once()

    def test_telegram_skipped_when_unconfigured(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_empty()):
            with mock.patch("requests.post") as m:
                result = notify_failure("test")
        m.assert_not_called()
        self.assertFalse(result["telegram"])

    def test_telegram_returns_false_on_api_error(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_telegram()):
            with mock.patch("requests.post", return_value=self._fail_resp()):
                result = notify_failure("test")
        self.assertFalse(result["telegram"])

    def test_telegram_returns_false_on_exception(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_telegram()):
            with mock.patch("requests.post", side_effect=ConnectionError("timeout")):
                result = notify_failure("test")
        self.assertFalse(result["telegram"])


# ── Email Kanalı ────────────────────────────────────────────────

class TestEmailChannel(unittest.TestCase):
    def test_email_skipped_when_unconfigured(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_empty()):
            with mock.patch("smtplib.SMTP") as m:
                result = notify_failure("test")
        m.assert_not_called()
        self.assertFalse(result["email"])

    def test_email_sends_when_configured(self):
        smtp_mock = mock.MagicMock()
        smtp_mock.__enter__ = mock.MagicMock(return_value=smtp_mock)
        smtp_mock.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_email()):
            with mock.patch("smtplib.SMTP", return_value=smtp_mock):
                result = notify_failure("test hata")
        self.assertTrue(result["email"])

    def test_email_returns_false_on_smtp_error(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=_cfg_email()):
            with mock.patch("smtplib.SMTP", side_effect=OSError("connection refused")):
                result = notify_failure("test")
        self.assertFalse(result["email"])


# ── Health Result Mantığı ───────────────────────────────────────

class TestHealthResultLogic(unittest.TestCase):
    def _tg_cfg(self):
        return _cfg_telegram("tok", "123")

    def test_failure_always_notifies(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=self._tg_cfg()):
            with mock.patch("requests.post", return_value=mock.MagicMock(ok=True)):
                result = notify_health_result("failure", error="API timeout", prev_result="success")
        self.assertTrue(result["telegram"])

    def test_success_after_failure_sends_recovery(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=self._tg_cfg()):
            with mock.patch("requests.post", return_value=mock.MagicMock(ok=True)) as m:
                result = notify_health_result("success", prev_result="failure")
        self.assertTrue(result["telegram"])
        call_json = m.call_args[1]["json"]
        self.assertIn("Normale", call_json["text"])

    def test_success_after_success_is_silent(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=self._tg_cfg()):
            with mock.patch("requests.post") as m:
                result = notify_health_result("success", prev_result="success")
        m.assert_not_called()
        self.assertFalse(result["telegram"])
        self.assertFalse(result["email"])

    def test_success_first_run_is_silent(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=self._tg_cfg()):
            with mock.patch("requests.post") as m:
                result = notify_health_result("success", prev_result=None)
        m.assert_not_called()

    def test_notify_recovery_message(self):
        with mock.patch.object(notifier_mod, "_cfg", return_value=self._tg_cfg()):
            with mock.patch("requests.post", return_value=mock.MagicMock(ok=True)) as m:
                notify_recovery("health_check")
        call_json = m.call_args[1]["json"]
        self.assertIn("Normale", call_json["text"])


if __name__ == "__main__":
    unittest.main()
