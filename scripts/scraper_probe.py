"""Magaza scraper'larinin BU makinenin IP'sinden (proxy'siz) calisip
calismadigini olcer. GitHub Actions runner'larindan tarama yapmanin mumkun
olup olmadigini gormek icin (bkz. .github/workflows/scraper-probe.yml).

Proxy anahtarlari bilerek ortamdan silinir -- amac dogrudan istegi olcmek.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for _key in ("SCRAPINGDOG_API_KEY", "SCRAPINGBEE_API_KEY"):
    os.environ.pop(_key, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from app import comparator  # noqa: E402

SCRAPERS = [
    "search_n11_direct", "search_amazon_tr", "search_trendyol_direct",
    "search_hepsiburada_direct", "search_pazarama", "search_mediamarkt",
    "search_teknosa", "search_vatanbilgisayar", "search_karaca",
    "search_vivense", "search_rossmann", "search_flo", "search_sokmarket",
]
QUERIES = ["sony hoparlör", "vestel süpürge", "nohut"]


def _probe(args: tuple[str, str]) -> tuple[str, str, object, float, str]:
    name, query = args
    started = time.time()
    try:
        result = getattr(comparator, name)(query)
        if isinstance(result, tuple):
            result = result[0]
        result = result or []
        sample = result[0].get("title", "")[:45] if result else ""
        return name, query, len(result), round(time.time() - started, 1), sample
    except Exception as exc:  # noqa: BLE001
        return name, query, f"HATA {type(exc).__name__}", round(time.time() - started, 1), ""


def main() -> None:
    try:
        info = requests.get("https://ipinfo.io/json", timeout=10).json()
        print(f"IP ulke/sehir/org: {info.get('country')} / {info.get('city')} / {info.get('org')}")
    except Exception as exc:  # noqa: BLE001
        print(f"IP bilgisi alinamadi: {exc}")

    jobs = [(name, query) for query in QUERIES for name in SCRAPERS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(_probe, jobs))

    for query in QUERIES:
        print(f"\n== {query}")
        for name, q, count, took, sample in rows:
            if q == query:
                print(f"  {name:28} {str(count):>18}  {took:>5}s  {sample}")

    print("\n== ozet (en az bir sorguda sonuc veren magazalar)")
    working = sorted({name for name, _, count, _, _ in rows if isinstance(count, int) and count > 0})
    print("  calisan:", ", ".join(working) or "-")
    print("  calismayan:", ", ".join(sorted(set(SCRAPERS) - set(working))) or "-")


if __name__ == "__main__":
    main()
