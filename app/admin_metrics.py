"""
Admin performans metrikleri — search_metrics tablosuna yaz ve oku.

Metrikler:
  cache_hit     — cache'den döndü
  cache_miss    — canlı kaynaklar çekildi
  proxy_used    — ScrapingBee kullanıldı
  stale_fallback — süresi dolmuş cache kullanıldı
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
METRICS_TABLE = "search_metrics"


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def record_event(
    event: str,
    query: str = "",
    category: str = "",
    source: str = "",
    duration_ms: int | None = None,
) -> None:
    """Metrik olayını kaydet — non-blocking (hata olursa sessizce devam et)."""
    if not _enabled():
        return
    try:
        payload = {
            "event": event,
            "query": query[:200] if query else "",
            "category": category,
            "source": source,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        requests.post(
            f"{SUPABASE_URL}/rest/v1/{METRICS_TABLE}",
            headers=_headers(),
            json=payload,
            timeout=2,
        )
    except Exception:
        pass  # Metrik kaydı asla ana akışı engellemez


def get_dashboard_stats(days: int = 7) -> dict:
    """Admin dashboard için son N günün özet istatistikleri."""
    if not _enabled():
        return {"enabled": False}
    try:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        url = (
            f"{SUPABASE_URL}/rest/v1/{METRICS_TABLE}"
            f"?recorded_at=gt.{since}"
            f"&select=event,duration_ms,recorded_at"
            f"&limit=5000"
        )
        resp = requests.get(url, headers=_headers(), timeout=5)
        rows = resp.json() if resp.ok else []

        counts: dict[str, int] = {}
        total_duration: dict[str, list[int]] = {}
        daily: dict[str, dict[str, int]] = {}

        for row in rows:
            ev = row.get("event", "unknown")
            counts[ev] = counts.get(ev, 0) + 1
            if row.get("duration_ms"):
                total_duration.setdefault(ev, []).append(row["duration_ms"])
            # Günlük breakdown
            day = (row.get("recorded_at") or "")[:10]
            if day:
                daily.setdefault(day, {})
                daily[day][ev] = daily[day].get(ev, 0) + 1

        avg_duration = {
            ev: round(sum(vals) / len(vals)) for ev, vals in total_duration.items()
        }
        total = sum(counts.values())
        hit_rate = (
            round(counts.get("cache_hit", 0) / total * 100, 1) if total else 0
        )

        return {
            "enabled": True,
            "period_days": days,
            "total_searches": total,
            "cache_hit_rate_pct": hit_rate,
            "counts": counts,
            "avg_duration_ms": avg_duration,
            "daily": dict(sorted(daily.items())[-7:]),  # son 7 gün
        }
    except Exception as exc:
        logger.warning("get_dashboard_stats error: %s", exc)
        return {"enabled": True, "error": str(exc)}
