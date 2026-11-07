"""
Tests for Phase 1.4: Almadan.app - Supabase Relational Schema & Two-Way Cloud Sync API.
Covers:
- JWT Authentication (`require_auth_user`: missing, invalid, expired, valid Bearer tokens)
- Two-Way Sync (`POST /api/v1/sync`) across `garments`, `outfit_logs`, `pinned_days`, `trips`
- Last-Write-Wins (LWW) conflict resolution (`updated_at` comparison: stale vs newer)
- Tombstone / Soft-Delete (`is_deleted=True`) propagation and stale-resurrection prevention
- Strict multi-tenant isolation (`user_id` enforced from verified JWT, immune to payload spoofing)
- Delta pull filtering via `since` / `last_synced_at`
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_jwt
from app.api.v1.endpoints.sync import reset_sync_store


@pytest.fixture(autouse=True)
def clean_sync_store():
    """Reset the in-memory LWW sync state before and after each test."""
    reset_sync_store()
    yield
    reset_sync_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_a_id() -> str:
    return "11111111-2222-4333-8444-555555555555"


@pytest.fixture
def user_b_id() -> str:
    return "99999999-8888-4777-8666-555555555555"


@pytest.fixture
def user_a_headers(user_a_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_a_id, email="usera@negiysem.app")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_headers(user_b_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_b_id, email="userb@negiysem.app")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. JWT Authentication & Security Tests
# ---------------------------------------------------------------------------

def test_sync_rejects_missing_jwt(client: TestClient):
    """POST /api/v1/sync without Authorization header must return 401."""
    resp = client.post("/api/v1/sync", json={"garments": []})
    assert resp.status_code == 401
    assert "Authorization" in resp.json()["detail"]


def test_sync_rejects_invalid_jwt(client: TestClient):
    """POST /api/v1/sync with forged/corrupted JWT must return 401."""
    resp = client.post(
        "/api/v1/sync",
        headers={"Authorization": "Bearer invalid.jwt.token.value"},
        json={"garments": []},
    )
    assert resp.status_code == 401


def test_sync_rejects_expired_jwt(client: TestClient, user_a_id: str):
    """POST /api/v1/sync with an expired JWT must return 401."""
    expired_token = create_access_jwt(
        user_id=user_a_id,
        email="expired@negiysem.app",
        expires_in=-60,
    )
    resp = client.post(
        "/api/v1/sync",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"garments": []},
    )
    assert resp.status_code == 401
    assert "JWT" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 2. Initial Full Sync Across All 4 Relational Collections
# ---------------------------------------------------------------------------

def test_initial_two_way_sync_all_tables(
    client: TestClient,
    user_a_id: str,
    user_a_headers: dict[str, str],
):
    """Initial sync pushes garments, outfit_logs, pinned_days, and trips and returns full SyncResponse."""
    t0 = datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone.utc).isoformat()
    garment_id = str(uuid.uuid4())
    outfit_id = str(uuid.uuid4())
    pin_id = str(uuid.uuid4())
    trip_id = str(uuid.uuid4())

    payload = {
        "garments": [
            {
                "id": garment_id,
                "name": "Zara Kaşmir Kazak",
                "kind": "ust",
                "subKind": "kazak",
                "color": "#1E293B",
                "price": 2499.0,
                "updatedAt": t0,
                "isDeleted": False,
            }
        ],
        "outfit_logs": [
            {
                "id": outfit_id,
                "date": t0,
                "garmentIds": [garment_id],
                "eveningAnswer": "tam",
                "eventType": "Toplantı",
                "updatedAt": t0,
                "isDeleted": False,
            }
        ],
        "pinned_days": [
            {
                "id": pin_id,
                "date": "2026-11-05T09:00:00Z",
                "garmentIds": [garment_id],
                "updatedAt": t0,
                "isDeleted": False,
            }
        ],
        "trips": [
            {
                "id": trip_id,
                "city": "Milano",
                "startDate": "2026-11-10T08:00:00Z",
                "endDate": "2026-11-14T20:00:00Z",
                "packingChecks": {garment_id: True},
                "updatedAt": t0,
                "isDeleted": False,
            }
        ],
    }

    resp = client.post("/api/v1/sync", headers=user_a_headers, json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["user_id"] == user_a_id
    assert data["pushed_count"] == 4
    assert data["pulled_count"] == 4
    assert data["conflicts_resolved"] == 0

    assert len(data["garments"]) == 1
    assert data["garments"][0]["id"] == garment_id
    assert data["garments"][0]["user_id"] == user_a_id
    assert data["garments"][0]["price"] == 2499.0
    assert data["garments"][0]["is_deleted"] is False

    assert len(data["outfit_logs"]) == 1
    assert data["outfit_logs"][0]["id"] == outfit_id

    assert len(data["pinned_days"]) == 1
    assert data["pinned_days"][0]["id"] == pin_id

    assert len(data["trips"]) == 1
    assert data["trips"][0]["id"] == trip_id
    assert data["trips"][0]["city"] == "Milano"


# ---------------------------------------------------------------------------
# 3. Last-Write-Wins (LWW) Conflict Resolution Tests
# ---------------------------------------------------------------------------

def test_lww_stale_client_data_does_not_overwrite_newer_server_data(
    client: TestClient,
    user_a_headers: dict[str, str],
):
    """
    When the server holds a record with `updated_at = T_server` (12:00) and a client
    sends the same UUID with `updated_at = T_stale` (11:00):
    - The server MUST NOT overwrite its newer record.
    - `conflicts_resolved` must increment.
    - The response payload must return the server's newer version (12:00) so the client heals.
    """
    garment_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    t_server = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
    t_stale = t_server - timedelta(hours=1)
    t_newer = t_server + timedelta(hours=1)

    # Step 1: Device 1 syncs at 12:00 UTC
    resp1 = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": garment_id,
                    "name": "Güncel Kazak (12:00)",
                    "kind": "ust",
                    "price": 1500.0,
                    "updated_at": t_server.isoformat(),
                    "is_deleted": False,
                }
            ]
        },
    )
    assert resp1.status_code == 200
    assert resp1.json()["pushed_count"] == 1

    # Step 2: Offline Device 2 comes online and pushes stale state from 11:00 UTC
    resp_stale = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": garment_id,
                    "name": "Eski Kazak (11:00 - Stale)",
                    "kind": "ust",
                    "price": 900.0,
                    "updated_at": t_stale.isoformat(),
                    "is_deleted": False,
                }
            ]
        },
    )
    assert resp_stale.status_code == 200
    stale_data = resp_stale.json()

    # Stale update rejected; conflict recorded
    assert stale_data["pushed_count"] == 0
    assert stale_data["conflicts_resolved"] == 1

    # Server returns authoritative 12:00 record to overwrite Device 2's stale local row
    returned_garment = stale_data["garments"][0]
    assert returned_garment["id"] == garment_id
    assert returned_garment["name"] == "Güncel Kazak (12:00)"
    assert returned_garment["price"] == 1500.0

    # Step 3: Device 2 updates at 13:00 UTC (newer than 12:00 UTC) -> should win
    resp_newer = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": garment_id,
                    "name": "En Yeni Kazak (13:00)",
                    "kind": "ust",
                    "price": 1800.0,
                    "updated_at": t_newer.isoformat(),
                    "is_deleted": False,
                }
            ]
        },
    )
    assert resp_newer.status_code == 200
    newer_data = resp_newer.json()
    assert newer_data["pushed_count"] == 1
    assert newer_data["conflicts_resolved"] == 0
    assert newer_data["garments"][0]["name"] == "En Yeni Kazak (13:00)"
    assert newer_data["garments"][0]["price"] == 1800.0


# ---------------------------------------------------------------------------
# 4. Tombstone (Soft Delete `is_deleted=True`) Propagation & Resurrection Guard
# ---------------------------------------------------------------------------

def test_tombstone_soft_delete_and_stale_resurrection_prevention(
    client: TestClient,
    user_a_headers: dict[str, str],
):
    """
    Verifies Tombstone lifecycle:
    1. Item created at T0 (`is_deleted=False`).
    2. Item soft-deleted at T1 (`is_deleted=True`, `T1 > T0`) -> persisted on server as Tombstone.
    3. Another offline device pushes stale edit from T0.5 (`is_deleted=False`, `T0.5 < T1`) ->
       Server MUST NOT resurrect the deleted item (`is_deleted` stays `True`).
    """
    garment_id = "deadbeef-1234-4567-89ab-cdef01234567"
    t0 = datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc)
    t_stale_edit = datetime(2026, 11, 3, 9, 30, 0, tzinfo=timezone.utc)
    t_delete = datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Create active garment at T0
    r1 = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": garment_id,
                    "name": "Silinecek Ceket",
                    "kind": "dis",
                    "updated_at": t0.isoformat(),
                    "is_deleted": False,
                }
            ]
        },
    )
    assert r1.status_code == 200
    assert r1.json()["garments"][0]["is_deleted"] is False

    # 2. Soft-delete garment at T_delete (10:00)
    r2 = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": garment_id,
                    "name": "Silinecek Ceket",
                    "kind": "dis",
                    "updated_at": t_delete.isoformat(),
                    "is_deleted": True,
                }
            ]
        },
    )
    assert r2.status_code == 200
    r2_data = r2.json()
    assert r2_data["pushed_count"] == 1
    assert len(r2_data["garments"]) == 1
    assert r2_data["garments"][0]["id"] == garment_id
    assert r2_data["garments"][0]["is_deleted"] is True

    # 3. Stale offline device attempts to sync an edit from 09:30 with `is_deleted=False`
    r3 = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": garment_id,
                    "name": "Hayalet Ceket (Stale Edit)",
                    "kind": "dis",
                    "updated_at": t_stale_edit.isoformat(),
                    "is_deleted": False,
                }
            ]
        },
    )
    assert r3.status_code == 200
    r3_data = r3.json()
    assert r3_data["pushed_count"] == 0
    assert r3_data["conflicts_resolved"] == 1
    # Tombstone remains intact!
    assert r3_data["garments"][0]["is_deleted"] is True
    assert r3_data["garments"][0]["name"] == "Silinecek Ceket"


# ---------------------------------------------------------------------------
# 5. Multi-Tenant User Isolation & Delta Pull Tests
# ---------------------------------------------------------------------------

def test_strict_user_isolation_prevents_cross_tenant_leakage(
    client: TestClient,
    user_a_id: str,
    user_b_id: str,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
):
    """
    User A cannot view or overwrite User B's records even if User A injects User B's `user_id`
    in the request body.
    """
    shared_item_id = str(uuid.uuid4())
    t0 = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc).isoformat()

    # User A attempts to spoof user_b_id in the payload
    resp_a = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {
                    "id": shared_item_id,
                    "user_id": user_b_id,  # Spoof attempt!
                    "name": "User A Gomlek",
                    "kind": "ust",
                    "updated_at": t0,
                    "is_deleted": False,
                }
            ]
        },
    )
    assert resp_a.status_code == 200
    # Server enforces user_a_id from verified JWT
    assert resp_a.json()["garments"][0]["user_id"] == user_a_id

    # User B syncs and must see 0 garments in their own tenant bucket
    resp_b = client.post("/api/v1/sync", headers=user_b_headers, json={})
    assert resp_b.status_code == 200
    assert resp_b.json()["user_id"] == user_b_id
    assert resp_b.json()["garments"] == []


def test_delta_pull_with_last_synced_at(
    client: TestClient,
    user_a_headers: dict[str, str],
):
    """When `last_synced_at` (`since`) is provided, only records updated after that timestamp are returned."""
    t_old = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_cutoff = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc)
    t_recent = datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone.utc)

    old_id = str(uuid.uuid4())
    recent_id = str(uuid.uuid4())

    # Push two garments with different timestamps
    client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={
            "garments": [
                {"id": old_id, "name": "Eski Gomlek", "updated_at": t_old.isoformat(), "is_deleted": False},
                {"id": recent_id, "name": "Yeni Gomlek", "updated_at": t_recent.isoformat(), "is_deleted": False},
            ]
        },
    )

    # Pull delta since t_cutoff
    resp_delta = client.post(
        "/api/v1/sync",
        headers=user_a_headers,
        json={"last_synced_at": t_cutoff.isoformat()},
    )
    assert resp_delta.status_code == 200
    delta_garments = resp_delta.json()["garments"]
    assert len(delta_garments) == 1
    assert delta_garments[0]["id"] == recent_id
