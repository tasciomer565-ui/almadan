"""
Lazy-loading product cache — Supabase product_cache tablosunu kullanır.

Akış:
  1. cache_get(key) → hit ise ürünleri döndür
  2. Miss ise scraper çalıştır
  3. cache_set(key, products) → Supabase'e kaydet
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "6"))
CACHE_TABLE = "product_cache"

from app.text_utils import normalize_turkish


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_turkish(text)).strip()


def make_cache_key(query: str, category: str = "GENEL") -> str:
    return f"{_norm(query)}|{category.upper()}"


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def cache_get(cache_key: str, query: str = "", category: str = "") -> Optional[list[dict]]:
    """Cache'de taze (süresi dolmamış) veri varsa döndür, yoksa None."""
    # 1. Redis önce — çok daha hızlı
    try:
        from app.redis_cache import rget
        hit = rget(cache_key)
        if hit is not None:
            logger.info("Redis HIT: %s (%d ürün)", cache_key, len(hit))
            try:
                from app.admin_metrics import record_event
                record_event("cache_hit", query=query, category=category, duration_ms=1)
            except Exception:
                pass
            return hit
    except Exception as exc:
        logger.warning("Redis cache_get hata: %s", exc)

    if not _enabled():
        return None
    import time as _time
    t0 = _time.monotonic()
    try:
        now = datetime.now(timezone.utc).isoformat()
        url = (
            f"{SUPABASE_URL}/rest/v1/{CACHE_TABLE}"
            f"?cache_key=eq.{requests.utils.quote(cache_key)}"
            f"&expires_at=gt.{now}"
            f"&select=products,source_count"
            f"&limit=1"
        )
        resp = requests.get(url, headers=_headers(), timeout=3)
        rows = resp.json() if resp.ok else []
        if rows:
            duration_ms = int((_time.monotonic() - t0) * 1000)
            logger.info("Cache HIT: %s (%d ürün)", cache_key, rows[0].get("source_count", 0))
            try:
                from app.admin_metrics import record_event
                record_event("cache_hit", query=query, category=category, duration_ms=duration_ms)
            except Exception:
                pass
            return rows[0]["products"]
    except Exception as exc:
        logger.warning("cache_get error: %s", exc)
    return None


def cache_get_stale(cache_key: str) -> Optional[list[dict]]:  # noqa: C901
    """Süresi dolmuş olsa bile son başarılı veriyi döndür (fault-tolerance fallback).
    Dönen ürünlere 'stale': True etiketi eklenir — frontend uyarı gösterir.
    """
    if not _enabled():
        return None
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{CACHE_TABLE}"
            f"?cache_key=eq.{requests.utils.quote(cache_key)}"
            f"&select=products,source_count,expires_at,created_at"
            f"&order=created_at.desc"
            f"&limit=1"
        )
        resp = requests.get(url, headers=_headers(), timeout=3)
        rows = resp.json() if resp.ok else []
        if rows and rows[0].get("products"):
            products = rows[0]["products"]
            created_at = rows[0].get("created_at", "")
            # Kaç saat önce kaydedildiğini hesapla
            try:
                from datetime import timedelta
                cached_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - cached_time).total_seconds() / 3600
                age_label = f"{int(age_hours)} saat" if age_hours >= 1 else f"{int(age_hours * 60)} dakika"
            except Exception:
                age_label = "birkaç saat"
            for p in products:
                p["stale_cache"] = True
                p["stale_age"] = age_label
                if "Eski veri (önbellek)" not in p.get("labels", []):
                    p.setdefault("labels", []).append("Eski veri (önbellek)")
            logger.warning("Stale cache fallback: %s (%d ürün, %s önce)", cache_key, len(products), age_label)
            return products
    except Exception as exc:
        logger.warning("cache_get_stale error: %s", exc)
    return None


def cache_set(cache_key: str, query: str, category: str, products: list[dict]) -> None:
    """Sonuçları cache'e kaydet / varsa güncelle."""
    # Redis'e de yaz (hızlı okuma için)
    try:
        from app.redis_cache import rset
        rset(cache_key, products)
    except Exception as exc:
        logger.warning("Redis cache_set hata: %s", exc)

    if not _enabled() or not products:
        return
    try:
        from datetime import timedelta
        expires = (
            datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS)
        ).isoformat()

        payload = {
            "cache_key": cache_key,
            "query": query,
            "category": category,
            "products": products,
            "source_count": len(products),
            "expires_at": expires,
        }
        url = f"{SUPABASE_URL}/rest/v1/{CACHE_TABLE}"
        # Upsert — aynı key varsa güncelle
        resp = requests.post(
            url,
            headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
            json=payload,
            timeout=5,
        )
        if resp.ok:
            logger.info("Cache SET: %s → %d ürün", cache_key, len(products))
        else:
            logger.warning("cache_set failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("cache_set error: %s", exc)


def cache_invalidate(cache_key: str) -> None:
    """Belirli bir cache kaydını sil (Redis + Supabase). cache_get Redis'i
    ONCE kontrol ettiği icin sadece Supabase'i silmek yetersizdi -- Redis'te
    duran (6 saate kadar) eski deger "Fiyati Guncelle" sonrasi bile geri
    donmeye devam ediyordu."""
    try:
        from app.redis_cache import rdel
        rdel(cache_key)
    except Exception as exc:
        logger.warning("Redis cache_invalidate hata: %s", exc)

    if not _enabled():
        return
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{CACHE_TABLE}"
            f"?cache_key=eq.{requests.utils.quote(cache_key)}"
        )
        requests.delete(url, headers=_headers(), timeout=3)
    except Exception as exc:
        logger.warning("cache_invalidate error: %s", exc)
