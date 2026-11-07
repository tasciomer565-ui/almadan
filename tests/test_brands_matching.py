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
