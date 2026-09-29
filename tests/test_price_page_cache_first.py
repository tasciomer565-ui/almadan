"""/fiyat/{slug}: once product_cache, eskiyse arka planda tazeleme."""
import time
from unittest import mock

from fastapi.testclient import TestClient

import app.cache as cache
import app.comparator as comparator
import app.main as main

client = TestClient(main.app)
SLUG = "nohut"


def _products(stale_hours=None):
    items = [
        {"title": f"Nohut Koçbaşı {i} kg", "price": 40 + i * 10, "source": s,
         "url": f"https://x/{i}", "image_url": ""}
        for i, s in enumerate(["sokmarket", "migros", "carrefoursa", "a101", "sokmarket"])
    ]
    if stale_hours is not None:
        for p in items:
            p["stale_age"] = f"{stale_hours} saat"
    return items


def _get(fresh, stale, live):
    main._PRICE_PAGE_HTML_CACHE.clear()
    with mock.patch.object(cache, "_enabled", return_value=True), \
         mock.patch.object(cache, "cache_get", return_value=fresh), \
         mock.patch.object(cache, "cache_get_stale", return_value=stale), \
         mock.patch.object(comparator, "search_products_by_name", return_value=live) as live_search:
        resp = client.get(f"/fiyat/{SLUG}")
        for _ in range(50):  # arka plan tazelemesinin bitmesini bekle
            if not main._PRICE_REFRESH_INFLIGHT:
                break
            time.sleep(0.02)
        return resp, live_search.call_count


def test_fresh_cache_skips_live_scrape():
    resp, calls = _get(_products(), None, _products())
    assert resp.status_code == 200
    assert calls == 0
    assert "önce güncellendi" not in resp.text


def test_stale_cache_renders_and_refreshes_in_background():
    resp, calls = _get(None, _products(stale_hours=7), _products())
    assert resp.status_code == 200
    assert "Fiyatlar 7 saat önce güncellendi" in resp.text
    assert calls == 1
    assert SLUG not in main._PRICE_PAGE_HTML_CACHE


def test_no_cache_falls_back_to_live_scrape():
    resp, calls = _get(None, None, _products())
    assert resp.status_code == 200
    assert calls == 1


def test_cache_disabled_is_reported_in_header():
    main._PRICE_PAGE_HTML_CACHE.clear()
    with mock.patch.object(cache, "_enabled", return_value=False), \
         mock.patch.object(comparator, "search_products_by_name", return_value=_products()):
        resp = client.get(f"/fiyat/{SLUG}")
    assert resp.headers["X-Price-Source"].startswith("cache-disabled")
    assert resp.headers["X-Price-Source"].endswith(";live")


def test_nothing_anywhere_is_404():
    resp, _ = _get(None, None, [])
    assert resp.status_code == 404
