"""/fiyat/{terim} sayfalarinin product_cache'ini DOGRUDAN bu makineden
(GitHub Actions runner) tarayarak isitir.

Neden: eski akis (GitHub cron -> Render /cron/warm-price-terms -> scraper
servisi) calisma basina 2 terim tariyordu ve scraper servisi 2026-09
sonunda cogu terimde sadece Amazon donuyordu (ucretli proxy'ye bagimli
magazalar bos). scripts/scraper_probe.py ile dogrulandi: GitHub runner
IP'sinden proxy'siz n11 + Amazon + Karaca + SOK calisiyor -- cogu terimde
2+ magaza, yani sayfa indexlenebilir (bkz. app/seo_rules.py).

Secim sirasi (taze kayitlar atlanir):
  1. GSC'de gosterim alan terimler, gosterime gore (app/seo_warm_priority.json)
  2. cache'te hic kaydi olmayan terimler
  3. suresi en once dolmus terimler

Koruma: yeni tarama 2'den az magaza donuyorsa VE eski kayitta daha fazla
magaza varsa yazilmaz (tek magazali taze veri, cok magazali eski veriyi
ezip sayfayi noindex'e dusurmesin).

Kullanim:
    python scripts/warm_price_cache.py [--limit 240] [--ttl 48] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Proxy'siz, dogrudan istek: runner'da anahtar yok ama acikca garanti et.
for _key in ("SCRAPINGDOG_API_KEY", "SCRAPINGBEE_API_KEY"):
    os.environ.pop(_key, None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from app import cache  # noqa: E402
from app.comparator import normalize_turkish_search_query  # noqa: E402
from app.main import _price_page_cache_key, _seo_price_slug_map  # noqa: E402
from app.search_orchestrator import marketplace_scan  # noqa: E402

CONCURRENCY = 2
TIME_BUDGET_SECONDS = 20 * 60


def fetch_cache_expiry() -> dict[str, datetime]:
    """cache_key -> expires_at (tum tablo, sayfalanarak; products cekilmez)."""
    out: dict[str, datetime] = {}
    offset = 0
    while True:
        resp = requests.get(
            f"{cache.SUPABASE_URL}/rest/v1/{cache.CACHE_TABLE}",
            headers=cache._headers(),
            params={"select": "cache_key,expires_at", "order": "cache_key.asc",
                    "limit": 1000, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json()
        for row in rows:
            try:
                out[row["cache_key"]] = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                continue
        if len(rows) < 1000:
            return out
        offset += 1000


def _priority_rank() -> dict[str, int]:
    """GSC'de gosterim alan /fiyat slug'lari -> sira (0 = en cok gosterim)."""
    import json
    try:
        data = json.loads((ROOT / "app" / "seo_warm_priority.json").read_text(encoding="utf-8"))
        return {slug: i for i, slug in enumerate(data.get("slugs", []))}
    except (OSError, ValueError):
        return {}


def pick_terms(expiry: dict[str, datetime], limit: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    boost = _priority_rank()
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    candidates = []
    for slug, term in _seo_price_slug_map().items():
        query = normalize_turkish_search_query(term)
        key, category = _price_page_cache_key(query)
        expires_at = expiry.get(key)
        if expires_at and expires_at > now:
            continue  # hala taze
        priority = (
            0 if slug in boost else 1,
            boost.get(slug, 0),
            0 if expires_at is None else 1,
            expires_at or epoch,
        )
        candidates.append({"slug": slug, "query": query, "key": key, "category": category,
                           "priority": priority})
    candidates.sort(key=lambda c: c["priority"])
    return candidates[:limit]


def _store_count(products: list) -> int:
    return len({p.get("source") for p in products if isinstance(p, dict) and p.get("source")})


async def warm_one(item: dict, ttl_hours: int, dry_run: bool) -> tuple[str, list[str]]:
    try:
        async with asyncio.timeout(20):
            raw = await marketplace_scan(item["query"], forced_category=item["category"])
    except Exception as exc:  # noqa: BLE001
        return f"hata:{type(exc).__name__}", []
    raw = [p for p in (raw or []) if isinstance(p, dict) and p.get("title") and p.get("url")]
    if not raw:
        return "bos", []

    sources = sorted({p.get("source") for p in raw if p.get("source")})
    if len(sources) < 2:
        old = await asyncio.to_thread(cache.cache_get_latest, item["key"])
        if old and _store_count(old[0]) > len(sources):
            return "atlandi:az-magaza", sources

    # master_search'un cache'e yazmadan once ekledigi teslimat alanlari
    # (konumsuz arama varsayilanlari) -- cache'ten okuyan kod bunlari bekliyor.
    for p in raw:
        p.setdefault("delivery_type", "global")
        p.setdefault("delivery_time", "2 İş Günü")
        p.setdefault("distance_km", None)
        p.setdefault("latitude", None)
        p.setdefault("longitude", None)
        p.setdefault("delivery_cost", "Ücretsiz Kargo")

    if dry_run:
        return "yazilacakti", sources

    def _write() -> str:
        try:
            from app.price_history import record_prices
            record_prices(raw)
        except Exception:  # noqa: BLE001
            pass
        cache.LAST_SET_DIAG = ""
        cache.cache_set(item["key"], item["query"], item["category"], raw, ttl_hours=ttl_hours)
        return cache.LAST_SET_DIAG or "?"

    result = await asyncio.to_thread(_write)
    return ("yazildi" if result == "ok" else f"yazma-hatasi:{result}"), sources


async def main_async(limit: int, ttl_hours: int, dry_run: bool) -> int:
    if not cache._enabled():
        print("HATA: SUPABASE_URL / SUPABASE_SERVICE_KEY tanimli degil.", file=sys.stderr)
        return 1

    expiry = fetch_cache_expiry()
    items = pick_terms(expiry, limit)
    print(f"cache'te {len(expiry)} kayit; bu turda {len(items)} terim taranacak "
          f"(ttl={ttl_hours}s, dry_run={dry_run})")

    started = time.time()
    outcomes: Counter[str] = Counter()
    store_hits: Counter[str] = Counter()
    multi_store = 0
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _run(item: dict) -> None:
        nonlocal multi_store
        async with sem:
            if time.time() - started > TIME_BUDGET_SECONDS:
                outcomes["sure-doldu"] += 1
                return
            outcome, sources = await warm_one(item, ttl_hours, dry_run)
            outcomes[outcome] += 1
            if outcome in ("yazildi", "yazilacakti"):
                store_hits.update(sources)
                if len(sources) >= 2:
                    multi_store += 1
            print(f"  {item['slug']:34} {outcome:22} {','.join(sources)}")

    await asyncio.gather(*(_run(item) for item in items))

    written = outcomes["yazildi"] + outcomes["yazilacakti"]
    print(f"\nozet ({int(time.time() - started)}s): " + ", ".join(f"{k}={v}" for k, v in outcomes.most_common()))
    print(f"2+ magazali yazilan: {multi_store}/{written}")
    print("magaza dagilimi: " + ", ".join(f"{k}={v}" for k, v in store_hits.most_common()))
    # Yazma hatasi varsa is basarisiz gorunsun (sessiz bozulma olmasin).
    return 1 if any(k.startswith("yazma-hatasi") for k in outcomes) else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=240)
    parser.add_argument("--ttl", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args.limit, args.ttl, args.dry_run)))


if __name__ == "__main__":
    main()
