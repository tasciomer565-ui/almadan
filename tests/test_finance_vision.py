"""
Tests for Phase 1.7: Almadan.app - Vision AI Destekli Fiş Okuma ve Otonom Bütçe Takip Sistemi.
Covers:
1. Vision AI Receipt Scanner (`POST /api/v1/finance/scan-receipt`):
   - Multipart/form-data receipt image upload with mocked Vision API (`gemini-1.5-pro` / `gpt-4o`) for a Migros receipt.
   - Verifies `RECEIPT_VISION_SYSTEM_PROMPT` and parsed JSON (`merchant_name`, `date`, `total_amount`, `tax_amount`, `category`, `items`).
2. Autonomous Budget Deduction (`POST /api/v1/finance/transactions`):
   - Confirming a scanned receipt automatically increments `budgets.current_spent` for that `month_year` and `category`.
3. Monthly Budget Analytics (`GET /api/v1/finance/budget-summary`):
   - Computes total spent, remaining budget, and per-category usage percentages (%85 Market/Gıda, %40 Ulaşım).
4. JWT Security & Multi-Tenant RLS Isolation:
   - Unauthenticated requests rejected with 401; User B cannot view User A's budget summary.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_jwt
from app.api.v1.endpoints.finance import reset_finance_store
from app.services import receipt_vision
from app.services.receipt_vision import RECEIPT_VISION_SYSTEM_PROMPT


@pytest.fixture(autouse=True)
def clean_finance_db():
    reset_finance_store()
    yield
    reset_finance_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_a_id() -> str:
    return "aaaa1111-2222-4333-8444-555555555555"


@pytest.fixture
def user_b_id() -> str:
    return "bbbb9999-8888-4777-8666-555555555555"


@pytest.fixture
def user_a_headers(user_a_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_a_id, email="usera@almadan.app")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_headers(user_b_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_b_id, email="userb@almadan.app")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Vision AI Receipt Scanner Tests (Mocked Migros Receipt)
# ---------------------------------------------------------------------------

def test_scan_receipt_with_mocked_vision_ai_migros(
    client: TestClient,
    user_a_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Uploads a fake Migros receipt via multipart/form-data to `POST /api/v1/finance/scan-receipt`
    with Vision AI mocked, and verifies the parsed JSON output.
    """
    assert "Bu bir fiş/fatura fotoğrafı" in RECEIPT_VISION_SYSTEM_PROMPT
    assert '"merchant_name": "Migros"' in RECEIPT_VISION_SYSTEM_PROMPT

    monkeypatch.setenv("GEMINI_API_KEY", "test-vision-gemini-key")

    async def mock_gemini_vision(image_bytes: bytes, mime_type: str, api_key: str):
        assert api_key == "test-vision-gemini-key"
        assert len(image_bytes) > 0
        assert mime_type == "image/jpeg"
        return {
            "merchant_name": "Migros",
            "date": "2026-11-03",
            "total_amount": 450.50,
            "tax_amount": 45.05,
            "category": "Market/Gıda",
            "items": [
                {"name": "Süt", "price": 35.0},
                {"name": "Ezine Beyaz Peynir", "price": 215.50},
                {"name": "Zeytinyağı 500ml", "price": 200.0},
            ],
        }

    monkeypatch.setattr(receipt_vision, "_call_gemini_vision", mock_gemini_vision)

    fake_jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF_FAKE_MIGROS_RECEIPT_IMAGE"
    resp = client.post(
        "/api/v1/finance/scan-receipt",
        headers=user_a_headers,
        files={"file": ("migros_fis_2026.jpg", fake_jpeg_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["merchant_name"] == "Migros"
    assert data["date"] == "2026-11-03"
    assert data["total_amount"] == 450.50
    assert data["tax_amount"] == 45.05
    assert data["category"] == "Market/Gıda"
    assert data["provider"] == "gemini-1.5-pro"
    assert len(data["items"]) == 3
    assert data["items"][0] == {"name": "Süt", "price": 35.0}


# ---------------------------------------------------------------------------
# 2. Autonomous Budget Deduction & Budget Summary Analytics Tests
# ---------------------------------------------------------------------------

def test_autonomous_budget_deduction_and_monthly_summary(
    client: TestClient,
    user_a_id: str,
    user_a_headers: dict[str, str],
):
    """
    Verifies end-to-end budget flow:
    1. User defines monthly limits for 2026-11:
       - Market/Gıda: 1.000 TL
       - Ulaşım: 1.000 TL
    2. User confirms scanned Migros receipt (450.50 TL) + second market expense (399.50 TL) -> 850.00 TL (%85 Market/Gıda).
    3. User adds Ulaşım expense (400.00 TL) -> 400.00 TL (%40 Ulaşım).
    4. `GET /api/v1/finance/budget-summary?month_year=2026-11` returns exact totals,
       remaining budget (750.00 TL), and category usage rates (%85 Market/Gıda, %40 Ulaşım).
    """
    # 1. Define monthly category budgets for 2026-11
    b1 = client.post(
        "/api/v1/finance/budgets",
        headers=user_a_headers,
        json={"category": "Market/Gıda", "limit_amount": 1000.0, "month_year": "2026-11"},
    )
    assert b1.status_code == 200

    b2 = client.post(
        "/api/v1/finance/budgets",
        headers=user_a_headers,
        json={"category": "Ulaşım", "limit_amount": 1000.0, "month_year": "2026-11"},
    )
    assert b2.status_code == 200

    # 2. Record confirmed Migros receipt transaction (450.50 TL)
    tx1 = client.post(
        "/api/v1/finance/transactions",
        headers=user_a_headers,
        json={
            "merchant_name": "Migros",
            "date": "2026-11-03",
            "total_amount": 450.50,
            "tax_amount": 45.05,
            "type": "expense",
            "category": "Market/Gıda",
            "receipt_image_url": "https://cdn.almadan.app/receipts/migros_001.jpg",
            "items": [{"name": "Süt", "price": 35.0}],
        },
    )
    assert tx1.status_code == 200
    tx1_data = tx1.json()
    assert tx1_data["budget_updated"] is True
    assert tx1_data["category_current_spent"] == 450.50
    assert tx1_data["category_limit_amount"] == 1000.0
    assert tx1_data["category_usage_percent"] == 45.05
    assert tx1_data["category_remaining_amount"] == 549.50

    # 3. Record second Market/Gıda transaction (399.50 TL -> cumulative 850.00 TL = %85)
    tx2 = client.post(
        "/api/v1/finance/transactions",
        headers=user_a_headers,
        json={
            "merchant_name": "CarrefourSA",
            "transaction_date": "2026-11-05",
            "amount": 399.50,
            "type": "expense",
            "category": "Market/Gıda",
        },
    )
    assert tx2.status_code == 200
    tx2_data = tx2.json()
    assert tx2_data["category_current_spent"] == 850.0
    assert tx2_data["category_usage_percent"] == 85.0
    assert tx2_data["category_remaining_amount"] == 150.0

    # 4. Record Ulaşım transaction (400.00 TL -> %40 Ulaşım)
    tx3 = client.post(
        "/api/v1/finance/transactions",
        headers=user_a_headers,
        json={
            "merchant_name": "İstanbulkart Dolum",
            "transaction_date": "2026-11-06",
            "amount": 400.0,
            "type": "expense",
            "category": "Ulaşım",
        },
    )
    assert tx3.status_code == 200
    assert tx3.json()["category_usage_percent"] == 40.0

    # 5. Fetch monthly budget summary
    summary_resp = client.get(
        "/api/v1/finance/budget-summary",
        headers=user_a_headers,
        params={"month_year": "2026-11"},
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()

    assert summary["user_id"] == user_a_id
    assert summary["month_year"] == "2026-11"
    assert summary["total_limit"] == 2000.0
    assert summary["total_spent"] == 1250.0
    assert summary["remaining_budget"] == 750.0
    assert summary["overall_usage_percent"] == 62.5

    assert len(summary["categories"]) == 2
    cat_market = summary["categories"][0]
    assert cat_market["category"] == "Market/Gıda"
    assert cat_market["current_spent"] == 850.0
    assert cat_market["remaining_amount"] == 150.0
    assert cat_market["usage_percent"] == 85.0
    assert cat_market["usage_label"] == "%85 Market/Gıda"

    cat_transport = summary["categories"][1]
    assert cat_transport["category"] == "Ulaşım"
    assert cat_transport["current_spent"] == 400.0
    assert cat_transport["remaining_amount"] == 600.0
    assert cat_transport["usage_percent"] == 40.0
    assert cat_transport["usage_label"] == "%40 Ulaşım"


# ---------------------------------------------------------------------------
# 3. Authentication & Multi-User RLS Isolation Tests
# ---------------------------------------------------------------------------

def test_finance_endpoints_require_jwt_and_isolate_users(
    client: TestClient,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
):
    """Unauthenticated requests must return 401, and User B must not see User A's budget."""
    unauth = client.get("/api/v1/finance/budget-summary")
    assert unauth.status_code == 401

    # User A adds an expense
    client.post(
        "/api/v1/finance/transactions",
        headers=user_a_headers,
        json={
            "merchant_name": "Migros",
            "amount": 500.0,
            "type": "expense",
            "category": "Market/Gıda",
            "transaction_date": "2026-11-03",
        },
    )

    # User B queries 2026-11 summary -> must be completely empty
    resp_b = client.get(
        "/api/v1/finance/budget-summary",
        headers=user_b_headers,
        params={"month_year": "2026-11"},
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["total_spent"] == 0.0
    assert resp_b.json()["categories"] == []
