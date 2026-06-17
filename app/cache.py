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

_TR_MAP = str.maketrans("şğıöüçŞĞIÖÜÇ", "sgioucSGIOUC")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().translate(_TR_MAP)).strip()


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


def cache_get(cache_key: str) -> Optional[list[dict]]:
    """Cache'de taze (süresi dolmamış) veri varsa döndür, yoksa None."""
    if not _enabled():
        return None
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
            logger.info("Cache HIT: %s (%d ürün)", cache_key, rows[0].get("source_count", 0))
            return rows[0]["products"]
    except Exception as exc:
        logger.warning("cache_get error: %s", exc)
    return None


def cache_get_stale(cache_key: str) -> Optional[list[dict]]:
    """Süresi dolmuş olsa bile son başarılı veriyi döndür (fault-tolerance fallback).
    Dönen ürünlere 'stale': True etiketi eklenir — frontend uyarı gösterir.
    """
    if not _enabled():
        return None
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{CACHE_TABLE}"
            f"?cache_key=eq.{requests.utils.quote(cache_key)}"
            f"&select=products,source_count,expires_at"
            f"&order=created_at.desc"
            f"&limit=1"
        )
        resp = requests.get(url, headers=_headers(), timeout=3)
        rows = resp.json() if resp.ok else []
        if rows and rows[0].get("products"):
            products = rows[0]["products"]
            # Her ürüne stale flag ekle — frontend "eski veri" uyarısı gösterir
            for p in products:
                p["stale_cache"] = True
                if "Eski veri (önbellek)" not in p.get("labels", []):
                    p.setdefault("labels", []).append("Eski veri (önbellek)")
            logger.warning("Stale cache fallback: %s (%d ürün)", cache_key, len(products))
            return products
    except Exception as exc:
        logger.warning("cache_get_stale error: %s", exc)
    return None


def cache_set(cache_key: str, query: str, category: str, products: list[dict]) -> None:
    """Sonuçları cache'e kaydet / varsa güncelle."""
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
    """Belirli bir cache kaydını sil."""
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
