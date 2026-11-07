"""
Tests for Phase 1.11: Almadan.app - Konum Tabanlı Otonom Kirli Sepeti ve Etkileşimli Bildirimler.
Covers:
1. `POST /api/v1/wardrobe/laundry-action`:
   - `{"action": "laundry"}` finds today's `outfit_logs` and sets `is_dirty = True` for all worn garments
     while leaving unworn garments untouched (`is_dirty = False`).
   - `{"action": "closet"}` leaves all garments clean (`is_dirty = False`).
2. `GET /api/v1/wardrobe/laundry-basket`:
   - Fetches `is_dirty = True` garments and groups them accurately into `Beyazlar`, `Renkliler`,
     and `Hassaslar` with appropriate washing instructions (e.g. "30 derece, hassas yıkama").
3. JWT Authentication guard.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_jwt
from app.api.v1.endpoints.sync import reset_sync_store


@pytest.fixture(autouse=True)
def clean_wardrobe_state():
    reset_sync_store()
    yield
    reset_sync_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_id() -> str:
    return "88881111-2222-4333-8444-777777777777"


@pytest.fixture
def user_headers(user_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_id, email="laundry@negiysem.app")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. "laundry" Action Marks Today's Outfit Dirty & Groups in Laundry Basket
# ---------------------------------------------------------------------------

def test_laundry_action_marks_todays_outfit_dirty_and_groups_basket(
    client: TestClient,
    user_headers: dict[str, str],
):
    """
    Verifies that sending `{"action": "laundry"}`:
    1. Finds today's `outfit_logs` entry.
    2. Updates the 3 garments worn today (`white-shirt`, `navy-chino`, `cashmere-sweater`) to `is_dirty = True`.
    3. Does NOT touch `unworn-jeans` (`is_dirty` remains `False`).
    4. `GET /api/v1/wardrobe/laundry-basket` groups the 3 dirty garments into
       `Beyazlar` (1), `Renkliler` (1), and `Hassaslar` (1) with washing instructions.
    """
    today_iso = datetime.now(timezone.utc).isoformat()

    # 1. Sync 4 garments (all initially clean) + today's outfit log wearing 3 of them
    sync_payload = {
        "garments": [
            {
                "id": "white-shirt-uuid",
                "name": "Pamuklu Beyaz Gömlek",
                "kind": "ust",
                "color": "beyaz",
                "is_dirty": False,
                "is_deleted": False,
            },
            {
                "id": "navy-chino-uuid",
                "name": "Mavi Chino Pantolon",
                "kind": "alt",
                "color": "lacivert",
                "is_dirty": False,
                "is_deleted": False,
            },
            {
                "id": "cashmere-sweater-uuid",
                "name": "Massimo Dutti Kaşmir Kazak",
                "kind": "ust",
                "color": "bordo",
                "tags": ["hassas", "kaşmir"],
                "is_dirty": False,
                "is_deleted": False,
            },
            {
                "id": "unworn-jeans-uuid",
                "name": "Dolapta Duran Siyah Jean",
                "kind": "alt",
                "color": "siyah",
                "is_dirty": False,
                "is_deleted": False,
            },
        ],
        "outfit_logs": [
            {
                "id": "todays-outfit-log-uuid",
                "date": today_iso,
                "garment_ids": [
                    "white-shirt-uuid",
                    "navy-chino-uuid",
                    "cashmere-sweater-uuid",
                ],
                "event_type": "Ofis",
                "is_deleted": False,
            }
        ],
    }

    r_sync = client.post("/api/v1/sync", headers=user_headers, json=sync_payload)
    assert r_sync.status_code == 200

    # 2. Trigger POST /api/v1/wardrobe/laundry-action with {"action": "laundry"}
    r_action = client.post(
        "/api/v1/wardrobe/laundry-action",
        headers=user_headers,
        json={"action": "laundry"},
    )
    assert r_action.status_code == 200
    action_data = r_action.json()

    assert action_data["status"] == "ok"
    assert action_data["action"] == "laundry"
    assert action_data["updated_dirty_count"] == 3
    assert set(action_data["affected_garment_ids"]) == {
        "white-shirt-uuid",
        "navy-chino-uuid",
        "cashmere-sweater-uuid",
    }

    # 3. Verify GET /api/v1/wardrobe/laundry-basket grouping & care instructions
    r_basket = client.get("/api/v1/wardrobe/laundry-basket", headers=user_headers)
    assert r_basket.status_code == 200
    basket = r_basket.json()

    assert basket["total_dirty_count"] == 3
    dirty_ids = {g["id"] for g in basket["dirty_garments"]}
    assert "unworn-jeans-uuid" not in dirty_ids

    groups = basket["groups"]
    assert groups["Beyazlar"]["count"] == 1
    assert groups["Beyazlar"]["items"][0]["id"] == "white-shirt-uuid"

    assert groups["Renkliler"]["count"] == 1
    assert groups["Renkliler"]["items"][0]["id"] == "navy-chino-uuid"

    assert groups["Hassaslar"]["count"] == 1
    assert groups["Hassaslar"]["items"][0]["id"] == "cashmere-sweater-uuid"
    assert "30 derece, hassas yıkama" in groups["Hassaslar"]["items"][0]["care_instructions"]


# ---------------------------------------------------------------------------
# 2. "closet" Action Leaves Today's Outfit Clean (`is_dirty=False`)
# ---------------------------------------------------------------------------

def test_closet_action_does_not_mark_garments_dirty(
    client: TestClient,
    user_headers: dict[str, str],
):
    """When user taps 'Dolaba Astım' (`action == 'closet'`), garments stay `is_dirty=False`."""
    today_iso = datetime.now(timezone.utc).isoformat()

    client.post(
        "/api/v1/sync",
        headers=user_headers,
        json={
            "garments": [
                {"id": "g-1", "name": "Beyaz Tişört", "kind": "ust", "color": "beyaz", "is_dirty": False}
            ],
            "outfit_logs": [
                {"id": "log-1", "date": today_iso, "garment_ids": ["g-1"]}
            ],
        },
    )

    r_closet = client.post(
        "/api/v1/wardrobe/laundry-action",
        headers=user_headers,
        json={"action": "closet"},
    )
    assert r_closet.status_code == 200
    assert r_closet.json()["updated_dirty_count"] == 0

    r_basket = client.get("/api/v1/wardrobe/laundry-basket", headers=user_headers)
    assert r_basket.status_code == 200
    assert r_basket.json()["total_dirty_count"] == 0


def test_wardrobe_endpoints_require_jwt_auth(client: TestClient):
    """Unauthenticated requests must return 401."""
    r1 = client.post("/api/v1/wardrobe/laundry-action", json={"action": "laundry"})
    assert r1.status_code == 401

    r2 = client.get("/api/v1/wardrobe/laundry-basket")
    assert r2.status_code == 401
