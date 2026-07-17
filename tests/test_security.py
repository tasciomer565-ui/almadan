"""app/security.py icin testler: rate limit (429) ve CSRF middleware.
Gercek ag istegi/gercek FastAPI sunucusu gerektirmez -- Request nesneleri
Starlette scope/receive ile elle olusturulur, middleware fonksiyonlari
dogrudan cagrilir.
"""
import asyncio
import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.security import (
    check_rate_limit, _RATE_LIMIT_BUCKETS, csrf_middleware,
    generate_csrf_token, CSRF_EXEMPT_PATHS,
)


def _make_request(method="POST", path="/api/some-protected-endpoint", headers=None, cookies=None, ip="1.2.3.4"):
    raw_headers = []
    header_map = dict(headers or {})
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        header_map["cookie"] = cookie_str
    for k, v in header_map.items():
        raw_headers.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": (ip, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


# ── check_rate_limit ──────────────────────────────────────────

def test_check_rate_limit_allows_under_limit():
    _RATE_LIMIT_BUCKETS.clear()
    req = _make_request(ip="9.9.9.1")
    for _ in range(3):
        check_rate_limit(req, "test_bucket_a", limit=5, window_seconds=60)  # raise etmemeli
    assert True


def test_check_rate_limit_raises_429_when_exceeded():
    _RATE_LIMIT_BUCKETS.clear()
    req = _make_request(ip="9.9.9.2")
    for _ in range(3):
        check_rate_limit(req, "test_bucket_b", limit=3, window_seconds=60)
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(req, "test_bucket_b", limit=3, window_seconds=60)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_check_rate_limit_different_ips_isolated():
    _RATE_LIMIT_BUCKETS.clear()
    req1 = _make_request(ip="9.9.9.3")
    req2 = _make_request(ip="9.9.9.4")
    for _ in range(3):
        check_rate_limit(req1, "test_bucket_c", limit=3, window_seconds=60)
    # req2 farkli IP -- kendi bucket'inda hala izinli
    check_rate_limit(req2, "test_bucket_c", limit=3, window_seconds=60)


def test_check_rate_limit_window_expiry_resets():
    _RATE_LIMIT_BUCKETS.clear()
    req = _make_request(ip="9.9.9.5")
    key = "test_bucket_d:9.9.9.5"
    # Pencere disina dusmus eski zaman damgalari enjekte et
    _RATE_LIMIT_BUCKETS[key] = [time.time() - 1000]
    # window_seconds=1 ile eski kayit gecersiz sayilmali, yeni istek izinli olmali
    check_rate_limit(req, "test_bucket_d", limit=1, window_seconds=1)


# ── CSRF middleware ───────────────────────────────────────────

async def _call_next_ok(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True})


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_csrf_middleware_rejects_non_exempt_post_without_token():
    req = _make_request(method="POST", path="/api/some-protected-endpoint")
    response = _run(csrf_middleware(req, _call_next_ok))
    assert response.status_code == 403


def test_csrf_middleware_rejects_invalid_token():
    req = _make_request(
        method="POST", path="/api/some-protected-endpoint",
        headers={"x-csrf-token": "garbage.token"},
        cookies={"almadan_device_id": "device-123"},
    )
    response = _run(csrf_middleware(req, _call_next_ok))
    assert response.status_code == 403


def test_csrf_middleware_accepts_valid_token_on_non_exempt_path():
    session_id = "device-abc"
    token = generate_csrf_token(session_id)
    req = _make_request(
        method="POST", path="/api/some-protected-endpoint",
        headers={"x-csrf-token": token},
        cookies={"almadan_device_id": session_id},
    )
    response = _run(csrf_middleware(req, _call_next_ok))
    assert response.status_code == 200


def test_csrf_middleware_allows_exempt_path_without_token():
    exempt_path = next(iter(CSRF_EXEMPT_PATHS))
    req = _make_request(method="POST", path=exempt_path)
    response = _run(csrf_middleware(req, _call_next_ok))
    assert response.status_code == 200


def test_csrf_middleware_allows_get_without_token():
    req = _make_request(method="GET", path="/api/some-protected-endpoint")
    response = _run(csrf_middleware(req, _call_next_ok))
    assert response.status_code == 200
