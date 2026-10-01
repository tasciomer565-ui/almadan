"""Kayit onay e-postasi, onaysiz giris ve kimlik uclarinda hiz siniri."""
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
import app.main as main
import app.security as security

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    security._RATE_LIMIT_BUCKETS.clear()
    yield
    security._RATE_LIMIT_BUCKETS.clear()


def test_admin_signup_unconfirmed_sends_confirmation_email():
    created = mock.Mock(status_code=201)
    created.json.return_value = {"id": "u1", "email": "a@b.co"}
    unconfirmed = auth.AuthError("Email not confirmed", 400, error_code="email_not_confirmed")
    with mock.patch("app.storage.SUPABASE_KEY", "service"), \
         mock.patch.object(auth, "supabase_base_url", return_value="https://x"), \
         mock.patch.object(auth.requests, "post", return_value=created), \
         mock.patch.object(auth, "sign_in", side_effect=unconfirmed), \
         mock.patch.object(auth, "resend_signup_confirmation") as resend:
        result = auth.sign_up("a@b.co", "password123", redirect_to="https://almadan.app")
    assert result == {"user": {"id": "u1", "email": "a@b.co"}}
    resend.assert_called_once_with("a@b.co", "https://almadan.app")


def test_login_with_unconfirmed_email_resends_and_explains_in_turkish():
    unconfirmed = auth.AuthError("Email not confirmed", 400, error_code="email_not_confirmed")
    with mock.patch.object(main, "sign_in", side_effect=unconfirmed), \
         mock.patch.object(main, "resend_signup_confirmation") as resend:
        resp = client.post("/auth/login", json={"email": "a@b.co", "password": "password123"})
    assert resp.status_code == 403
    assert "onaylanmamış" in resp.json()["detail"]
    resend.assert_called_once()


def test_wrong_password_is_not_treated_as_unconfirmed():
    wrong = auth.AuthError("Invalid login credentials", 400, error_code="invalid_credentials")
    with mock.patch.object(main, "sign_in", side_effect=wrong), \
         mock.patch.object(main, "resend_signup_confirmation") as resend:
        resp = client.post("/auth/login", json={"email": "a@b.co", "password": "password123"})
    assert resp.status_code == 400
    resend.assert_not_called()


def test_otp_send_is_limited_per_phone():
    with mock.patch.object(main, "send_otp", return_value={}):
        codes = [client.post("/auth/otp/send", json={"phone": "05551112233"}).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_login_attempts_are_limited():
    wrong = auth.AuthError("Invalid login credentials", 400, error_code="invalid_credentials")
    with mock.patch.object(main, "sign_in", side_effect=wrong):
        codes = [client.post("/auth/login", json={"email": "x@y.co", "password": "password123"}).status_code
                 for _ in range(11)]
    assert codes[:10] == [400] * 10
    assert codes[10] == 429


# ── Giris yapmis kullanicinin telefon dogrulamasi (Netgsm) ─────

import app.phone_verification as pv


from contextlib import ExitStack


def _as_user(user_id="u1"):
    """Middleware'in oturum cerezinden kullaniciyi cozmesini taklit et."""
    stack = ExitStack()
    stack.enter_context(mock.patch.object(main, "auth_enabled", return_value=True))
    stack.enter_context(mock.patch.object(main, "get_user", return_value={
        "id": user_id, "email": "a@b.co", "user_metadata": {"phone": "+905551112233"}}))
    return stack


def _logged_in_client():
    c = TestClient(main.app)
    c.cookies.set(main.ACCESS_COOKIE, "token")
    return c


def test_logged_in_otp_uses_netgsm_and_confirms_own_account():
    pv._pending.clear()
    sent = {}
    with _as_user(), \
         mock.patch("app.netgsm.netgsm_enabled", return_value=True), \
         mock.patch("app.netgsm.send_netgsm_sms", side_effect=lambda to, msg: sent.update(to=to, msg=msg) or True), \
         mock.patch.object(main, "send_otp") as supabase_otp:
        c = _logged_in_client()
        assert c.post("/auth/otp/send", json={"phone": "05551112233"}).status_code == 200
        supabase_otp.assert_not_called()           # Supabase "telefonla giris" kullanilmadi
        code = sent["msg"].split(": ")[1][:6]
        with mock.patch.object(main, "admin_confirm_phone", return_value={"email": "a@b.co"}) as confirm, \
             mock.patch.object(main, "verify_otp") as supabase_verify:
            bad = c.post("/auth/otp/verify", json={"phone": "05551112233", "code": "000000" if code != "000000" else "111111"})
            ok = c.post("/auth/otp/verify", json={"phone": "05551112233", "code": code})
        supabase_verify.assert_not_called()
    assert bad.status_code == 400
    assert ok.status_code == 200 and ok.json()["user"]["phone_verified"] is True
    confirm.assert_called_once_with("u1", "+905551112233")


def test_code_is_invalidated_after_five_wrong_attempts():
    pv._pending.clear()
    with mock.patch("app.netgsm.netgsm_enabled", return_value=True), \
         mock.patch("app.netgsm.send_netgsm_sms", return_value=True):
        assert pv.send_code("u1", "+905551112233")
    code_hash = pv._pending["+905551112233"][0]
    for _ in range(5):
        assert not pv.verify_code("u1", "+905551112233", "999999")
    # dogru kod bile artik kabul edilmez (kod tukendi)
    pv._pending["+905551112233"] = (code_hash, pv._pending["+905551112233"][1], 5, "u1")
    assert not pv.verify_code("u1", "+905551112233", "123456")
    assert "+905551112233" not in pv._pending


def test_logged_in_otp_without_sms_service_gives_clear_error():
    with _as_user(), mock.patch("app.netgsm.netgsm_enabled", return_value=False):
        resp = _logged_in_client().post("/auth/otp/send", json={"phone": "05551112233"})
    assert resp.status_code == 503
    assert "SMS" in resp.json()["detail"]
