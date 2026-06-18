"""
Sprint 1 — Güvenlik katmanı:
  - Security Headers (CSP, HSTS, X-Frame-Options, vb.)
  - CSRF token üretimi / doğrulaması
  - XSS: input sanitizasyonu
  - RBAC yardımcıları (require_role, require_premium)
  - Audit log yazma
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import time
from functools import wraps
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.storage import supabase_base_url, supabase_headers, supabase_enabled

logger = logging.getLogger(__name__)

# ── Ortam değişkenleri ──────────────────────────────────────
_CSRF_SECRET = os.getenv("CSRF_SECRET", secrets.token_hex(32))
_ENV = os.getenv("VERCEL_ENV", "development")
_IS_PROD = _ENV == "production"

# ── Security Headers ────────────────────────────────────────

# Content-Security-Policy
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://*.supabase.co https://api.replicate.com https://app.scrapingbee.com; "
    "frame-ancestors 'none';"
)

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy":           _CSP,
    "X-Content-Type-Options":            "nosniff",
    "X-Frame-Options":                   "DENY",
    "X-XSS-Protection":                  "1; mode=block",
    "Referrer-Policy":                   "strict-origin-when-cross-origin",
    "Permissions-Policy":                "camera=(self), microphone=(), geolocation=(self)",
    "Strict-Transport-Security":         "max-age=31536000; includeSubDomains" if _IS_PROD else "",
    "Cross-Origin-Opener-Policy":        "same-origin",
    "Cross-Origin-Resource-Policy":      "same-origin",
}


def apply_security_headers(response) -> None:
    """FastAPI Response nesnesine güvenlik başlıklarını ekle."""
    for key, value in SECURITY_HEADERS.items():
        if value:
            response.headers[key] = value


# ── CSRF Koruması ────────────────────────────────────────────

def generate_csrf_token(session_id: str) -> str:
    """
    HMAC-SHA256 tabanlı durumsuz (stateless) CSRF token.
    Format: {timestamp}.{hmac}
    """
    ts = str(int(time.time()))
    payload = f"{session_id}:{ts}"
    sig = hmac.new(_CSRF_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def verify_csrf_token(token: str, session_id: str, max_age_seconds: int = 7200) -> bool:
    """Token'ı doğrula; geçerliyse True döner."""
    if not token or "." not in token:
        return False
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
    except ValueError:
        return False

    if time.time() - ts > max_age_seconds:
        return False

    payload = f"{session_id}:{ts_str}"
    expected = hmac.new(_CSRF_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


CSRF_EXEMPT_PATHS = {"/api/auth/", "/api/barcode/", "/api/search", "/api/vton/"}
CSRF_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _csrf_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in CSRF_EXEMPT_PATHS)


async def csrf_middleware(request: Request, call_next):
    """
    Durum değiştiren isteklerde (POST/PUT/PATCH/DELETE) CSRF token doğrula.
    Muaf yollar: auth, barcode, search (GET-benzeri semantik POST'lar).
    """
    if request.method in CSRF_MUTATING_METHODS and not _csrf_exempt(request.url.path):
        token = (
            request.headers.get("x-csrf-token")
            or request.cookies.get("csrf_token")
        )
        session_id = request.cookies.get("almadan_device_id", "")
        if not verify_csrf_token(token or "", session_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token geçersiz veya eksik."},
            )
    return await call_next(request)


# ── XSS: Input Sanitizasyon ─────────────────────────────────

_SCRIPT_RE = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE    = re.compile(r"<[^>]+>")
_EVENT_RE  = re.compile(r"\bon\w+\s*=", re.IGNORECASE)


def sanitize(value: str, max_length: int = 500) -> str:
    """Kullanıcı girdisinden HTML/script etiketlerini temizle."""
    if not isinstance(value, str):
        return value
    value = value[:max_length]
    value = _SCRIPT_RE.sub("", value)
    value = _EVENT_RE.sub("", value)
    value = _TAG_RE.sub("", value)
    return html.escape(value, quote=True).strip()


def sanitize_dict(data: dict[str, Any], max_length: int = 500) -> dict[str, Any]:
    """Dict içindeki string değerleri sanitize et (tek seviye)."""
    return {
        k: sanitize(v, max_length) if isinstance(v, str) else v
        for k, v in data.items()
    }


# ── RBAC ────────────────────────────────────────────────────

async def _get_user_role(request: Request) -> str:
    """profiles tablosundan kullanıcı rolünü çek. Oturum yoksa 'anonymous'."""
    import requests as _req
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return "anonymous"
    if not supabase_enabled():
        return "free"
    try:
        url = f"{supabase_base_url()}/rest/v1/profiles?id=eq.{user_id}&select=role"
        resp = _req.get(url, headers=supabase_headers(), timeout=3)
        if resp.ok:
            rows = resp.json()
            if rows:
                return rows[0].get("role", "free")
    except Exception:
        pass
    return "free"


class RequireRole:
    """
    FastAPI Depends() ile kullanılacak RBAC guard.

    Örnek:
        @app.get("/api/premium")
        async def endpoint(user=Depends(RequireRole("premium"))):
            ...
    """
    _ROLE_RANK = {"anonymous": 0, "free": 1, "premium": 2, "admin": 3}

    def __init__(self, minimum_role: str):
        self.minimum_rank = self._ROLE_RANK.get(minimum_role, 1)

    async def __call__(self, request: Request) -> dict:
        role = await _get_user_role(request)
        if self._ROLE_RANK.get(role, 0) < self.minimum_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Bu özellik için yetkiniz yok.",
                    "required_role": list(self._ROLE_RANK.keys())[self.minimum_rank],
                    "current_role": role,
                },
            )
        return {"user_id": getattr(request.state, "user_id", None), "role": role}


# Kısayollar
require_login   = RequireRole("free")
require_premium = RequireRole("premium")
require_admin   = RequireRole("admin")


# ── Auth-Wall Middleware ─────────────────────────────────────

# Frontend'de kimlik gerektiren route prefix'leri
_PROTECTED_API_PATHS = {
    "/api/cart",
    "/api/profile",
    "/api/vton",
    "/api/admin",
    "/api/sync",
}


_CRON_BYPASS_PATHS = {
    "/api/admin/notifier/status",
    "/api/admin/notifier/test",
    "/api/admin/run-health-check",
}


async def auth_wall_middleware(request: Request, call_next):
    """
    Korumalı API yollarına oturumsuz erişimi 401 ile engelle.
    Frontend bu 401'i alınca /login'e yönlendirir.

    İstisna: X-Cron-Secret header'ı ile gelen istekler
    _CRON_BYPASS_PATHS listesindeyse middleware'i geçer.
    Gerçek doğrulama endpoint içinde yapılır.
    """
    path = request.url.path

    # Cron/secret bypass — önce kontrol et
    if path in _CRON_BYPASS_PATHS:
        cron_secret = request.headers.get("x-cron-secret", "").strip()
        env_secret  = os.getenv("CRON_SECRET", "").strip()
        if cron_secret and env_secret and hmac.compare_digest(env_secret, cron_secret):
            return await call_next(request)

    if any(path.startswith(p) for p in _PROTECTED_API_PATHS):
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Oturum açmanız gerekiyor.", "redirect": "/login"},
            )
    return await call_next(request)


# ── Audit Log ────────────────────────────────────────────────

def log_activity(
    request: Request,
    event: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """activity_logs tablosuna fire-and-forget kayıt yazar."""
    import threading
    import requests as _req

    user_id   = getattr(request.state, "user_id", None)
    device_id = request.cookies.get("almadan_device_id")
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    ua = request.headers.get("user-agent", "")

    payload = {
        "user_id":    user_id,
        "session_id": device_id,
        "event":      event,
        "metadata":   metadata or {},
        "ip_address": ip[:64],
        "user_agent": ua[:256],
    }

    def _write():
        if not supabase_enabled():
            return
        try:
            url = f"{supabase_base_url()}/rest/v1/activity_logs"
            _req.post(url, json=payload, headers=supabase_headers(), timeout=3)
        except Exception:
            pass

    threading.Thread(target=_write, daemon=True).start()


# ── Social Login Helper ──────────────────────────────────────

OAUTH_PROVIDERS = {
    "google": "google",
    "apple":  "apple",
}


def get_oauth_url(provider: str, redirect_url: str, supabase_url: str, anon_key: str) -> str:
    """
    Supabase OAuth yönlendirme URL'si döner.
    /api/auth/oauth/{provider} endpoint'inden çağrılır.
    """
    if provider not in OAUTH_PROVIDERS:
        raise ValueError(f"Desteklenmeyen provider: {provider}")
    encoded = redirect_url.replace(":", "%3A").replace("/", "%2F")
    return (
        f"{supabase_url}/auth/v1/authorize"
        f"?provider={OAUTH_PROVIDERS[provider]}"
        f"&redirect_to={encoded}"
    )
