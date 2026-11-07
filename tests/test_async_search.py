import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_async_search_structure_and_sorting():
    # 1. Full query with price ascending sort
    resp = client.get("/api/v1/search?q=iPhone+16+Pro+256GB&sort=price_asc")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["query"] == "iPhone 16 Pro 256GB"
    assert data["total_results"] > 0
    assert len(data["results"]) == data["total_results"]

    # Check required fields in AggregatedProduct
    first = data["results"][0]
    required_keys = [
        "product_name",
        "platform_name",
        "seller_name",
        "price",
        "original_price",
        "product_url",
        "image_url",
        "rating_score",
        "review_count",
        "has_same_day_delivery",
    ]
    for k in required_keys:
        assert k in first

    prices = [p["price"] for p in data["results"]]
    assert prices == sorted(prices)


def test_async_search_cache_hit():
    # Trigger cached call
    resp1 = client.get("/api/v1/search?q=Stanley+termos&sort=fast_shipping")
    assert resp1.status_code == 200

    resp2 = client.get("/api/v1/search?q=Stanley+termos&sort=fast_shipping")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "success"
    assert data2["cached"] is True
