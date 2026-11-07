"""
Almadan.app - Hava Durumu ve Takvim Destekli Otonom Stilist Uç Noktası (Aşama 1.9).

Uç Nokta:
- `GET /api/v1/stylist/daily-outfit?lat=...&lon=...`
  Kullanıcının konumuna göre MET Norway hava durumunu ve günlük takvim etkinliğini çeker,
  Supabase/Drift eşitlenmiş gardırobundan en uygun 1 Üst, 1 Alt ve 1 Dış Giyim kombinini JSON olarak döner.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.security import require_auth_user
from app.services import context_providers, stylist_llm

router = APIRouter(prefix="/api/v1/stylist", tags=["stylist"])


class DailyOutfitResponse(BaseModel):
    top_id: str | None = Field(default=None, description="Seçilen Üst Giyim UUID")
    bottom_id: str | None = Field(default=None, description="Seçilen Alt Giyim UUID")
    outer_id: str | None = Field(default=None, description="Seçilen Dış Giyim UUID")
    explanation: str = Field(..., description="Stilistin kombin seçim açıklaması")
    weather: dict[str, Any] = Field(default_factory=dict, description="MET Norway hava durumu bağlamı")
    calendar_event: str = Field(..., description="Günün ana takvim etkinliği")
    provider: str = Field(default="stylist-llm")
    selected_garments: dict[str, dict[str, Any] | None] = Field(
        default_factory=dict,
        description="Seçilen kıyafetlerin detaylı nesneleri (top, bottom, outer)",
    )


@router.get("/daily-outfit", response_model=DailyOutfitResponse)
async def get_daily_outfit_endpoint(
    lat: float = Query(default=41.0082, ge=-90.0, le=90.0, description="Kullanıcı Enlem (Latitude)"),
    lon: float = Query(default=28.9784, ge=-180.0, le=180.0, description="Kullanıcı Boylam (Longitude)"),
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> DailyOutfitResponse:
    """
    Kullanıcının konumunu (`lat`, `lon`) alarak MET Norway hava durumunu ve takvim bağlamını
    analiz eder; gardırobundaki aktif kıyafetlerden LLM destekli günlük kombin önerisi sunar.
    """
    user_id = str(auth_user["id"])

    # 1. Hava Durumu (MET Norway API) ve Takvim Bağlamlarını Çek
    weather_ctx = await context_providers.fetch_weather_context_async(lat=lat, lon=lon)
    calendar_ctx = context_providers.get_calendar_context(user_id=user_id)

    # 2. Kullanıcının Aktif Gardırobunu Çek
    garments = stylist_llm.get_active_user_garments(user_id=user_id)

    # 3. LLM Stilist Kombin Motorunu Çalıştır
    recommendation = await stylist_llm.recommend_daily_outfit_async(
        garments=garments,
        weather=weather_ctx,
        calendar=calendar_ctx,
    )

    garment_map = {str(g["id"]): g for g in garments}

    return DailyOutfitResponse(
        top_id=recommendation.top_id,
        bottom_id=recommendation.bottom_id,
        outer_id=recommendation.outer_id,
        explanation=recommendation.explanation,
        weather=weather_ctx.to_dict(),
        calendar_event=calendar_ctx.summary_text,
        provider=recommendation.provider,
        selected_garments={
            "top": garment_map.get(str(recommendation.top_id)) if recommendation.top_id else None,
            "bottom": garment_map.get(str(recommendation.bottom_id)) if recommendation.bottom_id else None,
            "outer": garment_map.get(str(recommendation.outer_id)) if recommendation.outer_id else None,
        },
    )
