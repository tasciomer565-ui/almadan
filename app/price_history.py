"""
Fiyat geçmişi kaydı ve analizi.

Her başarılı arama sonucunda ürün fiyatları price_history tablosuna
kaydedilir. Bir sonraki aramada aynı ürünün son 7 günlük trendi
hesaplanıp ürün kartına eklenir.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

from app.text_utils import normalize_turkish


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_turkish(text)).strip()


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def make_product_key(title: str, source: str) -> str:
    return _norm(title[:80]) + "|" + _norm(source)


def record_prices(products: list[dict]) -> None:
    """Ürün listesindeki fiyatları price_history'e toplu kaydet."""
    if not _enabled() or not products:
        return
    rows = []
    for p in products:
        if not p.get("title") or not p.get("price") or not p.get("source"):
            continue
        if p.get("stale_cache"):  # Eski veriyi tekrar kaydetme
            continue
        rows.append({
            "product_key": make_product_key(p["title"], p["source"]),
            "title": p["title"][:200],
            "source": p["source"],
            "price": float(p["price"]),
            "url": (p.get("url") or "")[:500],
        })
    if not rows:
        return
    try:
        url = f"{SUPABASE_URL}/rest/v1/price_history"
        resp = requests.post(url, headers=_headers(), json=rows, timeout=4)
        if not resp.ok:
            logger.warning("record_prices failed: %s", resp.text[:200])
    except Exception as exc:
        logger.warning("record_prices error: %s", exc)


def get_price_trends(products: list[dict], days: int = 7) -> dict[str, dict]:
    """
    Ürün listesi için fiyat trendini döndür.
    Returns: { product_key: { change_pct: float, direction: 'up'|'down'|'stable', first_price: float } }
    """
    if not _enabled() or not products:
        return {}

    keys = list({make_product_key(p["title"], p["source"]) for p in products if p.get("title") and p.get("source")})
    if not keys:
        return {}

    try:
        # Son 7 gün içindeki en eski ve en yeni fiyatı çek
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Tek sorguda tüm key'lerin verilerini al
        keys_filter = "(" + ",".join(f'"{k}"' for k in keys[:20]) + ")"
        url = (
            f"{SUPABASE_URL}/rest/v1/price_history"
            f"?product_key=in.{keys_filter}"
            f"&recorded_at=gt.{since}"
            f"&select=product_key,price,recorded_at"
            f"&order=recorded_at.asc"
            f"&limit=500"
        )
        resp = requests.get(url, headers=_headers(), timeout=4)
        rows = resp.json() if resp.ok else []

        # Her key için ilk ve son fiyatı hesapla
        by_key: dict[str, list[float]] = {}
        for row in rows:
            k = row.get("product_key", "")
            p = row.get("price")
            if k and p is not None:
                by_key.setdefault(k, []).append(float(p))

        trends: dict[str, dict] = {}
        for k, prices in by_key.items():
            if len(prices) < 2:
                continue
            first, last = prices[0], prices[-1]
            pct = round((last - first) / first * 100, 1)
            trends[k] = {
                "change_pct": pct,
                "direction": "up" if pct > 1 else ("down" if pct < -1 else "stable"),
                "first_price": first,
                "last_price": last,
                "data_points": len(prices),
            }
        return trends
    except Exception as exc:
        logger.warning("get_price_trends error: %s", exc)
        return {}


def enrich_with_trends(products: list[dict]) -> list[dict]:
    """Ürünlere price_trend alanı ekle."""
    trends = get_price_trends(products)
    for p in products:
        key = make_product_key(p.get("title", ""), p.get("source", ""))
        if key in trends:
            p["price_trend"] = trends[key]
    return products


def get_price_list(title: str, source: str, limit: int = 90) -> list[float]:
    """Bir ürünün kronolojik (eskiden yeniye) fiyat listesini döndür."""
    if not _enabled() or not title or not source:
        return []
    key = make_product_key(title, source)
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/price_history"
            f"?product_key=eq.{key}"
            f"&select=price,recorded_at"
            f"&order=recorded_at.asc"
            f"&limit={int(limit)}"
        )
        resp = requests.get(url, headers=_headers(), timeout=4)
        rows = resp.json() if resp.ok else []
        return [float(r["price"]) for r in rows if r.get("price") is not None]
    except Exception as exc:
        logger.warning("get_price_list error: %s", exc)
        return []


def get_biggest_movers(limit: int = 20, sample: int = 2000) -> list[dict]:
    """En büyük fiyat düşüşü/en stabil ürünleri hesapla (gerçek price_history verisinden).

    Returns: [{ title, source, first_price, last_price, min_price, max_price,
                change_pct, kind: 'drop'|'stable' }]
    """
    if not _enabled():
        return []
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/price_history"
            f"?select=product_key,title,source,price,recorded_at"
            f"&order=recorded_at.desc"
            f"&limit={int(sample)}"
        )
        resp = requests.get(url, headers=_headers(), timeout=6)
        rows = resp.json() if resp.ok else []
    except Exception as exc:
        logger.warning("get_biggest_movers error: %s", exc)
        return []

    if not rows:
        return []

    by_key: dict[str, dict] = {}
    for row in rows:
        k = row.get("product_key")
        p = row.get("price")
        if not k or p is None:
            continue
        entry = by_key.setdefault(k, {
            "title": row.get("title", ""),
            "source": row.get("source", ""),
            "prices": [],
        })
        entry["prices"].append(float(p))

    movers = []
    for k, entry in by_key.items():
        prices = entry["prices"]  # rows are desc, so prices[0] = latest
        if len(prices) < 2:
            continue
        latest = prices[0]
        oldest = prices[-1]
        lowest = min(prices)
        highest = max(prices)
        if highest <= 0:
            continue
        drop_pct = round((highest - latest) / highest * 100, 1)
        movers.append({
            "title": entry["title"],
            "source": entry["source"],
            "first_price": oldest,
            "last_price": latest,
            "min_price": lowest,
            "max_price": highest,
            "change_pct": drop_pct,
            "data_points": len(prices),
        })

    movers.sort(key=lambda m: m["change_pct"], reverse=True)
    return movers[:limit]


def get_category_price_change(store_slugs: list[str], days: int = 30, sample: int = 1000) -> dict | None:
    """Verilen kategori mağazaları için son N gündeki ortalama fiyat değişim yüzdesi.

    Returns None if data unavailable (caller should render a 'yakında' placeholder).
    """
    if not _enabled() or not store_slugs:
        return None
    try:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sources_filter = "(" + ",".join(f'"{s}"' for s in store_slugs) + ")"
        url = (
            f"{SUPABASE_URL}/rest/v1/price_history"
            f"?source=in.{sources_filter}"
            f"&recorded_at=gt.{since}"
            f"&select=product_key,price,recorded_at"
            f"&order=recorded_at.asc"
            f"&limit={int(sample)}"
        )
        resp = requests.get(url, headers=_headers(), timeout=6)
        rows = resp.json() if resp.ok else []
    except Exception as exc:
        logger.warning("get_category_price_change error: %s", exc)
        return None

    if not rows:
        return None

    by_key: dict[str, list[float]] = {}
    for row in rows:
        k = row.get("product_key")
        p = row.get("price")
        if k and p is not None:
            by_key.setdefault(k, []).append(float(p))

    pcts = []
    for prices in by_key.values():
        if len(prices) < 2 or prices[0] <= 0:
            continue
        pcts.append((prices[-1] - prices[0]) / prices[0] * 100)

    if not pcts:
        return None

    avg_pct = round(sum(pcts) / len(pcts), 1)
    return {"avg_change_pct": avg_pct, "sample_size": len(pcts), "days": days}
