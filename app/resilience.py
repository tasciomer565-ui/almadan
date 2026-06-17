"""
Resilience — Sprint 8: Circuit Breaker, Retry & Fallback

Sunucu taraflı dayanıklılık katmanı. Supabase, Replicate, OpenAI veya
harici scraper'lar yavaşladığında ya da çöktüğünde sistemin diğer
bölümlerini koruyan mekanizmalar.

Bileşenler:
  1. CircuitBreaker  — 3 durumlu state machine (closed → open → half_open)
  2. retry           — exponential backoff + jitter dekoratörü
  3. with_timeout    — Vercel 10s limiti için hard timeout sarmalayıcı
  4. Fallback        — hata durumunda alternatif değer/fonksiyon

Circuit Breaker davranışı:
  CLOSED   → normal çalışma, her hata failure_count artar
  OPEN     → istekler anında PermissionError fırlatır (threshold aşıldı)
  HALF_OPEN→ tek test isteği geçer; başarıysa CLOSED, başarısızsa OPEN
"""
from __future__ import annotations

import functools
import logging
import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any, Callable, Generator, TypeVar

import requests as _req

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


# ── Circuit Breaker ───────────────────────────────────────────

class CBState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


@dataclass
class CBStats:
    state: CBState = CBState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_at: float = 0.0
    opened_at: float = 0.0


class CircuitBreaker:
    """
    In-process circuit breaker. Vercel serverless'ta process başına
    state tutulur (Redis gerektirmez). Supabase'e de persist edilir.

    Parametreler:
      failure_threshold : Kaç başarısız istekten sonra OPEN olur (varsayılan 5)
      recovery_timeout  : OPEN'dan HALF_OPEN'a geçiş süresi, saniye (varsayılan 30)
      success_threshold : HALF_OPEN'dan CLOSED'a geçmek için başarı sayısı
    """

    _instances: dict[str, "CircuitBreaker"] = {}
    _lock: Lock = Lock()

    def __init__(
        self,
        service: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.success_threshold = success_threshold
        self._stats = CBStats()
        self._lock  = Lock()

    @classmethod
    def get(cls, service: str, **kwargs) -> "CircuitBreaker":
        """Servis adına göre singleton CircuitBreaker döndürür."""
        with cls._lock:
            if service not in cls._instances:
                cls._instances[service] = cls(service, **kwargs)
            return cls._instances[service]

    @contextmanager
    def call(self) -> Generator[None, None, None]:
        """
        Circuit breaker bağlamında istek yapar.

        Kullanım:
            with CircuitBreaker.get("supabase").call():
                result = _req.get(...)
        """
        self._check_state()
        try:
            yield
            self._on_success()
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _check_state(self) -> None:
        with self._lock:
            stats = self._stats
            if stats.state == CBState.OPEN:
                elapsed = time.monotonic() - stats.opened_at
                if elapsed >= self.recovery_timeout:
                    logger.info("CircuitBreaker [%s]: OPEN → HALF_OPEN", self.service)
                    stats.state = CBState.HALF_OPEN
                    stats.success_count = 0
                else:
                    remaining = self.recovery_timeout - elapsed
                    raise PermissionError(
                        f"Circuit breaker OPEN: '{self.service}' "
                        f"({remaining:.0f}s kaldı)"
                    )

    def _on_success(self) -> None:
        with self._lock:
            stats = self._stats
            if stats.state == CBState.HALF_OPEN:
                stats.success_count += 1
                if stats.success_count >= self.success_threshold:
                    logger.info("CircuitBreaker [%s]: HALF_OPEN → CLOSED", self.service)
                    stats.state = CBState.CLOSED
                    stats.failure_count = 0
            elif stats.state == CBState.CLOSED:
                stats.failure_count = max(0, stats.failure_count - 1)
        self._persist()

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            stats = self._stats
            stats.failure_count += 1
            stats.last_failure_at = time.monotonic()
            if stats.state == CBState.HALF_OPEN:
                logger.warning("CircuitBreaker [%s]: HALF_OPEN → OPEN (test başarısız)", self.service)
                stats.state = CBState.OPEN
                stats.opened_at = time.monotonic()
            elif stats.failure_count >= self.failure_threshold:
                logger.error(
                    "CircuitBreaker [%s]: CLOSED → OPEN (%d hata: %s)",
                    self.service, stats.failure_count, exc
                )
                stats.state = CBState.OPEN
                stats.opened_at = time.monotonic()
        self._persist()

    @property
    def state(self) -> CBState:
        return self._stats.state

    @property
    def is_open(self) -> bool:
        return self._stats.state == CBState.OPEN

    def reset(self) -> None:
        """Manuel sıfırlama (admin endpoint'inden)."""
        with self._lock:
            self._stats = CBStats()
        self._persist()
        logger.info("CircuitBreaker [%s]: manuel sıfırlama", self.service)

    def status(self) -> dict:
        s = self._stats
        return {
            "service":       self.service,
            "state":         s.state.value,
            "failure_count": s.failure_count,
            "success_count": s.success_count,
        }

    def _persist(self) -> None:
        """Durumu Supabase'e yazar (fire-and-forget)."""
        if not _SUPABASE_URL:
            return
        s = self._stats
        row = {
            "service":       self.service,
            "state":         s.state.value,
            "failure_count": s.failure_count,
            "success_count": s.success_count,
            "updated_at":    datetime.now(timezone.utc).isoformat(),
        }
        try:
            _req.patch(
                f"{_SUPABASE_URL}/rest/v1/circuit_breaker_state",
                params={"service": f"eq.{self.service}"},
                headers=_sb_headers(),
                json=row,
                timeout=2,
            )
        except Exception:
            pass   # CB persist hatası uygulamayı durdurmamalı


# Hazır CB örnekleri
cb_supabase  = CircuitBreaker.get("supabase",  failure_threshold=5, recovery_timeout=30)
cb_replicate = CircuitBreaker.get("replicate", failure_threshold=3, recovery_timeout=60)
cb_openai    = CircuitBreaker.get("openai",    failure_threshold=3, recovery_timeout=60)
cb_scrapers  = CircuitBreaker.get("scrapers",  failure_threshold=8, recovery_timeout=120)


# ── Retry Dekoratörü ─────────────────────────────────────────

def retry(
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[F], F]:
    """
    Exponential backoff + jitter ile yeniden deneme dekoratörü.

    Kullanım:
        @retry(max_attempts=3, backoff_base=1.5)
        def call_external_api():
            ...
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                    if jitter:
                        delay *= (0.5 + random.random())
                    logger.debug(
                        "retry: %s attempt %d/%d, %.1fs bekleniyor (hata: %s)",
                        fn.__name__, attempt, max_attempts, delay, exc
                    )
                    if on_retry:
                        on_retry(attempt, exc)
                    time.sleep(delay)
            raise last_exc   # type: ignore[misc]
        return wrapper   # type: ignore[return-value]
    return decorator


# ── Timeout Sarmalayıcı ───────────────────────────────────────

@contextmanager
def with_timeout(seconds: float, operation: str = "operation") -> Generator[None, None, None]:
    """
    Vercel 10s timeout'u için soft guard.
    signal tabanlı timeout (thread-safe olmayan) yerine
    başlangıç zamanını kaydet ve sonraki kontrollerde aşılıp aşılmadığını döndür.

    Not: Bu bir "best-effort" guard. Hard kill için signal.alarm kullanılır
    ancak Windows/Vercel serverless uyumluluğu için basit versiyon yeterli.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        if elapsed > seconds:
            logger.warning(
                "Timeout aşıldı: '%s' %.2fs sürdü (limit: %.0fs)",
                operation, elapsed, seconds
            )


def check_timeout(start: float, limit_seconds: float, operation: str = "") -> None:
    """Döngü içinde timeout kontrolü için kullanılır."""
    elapsed = time.monotonic() - start
    if elapsed > limit_seconds:
        raise TimeoutError(
            f"'{operation}' zaman aşımı: {elapsed:.2f}s > {limit_seconds}s"
        )


# ── Fallback Dekoratörü ──────────────────────────────────────

def with_fallback(fallback_value: Any = None, log_error: bool = True):
    """
    Hata durumunda sabit bir değer döndüren dekoratör.

    Kullanım:
        @with_fallback(fallback_value=[])
        def get_products_from_cache():
            ...
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if log_error:
                    logger.error(
                        "Fallback devreye girdi: %s → %s (%s)",
                        fn.__name__, repr(fallback_value), exc
                    )
                return fallback_value
        return wrapper   # type: ignore[return-value]
    return decorator


# ── Genel Sistem Sağlığı ─────────────────────────────────────

def get_all_circuit_states() -> list[dict]:
    """Tüm circuit breaker durumlarını listeler (admin dashboard)."""
    return [
        CircuitBreaker.get(svc).status()
        for svc in ("supabase", "replicate", "openai", "scrapers", "push")
    ]


def reset_circuit_breaker(service: str) -> bool:
    """Belirtilen servisi manuel sıfırlar."""
    cb = CircuitBreaker.get(service)
    cb.reset()
    return True
