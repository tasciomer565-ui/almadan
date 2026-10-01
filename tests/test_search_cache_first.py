"""search_products_by_name: taze + 2+ magazali product_cache varsa scraper servisine gitmez."""
from unittest import mock

import app.cache as cache
import app.comparator as comparator


def _products(sources):
    models = ["T40", "H30", "D55", "S21", "K72"]
    return [{"title": f"Vestel {models[i]} Elektrikli Süpürge", "price": 1000 + i * 100, "source": s,
             "url": f"https://x/{s}/{i}"} for i, s in enumerate(sources)]


def _search(latest, mode="hybrid"):
    railway = _products(["amazon"] * 3)
    with mock.patch.object(cache, "_enabled", return_value=True), \
         mock.patch.object(cache, "cache_get_latest", return_value=latest), \
         mock.patch.object(comparator, "_call_railway_scraper", return_value=railway) as rw:
        out = comparator.search_products_by_name("vestel süpürge", mode=mode)
    return out, rw.call_count


def test_fresh_multi_store_cache_skips_scraper_service():
    out, calls = _search((_products(["n11", "amazon", "n11", "amazon"]), True, 3.0))
    assert calls == 0
    assert {p["source"] for p in out} == {"n11", "amazon"}


def test_single_store_cache_falls_back_to_scraper_service():
    _, calls = _search((_products(["amazon", "amazon"]), True, 3.0))
    assert calls == 1


def test_stale_cache_falls_back_to_scraper_service():
    _, calls = _search((_products(["n11", "amazon"]), False, 60.0))
    assert calls == 1


def test_local_mode_ignores_cache():
    _, calls = _search((_products(["n11", "amazon"]), True, 3.0), mode="local")
    assert calls == 1


def test_cache_products_are_not_mutated():
    cached = _products(["n11", "amazon", "n11"])
    snapshot = [dict(p) for p in cached]
    _search((cached, True, 3.0))
    assert cached == snapshot
