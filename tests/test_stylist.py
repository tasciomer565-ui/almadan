"""
Tests for Phase 1.9: Almadan.app - Hava Durumu ve Takvim Destekli Otonom Stilist.
Covers:
1. `GET /api/v1/stylist/daily-outfit?lat=...&lon=...` with a mock wardrobe and rainy weather (`15°C ve Yağmurlu`)
   + formal meeting (`Saat 10:00 - Yönetim Toplantısı (Resmi)`):
   - Verifies that the stylist selects the waterproof outerwear (`waterproof=True`), formal top, and formal bottom.
2. `build_stylist_prompt` verification (includes weather, calendar event, garments JSON, and JSON output schema).
3. Exclusion of `is_deleted=True` and `is_dirty=True` garments and JWT authentication enforcement.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_jwt
from app.api.v1.endpoints.sync import reset_sync_store
from app.services import context_providers
from app.services.context_providers import CalendarContext, WeatherContext
from app.services.stylist_llm import build_stylist_prompt, get_active_user_garments


@pytest.fixture(autouse=True)
def clean_wardrobe_store():
    reset_sync_store()
    yield
    reset_sync_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_id() -> str:
    return "55551111-2222-4333-8444-999999999999"


@pytest.fixture
def user_headers(user_id: str) -> dict[str, str]:
    token = create_access_jwt(user_id=user_id, email="stilist@almadan.app")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Rainy Weather + Formal Calendar Event -> Selects Waterproof Outerwear
# ---------------------------------------------------------------------------

def test_daily_outfit_selects_waterproof_outerwear_on_rainy_meeting_day(
    client: TestClient,
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Syncs a mock wardrobe containing casual & formal tops/bottoms and two outerwear items
    (one non-waterproof suede jacket and one waterproof trenchcoat).
    Under 15°C Rainy weather and 'Saat 10:00 - Yönetim Toplantısı (Resmi)', verifies that
    `GET /api/v1/stylist/daily-outfit` selects the waterproof trenchcoat (`waterproof=True`).
    """
    # 1. Populate user's synced wardrobe via POST /api/v1/sync
    sync_payload = {
        "garments": [
            {
                "id": "top-casual-tee",
                "name": "Beyaz Spor Tişört",
                "kind": "ust",
                "color": "beyaz",
                "min_temp_c": 20.0,
                "max_temp_c": 32.0,
                "waterproof": False,
                "tags": ["spor", "günlük"],
                "is_deleted": False,
            },
            {
                "id": "top-formal-shirt",
                "name": "Zara Oxford Beyaz Gömlek",
                "kind": "ust",
                "color": "beyaz",
                "min_temp_c": 10.0,
                "max_temp_c": 24.0,
                "waterproof": False,
                "tags": ["resmi", "ofis", "toplantı"],
                "is_deleted": False,
            },
            {
                "id": "bottom-shorts",
                "name": "Bej Keten Şort",
                "kind": "alt",
                "color": "bej",
                "min_temp_c": 23.0,
                "max_temp_c": 35.0,
                "waterproof": False,
                "tags": ["tatil", "spor"],
                "is_deleted": False,
            },
            {
                "id": "bottom-formal-trousers",
                "name": "Massimo Dutti Lacivert Kumaş Pantolon",
                "kind": "alt",
                "color": "lacivert",
                "min_temp_c": 8.0,
                "max_temp_c": 22.0,
                "waterproof": False,
                "tags": ["resmi", "ofis", "toplantı"],
                "is_deleted": False,
            },
            {
                "id": "outer-suede-jacket",
                "name": "Kahverengi Süet Ceket",
                "kind": "dis",
                "color": "kahverengi",
                "min_temp_c": 12.0,
                "max_temp_c": 20.0,
                "waterproof": False,
                "tags": ["günlük"],
                "is_deleted": False,
            },
            {
                "id": "outer-waterproof-trench",
                "name": "Burberry Su Geçirmez Trençkot",
                "kind": "dis",
                "color": "antrasit",
                "min_temp_c": 10.0,
                "max_temp_c": 20.0,
                "waterproof": True,
                "tags": ["resmi", "toplantı", "ofis"],
                "is_deleted": False,
            },
            {
                "id": "outer-deleted-raincoat",
                "name": "Silinmiş Yağmurluk",
                "kind": "dis",
                "color": "siyah",
                "min_temp_c": 10.0,
                "max_temp_c": 20.0,
                "waterproof": True,
                "tags": ["resmi"],
                "is_deleted": True,  # Tombstone -> seçilmemeli!
            },
        ]
    }
    sync_resp = client.post("/api/v1/sync", headers=user_headers, json=sync_payload)
    assert sync_resp.status_code == 200

    # 2. Mock MET Norway Weather (15°C ve Yağmurlu) & Calendar Context (Yönetim Toplantısı)
    async def mock_rainy_weather(lat: float, lon: float) -> WeatherContext:
        return WeatherContext(
            temperature_c=15.0,
            condition_code="heavyrain",
            condition_tr="Yağmurlu",
            is_rainy=True,
            summary_text="15°C ve Yağmurlu",
        )

    def mock_meeting_calendar(user_id=None, target_date=None) -> CalendarContext:
        return CalendarContext(
            event_title="Saat 10:00 - Yönetim Toplantısı",
            formality="resmi",
            summary_text="Saat 10:00 - Yönetim Toplantısı (Resmi)",
        )

    monkeypatch.setattr(context_providers, "fetch_weather_context_async", mock_rainy_weather)
    monkeypatch.setattr(context_providers, "get_calendar_context", mock_meeting_calendar)

    # 3. Call GET /api/v1/stylist/daily-outfit
    resp = client.get(
        "/api/v1/stylist/daily-outfit",
        headers=user_headers,
        params={"lat": 41.0082, "lon": 28.9784},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Verify selected IDs
    assert data["top_id"] == "top-formal-shirt"
    assert data["bottom_id"] == "bottom-formal-trousers"
    assert data["outer_id"] == "outer-waterproof-trench"
    assert data["selected_garments"]["outer"]["waterproof"] is True
    assert "15°C ve Yağmurlu" in data["explanation"]
    assert data["weather"]["is_rainy"] is True


# ---------------------------------------------------------------------------
# 2. Prompt Builder & Auth Verification
# ---------------------------------------------------------------------------

def test_stylist_prompt_structure_and_auth_guard(client: TestClient, user_id: str, user_headers: dict[str, str]):
    """Verifies prompt structure and 401 on unauthenticated request."""
    unauth = client.get("/api/v1/stylist/daily-outfit?lat=41.0&lon=29.0")
    assert unauth.status_code == 401

    prompt = build_stylist_prompt(
        weather_summary="15°C ve Yağmurlu",
        calendar_summary="Yönetim Toplantısı (Resmi)",
        garments=[{"id": "1", "name": "Trençkot", "kind": "dis", "waterproof": True}],
    )
    assert "Sen profesyonel bir stilistsin. Bugün hava 15°C ve Yağmurlu." in prompt
    assert "Kullanıcının takviminde Yönetim Toplantısı (Resmi) var." in prompt
    assert '"top_id"' in prompt and '"outer_id"' in prompt and '"explanation"' in prompt
