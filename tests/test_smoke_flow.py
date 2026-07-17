"""Kritik kullanici akisinin (parse-url -> find-alternatives) API seviyesinde
smoke-testi. Gercek ag istegi YAPILMAZ -- parse_product_url ve
master_search/marketplace_scan/is_logical_product fonksiyonlari mock'lanir,
sadece endpoint kod yolunun (istek -> yanit) sorunsuz calistigi dogrulanir.
"""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import parse_url, find_alternatives, UrlParseRequest, AlternativesRequest
from app.parser import ParsedProduct


def _run(coro):
    return asyncio.run(coro)


def test_parse_url_smoke():
    fake_parsed = ParsedProduct(
        title="Apple iPhone 15 128 GB Mavi",
        price=32999.0,
        image_url="https://example.com/img.jpg",
        source="trendyol",
        canonical_url="https://www.trendyol.com/apple/iphone-15-p-1",
        confidence=90,
        warnings=[],
        original_price=34999.0,
        extra_info={},
    )
    payload = UrlParseRequest(url="https://www.trendyol.com/apple/iphone-15-p-1")
    with patch("app.main.parse_product_url", return_value=fake_parsed):
        result = parse_url(payload)

    assert result["title"] == "Apple iPhone 15 128 GB Mavi"
    assert result["price"] == 32999.0
    assert result["source"] == "trendyol"


def test_find_alternatives_smoke():
    fake_products = [
        {
            "title": "Apple iPhone 15 128 GB Mavi", "price": 31999.0, "original_price": None,
            "image_url": "https://example.com/img2.jpg", "source": "hepsiburada",
            "url": "https://www.hepsiburada.com/apple-iphone-15-p-HB123",
            "labels": ["En Ucuz"], "extra_info": {"out_of_stock": False}, "verified": True,
        },
    ]

    class _FakeRequest:
        headers = {}
        cookies = {}
        client = MagicMock(host="127.0.0.1")
        state = MagicMock()

    payload = AlternativesRequest(
        title="Apple iPhone 15 128 GB Mavi",
        original_url="https://www.trendyol.com/apple/iphone-15-p-1",
        source="trendyol",
        image_url="https://example.com/img.jpg",
        price=32999.0,
    )

    with patch("app.security.check_rate_limit", return_value=None), \
         patch("app.search_orchestrator.master_search", new=AsyncMock(return_value=fake_products)), \
         patch("app.search_orchestrator.marketplace_scan", new=AsyncMock(return_value=fake_products)), \
         patch("app.comparator.is_logical_product", return_value=True):
        result = _run(find_alternatives(payload, _FakeRequest()))

    assert isinstance(result, dict)
    # 'products' veya benzeri bir anahtar altinda liste donmeli
    products_key = "products" if "products" in result else next(
        (k for k, v in result.items() if isinstance(v, list)), None
    )
    assert products_key is not None
    assert isinstance(result[products_key], list)
