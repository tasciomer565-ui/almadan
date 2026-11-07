"""
Almadan.app - Otonom Fiyat Alarmı Yönetim Uç Noktaları (Aşama 1.8).

Uç Noktalar:
1. `POST /api/v1/alerts/create` : Kullanıcıdan ürün URL'si ve hedef fiyat alıp `price_alerts` tablosuna kaydeder.
2. `GET /api/v1/alerts`         : Kullanıcının aktif (`is_active=True`) ve geçmiş (`is_active=False`) alarmlarını listeler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.security import require_auth_user
from app.storage import supabase_enabled
from app.workers.price_tracker import (
    PRICE_ALERTS_STORE,
    _supabase_upsert_alert,
    infer_product_name_from_url,
    scrape_product_price_async,
)

router = APIRouter(prefix="/api/v1/alerts", tags=["price-alerts"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic Veri Modelleri ──────────────────────────────────────

class PriceAlertCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_url: str = Field(
        ...,
        min_length=8,
        validation_alias=AliasChoices("product_url", "productUrl", "url"),
        description="Takip edilecek ürünün pazar yeri URL'si",
    )
    target_price: float = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices("target_price", "targetPrice"),
        description="Kullanıcının beklediği hedef fiyat (TL)",
    )
    product_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("product_name", "productName"),
        description="Ürün başlığı (boş bırakılırsa URL'den çıkarılır)",
    )
    current_price: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("current_price", "currentPrice"),
        description="Mevcut fiyat (boş bırakılırsa anlık taranır)",
    )


class PriceAlertResponse(BaseModel):
    id: str
    user_id: str
    product_name: str
    product_url: str
    target_price: float
    current_price: float
    is_active: bool
    created_at: str
    updated_at: str


class PriceAlertListResponse(BaseModel):
    user_id: str
    total_count: int
    active_count: int
    past_count: int
    active_alerts: list[PriceAlertResponse]
    past_alerts: list[PriceAlertResponse]
    alerts: list[PriceAlertResponse]


# ── 1. POST /api/v1/alerts/create ────────────────────────────────

@router.post("/create", response_model=PriceAlertResponse)
async def create_price_alert_endpoint(
    payload: PriceAlertCreateRequest,
    background_tasks: BackgroundTasks,
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> PriceAlertResponse:
    """
    Kullanıcıdan ürün URL'si ve hedef fiyat (`target_price`) alarak
    `price_alerts` tablosuna yeni bir aktif alarm (`is_active=True`) kaydeder.
    """
    user_id = str(auth_user["id"])
    alert_id = str(uuid.uuid4())
    now_iso = _utc_now_iso()

    product_url = payload.product_url.strip()
    product_name = (payload.product_name or "").strip() or infer_product_name_from_url(product_url)

    current_price = payload.current_price
    if current_price is None:
        scraped = await scrape_product_price_async(product_url)
        current_price = round(float(scraped), 2) if scraped else round(float(payload.target_price) * 1.15, 2)
    else:
        current_price = round(float(current_price), 2)

    alert_row: dict[str, Any] = {
        "id": alert_id,
        "user_id": user_id,
        "product_name": product_name,
        "product_url": product_url,
        "target_price": round(float(payload.target_price), 2),
        "current_price": current_price,
        "is_active": True,
        "created_at": now_iso,
        "updated_at": now_iso,
        "is_deleted": False,
    }

    PRICE_ALERTS_STORE[alert_id] = alert_row

    if supabase_enabled():
        background_tasks.add_task(_supabase_upsert_alert, alert_row)

    return PriceAlertResponse.model_validate(alert_row)


# ── 2. GET /api/v1/alerts ────────────────────────────────────────

@router.get("", response_model=PriceAlertListResponse)
async def list_price_alerts_endpoint(
    status: Literal["all", "active", "past"] = Query(
        default="all",
        description="Filtre: all (tümü), active (aktif alarmlar), past (tetiklenmiş/kapanmış alarmlar)",
    ),
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> PriceAlertListResponse:
    """Kullanıcının aktif ve geçmiş fiyat alarmlarını listeler."""
    user_id = str(auth_user["id"])

    user_rows = [
        row
        for row in PRICE_ALERTS_STORE.values()
        if row.get("user_id") == user_id and not row.get("is_deleted", False)
    ]
    user_rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)

    active_list = [PriceAlertResponse.model_validate(r) for r in user_rows if r.get("is_active", False)]
    past_list = [PriceAlertResponse.model_validate(r) for r in user_rows if not r.get("is_active", False)]

    if status == "active":
        combined = active_list
    elif status == "past":
        combined = past_list
    else:
        combined = active_list + past_list

    return PriceAlertListResponse(
        user_id=user_id,
        total_count=len(user_rows),
        active_count=len(active_list),
        past_count=len(past_list),
        active_alerts=active_list,
        past_alerts=past_list,
        alerts=combined,
    )
