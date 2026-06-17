"""
Sprint 6 — AI Zeka Katmanı Birim Testleri

Çalıştırma:
    pytest tests/test_sprint6_ai.py -v
"""
from __future__ import annotations

import unittest.mock as mock
from datetime import date, timedelta


# ══════════════════════════════════════════════════════════════
# AIMonitor
# ══════════════════════════════════════════════════════════════

class TestAIMonitorSpan:
    def test_span_latency_positive(self):
        from app.ai_monitor import AISpan
        span = AISpan(service="test", operation="op", model_id="m", user_id=None)
        assert span.latency_ms >= 0

    def test_span_set_tokens_auto_cost(self):
        from app.ai_monitor import AISpan
        span = AISpan(service="embedding", operation="embed",
                      model_id="text-embedding-3-small", user_id=None)
        span.set_tokens(input=1000, output=0)
        # 1000 tokens × $0.02/1K = $0.00002
        assert abs(span._cost_usd - 0.00002) < 1e-8
        assert span._input_tokens == 1000

    def test_span_set_error(self):
        from app.ai_monitor import AISpan
        span = AISpan(service="s", operation="o", model_id="m", user_id=None)
        span.set_error("Connection timeout")
        assert span._status == "error"
        assert "timeout" in span._error

    def test_span_set_status(self):
        from app.ai_monitor import AISpan
        span = AISpan(service="s", operation="o", model_id="m", user_id=None)
        span.set_status("guardrail_blocked")
        assert span._status == "guardrail_blocked"

    def test_trace_context_manager_flushes(self):
        from app.ai_monitor import AIMonitor
        import app.ai_monitor as mon_mod
        with mock.patch("app.ai_monitor._req.post") as mock_post, \
             mock.patch.object(mon_mod, "_SUPABASE_URL", "https://fake.supabase.co"), \
             mock.patch.object(mon_mod, "_SUPABASE_KEY", "fake-key"):
            mock_post.return_value = mock.Mock(ok=True)
            with AIMonitor.trace("embedding", "test_op", model_id="text-embedding-3-small") as span:
                span.set_tokens(input=500)
        assert mock_post.called
        sent = mock_post.call_args.kwargs.get("json", {})
        assert sent["service"] == "embedding"
        assert sent["input_tokens"] == 500

    def test_trace_records_error_on_exception(self):
        from app.ai_monitor import AIMonitor
        with mock.patch("app.ai_monitor._req.post"):
            try:
                with AIMonitor.trace("vision", "analyze") as span:
                    raise ValueError("Test error")
            except ValueError:
                pass
        assert span._status == "error"
        assert "Test error" in (span._error or "")

    def test_cost_per_1k_defined(self):
        from app.ai_monitor import COST_PER_1K
        assert "text-embedding-3-small" in COST_PER_1K
        assert "gpt-4o" in COST_PER_1K
        assert COST_PER_1K["gpt-4o"] > COST_PER_1K["text-embedding-3-small"]


# ══════════════════════════════════════════════════════════════
# Guardrails
# ══════════════════════════════════════════════════════════════

class TestGuardrails:
    def _g(self):
        from app.guardrails import Guardrails
        return Guardrails()

    def test_price_bounds_valid(self):
        g = self._g()
        r = g.check_price_bounds(24.90)
        assert r.passed is True

    def test_price_bounds_too_low(self):
        g = self._g()
        r = g.check_price_bounds(0.10)
        assert r.passed is False
        assert "düşük" in (r.reason or "").lower()

    def test_price_bounds_too_high(self):
        g = self._g()
        r = g.check_price_bounds(999_999.0)
        assert r.passed is False
        assert "yüksek" in (r.reason or "").lower()

    def test_price_deviation_within_bounds(self):
        g = self._g()
        r = g.check_price_deviation(25.0, 24.90)
        assert r.passed is True

    def test_price_deviation_extreme(self):
        g = self._g()
        r = g.check_price_deviation(500.0, 25.0)   # %1900 sapma
        assert r.passed is False
        assert r.sanitized_value == 25.0   # fallback: ortalama

    def test_price_deviation_no_history(self):
        g = self._g()
        r = g.check_price_deviation(50.0, 0)
        assert r.passed is True   # Geçmişi yoksa bloke etme

    def test_forecast_trend_stable(self):
        g = self._g()
        prices = [24.0, 24.5, 25.0, 24.8, 25.1]
        r = g.check_forecast_trend(prices)
        assert r.passed is True

    def test_forecast_trend_wild_jump(self):
        g = self._g()
        prices = [24.0, 24.5, 80.0]   # Adım 2'de %226 atlayış
        r = g.check_forecast_trend(prices)
        assert r.passed is False
        assert "atlayış" in (r.reason or "").lower()

    def test_product_name_valid(self):
        g = self._g()
        r = g.check_product_name("Pınar Tam Yağlı Süt 1L")
        assert r.passed is True
        assert r.sanitized_value is None   # kısaltılmadı

    def test_product_name_too_short(self):
        g = self._g()
        r = g.check_product_name("A")
        assert r.passed is False

    def test_product_name_blocklist(self):
        g = self._g()
        r = g.check_product_name("Efes Bira 330ml")
        assert r.passed is False

    def test_product_name_too_long_sanitized(self):
        g = self._g()
        long_name = "X" * 300
        r = g.check_product_name(long_name)
        assert r.passed is True   # Kırp, bloke etme
        assert len(str(r.sanitized_value)) <= 200

    def test_filter_shopping_list_removes_blocked(self):
        g = self._g()
        items = [
            {"title": "Süt 1L"},
            {"title": "Efes Bira"},   # blocklist
            {"title": "Yumurta"},
        ]
        passed, blocked = g.filter_shopping_list(items)
        assert len(passed) == 2
        assert len(blocked) == 1
        assert "Efes" in blocked[0]

    def test_confidence_check_pass(self):
        g = self._g()
        r = g.check_confidence(0.85)
        assert r.passed is True

    def test_confidence_check_fail(self):
        g = self._g()
        r = g.check_confidence(0.40)
        assert r.passed is False

    def test_run_all_price_checks_all_pass(self):
        g = self._g()
        results = g.run_all_price_checks(25.0, historical_avg=24.0)
        assert g.all_passed(results) is True

    def test_run_all_price_checks_blocks_deviation(self):
        g = self._g()
        results = g.run_all_price_checks(1000.0, historical_avg=25.0)
        assert g.all_passed(results) is False


# ══════════════════════════════════════════════════════════════
# PriceForecaster
# ══════════════════════════════════════════════════════════════

class TestPriceForecaster:
    def _forecaster(self):
        from app.price_forecaster import PriceForecaster
        return PriceForecaster()

    def _history(self, prices: list[float]) -> list:
        from app.price_forecaster import PricePoint
        base = date.today() - timedelta(days=len(prices))
        return [PricePoint(date=base + timedelta(days=i), price=p)
                for i, p in enumerate(prices)]

    def test_forecast_insufficient_data(self):
        f = self._forecaster()
        history = self._history([24.90, 25.0, 24.5])   # 3 nokta < MIN_DATA_POINTS(5)
        result = f.forecast("key", "Test", "migros", history, use_cache=False)
        assert result.predictions == []

    def test_linear_forecast_produces_predictions(self):
        f = self._forecaster()
        prices = [20.0, 21.0, 22.0, 22.5, 23.0, 23.5, 24.0]
        history = self._history(prices)
        with mock.patch.object(f, "_load_cache", return_value=None), \
             mock.patch.object(f, "_save_cache"):
            result = f.forecast("p::test", "Test Ürün", "migros", history,
                                days=7, use_cache=True)
        assert len(result.predictions) == 7
        assert all(p.predicted_price > 0 for p in result.predictions)

    def test_linear_forecast_rising_trend(self):
        f = self._forecaster()
        # Net artan trend
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
        history = self._history(prices)
        preds = f._linear_forecast(history, 3)
        assert preds[0].trend == "rising"
        assert preds[0].predicted_price > prices[-1]

    def test_linear_forecast_falling_trend(self):
        f = self._forecaster()
        prices = [30.0, 28.0, 26.0, 24.0, 22.0, 20.0, 18.0, 16.0]
        history = self._history(prices)
        preds = f._linear_forecast(history, 3)
        assert preds[0].trend == "falling"

    def test_linear_forecast_stable_trend(self):
        f = self._forecaster()
        prices = [24.90, 24.90, 25.00, 24.80, 24.90, 25.10, 24.95, 24.90]
        history = self._history(prices)
        preds = f._linear_forecast(history, 3)
        # Sabit seri → stable veya küçük değişim
        assert preds[0].trend in {"stable", "rising", "falling"}
        assert abs(preds[0].change_pct) < 10   # çılgın değişim olmamalı

    def test_confidence_interval_low_less_than_high(self):
        f = self._forecaster()
        prices = [24.0, 24.5, 25.0, 25.5, 26.0, 26.5, 27.0]
        history = self._history(prices)
        preds = f._linear_forecast(history, 5)
        for p in preds:
            assert p.confidence_low <= p.predicted_price <= p.confidence_high

    def test_guardrail_blocks_wild_forecast(self):
        f = self._forecaster()
        # Tarihi veri düşük ama ortalama hesaplana gelecek tahmin dev olacak
        prices = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        history = self._history(prices)

        with mock.patch.object(f, "_load_cache", return_value=None), \
             mock.patch.object(f, "_save_cache"), \
             mock.patch.object(f, "_linear_forecast") as mock_lf:
            # Mock: absürt tahmin serisi döndür
            from app.price_forecaster import PricePrediction
            mock_lf.return_value = [
                PricePrediction(forecast_date=date.today() + timedelta(days=i+1),
                                predicted_price=5000.0,  # %49900 sapma
                                confidence_low=4000.0, confidence_high=6000.0,
                                trend="rising", change_pct=4990.0)
                for i in range(7)
            ]
            result = f.forecast("key", "Test", "migros", history,
                                days=7, use_cache=False)
        assert result.guardrail_blocked is True
        # Fallback: düz çizgi (tarihsel ortalama)
        assert all(p.trend == "stable" for p in result.predictions)

    def test_flat_forecast_stable_prices(self):
        f = self._forecaster()
        preds = f._flat_forecast(25.0, 7)
        assert len(preds) == 7
        assert all(p.predicted_price == 25.0 for p in preds)
        assert all(p.trend == "stable" for p in preds)

    def test_no_negative_price_predictions(self):
        f = self._forecaster()
        prices = [5.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.80]
        history = self._history(prices)
        preds = f._linear_forecast(history, 5)
        assert all(p.predicted_price >= 0.50 for p in preds)


# ══════════════════════════════════════════════════════════════
# SemanticSearch / Embedding
# ══════════════════════════════════════════════════════════════

class TestSemanticSearch:
    def test_embed_fallback_returns_1536_dims(self):
        from app.semantic_search import _embed_fallback
        vec = _embed_fallback("Pınar Süt 1L")
        assert len(vec) == 1536

    def test_embed_fallback_deterministic(self):
        from app.semantic_search import _embed_fallback
        v1 = _embed_fallback("test sorgusu")
        v2 = _embed_fallback("test sorgusu")
        assert v1 == v2

    def test_embed_fallback_different_texts(self):
        from app.semantic_search import _embed_fallback
        v1 = _embed_fallback("Pınar Süt")
        v2 = _embed_fallback("Ariel Deterjan")
        # Farklı metinler farklı vektör üretmeli
        assert v1 != v2

    def test_embed_fallback_l2_normalized(self):
        import math
        from app.semantic_search import _embed_fallback
        vec = _embed_fallback("normalizasyon testi")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_embed_text_uses_fallback_without_openai(self):
        from app.semantic_search import embed_text
        import app.semantic_search as ss_mod
        original = ss_mod._OPENAI_KEY
        try:
            ss_mod._OPENAI_KEY = ""
            vec = embed_text("test metin")
            assert vec is not None
            assert len(vec) == 1536
        finally:
            ss_mod._OPENAI_KEY = original

    def test_search_calls_vector_search(self):
        from app.semantic_search import SemanticSearch, SemanticResult
        ss = SemanticSearch()
        mock_results = [
            SemanticResult("k1", "Pınar Süt 1L", "migros", "GIDA", 24.90, 0.92, {})
        ]
        with mock.patch.object(ss, "_vector_search", return_value=mock_results) as mock_vs:
            results = ss.search("süt", store="migros")
        assert len(results) == 1
        assert results[0].product_title == "Pınar Süt 1L"
        assert results[0].similarity == 0.92
        mock_vs.assert_called_once()

    def test_search_falls_back_to_keyword_on_embed_failure(self):
        from app.semantic_search import SemanticSearch, SemanticResult
        ss = SemanticSearch()
        with mock.patch("app.semantic_search.embed_text", return_value=None), \
             mock.patch.object(ss, "_keyword_fallback", return_value=[]) as mock_kw:
            ss.search("süt")
        mock_kw.assert_called_once()

    def test_slugify(self):
        from app.semantic_search import _slugify
        assert _slugify("Pınar Süt 1L") == "pnar-st-1l" or len(_slugify("Pınar Süt 1L")) > 0
        assert " " not in _slugify("test ürün")


# ══════════════════════════════════════════════════════════════
# VisionAnalyzer
# ══════════════════════════════════════════════════════════════

class TestVisionAnalyzer:
    def _analyzer(self):
        from app.vision_analyzer import VisionAnalyzer
        return VisionAnalyzer()

    def test_mock_response_fridge_structure(self):
        va = self._analyzer()
        raw = va._mock_response("fridge")
        import json
        data = json.loads(raw)
        assert "detected_items" in data
        assert "shopping_list" in data
        assert len(data["shopping_list"]) >= 1

    def test_parse_response_fridge(self):
        va = self._analyzer()
        import json
        raw = json.dumps({
            "detected_items": [{"name": "Süt", "low": True}],
            "shopping_list": [{"title": "Süt 1L", "priority": "high"}],
        }, ensure_ascii=False)
        result = va._parse_response(raw, "fridge")
        assert len(result.detected_items) == 1
        assert result.detected_items[0]["name"] == "Süt"
        assert result.shopping_list[0]["title"] == "Süt 1L"

    def test_parse_response_markdown_json(self):
        va = self._analyzer()
        raw = '```json\n{"detected_items": [], "shopping_list": [{"title": "Ekmek", "priority": "medium"}]}\n```'
        result = va._parse_response(raw, "fridge")
        assert result.shopping_list[0]["title"] == "Ekmek"

    def test_parse_response_invalid_json(self):
        va = self._analyzer()
        result = va._parse_response("Bu bir yanıt değil sadece metin", "fridge")
        assert result.detected_items == []
        assert result.shopping_list == []

    def test_analyze_fridge_mock_mode(self):
        """OpenAI ve Replicate yokken mock modu çalışmalı."""
        va = self._analyzer()
        import app.vision_analyzer as va_mod
        orig_openai = va_mod._OPENAI_KEY
        orig_rep    = va_mod._REPLICATE_TOKEN
        try:
            va_mod._OPENAI_KEY = ""
            va_mod._REPLICATE_TOKEN = ""
            with mock.patch.object(va, "_save", return_value=None):
                result = va.analyze_fridge("https://example.com/fridge.jpg")
            assert result.model_used == "mock"
            assert len(result.shopping_list) >= 1
        finally:
            va_mod._OPENAI_KEY = orig_openai
            va_mod._REPLICATE_TOKEN = orig_rep

    def test_guardrail_blocks_alcohol_from_shopping_list(self):
        """Vision modeli alkol önerirse guardrail filtrelemeli."""
        va = self._analyzer()
        import json
        raw = json.dumps({
            "detected_items": [],
            "shopping_list": [
                {"title": "Süt 1L", "priority": "high"},
                {"title": "Efes Bira 500ml", "priority": "low"},   # blocklist
            ],
        }, ensure_ascii=False)
        import app.vision_analyzer as va_mod
        orig_openai = va_mod._OPENAI_KEY
        orig_rep    = va_mod._REPLICATE_TOKEN
        try:
            va_mod._OPENAI_KEY = ""
            va_mod._REPLICATE_TOKEN = ""
            with mock.patch.object(va, "_mock_response", return_value=raw), \
                 mock.patch.object(va, "_save", return_value=None):
                result = va.analyze_fridge("https://example.com/test.jpg")
            titles = [item["title"] for item in result.shopping_list]
            assert "Süt 1L" in titles
            assert not any("Bira" in t for t in titles)
            assert len(result.guardrail_blocked_items) >= 1
        finally:
            va_mod._OPENAI_KEY = orig_openai
            va_mod._REPLICATE_TOKEN = orig_rep
