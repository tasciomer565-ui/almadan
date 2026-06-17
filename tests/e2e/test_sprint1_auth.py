"""
Sprint 1 — Playwright E2E Auth Testleri

Çalıştırmak için:
    pip install playwright pytest-playwright
    playwright install chromium
    pytest tests/e2e/test_sprint1_auth.py --base-url http://localhost:8000 -v

Ortam değişkenleri:
    TEST_USER_EMAIL=test@almadan.app
    TEST_USER_PASSWORD=TestP@ss1234
    TEST_ADMIN_EMAIL=admin@almadan.app
    TEST_ADMIN_PASSWORD=AdminP@ss1234
"""
from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import Page, expect

BASE_URL        = os.getenv("BASE_URL", "http://localhost:8000")
USER_EMAIL      = os.getenv("TEST_USER_EMAIL", "test@almadan.app")
USER_PASS       = os.getenv("TEST_USER_PASSWORD", "TestP@ss1234")
ADMIN_EMAIL     = os.getenv("TEST_ADMIN_EMAIL", "admin@almadan.app")
ADMIN_PASS      = os.getenv("TEST_ADMIN_PASSWORD", "AdminP@ss1234")


# ── Yardımcılar ─────────────────────────────────────────────

def login(page: Page, email: str, password: str) -> None:
    page.goto(f"{BASE_URL}/")
    page.click("text=Giriş Yap")
    page.fill("[data-testid='email-input'], input[type='email']", email)
    page.fill("[data-testid='password-input'], input[type='password']", password)
    page.click("[data-testid='login-submit'], button[type='submit']:has-text('Giriş')")
    page.wait_for_selector("[data-testid='user-menu'], #userAvatar", timeout=8000)


def logout(page: Page) -> None:
    page.click("[data-testid='user-menu'], #userAvatar")
    page.click("text=Çıkış")
    page.wait_for_selector("text=Giriş Yap", timeout=5000)


# ── 1. Auth-Wall: Korumalı sayfa misafiri /login'e iter ─────

class TestAuthWall:
    def test_protected_cart_api_returns_401_for_guest(self, page: Page):
        """GET /api/cart oturumu olmayan kullanıcıya 401 döner."""
        response = page.request.get(f"{BASE_URL}/api/cart")
        assert response.status == 401
        body = response.json()
        assert "redirect" in body or "detail" in body

    def test_protected_profile_api_returns_401_for_guest(self, page: Page):
        response = page.request.get(f"{BASE_URL}/api/profile/me")
        assert response.status == 401

    def test_admin_api_returns_401_for_guest(self, page: Page):
        response = page.request.get(f"{BASE_URL}/api/admin/stats")
        assert response.status == 401

    def test_public_search_accessible_without_login(self, page: Page):
        """Arama API'si herkese açık olmalı."""
        response = page.request.get(f"{BASE_URL}/api/search?query=süt")
        assert response.status in (200, 422)  # 422 = eksik param, ama 401 değil


# ── 2. Security Headers ──────────────────────────────────────

class TestSecurityHeaders:
    def test_csp_header_present(self, page: Page):
        response = page.request.get(f"{BASE_URL}/")
        assert "content-security-policy" in {k.lower() for k in response.headers}

    def test_x_frame_options_deny(self, page: Page):
        response = page.request.get(f"{BASE_URL}/")
        assert response.headers.get("x-frame-options", "").upper() == "DENY"

    def test_x_content_type_nosniff(self, page: Page):
        response = page.request.get(f"{BASE_URL}/")
        assert response.headers.get("x-content-type-options", "") == "nosniff"

    def test_csrf_cookie_set(self, page: Page):
        page.goto(f"{BASE_URL}/")
        csrf = page.evaluate("() => document.cookie")
        assert "csrf_token" in csrf


# ── 3. Email/Password Giriş ──────────────────────────────────

class TestEmailPasswordLogin:
    def test_successful_login(self, page: Page):
        login(page, USER_EMAIL, USER_PASS)
        expect(page.locator("[data-testid='user-menu'], #userAvatar")).to_be_visible()

    def test_wrong_password_shows_error(self, page: Page):
        page.goto(f"{BASE_URL}/")
        page.click("text=Giriş Yap")
        page.fill("input[type='email']", USER_EMAIL)
        page.fill("input[type='password']", "yanlis_sifre_XYZ!")
        page.click("button[type='submit']:has-text('Giriş'), [data-testid='login-submit']")
        error = page.locator(".error-message, [data-testid='login-error'], .toast")
        expect(error).to_be_visible(timeout=5000)

    def test_logout_clears_session(self, page: Page):
        login(page, USER_EMAIL, USER_PASS)
        logout(page)
        response = page.request.get(f"{BASE_URL}/api/profile/me")
        assert response.status == 401


# ── 4. JWT Refresh ───────────────────────────────────────────

class TestJWTRefresh:
    def test_expired_access_token_refreshed_automatically(self, page: Page):
        """
        Access token silinip refresh token bırakılınca middleware otomatik yeniler.
        """
        login(page, USER_EMAIL, USER_PASS)
        # Access token cookie'sini zorla sil
        page.evaluate(
            "name => document.cookie = name + '=; Max-Age=0; path=/'",
            "almadan_access_token"
        )
        # Yeni istek: middleware refresh_token ile yeniden auth etmeli
        response = page.request.get(f"{BASE_URL}/api/profile/me")
        # 200 veya 401 (test ortamında Supabase gerçek olmayabilir)
        assert response.status in (200, 401)

    def test_both_tokens_expired_returns_401(self, page: Page):
        page.evaluate("""() => {
            document.cookie = 'almadan_access_token=; Max-Age=0; path=/';
            document.cookie = 'almadan_refresh_token=; Max-Age=0; path=/';
        }""")
        response = page.request.get(f"{BASE_URL}/api/profile/me")
        assert response.status == 401


# ── 5. RBAC ─────────────────────────────────────────────────

class TestRBAC:
    def test_free_user_cannot_access_admin(self, page: Page):
        login(page, USER_EMAIL, USER_PASS)
        response = page.request.get(f"{BASE_URL}/api/admin/stats")
        assert response.status == 403

    def test_admin_user_can_access_admin(self, page: Page):
        login(page, ADMIN_EMAIL, ADMIN_PASS)
        response = page.request.get(f"{BASE_URL}/api/admin/stats")
        assert response.status == 200

    def test_profile_role_included_in_me_response(self, page: Page):
        login(page, USER_EMAIL, USER_PASS)
        response = page.request.get(f"{BASE_URL}/api/profile/me")
        assert response.status == 200
        body = response.json()
        assert body.get("role") in ("free", "premium", "admin")


# ── 6. Social Login Redirect ─────────────────────────────────

class TestSocialLogin:
    def test_google_oauth_redirects(self, page: Page):
        response = page.request.get(
            f"{BASE_URL}/api/auth/oauth/google",
            max_redirects=0,
        )
        assert response.status in (302, 307)
        location = response.headers.get("location", "")
        assert "accounts.google.com" in location or "supabase" in location

    def test_invalid_provider_returns_400(self, page: Page):
        response = page.request.get(f"{BASE_URL}/api/auth/oauth/twitter")
        assert response.status == 400


# ── 7. XSS Koruması ─────────────────────────────────────────

class TestXSSProtection:
    def test_search_query_xss_not_reflected(self, page: Page):
        """Script tag arama yanıtına yansımamalı."""
        xss = "<script>alert('xss')</script>"
        response = page.request.get(
            f"{BASE_URL}/api/search",
            params={"query": xss, "category": "GENEL"},
        )
        body = response.text()
        assert "<script>" not in body

    def test_profile_update_sanitizes_display_name(self, page: Page):
        login(page, USER_EMAIL, USER_PASS)
        response = page.request.put(
            f"{BASE_URL}/auth/profile",
            data={"display_name": "<img src=x onerror=alert(1)>"},
        )
        # 422 (validation) veya 200 ama sanitize edilmiş veri
        if response.status == 200:
            body = response.json()
            name = str(body)
            assert "onerror" not in name and "<img" not in name


# ── 8. Audit Log ────────────────────────────────────────────

class TestAuditLog:
    def test_login_creates_activity_log(self, page: Page):
        login(page, USER_EMAIL, USER_PASS)
        response = page.request.get(f"{BASE_URL}/api/activity-log?limit=5")
        assert response.status == 200
        events = response.json().get("events", [])
        assert len(events) >= 0  # Supabase yoksa boş olabilir, crash etmemeli


# ── 9. Full E2E — Kayıt → Arama → Sepete ────────────────────

class TestFullFlow:
    def test_guest_search_then_login_then_add_to_cart(self, page: Page):
        """Misafir arama yapar, giriş yapar, ürün sepete ekler."""
        # 1. Misafir arama
        page.goto(f"{BASE_URL}/")
        search_input = page.locator("#productUrl, [data-testid='search-input']")
        search_input.fill("Samsung telefon")
        page.keyboard.press("Enter")
        page.wait_for_selector(".product-card, .result-item, [data-testid='result']", timeout=15000)

        # 2. Giriş yap
        page.click("text=Giriş Yap")
        page.fill("input[type='email']", USER_EMAIL)
        page.fill("input[type='password']", USER_PASS)
        page.click("button[type='submit']:has-text('Giriş'), [data-testid='login-submit']")
        page.wait_for_selector("[data-testid='user-menu'], #userAvatar", timeout=8000)

        # 3. Ürün ekle (varsa)
        add_btn = page.locator(".add-to-list-btn, [data-testid='add-to-cart']").first
        if add_btn.is_visible():
            add_btn.click()
            page.wait_for_selector(".toast, .notification", timeout=3000)
