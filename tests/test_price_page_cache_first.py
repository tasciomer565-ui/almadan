"""/fiyat/{slug}: once product_cache, eskiyse arka planda tazeleme."""
import time
from unittest import mock

from fastapi.testclient import TestClient

import app.cache as cache
import app.comparator as comparator
import app.main as main

client = TestClient(main.app)
SLUG = "nohut"


def _products():
    return [
        {"title": f"Nohut Koçbaşı {i} kg", "price": 40 + i * 10, "source": s,
         "url": f"https://x/{i}", "image_url": ""}
        for i, s in enumerate(["sokmarket", "migros", "carrefoursa", "a101", "sokmarket"])
    ]


def _get(latest, live, railway=None):
    """latest: cache_get_latest donusu ((urunler, taze_mi, yas_saat) ya da None)."""
    main._PRICE_PAGE_HTML_CACHE.clear()
    main._PRICE_REFRESH_LAST.clear()
    with mock.patch.object(cache, "_enabled", return_value=True), \
         mock.patch.object(cache, "cache_get_latest", return_value=latest), \
         mock.patch.object(cache, "cache_set") as cache_set, \
         mock.patch.object(comparator, "_call_railway_scraper", return_value=railway), \
         mock.patch.object(comparator, "search_products_by_name", return_value=live) as live_search:
        resp = client.get(f"/fiyat/{SLUG}")
        for _ in range(50):  # arka plan tazelemesinin bitmesini bekle
            if not main._PRICE_REFRESH_INFLIGHT:
                break
            time.sleep(0.02)
        return resp, live_search.call_count, cache_set.call_count


def test_fresh_cache_skips_live_scrape():
    resp, calls, _ = _get((_products(), True, 1.0), _products())
    assert resp.status_code == 200
    assert calls == 0
    assert "önce güncellendi" not in resp.text
    assert resp.headers["X-Price-Source"].startswith("cache-fresh")


def test_stale_cache_renders_and_refreshes_in_background():
    resp, _, writes = _get((_products(), False, 7.4), _products(), railway=_products())
    assert resp.status_code == 200
    assert "Fiyatlar 7 saat önce güncellendi" in resp.text
    # Railway sonucu arka planda cache'e bu tarafta yazilir
    assert writes == 1
    assert SLUG not in main._PRICE_PAGE_HTML_CACHE


def test_stale_age_in_days():
    resp, _, _ = _get((_products(), False, 50.0), _products(), railway=_products())
    assert "Fiyatlar 2 gün önce güncellendi" in resp.text


def test_stale_refresh_without_railway_does_not_run_local_search():
    # Yerel tam arama arka plan thread'inde canlida dakikalarca takiliyordu
    _, calls, writes = _get((_products(), False, 7.0), _products(), railway=None)
    assert calls == 0
    assert writes == 0
    assert main._PRICE_REFRESH_LAST[SLUG].startswith("railway:sonuc-yok")


def test_stale_refresh_does_not_overwrite_with_fewer_stores():
    # Railway su an cogu terimde sadece Amazon donuyor; 4 magazali eski kayit
    # tek magazali taze sonucla ezilmemeli
    amazon_only = [dict(p, source="amazon") for p in _products()]
    _, _, writes = _get((_products(), False, 7.0), _products(), railway=amazon_only)
    assert writes == 0
    assert main._PRICE_REFRESH_LAST[SLUG].startswith("railway:az-magaza(1<4)")


def test_no_cache_falls_back_to_live_scrape():
    resp, calls, _ = _get(None, _products())
    assert resp.status_code == 200
    assert calls == 1


def test_cache_disabled_is_reported_in_header():
    main._PRICE_PAGE_HTML_CACHE.clear()
    main._PRICE_REFRESH_LAST.clear()
    with mock.patch.object(cache, "_enabled", return_value=False), \
         mock.patch.object(comparator, "search_products_by_name", return_value=_products()):
        resp = client.get(f"/fiyat/{SLUG}")
    assert resp.headers["X-Price-Source"].startswith("cache-disabled")
    assert resp.headers["X-Price-Source"].endswith(";live")


def test_nothing_anywhere_is_404():
    resp, _, _ = _get(None, [])
    assert resp.status_code == 404


def test_slow_live_scrape_does_not_block_other_requests():
    """price_landing_page 'async def' iken canli tarama event loop'u kilitliyor,
    o sirada /health (ve robots.txt, sitemap) yanit veremiyordu."""
    import threading

    def slow_search(*_a, **_k):
        time.sleep(1.5)
        return _products()

    main._PRICE_PAGE_HTML_CACHE.clear()
    main._PRICE_REFRESH_LAST.clear()
    with TestClient(main.app) as shared, \
         mock.patch.object(cache, "_enabled", return_value=False), \
         mock.patch.object(comparator, "search_products_by_name", side_effect=slow_search):
        result = {}
        worker = threading.Thread(target=lambda: result.update(page=shared.get(f"/fiyat/{SLUG}")))
        worker.start()
        time.sleep(0.3)  # tarama basladi
        started = time.time()
        health = shared.get("/health")
        health_took = time.time() - started
        worker.join()
    assert health.status_code == 200
    assert health_took < 0.8, f"/health {health_took:.2f}s bekledi -- sunucu kilitli"
    assert result["page"].status_code == 200
