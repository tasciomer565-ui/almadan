"""
Almadan.app - Atıl Kıyafet Tespit ve Otonom 2. El Değerleme (Re-Commerce) Uç Noktası (Aşama 1.10).

Uç Nokta:
- `GET /api/v1/recommerce/suggestions`
  Kullanıcının 6 aydır giymediği veya dolapta atıl bekleyen kıyafetlerini tespit eder,
  Hibrit Amortisman Algoritması ile 2. el satış fiyatını hesaplar ve LLM destekli
  ilan başlığı/açıklaması ile birlikte döner.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security import require_auth_user
from app.services.recommerce import (
    find_idle_garments_for_user,
    generate_resale_listing_async,
)

router = APIRouter(prefix="/api/v1/recommerce", tags=["recommerce"])


class RecommerceSuggestionItem(BaseModel):
    garment_id: str
    garment_name: str
    brand_name: str
    brand_segment: str
    brand_multiplier: float
    kind: str
    color: str
    original_price: float
    suggested_resale_price: float
    floor_price: float
    wear_count: int
    months_owned: int
    days_since_last_worn: int
    idle_reason: str
    listing_title: str
    listing_description: str


class RecommerceSuggestionsResponse(BaseModel):
    user_id: str
    idle_count: int
    total_estimated_earnings: float = Field(
        ...,
        description="Atıl kıyafetlerin tamamı satıldığında elde edilecek tahmini toplam gelir (TL)",
    )
    suggestions: list[RecommerceSuggestionItem]


@router.get("/suggestions", response_model=RecommerceSuggestionsResponse)
async def get_recommerce_suggestions_endpoint(
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> RecommerceSuggestionsResponse:
    """
    Kullanıcının gardırobundaki atıl kıyafetleri (`is_idle=True`), amortisman algoritmasıyla
    hesaplanan `suggested_resale_price` değerini ve LLM tarafından hazırlanan 2. el ilan metnini döner.
    """
    user_id = str(auth_user["id"])
    idle_items = find_idle_garments_for_user(user_id=user_id)

    if not idle_items:
        return RecommerceSuggestionsResponse(
            user_id=user_id,
            idle_count=0,
            total_estimated_earnings=0.0,
            suggestions=[],
        )

    listing_tasks = [
        generate_resale_listing_async(
            garment_name=str(item.garment.get("name", "")),
            brand_name=item.valuation.brand_name,
            color=str(item.garment.get("color", "")),
            kind=str(item.garment.get("kind", "ust")),
            wear_count=item.wear_count,
            suggested_price=item.valuation.suggested_resale_price,
        )
        for item in idle_items
    ]
    listings = await asyncio.gather(*listing_tasks)

    suggestions: list[RecommerceSuggestionItem] = []
    for item, copy_dict in zip(idle_items, listings):
        suggestions.append(
            RecommerceSuggestionItem(
                garment_id=item.garment_id,
                garment_name=str(item.garment.get("name", "")),
                brand_name=item.valuation.brand_name,
                brand_segment=item.valuation.brand_segment,
                brand_multiplier=item.valuation.brand_multiplier,
                kind=str(item.garment.get("kind", "ust")),
                color=str(item.garment.get("color", "siyah")),
                original_price=item.valuation.original_price,
                suggested_resale_price=item.valuation.suggested_resale_price,
                floor_price=item.valuation.floor_price,
                wear_count=item.wear_count,
                months_owned=item.months_owned,
                days_since_last_worn=item.days_since_last_worn,
                idle_reason=item.idle_reason,
                listing_title=copy_dict["listing_title"],
                listing_description=copy_dict["listing_description"],
            )
        )

    total_earnings = round(sum(s.suggested_resale_price for s in suggestions), 2)

    return RecommerceSuggestionsResponse(
        user_id=user_id,
        idle_count=len(suggestions),
        total_estimated_earnings=total_earnings,
        suggestions=suggestions,
    )
