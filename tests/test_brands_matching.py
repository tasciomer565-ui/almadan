"""Marka sayfaları ve "aynı ürün farklı isimle" eşleştirme testleri."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.brands import (
    BRANDS,
    are_same_product,
    extract_brand,
    group_same_products,
    product_signature,
    same_product_score,
)
from app.main import ALL_STORES_MAP, app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ── Marka çıkarımı ───────────────────────────────────────────

@pytest.mark.parametrize("title,slug", [
    ("Samsung Galaxy S24 256 GB", "samsung"),
    ("Apple iPhone 15 128GB", "apple"),
    ("iPhone 15 Pro", "apple"),
    ("PINAR Süt 1 LT", "pinar"),
    ("Ülker Çikolatalı Gofret", "ulker"),
    ("Nike Air Max 90", "nike"),
])
def test_extract_brand(title, slug):
    assert extract_brand(title) == slug


def test_extract_brand_unknown_and_word_boundary():
    assert extract_brand("Kahve makinesi") is None
    assert extract_brand("Etiket yazıcı") is None  # "eti" kelime içinde marka değil
    assert extract_brand("") is None


def test_brand_categories_exist_in_store_map():
    for slug, meta in BRANDS.items():
        assert meta["category"] in ALL_STORES_MAP, slug


# ── İmza ─────────────────────────────────────────────────────

def test_signature_normalizes_units():
    assert product_signature("Süt 1 LT").specs == product_signature("Süt 1000 ml").specs
    assert product_signature("SSD 1 TB").specs == product_signature("SSD 1024GB").specs


def test_signature_model_codes_exclude_specs():
    sig = product_signature("Samsung Galaxy S24 256GB 5G")
    assert "s24" in sig.models
    assert "256gb" not in sig.models and "5g" not in sig.models


# ── Eşleştirme ───────────────────────────────────────────────

def test_same_product_different_wording():
    assert are_same_product("Samsung Galaxy S24 256 GB", "GALAXY S24 256GB Samsung Akıllı Telefon")
    assert are_same_product("Pınar Süt 1 LT", "PINAR Süt 1000 ml")


@pytest.mark.parametrize("a,b", [
    ("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 128GB"),   # farklı kapasite
    ("Samsung Galaxy S24 256GB", "Samsung Galaxy S23 256GB"),   # farklı model
    ("Apple iPhone 15 128GB", "Apple iPhone 15 Pro 128GB"),     # varyant
    ("Samsung Galaxy S24", "Apple iPhone 15"),                   # farklı marka
    ("Pınar Süt 1 LT", "Pınar Süt 500 ml"),                      # farklı hacim
])
def test_different_products_never_match(a, b):
    assert same_product_score(a, b) == 0.0
    assert not are_same_product(a, b)


def test_group_same_products_preserves_order_and_splits():
    items = [
        {"title": "Samsung Galaxy S24 256GB", "store": "a"},
        {"title": "Apple iPhone 15 128GB", "store": "a"},
        {"title": "GALAXY S24 256 GB Samsung", "store": "b"},
        {"title": "iPhone 15 128 GB Apple", "store": "b"},
        {"title": "Samsung Galaxy S24 128GB", "store": "c"},
    ]
    groups = group_same_products(items)
    assert [[i["store"] for i in g] for g in groups] == [["a", "b"], ["a", "b"], ["c"]]


# ── Sayfalar ─────────────────────────────────────────────────

def test_brand_index_lists_brands(client):
    r = client.get("/marka")
    assert r.status_code == 200
    assert "/marka/samsung" in r.text


def test_brand_page_ok(client):
    r = client.get("/marka/samsung")
    assert r.status_code == 200
    assert 'rel="canonical" href="https://www.almadan.app/marka/samsung"' in r.text
    assert "application/ld+json" in r.text


def test_brand_page_case_redirect_and_404(client):
    r = client.get("/marka/Samsung", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/marka/samsung"
    assert client.get("/marka/yok-boyle-marka").status_code == 404


# ── Marka ürün özeti ─────────────────────────────────────────

def _row(key, title, source, price):
    return {"product_key": key, "title": title, "source": source, "price": price, "url": ""}


def test_summarize_brand_products_groups_across_stores():
    from app.brands import summarize_brand_products

    rows = [  # yeniden eskiye: aynı anahtarın ilk satırı güncel fiyattır
        _row("k1", "Samsung Galaxy S24 256GB", "trendyol", 40000),
        _row("k1", "Samsung Galaxy S24 256GB", "trendyol", 45000),
        _row("k2", "GALAXY S24 256 GB Samsung", "hepsiburada", 39000),
        _row("k3", "Samsung Galaxy S24 128GB", "n11", 35000),
        _row("k4", "Apple iPhone 15 128GB", "n11", 50000),
        _row("k5", "Samsung bozuk fiyat", "n11", None),
    ]
    out = summarize_brand_products(rows, "samsung")
    assert [p["store_count"] for p in out] == [2, 1]
    top = out[0]
    assert top["min_price"] == 39000 and top["min_source"] == "hepsiburada"
    assert [o["price"] for o in top["offers"]] == [39000, 40000]


def test_summarize_brand_products_empty():
    from app.brands import summarize_brand_products

    assert summarize_brand_products([], "samsung") == []


def test_brand_page_renders_products(client, monkeypatch):
    import app.main as m

    monkeypatch.setattr(m, "_brand_products_cached", lambda slug: [
        {"title": "Samsung Galaxy S24 256GB", "min_price": 39000.0, "min_source": "hepsiburada",
         "store_count": 2, "offers": []},
    ])
    r = client.get("/marka/samsung")
    assert r.status_code == 200
    assert "Samsung Galaxy S24 256GB" in r.text and "2 mağazada" in r.text


# ── Arama sonuçlarında gruplama ──────────────────────────────

def test_search_results_annotated_with_match_groups():
    from app.api.v1.endpoints.search import AggregatedProduct, _annotate_same_product_groups

    def prod(name, platform, price):
        return AggregatedProduct(product_name=name, platform_name=platform, price=price, product_url="https://x")

    items = [
        prod("Samsung Galaxy S24 256GB", "Trendyol", 40000),
        prod("GALAXY S24 256 GB Samsung", "Hepsiburada", 39000),
        prod("Samsung Galaxy S24 128GB", "N11", 35000),
        prod("Samsung Galaxy S24 256GB", "Trendyol", 41000),  # aynı mağaza tekrarı
    ]
    _annotate_same_product_groups(items)
    assert items[0].match_group_id == items[1].match_group_id == items[3].match_group_id is not None
    assert items[1].is_group_cheapest and not items[0].is_group_cheapest
    assert items[2].match_group_id is None and not items[2].is_group_cheapest


# ── Sorguya göre alaka süzgeci ───────────────────────────────

@pytest.mark.parametrize("query,title,ok", [
    ("iphone 15", "Apple iPhone 15 128 GB (Apple Türkiye Garantili)", True),
    ("iphone 15", "Apple iPhone 14 128 GB", False),
    ("iphone 15", "Apple iPhone 17e 256GB Akıllı Telefon", False),
    ("iphone 15", "Apple iPhone 15 Pro Max 256 GB", False),
    ("samsung galaxy s24", "SAMSUNG Galaxy S24 5G 8 GB 256 GB Akıllı Telefon", True),
    ("samsung galaxy s24", "Samsung Galaxy S25 FE 256GB", False),
    ("samsung galaxy s24", "Samsung Galaxy S24 Ultra Uyumlu Type-c Kulaklık", False),
    ("airpods pro 2", "Apple AirPods Pro (2. Nesil)", True),
    ("airpods pro 2", "AirPods Pro 2. Nesil için 3 Çift Yedek Kulak Uçları", False),
    ("airpods pro 2", "Pro 2 Airpods Pro 2 Görünümlü Premium Kulaklık", False),
    ("airpods pro 2", "Apple AirPods 5", False),
    ("iphone 15 256 gb", "Apple iPhone 15 128 GB", False),
    ("iphone 15", "Nike", False),
    ("nike air max", "Nike Air Max 270 Siyah Erkek Sneaker", True),   # genel sorgu: süzgeç karışmaz
    ("pinar sut 1 lt", "Pınar Süt %1 Yağlı 1 L", True),
    ("pinar sut 1 lt", "Pınar Süt 500 ml", False),
])
def test_title_matches_query(query, title, ok):
    from app.brands import title_matches_query
    assert title_matches_query(query, title) is ok


def test_filter_relevant_products_empty_for_specific_query_without_match():
    from app.brands import filter_relevant_products

    items = [{"title": "Samsung Galaxy S25 256GB"}, {"title": "Samsung Galaxy A37 5G"}]
    assert filter_relevant_products("samsung galaxy s24", items) == []      # spesifik: yanlis model gosterme
    generic = [{"title": "Nike Air Force 1"}, {"title": "Adidas Samba"}]
    assert filter_relevant_products("ayakkabi", generic) == generic        # genel sorgu: dokunma
    kept = filter_relevant_products("iphone 15", [{"title": "Apple iPhone 15 128 GB"}, {"title": "Apple iPhone 14"}])
    assert [p["title"] for p in kept] == ["Apple iPhone 15 128 GB"]


def test_plus_sign_is_a_variant():
    from app.brands import title_matches_query
    assert not title_matches_query("samsung galaxy s24", "SAMSUNG Galaxy S24+ 12 GB 256 GB Akıllı Telefon")
    assert title_matches_query("samsung galaxy s24 plus", "SAMSUNG Galaxy S24+ 12 GB 256 GB Akıllı Telefon")


def test_amazon_fashion_card_title_joins_brand_and_name(monkeypatch):
    """Amazon moda kartında marka ve ürün adı ayrı h2'lerde; başlık 'Nike' kalmamalı."""
    import app.comparator as cmp

    html = """<div data-component-type="s-search-result" data-asin="B0TEST">
      <h2><span>Nike</span></h2><h2 aria-label="x"><span>Air Max 90 Erkek Ayakkabı</span></h2>
      <span class="a-price"><span class="a-offscreen">3.089,23 TL</span></span></div>"""

    class R:
        status_code, ok, text = 200, True, html

    monkeypatch.setattr(cmp.requests, "get", lambda *a, **k: R())
    out = cmp.search_amazon_tr("nike air max")
    assert out and out[0]["title"] == "Nike Air Max 90 Erkek Ayakkabı" and out[0]["price"] == 3089.23


# ── Arama önerisi ────────────────────────────────────────────

@pytest.mark.parametrize("query,expected", [
    ("samsung galaxy s24", "samsung galaxy"),     # model numarasi eksiltilmez, son kelime atilir
    ("airpods pro 2", "airpods pro"),
    ("samsun telefon", "samsung telefon"),        # gercek yazim hatasi duzelir
    ("samsung telefon", "samsung"),               # dogru yazilmis kelime bozulmaz ("samsungg" olmaz)
    ("iphone 20", "iphone 17"),
    ("kitap", None),
])
def test_generate_search_suggestion(query, expected):
    from app.comparator import generate_search_suggestion
    assert generate_search_suggestion(query) == expected


# ── Mağazalar arası aynı ürün korunur ────────────────────────

def test_postprocess_keeps_same_product_from_different_stores():
    from app.comparator import postprocess_search_products

    def p(source, price, title):
        return {"title": title, "price": price, "source": source, "url": f"https://{source}/{price}",
                "image_url": "", "labels": [], "extra_info": {}}

    out = postprocess_search_products("iphone 15", [
        p("amazon", 56199, "Apple iPhone 15 (128 GB) - Mavi"),
        p("amazon", 56558, "Apple iPhone 15 (128 GB) - Siyah"),      # ayni magaza renk varyanti -> birlesir
        p("n11", 56499, "Apple iPhone 15 128 GB (Apple Türkiye Garantili)"),
        p("mediamarkt", 57999, "APPLE iPhone 15 128 GB Akıllı Telefon Mavi MTP43TU/A"),
    ])
    sources = sorted(x["source"] for x in out)
    assert sources == ["amazon", "mediamarkt", "n11"]          # her magaza gorunur, eskiden sadece en ucuzu kaliyordu
    assert [x["price"] for x in out if x["source"] == "amazon"] == [56199]
