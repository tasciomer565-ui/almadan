"""
Cache Strategy — Sprint 8

Katmanlı önbellekleme stratejisi:
  L1 — In-process LRU (process ömrü boyunca, Vercel warm instance)
  L2 — Supabase tablo (cross-instance, TTL sütunlu)
  Edge — Vercel CDN / Cache-Control header'ları

Vercel serverless'ta Redis yok → sadece in-process + Supabase.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, TypeVar

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
    }


# ── L1: In-Process LRU Cache ────────────────────────────────

class LRUCache:
    """Thread-safe LRU önbellek. Supabase istemiyorsak burayı kullan."""

    def __init__(self, max_size: int = 256, default_ttl: float = 300.0):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> tuple[bool, Any]:
        with self._lock:
            if key not in self._store:
                return False, None
            value, expire_at = self._store[key]
            if expire_at and time.monotonic() > expire_at:
                del self._store[key]
                return False, None
            self._store.move_to_end(key)
            return True, value

    def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        with self._lock:
            expire_at = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, expire_at)
            if len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self._lock:
            return bool(self._store.pop(key, None) is not None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            expired = sum(1 for _, (_, e) in self._store.items() if e and now > e)
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "expired_items": expired,
            }


# Uygulama genelinde paylaşılan L1 cache örnekleri
_price_cache    = LRUCache(max_size=512, default_ttl=300)   # 5 dk
_search_cache   = LRUCache(max_size=256, default_ttl=120)   # 2 dk
_product_cache  = LRUCache(max_size=1024, default_ttl=600)  # 10 dk


def get_price_cache()   -> LRUCache: return _price_cache
def get_search_cache()  -> LRUCache: return _search_cache
def get_product_cache() -> LRUCache: return _product_cache


def cache_key(*parts: Any) -> str:
    """Parametrelerden tekrarlanabilir önbellek anahtarı üretir."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


# ── LRU Cache Dekoratörü ─────────────────────────────────────

def lru_cached(cache: LRUCache, *, ttl: float | None = None, key_fn: Callable | None = None):
    """
    Fonksiyonu L1 LRU önbelleğine alır.

    Kullanım:
        @lru_cached(_price_cache, ttl=60)
        def fetch_price(product_id: str) -> float: ...
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if key_fn:
                k = key_fn(*args, **kwargs)
            else:
                k = cache_key(fn.__name__, *args, *sorted(kwargs.items()))
            hit, value = cache.get(k)
            if hit:
                return value
            result = fn(*args, **kwargs)
            cache.set(k, result, ttl=ttl)
            return result
        return wrapper   # type: ignore[return-value]
    return decorator


# ── Edge Cache Header'ları ────────────────────────────────────

def cache_headers(
    *,
    max_age: int = 60,
    stale_while_revalidate: int = 300,
    stale_if_error: int = 3600,
    private: bool = False,
    no_store: bool = False,
) -> dict[str, str]:
    """
    Vercel CDN için Cache-Control + CDN-Cache-Control header'ları.

    Parametreler:
      max_age                  : Tarayıcı önbellek süresi (saniye)
      stale_while_revalidate   : Arka planda yenilenirken stale içerik sunma
      stale_if_error           : Origin hatalıyken stale içerik sunma
      private                  : Kişisel veri; CDN cache'leme
      no_store                 : Hiç cache'leme (token/hassas endpoint)
    """
    if no_store:
        return {
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "CDN-Cache-Control": "no-store",
        }
    if private:
        return {
            "Cache-Control": f"private, max-age={max_age}",
        }

    cc = (
        f"public, max-age={max_age}, "
        f"stale-while-revalidate={stale_while_revalidate}, "
        f"stale-if-error={stale_if_error}"
    )
    return {
        "Cache-Control": cc,
        "CDN-Cache-Control": cc,
        "Vercel-CDN-Cache-Control": cc,
    }


# Önceden tanımlı preset'ler
CACHE_STATIC   = functools.partial(cache_headers, max_age=3600, stale_while_revalidate=86400)
CACHE_PRICES   = functools.partial(cache_headers, max_age=300,  stale_while_revalidate=600)
CACHE_SEARCH   = functools.partial(cache_headers, max_age=60,   stale_while_revalidate=120)
CACHE_PRIVATE  = functools.partial(cache_headers, private=True, max_age=0)
CACHE_NO_STORE = functools.partial(cache_headers, no_store=True)


# ── Cache Invalidation Audit ──────────────────────────────────

def log_cache_invalidation(
    cache_key_pattern: str,
    reason: str,
    triggered_by: str = "system",
) -> None:
    """CDN / in-memory cache invalidasyonunu Supabase'e loglar."""
    if not _SUPABASE_URL:
        return
    try:
        _req.post(
            f"{_SUPABASE_URL}/rest/v1/cache_invalidations",
            headers={**_sb_headers(), "Prefer": "return=minimal"},
            json={
                "cache_key": cache_key_pattern,
                "reason": reason,
                "triggered_by": triggered_by,
                "invalidated_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=3,
        )
    except Exception:
        pass


def invalidate_price_cache(product_key: str, *, reason: str = "price_update") -> None:
    """Belirtilen ürünün fiyat önbelleğini temizler."""
    k = cache_key("price", product_key)
    _price_cache.delete(k)
    log_cache_invalidation(f"price:{product_key}", reason)


def invalidate_search_cache(query: str) -> None:
    """Arama sonucu önbelleğini temizler."""
    k = cache_key("search", query)
    _search_cache.delete(k)
    log_cache_invalidation(f"search:{query}", "manual_invalidation")


def get_cache_stats() -> dict:
    """Tüm L1 cache örneklerinin istatistiklerini döndürür."""
    return {
        "price_cache":   _price_cache.stats(),
        "search_cache":  _search_cache.stats(),
        "product_cache": _product_cache.stats(),
    }
