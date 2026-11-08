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
    python scripts/warm_price_cache.py [--limit 400] [--ttl 48] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
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
from app.warm_demand import count_search_terms  # noqa: E402
from app.warm_extra_terms import extra_warm_terms  # noqa: E402

CONCURRENCY = 2
TIME_BUDGET_SECONDS = 24 * 60  # is zaman asimi 30 dk; kurulum ~1 dk
SKIP_IF_FRESH_FOR_HOURS = 6


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


def fetch_demand_terms(days: int = 14, max_rows: int = 3000) -> dict[str, int]:
    """Son `days` gunde en cok aranan sorgular (user_events.url_search). Hata -> bos."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        resp = requests.get(
            f"{cache.SUPABASE_URL}/rest/v1/user_events",
            headers=cache._headers(),
            params={"select": "payload", "event_type": "eq.url_search",
                    "created_at": f"gt.{since}", "order": "created_at.desc", "limit": max_rows},
            timeout=30,
        )
        resp.raise_for_status()
        return dict(count_search_terms(resp.json()))
    except Exception as exc:  # noqa: BLE001
        print(f"uyari: arama talebi okunamadi ({type(exc).__name__}) -- sadece sabit listeler taranacak")
        return {}


def _priority_rank() -> dict[str, int]:
    """GSC'de gosterim alan /fiyat slug'lari -> sira (0 = en cok gosterim)."""
    import json
    try:
        data = json.loads((ROOT / "app" / "seo_warm_priority.json").read_text(encoding="utf-8"))
        return {slug: i for i, slug in enumerate(data.get("slugs", []))}
    except (OSError, ValueError):
        return {}


def pick_terms(expiry: dict[str, datetime], limit: int, demand: dict[str, int] | None = None) -> list[dict]:
    now = datetime.now(timezone.utc)
    boost = _priority_rank()
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    candidates = []
    for slug, term in _seo_price_slug_map().items():
        query = normalize_turkish_search_query(term)
        key, category = _price_page_cache_key(query)
        expires_at = expiry.get(key)
        # Sadece omru 6 saatten fazla kalan kayitlari atla: bu script 48 saat
        # TTL ile yazar; 6 saat ve altinda omru kalanlar ya son demlerindeki
        # kendi kayitlari ya da scraper servisinin (varsayilan TTL 6 saat,
        # cogu zaman tek magazali) yazdiklaridir -- onlar isitmayi engellemesin.
        if expires_at and expires_at > now + timedelta(hours=SKIP_IF_FRESH_FOR_HOURS):
            continue
        priority = (
            0 if slug in boost else 1,
            boost.get(slug, 0),
            0 if expires_at is None else 1,
            expires_at or epoch,
        )
        candidates.append({"slug": slug, "query": query, "key": key, "category": category,
                           "priority": priority})
    # SEO whitelist'inde olmayan model/marka sorgulari (ör. "iphone 15"): canli
    # aramada en cok sorulanlar bunlar; onbellekte yoksa sadece Amazon doner.
    # En yuksek oncelik: GSC onceliklerinden bile once, cunku sayilari az.
    seo_keys = {c["key"] for c in candidates}
    for term in extra_warm_terms():
        query = normalize_turkish_search_query(term)
        key, category = _price_page_cache_key(query)
        if key in seo_keys:  # ayni cache anahtari zaten aday (SEO listesi ya da onceki ek terim)
            continue
        expires_at = expiry.get(key)
        if expires_at and expires_at > now + timedelta(hours=SKIP_IF_FRESH_FOR_HOURS):
            continue
        seo_keys.add(key)
        candidates.append({"slug": "x:" + term.replace(" ", "-"), "query": query, "key": key,
                           "category": category,
                           "priority": (0, -1, 0 if expires_at is None else 1, expires_at or epoch)})
    # Gercek kullanici aramalari (user_events): en yuksek oncelik, cok aranandan aza.
    # Onbellekte olmayan sorgu canlida tek magaza dondurur; bir kez aranan sorgu
    # sonraki turda cok magazali hazir olur.
    for term, count in sorted((demand or {}).items(), key=lambda kv: -kv[1]):
        query = normalize_turkish_search_query(term)
        key, category = _price_page_cache_key(query)
        if key in seo_keys:
            continue
        expires_at = expiry.get(key)
        if expires_at and expires_at > now + timedelta(hours=SKIP_IF_FRESH_FOR_HOURS):
            continue
        seo_keys.add(key)
        candidates.append({"slug": "d:" + term.replace(" ", "-"), "query": query, "key": key,
                           "category": category,
                           "priority": (0, -2, -count, expires_at or epoch)})
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


def _write_step_summary(rows, outcomes, store_hits, multi_store, written, demand, seconds) -> None:
    """GitHub Actions "Summary" sayfasina ozet yazar (ham gunluk cok buyuk oldugu icin
    arayuzde kesiliyor). GITHUB_STEP_SUMMARY yoksa (yerel calisma) hicbir sey yapmaz."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        lines = [
            "## Onbellek isitma ozeti",
            f"- sure: {seconds}s, yazilan: {written}, 2+ magazali: {multi_store}",
            "- sonuclar: " + ", ".join(f"{k}={v}" for k, v in outcomes.most_common()),
            "- magaza dagilimi: " + ", ".join(f"{k}={v}" for k, v in store_hits.most_common()),
            f"- gercek arama talebi: {len(demand)} benzersiz sorgu",
            "",
            "### Ek model/marka (x:) ve gercek arama (d:) terimleri",
            "| terim | sonuc | magazalar |",
            "|---|---|---|",
        ]
        for slug, outcome, sources in rows:
            if slug.startswith(("x:", "d:")):
                lines.append(f"| {slug} | {outcome} | {', '.join(sources) or '-'} |")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


async def main_async(limit: int, ttl_hours: int, dry_run: bool) -> int:
    if not cache._enabled():
        print("HATA: SUPABASE_URL / SUPABASE_SERVICE_KEY tanimli degil.", file=sys.stderr)
        return 1

    expiry = fetch_cache_expiry()
    demand = fetch_demand_terms()
    items = pick_terms(expiry, limit, demand)
    print(f"gercek arama talebi: {len(demand)} benzersiz sorgu (son 14 gun)")
    print(f"cache'te {len(expiry)} kayit; bu turda {len(items)} terim taranacak "
          f"(ttl={ttl_hours}s, dry_run={dry_run})")

    started = time.time()
    outcomes: Counter[str] = Counter()
    store_hits: Counter[str] = Counter()
    multi_store = 0
    sem = asyncio.Semaphore(CONCURRENCY)
    rows: list[tuple[str, str, list[str]]] = []  # (slug, sonuc, magazalar) -- ozet sayfasi icin

    async def _run(item: dict) -> None:
        nonlocal multi_store
        async with sem:
            if time.time() - started > TIME_BUDGET_SECONDS:
                outcomes["sure-doldu"] += 1
                return
            outcome, sources = await warm_one(item, ttl_hours, dry_run)
            outcomes[outcome] += 1
            rows.append((item["slug"], outcome, list(sources)))
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
    _write_step_summary(rows, outcomes, store_hits, multi_store, written, demand, int(time.time() - started))
    # Yazma hatasi varsa is basarisiz gorunsun (sessiz bozulma olmasin).
    return 1 if any(k.startswith("yazma-hatasi") for k in outcomes) else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--ttl", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args.limit, args.ttl, args.dry_run)))


if __name__ == "__main__":
    main()
