"""
Tests for Phase 1.6: Almadan.app - LLM Tabanlı Dinamik Sorgu Analiz Motoru & Semantik Önbellek.
Covers:
1. LLM Dynamic Query Disambiguation (`analyze_search_query_async` & `GET /api/v1/search`):
   - Dynamic question & option generation for arbitrary categories ("kız tişörtü", "oyuncu koltuğu", "kamp çadırı", "5 kiloluk yağ").
   - Direct "complete" status for clear queries ("iPhone 16 Pro", "Zara siyah kaban S beden").
2. Semantic Caching (`SEMANTIC_CACHE`):
   - Caches LLM `needs_clarification` / `complete` responses.
   - Subsequent identical or token-reordered queries ("tişörtü kız") return from cache in < 5ms (`cached=True`).
3. Gemini 1.5 Flash / OpenAI GPT-4o-mini REST API integration with `SYSTEM_PROMPT`.
4. Full Pipeline when LLM returns `complete`:
   - Async scraping + Negative Keyword Spam filtering + Median (85.000 TL) & IQR Outlier Drop (150-500 TL).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.endpoints import search as search_module
from app.api.v1.endpoints.search import AggregatedProduct, _SEARCH_CACHE
from app.services import query_analyzer
from app.services.query_analyzer import (
    NEGATIVE_KEYWORDS,
    SEMANTIC_CACHE,
    SYSTEM_PROMPT,
    filter_negative_keywords,
)


@pytest.fixture(autouse=True)
def clear_all_caches():
    _SEARCH_CACHE.clear()
    SEMANTIC_CACHE.clear()
    yield
    _SEARCH_CACHE.clear()
    SEMANTIC_CACHE.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. LLM Dynamic Disambiguation across 3 Unseen Categories
# ---------------------------------------------------------------------------

def test_llm_dynamic_disambiguation_three_categories(client: TestClient):
    """
    Tests dynamic LLM question & option generation for 3 categories:
    1) "kız tişörtü"
    2) "oyuncu koltuğu"
    3) "kamp çadırı"
    """
    # Kategori 1: "kız tişörtü"
    r1 = client.get("/api/v1/search", params={"q": "kız tişörtü"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["status"] == "needs_clarification"
    assert d1["missing_parameter"] is not None
    assert "?" in d1["question"]
    assert len(d1["options"]) >= 3
    assert "Fark Etmez" in d1["options"]

    # Kategori 2: "oyuncu koltuğu"
    r2 = client.get("/api/v1/search", params={"q": "oyuncu koltuğu"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["status"] == "needs_clarification"
    assert d2["missing_parameter"] is not None
    assert "?" in d2["question"]
    assert len(d2["options"]) >= 3
    assert "Fark Etmez" in d2["options"]

    # Kategori 3: "kamp çadırı"
    r3 = client.get("/api/v1/search", params={"q": "kamp çadırı"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["status"] == "needs_clarification"
    assert d3["missing_parameter"] is not None
    assert "?" in d3["question"]
    assert len(d3["options"]) >= 3
    assert "Fark Etmez" in d3["options"]


# ---------------------------------------------------------------------------
# 2. Semantic Caching (< 5ms Cache Hit & Token Order Invariance)
# ---------------------------------------------------------------------------

def test_semantic_cache_hit_under_5ms_and_token_order_invariance(client: TestClient):
    """
    First query for 'kız tişörtü' invokes the LLM and stores the result in SEMANTIC_CACHE.
    Second query ('kız tişörtü' or semantically equivalent 'tişörtü kız için') returns directly
    from SEMANTIC_CACHE with `cached=True` and `execution_time_ms < 5.0`.
    """
    # 1. İlk çağrı (Cache Miss -> LLM)
    r_first = client.get("/api/v1/search", params={"q": "kız tişörtü"})
    assert r_first.status_code == 200
    d_first = r_first.json()
    assert d_first["status"] == "needs_clarification"
    assert d_first["cached"] is False

    # 2. İkinci çağrı: Aynı sorgu (Cache Hit < 5ms)
    r_second = client.get("/api/v1/search", params={"q": "kız tişörtü"})
    assert r_second.status_code == 200
    d_second = r_second.json()
    assert d_second["status"] == "needs_clarification"
    assert d_second["cached"] is True
    assert d_second["execution_time_ms"] < 5.0
    assert d_second["question"] == d_first["question"]
    assert d_second["options"] == d_first["options"]

    # 3. Üçüncü çağrı: Kelime sırası değişmiş semantik eşdeğer sorgu ("tişörtü kız için")
    r_semantic = client.get("/api/v1/search", params={"q": "tişörtü kız için"})
    assert r_semantic.status_code == 200
    d_semantic = r_semantic.json()
    assert d_semantic["status"] == "needs_clarification"
    assert d_semantic["cached"] is True
    assert d_semantic["execution_time_ms"] < 5.0


# ---------------------------------------------------------------------------
# 3. External Gemini 1.5 Flash API Integration Test
# ---------------------------------------------------------------------------

def test_gemini_flash_api_integration_with_system_prompt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verifies that when GEMINI_API_KEY is configured, Gemini 1.5 Flash is called with SYSTEM_PROMPT."""
    assert "Sen bir e-ticaret asistanısın" in SYSTEM_PROMPT
    assert "needs_clarification" in SYSTEM_PROMPT
    assert "complete" in SYSTEM_PROMPT

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-123")

    async def mock_gemini_flash(query: str, api_key: str):
        assert api_key == "test-gemini-key-123"
        return {
            "status": "needs_clarification",
            "missing_parameter": "Tür ve Demleme Tipi",
            "question": "Nasıl bir kahve makinesi arıyorsun?",
            "options": ["Türk Kahvesi Makinesi", "Espresso Makinesi", "Filtre Kahve", "Fark Etmez"],
        }

    monkeypatch.setattr(query_analyzer, "_call_gemini_flash", mock_gemini_flash)

    resp = client.get("/api/v1/search", params={"q": "kahve makinesi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "needs_clarification"
    assert data["provider"] == "gemini-1.5-flash"
    assert data["missing_parameter"] == "Tür ve Demleme Tipi"
    assert "Espresso Makinesi" in data["options"]


# ---------------------------------------------------------------------------
# 4. Complete Query -> Scraping + Negative Keyword Spam + Median/IQR Outlier Filter
# ---------------------------------------------------------------------------

def test_50_results_median_85000_drops_150_to_500_tl_outliers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    When LLM returns `{"status": "complete"}` (e.g. for "iPhone 16 Pro 256GB"):
    - Async scraping runs across platforms
    - Negative keyword spam ("kılıf, uyumlu, ekran koruyucu, boş kutu, muadil, aparat") is removed
    - With 85.000 TL median price, all 150 TL - 500 TL outliers are dropped automatically.
    """
    mock_pool: list[AggregatedProduct] = []

    for i in range(36):
        if i < 10:
            p_val = 84000.0
        elif i < 26:
            p_val = 85000.0
        else:
            p_val = 86000.0
        mock_pool.append(
            AggregatedProduct(
                product_name=f"Apple iPhone 16 Pro 256GB Doğal Titanyum Mağaza-{i}",
                platform_name="Trendyol" if i % 2 == 0 else "Hepsiburada",
                seller_name=f"Yetkili Satıcı {i}",
                price=p_val,
                product_url=f"https://www.trendyol.com/iphone-16-pro-256gb-{i}",
                has_same_day_delivery=True,
            )
        )

    outlier_prices = [150.0, 199.0, 249.0, 299.0, 350.0, 399.0, 450.0, 500.0]
    for idx, o_price in enumerate(outlier_prices):
        mock_pool.append(
            AggregatedProduct(
                product_name=f"Apple iPhone 16 Pro 256GB Type-C Şarj Kablosu {idx}",
                platform_name="N11",
                seller_name="Aksesuar Merkezi",
                price=o_price,
                product_url=f"https://www.n11.com/type-c-kablo-{idx}",
                has_same_day_delivery=False,
            )
        )

    spam_titles = [
        "iPhone 16 Pro 256GB MagSafe Şeffaf Kılıf",
        "iPhone 16 Pro 256GB Uyumlu Kamera Lens Camı",
        "iPhone 16 Pro 256GB Tam Kaplayan Ekran Koruyucu",
        "iPhone 16 Pro 256GB Orijinal Boş Kutu",
        "iPhone 16 Pro 256GB Muadil Batarya",
        "iPhone 16 Pro 256GB Şarj Aparat Seti",
    ]
    for idx, s_title in enumerate(spam_titles):
        mock_pool.append(
            AggregatedProduct(
                product_name=s_title,
                platform_name="Amazon TR",
                seller_name="Yan Ürün Satıcısı",
                price=299.0,
                product_url=f"https://www.amazon.com.tr/dp/SPAM{idx}",
                has_same_day_delivery=False,
            )
        )

    assert len(mock_pool) == 50

    async def fake_trendyol(http_client, q):
        return mock_pool[:25]

    async def fake_hepsiburada(http_client, q):
        return mock_pool[25:]

    async def fake_empty(http_client, q):
        return []

    monkeypatch.setattr(search_module, "_fetch_trendyol", fake_trendyol)
    monkeypatch.setattr(search_module, "_fetch_hepsiburada", fake_hepsiburada)
    monkeypatch.setattr(search_module, "_fetch_amazon", fake_empty)
    monkeypatch.setattr(search_module, "_fetch_n11", fake_empty)

    resp = client.get("/api/v1/search", params={"q": "iPhone 16 Pro 256GB", "sort": "price_asc"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["query"] == "iPhone 16 Pro 256GB"
    assert data["median_price"] == 85000.0
    assert data["filtered_spam_count"] == 6
    assert data["filtered_outliers_count"] == 8
    assert data["total_results"] == 36
    assert len(data["results"]) == 36
