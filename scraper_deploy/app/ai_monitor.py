"""
AIMonitor — Sprint 6: AI Servis İzleme

Tüm AI çağrılarını (embedding, forecast, vision, VTON) latency,
token kullanımı ve maliyet bazında kayıt altına alır.

Kullanım (context manager):
    with AIMonitor.trace("embedding", "embed_product", model_id="text-embedding-3-small") as span:
        result = call_openai(...)
        span.set_tokens(input=100, output=0)
        span.set_cost(0.000010)
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generator

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# Maliyet tablosu (USD / 1K token)
COST_PER_1K: dict[str, float] = {
    "text-embedding-3-small": 0.00002,
    "text-embedding-3-large": 0.00013,
    "gpt-4o":                 0.005,
    "gpt-4o-mini":            0.00015,
    "gpt-4-vision-preview":   0.01,
    "replicate-vton":         0.0023,   # per second, tracked separately
}


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


# ── Span ────────────────────────────────────────────────────

@dataclass
class AISpan:
    """Tek bir AI çağrısının ölçüm nesnesi."""
    service: str
    operation: str
    model_id: str
    user_id: str | None
    _start: float = field(default_factory=time.perf_counter, repr=False)
    _input_tokens: int = 0
    _output_tokens: int = 0
    _cost_usd: float = 0.0
    _status: str = "ok"
    _error: str | None = None
    _metadata: dict = field(default_factory=dict)

    def set_tokens(self, *, input: int = 0, output: int = 0) -> None:
        self._input_tokens = input
        self._output_tokens = output
        if not self._cost_usd:
            rate = COST_PER_1K.get(self.model_id, 0)
            self._cost_usd = rate * (input + output) / 1000

    def set_cost(self, usd: float) -> None:
        self._cost_usd = usd

    def set_error(self, msg: str) -> None:
        self._status = "error"
        self._error = msg[:500]

    def set_status(self, status: str) -> None:
        self._status = status

    def add_meta(self, **kwargs) -> None:
        self._metadata.update(kwargs)

    @property
    def latency_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

    def flush(self) -> None:
        """Ölçümleri Supabase'e yazar (fire-and-forget)."""
        row = {
            "service":       self.service,
            "operation":     self.operation,
            "user_id":       self.user_id,
            "status":        self._status,
            "latency_ms":    self.latency_ms,
            "input_tokens":  self._input_tokens,
            "output_tokens": self._output_tokens,
            "cost_usd":      round(self._cost_usd, 8),
            "model_id":      self.model_id,
            "error_message": self._error,
            "metadata":      self._metadata,
        }
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            return
        try:
            _req.post(_sb("ai_monitor_log"), headers=_headers(), json=row, timeout=3)
        except Exception as exc:
            logger.debug("AIMonitor flush failed: %s", exc)


# ── AIMonitor ────────────────────────────────────────────────

class AIMonitor:
    """
    AI servis izleyicisi.

    Kullanım:
        with AIMonitor.trace("embedding", "embed_batch", model_id="text-embedding-3-small") as span:
            vectors = openai_embed(texts)
            span.set_tokens(input=len(texts) * 8)
    """

    @staticmethod
    @contextmanager
    def trace(
        service: str,
        operation: str,
        *,
        model_id: str = "unknown",
        user_id: str | None = None,
    ) -> Generator[AISpan, None, None]:
        span = AISpan(service=service, operation=operation,
                      model_id=model_id, user_id=user_id)
        try:
            yield span
        except Exception as exc:
            span.set_error(str(exc))
            raise
        finally:
            span.flush()

    @staticmethod
    def get_cost_summary(hours: int = 24) -> list[dict]:
        """Admin: son N saatin AI maliyet özeti."""
        try:
            r = _req.post(
                f"{_SUPABASE_URL}/rest/v1/rpc/get_ai_cost_summary",
                headers={**_headers(), "Prefer": ""},
                json={"hours": hours},
                timeout=6,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    @staticmethod
    def get_recent_errors(limit: int = 20) -> list[dict]:
        """Admin: son hatalar."""
        try:
            r = _req.get(
                _sb("ai_monitor_log"),
                params={
                    "status": "neq.ok",
                    "select": "service,operation,status,error_message,model_id,recorded_at",
                    "order": "recorded_at.desc",
                    "limit": str(limit),
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    @staticmethod
    def get_latency_percentiles(service: str, hours: int = 24) -> dict:
        """Belirtilen servis için latency p50/p95/p99."""
        try:
            r = _req.get(
                _sb("ai_monitor_log"),
                params={
                    "service": f"eq.{service}",
                    "status": "eq.ok",
                    "recorded_at": f"gte.{_utc_minus(hours)}",
                    "select": "latency_ms",
                    "order": "latency_ms",
                    "limit": "1000",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if not r.ok:
                return {}
            vals = sorted(int(row.get("latency_ms") or 0) for row in r.json())
            if not vals:
                return {}
            n = len(vals)
            return {
                "p50": vals[int(n * 0.50)],
                "p95": vals[int(n * 0.95)],
                "p99": vals[min(int(n * 0.99), n - 1)],
                "count": n,
            }
        except Exception:
            return {}


def _utc_minus(hours: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# Singleton (opsiyonel — static metodlar yeterli ama modül düzeyinde erişim için)
ai_monitor = AIMonitor()
