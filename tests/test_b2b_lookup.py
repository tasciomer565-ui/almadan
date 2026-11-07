from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.security import DEFAULT_B2B_API_KEY

client = TestClient(app)

VALID_HEADERS = {"X-API-Key": DEFAULT_B2B_API_KEY}


def test_b2b_lookup_missing_api_key_returns_401():
    """X-API-Key başlığı gönderilmediğinde 401 Unauthorized dönmelidir."""
    response = client.get("/api/v1/products/lookup", params={"ref": "2553/042/800"})
    assert response.status_code == 401
    data = response.json()
    assert "X-API-Key" in data["detail"]


def test_b2b_lookup_invalid_api_key_returns_401():
    """Geçersiz veya yetkisiz bir X-API-Key gönderildiğinde 401 Unauthorized dönmelidir."""
    response = client.get(
        "/api/v1/products/lookup",
        params={"ref": "2553/042/800"},
        headers={"X-API-Key": "alm_invalid_unauthorized_key_999"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "Geçersiz" in data["detail"]


def test_b2b_lookup_valid_zara_ref_from_catalog():
    """Geçerli B2B API Key ve katalogda mevcut Zara REF kodu ile standart AlmadanProduct dönmelidir."""
    response = client.get(
        "/api/v1/products/lookup",
        params={"ref": "2553/042/800"},
        headers=VALID_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()

    # Zorunlu AlmadanProduct alanlarının kontrolü
    required_fields = {
        "product_name",
        "brand",
        "category",
        "image_url",
        "fabric_composition",
        "care_instructions",
    }
    assert required_fields.issubset(data.keys())
    assert data["ref_code"] == "2553/042/800"
    assert data["brand"] == "Zara"
    assert data["category"] == "Üst"
    assert "%100 Keten" in data["fabric_composition"]
    assert "30°C" in data["care_instructions"]
    assert data["image_url"].startswith("https://")
    assert data["cached"] is True
    assert data["source"] == "almadan_catalog"


def test_b2b_lookup_by_barcode():
    """Barkod (EAN-13) parametresiyle sorgulama yapıldığında doğru ürünü dönmelidir."""
    response = client.get(
        "/api/v1/products/lookup",
        params={"barcode": "8439876543210"},
        headers=VALID_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["brand"] == "Massimo Dutti"
    assert data["category"] == "Dış Giyim"
    assert "Kaşmir" in data["fabric_composition"]


def test_b2b_lookup_unknown_zara_ref_triggers_async_scraper_and_caches():
    """
    Katalogda bulunmayan bir Zara REF kodu (Örn: 3912/410/800) sorgulandığında:
    1) 404 dönmemeli, asenkron scraper/aggregator ile resmi stüdyo verisini oluşturup 200 dönmeli.
    2) Ürünü Almadan kataloğuna kaydetmeli ve ikinci sorguda önbellekten (cached=True) servis etmeli.
    """
    new_ref = "3912/410/800"

    # 1. İlk çağrı: Katalogda yok -> Live Scraper devreye girer
    resp1 = client.get(
        "/api/v1/products/lookup",
        params={"ref": new_ref},
        headers=VALID_HEADERS,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["ref_code"] == new_ref
    assert data1["brand"] == "Zara"
    assert data1["product_name"]
    assert data1["image_url"].startswith("https://")
    assert data1["fabric_composition"]
    assert data1["care_instructions"]
    assert data1["source"] == "live_scraper"
    assert data1["cached"] is False

    # 2. İkinci çağrı: Artık katalogda kayıtlı -> Anında almadan_catalog'dan döner
    resp2 = client.get(
        "/api/v1/products/lookup",
        params={"ref": new_ref},
        headers=VALID_HEADERS,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["ref_code"] == new_ref
    assert data2["source"] == "almadan_catalog"
    assert data2["cached"] is True


def test_b2b_lookup_missing_params_returns_400():
    """Hem ref hem de barcode eksikse 400 Bad Request dönmelidir."""
    response = client.get("/api/v1/products/lookup", headers=VALID_HEADERS)
    assert response.status_code == 400
