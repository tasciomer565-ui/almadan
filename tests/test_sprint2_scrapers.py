"""
Sprint 2 — Scraper birim testleri

Ağ bağlantısı gerektiren testler @pytest.mark.integration ile işaretli.
Çalıştırma:
    pytest tests/test_sprint2_scrapers.py -v              # sadece unit
    pytest tests/test_sprint2_scrapers.py -v -m integration  # canlı ağ
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── BaseScraper Testleri ─────────────────────────────────────

class TestBaseScraper:
    def _make_scraper(self):
        from app.scrapers.base import BaseScraper
        class DummyScraper(BaseScraper):
            name = "dummy"
            base_url = "https://example.com"
            def search(self, query):
                return []
        return DummyScraper()

    def test_parse_price_turkish_format(self):
        s = self._make_scraper()
        assert s.parse_price("49,90 TL") == 49.90
        assert s.parse_price("1.299,00 TL") == 1299.0
        assert s.parse_price("₺23,50") == 23.50
        assert s.parse_price("150") == 150.0
        assert (s.parse_price("0") or 0) == 0  # 0.0 veya None — ikisi de geçersiz fiyat
        assert s.parse_price(None) is None
        assert s.parse_price("") is None

    def test_parse_price_numeric_input(self):
        s = self._make_scraper()
        assert s.parse_price(99.90) == 99.90
        assert s.parse_price(100) == 100.0
        assert s.parse_price(0) is None
        assert s.parse_price(-5) is None

    def test_normalize_product_valid(self):
        s = self._make_scraper()
        product = s._normalize_product(
            title="Test Ürün 500g",
            price="29,90",
            url="https://example.com/test",
            image_url="https://example.com/img.jpg",
        )
        assert product is not None
        assert product["title"] == "Test Ürün 500g"
        assert product["price"] == 29.90
        assert product["source"] == "dummy"

    def test_normalize_product_empty_title_returns_none(self):
        s = self._make_scraper()
        assert s._normalize_product(title="", price="29,90", url="https://x.com") is None

    def test_normalize_product_invalid_price_returns_none(self):
        s = self._make_scraper()
        assert s._normalize_product(title="Ürün", price="ücretsiz", url="https://x.com") is None
        assert s._normalize_product(title="Ürün", price=None, url="https://x.com") is None
        assert s._normalize_product(title="Ürün", price=0, url="https://x.com") is None

    def test_bot_detection_raises(self):
        from app.scrapers.base import BaseScraper, BotDetectedError
        s = self._make_scraper()
        with pytest.raises(BotDetectedError):
            s._assert_not_bot("Access Denied by Cloudflare", "https://x.com")

    def test_bot_detection_normal_html_passes(self):
        s = self._make_scraper()
        # Normal HTML içeriğinde exception fırlatmamalı
        s._assert_not_bot("<html><body><h1>Ürünler</h1></body></html>", "https://x.com")


# ── MigrosScraper Testleri ───────────────────────────────────

class TestMigrosScraper:
    def test_parse_hermes_response_valid(self):
        from app.scrapers.migros import MigrosScraper
        scraper = MigrosScraper()
        mock_data = {
            "products": [
                {
                    "name": "Migros Tam Yağlı Süt 1L",
                    "shownPrice": 24.90,
                    "imageUrl": "https://cdn.migros.com.tr/sut.jpg",
                    "url": "migros-tam-yagli-sut-1l-p-abc123",
                    "status": "IN_SALE",
                }
            ]
        }
        results = scraper._parse_hermes_response(mock_data, limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Migros Tam Yağlı Süt 1L"
        assert results[0]["price"] == 24.90
        assert results[0]["source"] == "migros"

    def test_parse_rest_response_valid(self):
        from app.scrapers.migros import MigrosScraper
        scraper = MigrosScraper()
        mock_data = {
            "data": {
                "products": [
                    {
                        "name": "Pınar Süt 1L",
                        "salePrice": 27.50,
                        "listPrice": 30.00,
                        "imageUrl": "https://cdn.migros.com.tr/pinar.jpg",
                        "url": "pinar-sut-1l-p-xyz",
                        "campaignUnit": True,
                    }
                ]
            }
        }
        results = scraper._parse_rest_response(mock_data, limit=10)
        assert len(results) == 1
        assert results[0]["price"] == 27.50
        assert results[0]["original_price"] == 30.00
        assert "Kampanyalı" in results[0]["labels"]

    def test_parse_empty_response(self):
        from app.scrapers.migros import MigrosScraper
        scraper = MigrosScraper()
        assert scraper._parse_hermes_response({}, 10) == []
        assert scraper._parse_hermes_response({"products": []}, 10) == []
        assert scraper._parse_rest_response({"data": {"products": []}}, 10) == []

    def test_parse_invalid_items_skipped(self):
        from app.scrapers.migros import MigrosScraper
        scraper = MigrosScraper()
        data = {
            "products": [
                {"name": "", "shownPrice": 10},          # boş başlık
                {"name": "İyi Ürün", "shownPrice": 0},   # geçersiz fiyat
                {"name": "Geçerli Ürün", "shownPrice": 15.99, "url": "/p/1"},
            ]
        }
        results = scraper._parse_hermes_response(data, 10)
        assert len(results) == 1
        assert results[0]["title"] == "Geçerli Ürün"

    def test_product_url_construction(self):
        from app.scrapers.migros import MigrosScraper
        scraper = MigrosScraper()
        # slug ile URL
        item = {"name": "Test", "shownPrice": 10, "url": "test-urun-p-abc"}
        product = scraper._parse_hermes_item(item)
        assert product is not None
        assert "migros.com.tr/test-urun-p-abc" in product["url"]

    def test_search_returns_empty_on_all_api_failure(self):
        from app.scrapers.migros import MigrosScraper
        from app.scrapers.base import ScraperError
        scraper = MigrosScraper()
        with patch.object(scraper, "_search_api", side_effect=ScraperError("404", retryable=False)):
            with patch.object(scraper, "_search_html", return_value=[]):
                results = scraper.search("xyz_nonexistent_product_abc")
                assert results == []

    @pytest.mark.integration
    def test_search_live_sut(self):
        """CANLI TEST: Migros API'sinde 'süt' araması."""
        from app.scrapers.migros import MigrosScraper
        scraper = MigrosScraper()
        results = scraper.search("süt", limit=5)
        assert isinstance(results, list)
        if results:
            assert all("title" in r and "price" in r and r["price"] > 0 for r in results)
            assert all(r["source"] == "migros" for r in results)


# ── CarrefourSAScraper Testleri ──────────────────────────────

class TestCarrefourSAScraper:
    def test_parse_api_response_valid(self):
        from app.scrapers.carrefoursa import CarrefourSAScraper
        scraper = CarrefourSAScraper()
        data = {
            "products": [
                {
                    "name": "Sek Süt 1L",
                    "price": {"value": 22.50},
                    "imageUrl": "https://carrefour.com/sek.jpg",
                    "url": "/p/sek-sut-1l",
                    "code": "12345",
                    "stock": {"stockLevelStatus": "inStock"},
                }
            ]
        }
        results = scraper._parse_api_response(data, 10)
        assert len(results) == 1
        assert results[0]["price"] == 22.50

    def test_parse_nested_price_format(self):
        from app.scrapers.carrefoursa import CarrefourSAScraper
        scraper = CarrefourSAScraper()
        item = {
            "name": "Ürün",
            "price": {"value": 35.90},
            "originalPrice": {"value": 40.00},
            "url": "/p/urun",
        }
        product = scraper._parse_item(item)
        assert product is not None
        assert product["price"] == 35.90
        assert product["original_price"] == 40.00

    def test_out_of_stock_flagged(self):
        from app.scrapers.carrefoursa import CarrefourSAScraper
        scraper = CarrefourSAScraper()
        item = {
            "name": "Ürün",
            "price": {"value": 15.0},
            "url": "/p/urun",
            "stock": {"stockLevelStatus": "outOfStock"},
        }
        product = scraper._parse_item(item)
        assert product is not None
        assert product["extra_info"]["out_of_stock"] is True

    @pytest.mark.integration
    def test_search_live_no_crash(self):
        """CANLI TEST: CarrefourSA arama — sonuç olmasa da crash etmemeli."""
        from app.scrapers.carrefoursa import CarrefourSAScraper
        scraper = CarrefourSAScraper()
        results = scraper.search("süt", limit=5)
        assert isinstance(results, list)
        for r in results:
            assert "title" in r
            assert r["price"] > 0


# ── A101Scraper Testleri ─────────────────────────────────────

class TestA101Scraper:
    def test_parse_valid_api_response(self):
        from app.scrapers.a101 import A101Scraper
        scraper = A101Scraper()
        data = {
            "products": [
                {
                    "name": "Ayçiçek Yağı 5L",
                    "price": 189.90,
                    "imageUrl": "https://a101.com/yag.jpg",
                    "url": "/aycicek-yagi",
                }
            ]
        }
        results = scraper._parse(data, 10)
        assert len(results) == 1
        assert results[0]["title"] == "Ayçiçek Yağı 5L"
        assert results[0]["price"] == 189.90

    @pytest.mark.integration
    def test_search_live_no_crash(self):
        from app.scrapers.a101 import A101Scraper
        scraper = A101Scraper()
        results = scraper.search("şeker", limit=5)
        assert isinstance(results, list)


# ── Proxy Stratejisi Testleri ────────────────────────────────

class TestProxyStrategy:
    def test_proxy_disabled_when_no_api_key(self):
        import os
        with patch.dict(os.environ, {"SCRAPINGBEE_API_KEY": ""}):
            from app.scrapers.migros import MigrosScraper
            scraper = MigrosScraper()
            scraper._proxy_enabled = scraper._check_proxy()
            assert scraper._proxy_enabled is False

    def test_proxy_enabled_with_api_key(self):
        import os
        with patch.dict(os.environ, {"SCRAPINGBEE_API_KEY": "test_key_abc123"}):
            from app.scrapers.migros import MigrosScraper
            scraper = MigrosScraper()
            scraper._proxy_enabled = scraper._check_proxy()
            assert scraper._proxy_enabled is True
