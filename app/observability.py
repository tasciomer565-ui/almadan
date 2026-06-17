"""
Observability — Sprint 8

Yapılandırılmış JSON loglama + FastAPI performans middleware.
Sentry entegrasyonu (isteğe bağlı, SENTRY_DSN env ile etkinleşir).

Bileşenler:
  1. StructuredLogger  — JSON formatında Supabase'e log yazar
  2. RequestMetrics    — Her isteğin latency/status/cache_hit kaydı
  3. PerformanceMiddleware — FastAPI ASGI middleware
  4. sentry_init()     — Sentry SDK başlatma
"""
from __future__ import annotations

import logging
import os
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import requests as _req
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
_SENTRY_DSN   = os.getenv("SENTRY_DSN", "")
_REGION       = os.getenv("VERCEL_REGION", "fra1")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


# ── Sentry Başlatma ───────────────────────────────────────────

def sentry_init() -> bool:
    """
    Sentry SDK'yı başlatır. SENTRY_DSN tanımlı değilse atlar.
    Vercel cold-start'ta main.py'den çağrılır.

    Returns:
        True — Sentry başarıyla başlatıldı
        False — DSN yok veya SDK yüklü değil
    """
    if not _SENTRY_DSN:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,   # %10 trace örnekleme
            profiles_sample_rate=0.05,
            environment=os.getenv("VERCEL_ENV", "production"),
            release=os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
        )
        logger.info("Sentry başlatıldı (DSN: %s...)", _SENTRY_DSN[:20])
        return True
    except ImportError:
        logger.warning("sentry-sdk yüklü değil — pip install sentry-sdk")
        return False


def capture_exception(exc: Exception, *, extra: dict | None = None) -> None:
    """Sentry'ye exception gönderir (Sentry yüklü değilse sessizce geçer)."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except ImportError:
        pass


# ── Yapılandırılmış Loglama ───────────────────────────────────

class StructuredLogger:
    """
    Uygulama loglarını Supabase structured_logs tablosuna yazar.
    Sentry entegrasyonuyla error/critical'ları iletir.

    Sadece error ve critical'lar DB'ye yazılır (debug/info yüksek hacim).
    """

    _PERSIST_LEVELS = {"error", "critical", "warning"}

    def __init__(self, name: str):
        self.name = name
        self._py_logger = logging.getLogger(name)

    def debug(self, msg: str, **extra) -> None:
        self._py_logger.debug(msg)

    def info(self, msg: str, **extra) -> None:
        self._py_logger.info(msg)

    def warning(self, msg: str, *, request_id: str | None = None, **extra) -> None:
        self._py_logger.warning(msg)
        self._persist("warning", msg, request_id=request_id, extra=extra)

    def error(
        self,
        msg: str,
        *,
        exc: Exception | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
        endpoint: str | None = None,
        **extra,
    ) -> None:
        self._py_logger.error(msg, exc_info=exc)
        if exc:
            capture_exception(exc, extra={"msg": msg, **extra})
        self._persist(
            "error", msg,
            exc=exc,
            request_id=request_id,
            user_id=user_id,
            endpoint=endpoint,
            extra=extra,
        )

    def critical(self, msg: str, *, exc: Exception | None = None, **extra) -> None:
        self._py_logger.critical(msg, exc_info=exc)
        if exc:
            capture_exception(exc, extra={"msg": msg, **extra})
        self._persist("critical", msg, exc=exc, extra=extra)

    def _persist(
        self,
        level: str,
        message: str,
        *,
        exc: Exception | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
        endpoint: str | None = None,
        extra: dict | None = None,
    ) -> None:
        if not _SUPABASE_URL:
            return
        row: dict[str, Any] = {
            "level":      level,
            "logger":     self.name,
            "message":    message[:2000],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if request_id:
            row["request_id"] = request_id
        if user_id:
            row["user_id"] = user_id
        if endpoint:
            row["endpoint"] = endpoint
        if exc:
            row["error_type"]  = type(exc).__name__
            row["stack_trace"] = traceback.format_exc()[-3000:]
        if extra:
            row["extra"] = extra
        try:
            _req.post(
                f"{_SUPABASE_URL}/rest/v1/structured_logs",
                headers=_sb_headers(),
                json=row,
                timeout=2,
            )
        except Exception:
            pass


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


# ── Request Metrics Kaydedici ─────────────────────────────────

def record_request_metric(
    *,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int,
    user_id: str | None = None,
    request_id: str | None = None,
    is_cache_hit: bool = False,
) -> None:
    """İstek metriğini Supabase request_metrics tablosuna kaydeder."""
    if not _SUPABASE_URL:
        return
    try:
        _req.post(
            f"{_SUPABASE_URL}/rest/v1/request_metrics",
            headers=_sb_headers(),
            json={
                "endpoint":     endpoint,
                "method":       method,
                "status_code":  status_code,
                "latency_ms":   latency_ms,
                "user_id":      user_id,
                "request_id":   request_id,
                "region":       _REGION,
                "is_cache_hit": is_cache_hit,
                "recorded_at":  datetime.now(timezone.utc).isoformat(),
            },
            timeout=2,
        )
    except Exception:
        pass


# ── FastAPI Performans Middleware ─────────────────────────────

class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Her isteğin latency'sini ölçer ve:
      - X-Request-ID header ekler
      - X-Response-Time header ekler
      - request_metrics tablosuna kaydeder
      - P99 > 3000ms ise warning loglar
    """

    P99_WARN_MS = 3000

    def __init__(self, app: ASGIApp, *, skip_paths: list[str] | None = None):
        super().__init__(app)
        self._skip = set(skip_paths or ["/health", "/favicon.ico"])

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._skip:
            return await call_next(request)

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        start = time.monotonic()

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            record_request_metric(
                endpoint=request.url.path,
                method=request.method,
                status_code=500,
                latency_ms=elapsed_ms,
                request_id=request_id,
            )
            raise

        elapsed_ms = int((time.monotonic() - start) * 1000)
        is_cache = response.headers.get("X-Cache-Hit", "false").lower() == "true"

        record_request_metric(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=elapsed_ms,
            request_id=request_id,
            is_cache_hit=is_cache,
        )

        if elapsed_ms > self.P99_WARN_MS:
            logger.warning(
                "Yavaş istek: %s %s — %dms (limit: %dms)",
                request.method, request.url.path, elapsed_ms, self.P99_WARN_MS
            )

        response.headers["X-Request-ID"]    = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
        return response


# ── Latency İstatistikleri ────────────────────────────────────

def get_latency_stats(hours: int = 1) -> list[dict]:
    """Supabase'den endpoint latency P50/P95/P99 istatistiklerini getirir."""
    if not _SUPABASE_URL:
        return []
    try:
        resp = _req.post(
            f"{_SUPABASE_URL}/rest/v1/rpc/get_endpoint_latency_stats",
            headers=_sb_headers(),
            json={"hours": hours},
            timeout=5,
        )
        return resp.json() if resp.ok else []
    except Exception:
        return []
