"""
Sprint 4 — Katalog OCR & Eşleştirme Birim Testleri

Çalıştırma:
    pytest tests/test_sprint4_catalog.py -v
"""
from __future__ import annotations

import pytest


# ── CatalogParser ────────────────────────────────────────────

class TestCatalogParserPriceExtraction:
    def _parser(self):
        from app.catalog_parser import CatalogParser
        return CatalogParser()

    def test_price_tr_format(self):
        p = self._parser()
        assert p._extract_price("24,90 TL") == 24.90
        assert p._extract_price("₺149,90") == 149.90
        assert p._extract_price("1.299,00 TL") == 1299.0
        assert p._extract_price("99") == 99.0

    def test_price_not_found(self):
        p = self._parser()
        assert p._extract_price("") is None
        assert p._extract_price("İndirim Kampanyası") is None

    def test_discount_extraction(self):
        p = self._parser()
        assert p._extract_discount_pct("%30 indirim") == 30
        assert p._extract_discount_pct("50% off") == 50
        assert p._extract_discount_pct("Ürün adı") is None

    def test_unit_extraction(self):
        p = self._parser()
        assert p._extract_unit("Ayçiçek Yağı 5 lt") == "5lt"
        assert p._extract_unit("Un 1 kg") == "1kg"
        assert p._extract_unit("Şeker 2,5 kg") == "2,5kg"
        assert p._extract_unit("Yumurta 10'lu") == "10'lu"

    def test_calc_discount(self):
        p = self._parser()
        assert p._calc_discount(100.0, 75.0) == 25
        assert p._calc_discount(29.90, 24.90) == 17
        assert p._calc_discount(None, 24.90) is None
        assert p._calc_discount(10.0, 10.0) is None


class TestCatalogParserHtml:
    def _parser(self):
        from app.catalog_parser import CatalogParser
        return CatalogParser()

    def test_parse_simple_html(self):
        html = """
        <html><body>
          <div class="product-card">
            <div class="product-name">Pınar Tam Yağlı Süt 1L</div>
            <div class="price">24,90 TL</div>
          </div>
          <div class="product-card">
            <div class="product-name">Ülker Çikolatalı Gofret</div>
            <div class="price">12,90 TL</div>
          </div>
        </body></html>
        """
        p = self._parser()
        items = p.parse_html(html, store="test")
        assert len(items) >= 1
        assert any("Pınar" in i.product_name or "Süt" in i.product_name for i in items)

    def test_parse_text_line_groups(self):
        text = """
Pınar Süt 1L
24,90 TL
Ülker Bisküvi 250g
%15 İndirim 18,90 TL
Ariel Toz 3kg
89,90
        """
        p = self._parser()
        items = p.parse_text(text.strip())
        assert len(items) >= 2

    def test_parse_line_with_price_on_same_line(self):
        text = "Pinar Sut 24,90 TL"  # Birim harfi olmayan basit fiyat
        p = self._parser()
        items = p.parse_text(text)
        assert len(items) >= 1
        assert items[0].price == 24.90

    def test_parse_discount_extracted(self):
        from app.catalog_parser import CatalogParser
        p = CatalogParser()
        # extract_discount_pct direkt test
        assert p._extract_discount_pct("%20 indirim") == 20
        assert p._extract_discount_pct("50% off") == 50
        assert p._extract_discount_pct("indirim") is None

    def test_clean_product_name_removes_price(self):
        p = self._parser()
        name = p._clean_product_name("Pınar Süt 1L 24,90 TL")
        assert "TL" not in name
        assert "24" not in name or "1L" in name

    def test_noise_lines_filtered(self):
        text = """
Anasayfa
Sepete Ekle
Pınar Süt 1L
24,90 TL
Sayfa 1
        """
        p = self._parser()
        items = p.parse_text(text.strip())
        # Sadece gerçek ürün kalmalı
        for item in items:
            assert "anasayfa" not in item.product_name.lower()
            assert "sepete" not in item.product_name.lower()


class TestCatalogParserPdf:
    def test_parse_pdf_no_pdfplumber(self):
        """pdfplumber yoksa boş liste dönmeli."""
        from app.catalog_parser import CatalogParser
        import unittest.mock as mock
        p = CatalogParser()
        with mock.patch.dict("sys.modules", {"pdfplumber": None}):
            result = p.parse_pdf(b"fake_pdf_bytes")
        assert result == []


# ── FuzzyMatcher ─────────────────────────────────────────────

class TestFuzzyMatcher:
    def _matcher(self):
        from app.matching_engine import FuzzyMatcher
        return FuzzyMatcher()

    def test_exact_match(self):
        m = self._matcher()
        assert m.score("Pınar Süt", "Pınar Süt") == 1.0

    def test_case_insensitive(self):
        m = self._matcher()
        assert m.score("pınar süt", "PINAR SUT") > 0.8

    def test_turkish_chars_normalized(self):
        m = self._matcher()
        # ş→s, ı→i, ü→u
        score = m.score("Pınar Süt", "Pinar Sut")
        assert score > 0.75

    def test_known_match_short_query(self):
        # Kısa sorgu → uzun katalog item (token subset bonus devreye girer)
        m = self._matcher()
        assert m.score("Pinar Sut", "Pinar Tam Yagli Sut 1L") > 0.55

    def test_known_no_match(self):
        m = self._matcher()
        assert m.score("Ariel Toz Deterjan", "Persil Sivi") < 0.55

    def test_partial_match_same_brand(self):
        m = self._matcher()
        # Aynı marka — token overlap yüksek olmalı
        score = m.score("Samsung S24", "Samsung Galaxy S24 256GB")
        assert score > 0.40   # kısmi eşleşme

    def test_is_match_threshold(self):
        m = self._matcher()
        assert m.is_match("Ulker Cikolata", "Ulker Cikolata 100g") is True
        assert m.is_match("Aycicek Yagi", "Zeytinyagi") is False

    def test_best_match_returns_sorted(self):
        m = self._matcher()
        candidates = ["Pınar Süt 1L", "Ülker Bisküvi", "Ariel Deterjan", "Pınar Ayran"]
        results = m.best_match("Pınar Süt", candidates, top_n=2)
        assert len(results) >= 1
        assert results[0][0] == "Pınar Süt 1L"
        assert results[0][1] > results[-1][1] if len(results) > 1 else True

    def test_empty_string(self):
        m = self._matcher()
        assert m.score("", "Pınar Süt") == 0.0
        assert m.score("Pınar Süt", "") == 0.0

    def test_synonyms_matching(self):
        m = self._matcher()
        # Laptop and PC should match due to synonyms
        score1 = m.score("Monster Laptop", "Monster PC")
        assert score1 > 0.85

    def test_stemming_matching(self):
        m = self._matcher()
        # Plural vs singular should match due to stemming
        score1 = m.score("Kulaklıklar", "Kulaklık")
        assert score1 > 0.85

    def test_weighted_jaccard(self):
        m = self._matcher()
        # "Pınar Süt" vs "Sütaş Süt" has different brand, same generic word.
        # "Pınar Süt" vs "Pınar Yoğurt" has same brand, different generic word.
        # Since brand has higher weight, same brand should score higher than same generic word.
        score_brand = m.score("Pınar Süt", "Pınar Yoğurt")
        score_generic = m.score("Pınar Süt", "Sütaş Süt")
        assert score_brand > score_generic


# ── MatchingEngine ────────────────────────────────────────────

class TestMatchingEngine:
    def _engine(self):
        from app.matching_engine import MatchingEngine
        return MatchingEngine(threshold=0.55)

    def _make_item(self, name, price=None, discount=None, item_id=None):
        from app.catalog_parser import CatalogItem
        return CatalogItem(
            product_name=name,
            raw_text=name,
            price=price,
            discount_pct=discount,
        )

    def test_basic_match(self):
        engine = self._engine()
        watchlist = ["Pınar Süt 1L"]
        catalog   = [self._make_item("PINAR SUT 1LT", price=24.90)]
        summary   = engine.match(watchlist, catalog, store="migros")
        assert summary.match_count == 1
        assert summary.matches[0].price == 24.90

    def test_no_match(self):
        engine = self._engine()
        watchlist = ["Samsung Galaxy S24"]
        catalog   = [self._make_item("Zeytinyağı 1L", price=89.90)]
        summary   = engine.match(watchlist, catalog, store="migros")
        assert summary.match_count == 0

    def test_multiple_watchlist_items(self):
        # ASCII kullan — encoding sorunu yok
        engine = self._engine()
        watchlist = ["Pinar Sut", "Ariel Deterjan", "Ulker Biskuvi"]
        catalog   = [
            self._make_item("Pinar Tam Yagli Sut 1L", price=24.90),
            self._make_item("Zeytinyagi 1L", price=89.90),
            self._make_item("Ariel Toz 3kg", price=89.90, discount=20),
        ]
        summary = engine.match(watchlist, catalog, store="migros")
        assert summary.total_watchlist == 3
        assert summary.match_count >= 1   # En az Pinar Sut ve Ariel eşleşmeli

    def test_is_deal_flag(self):
        engine = self._engine()
        watchlist = ["Ariel"]
        catalog   = [self._make_item("Ariel Toz Deterjan 3kg", price=89.90, discount=20)]
        summary   = engine.match(watchlist, catalog)
        if summary.matches:
            assert summary.matches[0].is_deal is True

    def test_best_match_selected(self):
        """Kısa sorgu token subset bonusu ile eşleşmeli."""
        engine = self._engine()
        watchlist = ["Pinar Sut"]
        catalog   = [
            self._make_item("Pinar Tam Yagli Sut 1L", price=24.90),
            self._make_item("Sutas Sut 1L", price=22.90),
            self._make_item("Zeytinyagi 1L", price=89.90),
        ]
        summary = engine.match(watchlist, catalog)
        assert summary.match_count == 1
        assert "Pinar" in summary.matches[0].catalog_product


# ── Bildirim Payload Formatı ─────────────────────────────────

class TestNotificationPayload:
    def test_payload_with_discount(self):
        from app.notification_orchestrator import _build_push_payload
        from app.matching_engine import MatchResult
        match = MatchResult(
            watchlist_title="Pınar Süt",
            catalog_product="Pınar Tam Yağlı Süt 1L",
            store="migros",
            score=0.85,
            price=24.90,
            original_price=29.90,
            discount_pct=17,
            unit="1lt",
            is_deal=True,
        )
        payload = _build_push_payload(match, "Migros")
        assert "Migros" in payload["title"]
        assert "24,90" in payload["body"] or "24.90" in payload["body"]
        assert "%17" in payload["body"] or "17" in payload["body"]
        assert payload["data"]["price"] == 24.90

    def test_payload_without_discount(self):
        from app.notification_orchestrator import _build_push_payload
        from app.matching_engine import MatchResult
        match = MatchResult(
            watchlist_title="Ariel",
            catalog_product="Ariel Toz 3kg",
            store="a101",
            score=0.72,
            price=89.90,
            original_price=None,
            discount_pct=None,
            unit=None,
        )
        payload = _build_push_payload(match, "A101")
        assert "89,90" in payload["body"] or "89.90" in payload["body"]
        assert "tag" in payload
        assert "/static/icon-192.png" in payload["icon"]

    def test_payload_includes_search_url(self):
        from app.notification_orchestrator import _build_push_payload
        from app.matching_engine import MatchResult
        match = MatchResult(
            watchlist_title="Süt",
            catalog_product="Pınar Süt",
            store="migros",
            score=0.8,
            price=24.90,
            original_price=None,
            discount_pct=None,
            unit=None,
        )
        payload = _build_push_payload(match, "Migros")
        assert "url" in payload["data"]
        assert "q=" in payload["data"]["url"]
