"""
Tests for Phase 1.10: Almadan.app - Atıl Kıyafet Tespit ve Otonom 2. El Değerleme Motoru (Re-Commerce).
Covers:
1. Otonom Atıl Kıyafet Tespiti (Dead-Stock Finder) & Hibrit Amortisman Algoritması:
   - Orijinal fiyatı 2000 TL olan, 10 kez giyilmiş ve 8 aylık (240 günlük) bir Zara kabanın
     atıl (idle) olarak tespit edilmesi ve ~1000-1100 TL bandında (`1003.20 TL`) değerlenmesi.
   - Yakın zamanda sık giyilen aktif kıyafetlerin atıl listesine girmemesi.
2. Minimum %15 Taban Fiyat (`floor_price`) koruması.
3. LLM destekli 2. el ilan metni (`listing_title`, `listing_description`) üretimi ve JWT koruması.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_jwt
from app.api.v1.endpoints.sync import reset_sync_store
from app.services.recommerce import calculate_resale_valuation


@pytest.fixture(autouse=True)
def clean_wardrobe():
    reset_sync_store()
    yield
    reset_sync_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_id() -> str:
    return "77771111-2222-4333-8444-888888888888"


@pytest.fixture
def user_headers(user_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_id, email="recommerce@almadan.app")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Core Scenario: 2000 TL, 10x Worn, 8-Month-Old Idle Zara Coat -> ~1000-1100 TL
# ---------------------------------------------------------------------------

def test_idle_zara_coat_2000tl_10_wears_8_months_valuation_and_suggestions(
    client: TestClient,
    user_headers: dict[str, str],
):
    """
    Orijinal fiyatı 2000 TL olan, 10 kez giyilmiş ve 8 aylık (son 6+ aydır giyilmeyen)
    Zara kaban için:
    - Sistem doğru atıl (Idle) tespiti yapmalı,
    - Yakın zamanda giyilen aktif gömleği atıl olarak İŞARETLEMEMELİ,
    - Zara kaban için ~1000-1100 TL bandında (`1003.20 TL`) 2. el satış fiyatı ve ilan metni üretmelidir.
    """
    now = datetime.now(timezone.utc)
    eight_months_ago = now - timedelta(days=240)  # 8 ay (240 gün) önce satın alındı

    # 10 adet kombin kaydı (tümü 190 - 230 gün önce giyildi -> son 180 gündür hiç giyilmedi!)
    outfit_logs = []
    for i in range(10):
        worn_date = now - timedelta(days=190 + i * 4)
        outfit_logs.append(
            {
                "id": f"log-zara-{i}",
                "date": worn_date.isoformat(),
                "garment_ids": ["zara-kaban-uuid"],
                "updated_at": worn_date.isoformat(),
                "is_deleted": False,
            }
        )

    # Aktif kullanılan bir kıyafet için yakın tarihli kombin kayıtları (son 15 gün içinde 5 kez giyildi)
    for j in range(5):
        recent_date = now - timedelta(days=j * 2 + 1)
        outfit_logs.append(
            {
                "id": f"log-active-{j}",
                "date": recent_date.isoformat(),
                "garment_ids": ["active-shirt-uuid"],
                "updated_at": recent_date.isoformat(),
                "is_deleted": False,
            }
        )

    sync_payload = {
        "garments": [
            {
                "id": "zara-kaban-uuid",
                "name": "Zara Kaşmir Karışımlı Kaban",
                "brand": "Zara",
                "kind": "dis",
                "color": "lacivert",
                "price": 2000.0,
                "purchase_date": eight_months_ago.isoformat(),
                "updated_at": eight_months_ago.isoformat(),
                "is_deleted": False,
            },
            {
                "id": "active-shirt-uuid",
                "name": "Massimo Dutti Beyaz Gömlek",
                "brand": "Massimo Dutti",
                "kind": "ust",
                "color": "beyaz",
                "price": 1800.0,
                "purchase_date": (now - timedelta(days=90)).isoformat(),
                "updated_at": now.isoformat(),
                "is_deleted": False,
            },
        ],
        "outfit_logs": outfit_logs,
    }

    sync_resp = client.post("/api/v1/sync", headers=user_headers, json=sync_payload)
    assert sync_resp.status_code == 200

    # Call GET /api/v1/recommerce/suggestions
    resp = client.get("/api/v1/recommerce/suggestions", headers=user_headers)
    assert resp.status_code == 200
    data = resp.json()

    # Sadece atıl olan Zara kaban önerilmeli (aktif gömlek elenmeli)
    assert data["idle_count"] == 1
    assert len(data["suggestions"]) == 1

    item = data["suggestions"][0]
    assert item["garment_id"] == "zara-kaban-uuid"
    assert item["brand_name"] == "Zara"
    assert item["brand_segment"] == "orta_segment"
    assert item["brand_multiplier"] == 0.60
    assert item["original_price"] == 2000.0
    assert item["wear_count"] == 10
    assert item["months_owned"] == 8
    assert item["days_since_last_worn"] >= 180

    # Fiyat ~1000 - 1100 TL bandında olmalı (2000 * 0.60 * 0.95 * 0.88 = 1003.20 TL)
    assert 1000.0 <= item["suggested_resale_price"] <= 1100.0
    assert item["suggested_resale_price"] == 1003.20

    # LLM ilan başlığı ve açıklaması kontrolü
    assert "Zara" in item["listing_title"]
    assert "Kaban" in item["listing_title"]
    assert len(item["listing_description"]) > 20


# ---------------------------------------------------------------------------
# 2. Minimum 15% Floor Price & Brand Segment Multipliers Test
# ---------------------------------------------------------------------------

def test_minimum_15_percent_floor_price_and_segments():
    """
    Verifies that:
    - Massimo Dutti (üst segment) uses 0.70 multiplier
    - Heavy wear & long time decay never drops below 15% of original price (`floor_price`).
    """
    # Üst segment kontrolü
    v_premium = calculate_resale_valuation(
        original_price=3000.0,
        kind="dis",
        garment_name="Massimo Dutti Yün Palto",
        wear_count=0,
        months_owned=0,
    )
    assert v_premium.brand_multiplier == 0.70
    assert v_premium.suggested_resale_price == 2100.0

    # %15 Minimum Taban Fiyat Koruması (1000 TL ürün, 150 giyim, 60 ay)
    v_floor = calculate_resale_valuation(
        original_price=1000.0,
        kind="ust",
        garment_name="Koton Basic Tişört",
        wear_count=150,
        months_owned=60,
    )
    assert v_floor.floor_price == 150.0
    assert v_floor.suggested_resale_price == 150.0


def test_recommerce_requires_jwt_auth(client: TestClient):
    """Unauthenticated request to /api/v1/recommerce/suggestions must return 401."""
    r = client.get("/api/v1/recommerce/suggestions")
    assert r.status_code == 401
