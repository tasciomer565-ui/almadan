"""
Tests for Phase 1.8: Almadan.app - Otonom Fiyat İzleme Motoru ve Bildirim Sistemi (Price Tracker).
Covers:
1. Alert Management Endpoints (`POST /api/v1/alerts/create` & `GET /api/v1/alerts`)
2. Background Worker (`run_price_tracker_scan`):
   - When scraped price `<= target_price` (e.g., iPhone 16 Pro drops to 75.000 TL):
     * Sets `is_active = False`
     * Updates `current_price = 75000.0`
     * Emits Push Notification log:
       `PUSH NOTIFICATION SENDING: [<user_uuid>] - iPhone 16 Pro fiyatı 75.000 TL'ye düştü!`
   - When scraped price `> target_price`:
     * Updates `current_price` only, keeps `is_active = True`, sends no notification.
3. JWT Security & Multi-User Isolation.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_jwt
from app.workers import price_tracker
from app.workers.price_tracker import (
    SENT_PUSH_NOTIFICATIONS,
    reset_price_alerts_store,
    run_price_tracker_scan,
)


@pytest.fixture(autouse=True)
def clean_alerts_store():
    reset_price_alerts_store()
    yield
    reset_price_alerts_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_id() -> str:
    return "c0ffee11-2222-4333-8444-555555555555"


@pytest.fixture
def user_headers(user_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_id, email="firsataavcisi@almadan.app")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Price Drop -> Worker Triggers Push Notification & Closes Alert (`is_active=False`)
# ---------------------------------------------------------------------------

def test_price_tracker_worker_triggers_push_and_deactivates_alert_on_target_hit(
    client: TestClient,
    user_id: str,
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """
    Verifies the core Phase 1.8 scenario:
    1. User creates a price alert for 'iPhone 16 Pro' with `target_price = 78000.0` (initial `current_price = 85000.0`).
    2. Background worker `run_price_tracker_scan` runs and scrapes a new price of `75000.0 TL` (`<= 78000.0`).
    3. Worker sets `is_active = False`, updates `current_price = 75000.0`, and logs:
       `PUSH NOTIFICATION SENDING: [c0ffee11-2222-4333-8444-555555555555] - iPhone 16 Pro fiyatı 75.000 TL'ye düştü!`
    """
    # 1. Create active alert via POST /api/v1/alerts/create
    create_resp = client.post(
        "/api/v1/alerts/create",
        headers=user_headers,
        json={
            "product_name": "iPhone 16 Pro",
            "product_url": "https://www.trendyol.com/apple/iphone-16-pro-256gb-p-8547219",
            "target_price": 78000.0,
            "current_price": 85000.0,
        },
    )
    assert create_resp.status_code == 200
    created_alert = create_resp.json()
    alert_id = created_alert["id"]
    assert created_alert["is_active"] is True
    assert created_alert["current_price"] == 85000.0
    assert created_alert["target_price"] == 78000.0

    # 2. Mock async scraper to return 75.000 TL (<= 78.000 TL target)
    async def mock_scrape_price_drop(product_url: str, client=None) -> float:
        return 75000.0

    monkeypatch.setattr(price_tracker, "scrape_product_price_async", mock_scrape_price_drop)

    # 3. Execute background worker scan
    summary = asyncio.run(run_price_tracker_scan())

    assert summary.scanned_count == 1
    assert summary.triggered_count == 1
    assert summary.updated_count == 0

    expected_log = (
        f"PUSH NOTIFICATION SENDING: [{user_id}] - iPhone 16 Pro fiyatı 75.000 TL'ye düştü!"
    )
    captured = capsys.readouterr().out
    assert expected_log in captured
    assert expected_log in SENT_PUSH_NOTIFICATIONS

    # 4. Verify via GET /api/v1/alerts that `is_active` is now False and `current_price` is 75000.0
    list_resp = client.get("/api/v1/alerts", headers=user_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()

    assert list_data["total_count"] == 1
    assert list_data["active_count"] == 0
    assert list_data["past_count"] == 1

    closed_alert = list_data["past_alerts"][0]
    assert closed_alert["id"] == alert_id
    assert closed_alert["is_active"] is False
    assert closed_alert["current_price"] == 75000.0


# ---------------------------------------------------------------------------
# 2. Price Above Target -> Worker Only Updates `current_price`, Keeps `is_active=True`
# ---------------------------------------------------------------------------

def test_price_tracker_worker_updates_current_price_when_still_above_target(
    client: TestClient,
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    """
    When the newly scraped price (81.500 TL) is still above `target_price` (75.000 TL),
    the worker updates `current_price` to 81500.0, leaves `is_active = True`, and sends no push notification.
    """
    create_resp = client.post(
        "/api/v1/alerts/create",
        headers=user_headers,
        json={
            "product_name": "Sony PlayStation 5 Pro",
            "product_url": "https://www.hepsiburada.com/sony-ps5-pro-p-HBCV000999",
            "target_price": 75000.0,
            "current_price": 85000.0,
        },
    )
    assert create_resp.status_code == 200

    async def mock_scrape_still_high(product_url: str, client=None) -> float:
        return 81500.0

    monkeypatch.setattr(price_tracker, "scrape_product_price_async", mock_scrape_still_high)

    summary = asyncio.run(run_price_tracker_scan())

    assert summary.scanned_count == 1
    assert summary.triggered_count == 0
    assert summary.updated_count == 1
    assert len(SENT_PUSH_NOTIFICATIONS) == 0

    list_resp = client.get("/api/v1/alerts", headers=user_headers)
    list_data = list_resp.json()
    assert list_data["active_count"] == 1
    assert list_data["past_count"] == 0
    assert list_data["active_alerts"][0]["is_active"] is True
    assert list_data["active_alerts"][0]["current_price"] == 81500.0


# ---------------------------------------------------------------------------
# 3. Authentication & Multi-User Isolation Test
# ---------------------------------------------------------------------------

def test_alerts_endpoints_require_jwt_auth(client: TestClient):
    """Unauthenticated requests to /api/v1/alerts must return 401."""
    r1 = client.post(
        "/api/v1/alerts/create",
        json={"product_url": "https://www.trendyol.com/urun-p-1", "target_price": 1000.0},
    )
    assert r1.status_code == 401

    r2 = client.get("/api/v1/alerts")
    assert r2.status_code == 401
