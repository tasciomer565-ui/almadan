"""
Almadan.app - LLM Destekli Otonom Stilist ve Kombin Motoru (Aşama 1.9).

Modül Sorumlulukları:
1. Kullanıcının `garments` tablosundaki aktif kıyafetlerini (`id`, `name`, `kind`, `color`,
   `min_temp_c`, `max_temp_c`, `waterproof`, `tags`) çeker.
2. Hava durumu (`WeatherContext`) ve Takvim etkinliği (`CalendarContext`) bağlamlarını birleştirerek
   Gemini 1.5 Flash / GPT-4o-mini modellerine profesyonel stilist prompt'u gönderir.
3. En uygun 1 Üst (`top_id`), 1 Alt (`bottom_id`), 1 Dış Giyim (`outer_id`) ve seçim gerekçesini
   (`explanation`) JSON formatında döner.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.api.v1.endpoints.sync import _RELATIONAL_DB
from app.services.context_providers import CalendarContext, WeatherContext

logger = logging.getLogger(__name__)


# ── Veri Modelleri ───────────────────────────────────────────────

class StylistOutfitRecommendation(BaseModel):
    top_id: str | None = Field(default=None, description="Seçilen Üst Giyim UUID")
    bottom_id: str | None = Field(default=None, description="Seçilen Alt Giyim UUID")
    outer_id: str | None = Field(default=None, description="Seçilen Dış Giyim UUID")
    explanation: str = Field(..., description="Kombinin hava durumu ve takvime göre seçilme nedeni")
    provider: str = Field(default="stylist-llm", description="Öneriyi üreten LLM sağlayıcısı")


# ── Gardırop Sorgulama ve Prompt İnşası ──────────────────────────

def get_active_user_garments(user_id: str) -> list[dict[str, Any]]:
    """
    Kullanıcının `garments` tablosundaki silinmemiş (`is_deleted=False`) ve
    temiz (`is_dirty=False`) kıyafetlerini stilist analizi için gerekli alanlarla döner.
    """
    user_bucket = _RELATIONAL_DB.get("garments", {}).get(user_id, {})
    active_list: list[dict[str, Any]] = []

    for row in user_bucket.values():
        if row.get("is_deleted", False) or row.get("is_dirty", False):
            continue
        active_list.append(
            {
                "id": str(row.get("id")),
                "name": str(row.get("name", "")),
                "kind": str(row.get("kind", "ust")).lower(),
                "color": str(row.get("color", "siyah")),
                "min_temp_c": float(row.get("min_temp_c", 10.0)),
                "max_temp_c": float(row.get("max_temp_c", 25.0)),
                "waterproof": bool(row.get("waterproof", False)),
                "tags": list(row.get("tags") or []),
            }
        )
    return active_list


def build_stylist_prompt(
    weather_summary: str,
    calendar_summary: str,
    garments: list[dict[str, Any]],
) -> str:
    """Aşama 1.9 şartnamesine uygun dinamik Stilist LLM prompt'u oluşturur."""
    garments_json = json.dumps(garments, ensure_ascii=False)
    return (
        f"Sen profesyonel bir stilistsin. Bugün hava {weather_summary}. "
        f"Kullanıcının takviminde {calendar_summary} var. "
        "Aşağıdaki kıyafet listesinden hava durumuna ve etkinliğe en uygun "
        "1 adet Üst, 1 adet Alt ve 1 adet Dış Giyim seç. Neden seçtiğini kısaca açıkla.\n"
        f"Kıyafetler: {garments_json}\n"
        'Çıktı formatı: JSON ({"top_id": "...", "bottom_id": "...", "outer_id": "...", "explanation": "..."})'
    )


# ── Harici LLM İstemcileri (Gemini 1.5 Flash & OpenAI GPT-4o-mini) ─

async def _call_gemini_stylist(prompt: str, api_key: str) -> dict[str, Any] | None:
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, params={"key": api_key}, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                candidates = body.get("candidates") or []
                if candidates:
                    parts = (candidates[0].get("content") or {}).get("parts") or []
                    if parts and "text" in parts[0]:
                        return json.loads(parts[0]["text"])
    except Exception as exc:
        logger.warning("Gemini Stylist LLM hatası: %s", exc)
    return None


async def _call_openai_stylist(prompt: str, api_key: str) -> dict[str, Any] | None:
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Sen profesyonel bir moda ve gardırop stilistisin. Sadece JSON dönersin."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                choices = body.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content") or ""
                    if content:
                        return json.loads(content)
    except Exception as exc:
        logger.warning("OpenAI Stylist LLM hatası: %s", exc)
    return None


# ── Yerel Çok Kriterli Stilist Karar Motoru (Fallback Engine) ────

def _score_garment(
    item: dict[str, Any],
    weather: WeatherContext,
    calendar: CalendarContext,
) -> float:
    score = 0.0
    temp = weather.temperature_c
    min_t = float(item.get("min_temp_c", 10.0))
    max_t = float(item.get("max_temp_c", 25.0))

    # 1. Sıcaklık uyumu
    if min_t <= temp <= max_t:
        score += 40.0
    else:
        dist = min(abs(temp - min_t), abs(temp - max_t))
        score -= dist * 2.5

    # 2. Yağmur / Su geçirmezlik (Dış giyimde kritik kriter)
    if weather.is_rainy:
        if item.get("waterproof", False):
            score += 100.0
        elif item.get("kind") == "dis":
            score -= 30.0

    # 3. Takvim etkinliği ve resmiyet uyumu
    tags_lower = " ".join(str(t).lower() for t in (item.get("tags") or []))
    name_lower = str(item.get("name", "")).lower()
    combined_text = f"{name_lower} {tags_lower}"

    if calendar.formality == "resmi" or "toplantı" in calendar.summary_text.lower() or "resmi" in calendar.summary_text.lower():
        if any(k in combined_text for k in ("resmi", "ofis", "toplantı", "klasik", "gömlek", "gomlek", "kumaş", "kumas", "trençkot", "trenckot", "blazer", "ceket")):
            score += 35.0
        if any(k in combined_text for k in ("eşofman", "esofman", "şort", "sort", "spor")):
            score -= 25.0
    else:
        if any(k in combined_text for k in ("günlük", "gunluk", "rahat", "casual", "jean", "tişört", "tisort")):
            score += 25.0

    return score


def _local_stylist_engine(
    garments: list[dict[str, Any]],
    weather: WeatherContext,
    calendar: CalendarContext,
) -> dict[str, Any]:
    tops = [g for g in garments if g.get("kind") in ("ust", "top", "üst", "üst giyim")]
    bottoms = [g for g in garments if g.get("kind") in ("alt", "bottom", "alt giyim")]
    outers = [g for g in garments if g.get("kind") in ("dis", "outer", "dış", "dış giyim")]

    best_top = max(tops, key=lambda g: _score_garment(g, weather, calendar)) if tops else None
    best_bottom = max(bottoms, key=lambda g: _score_garment(g, weather, calendar)) if bottoms else None
    best_outer = max(outers, key=lambda g: _score_garment(g, weather, calendar)) if outers else None

    parts = []
    if best_top:
        parts.append(f"üst olarak '{best_top['name']}'")
    if best_bottom:
        parts.append(f"alt olarak '{best_bottom['name']}'")
    if best_outer:
        wp_note = " (su geçirmez)" if best_outer.get("waterproof") else ""
        parts.append(f"dış giyim olarak '{best_outer['name']}'{wp_note}")

    joined_items = ", ".join(parts) if parts else "mevcut gardırop parçaları"
    rain_reason = (
        "Yağışlı havada ıslanmamak için su geçirmez dış giyim önceliklendirildi."
        if weather.is_rainy
        else "Sıcaklık aralığına en uygun katmanlar tercih edildi."
    )

    explanation = (
        f"Bugünkü {weather.summary_text} hava durumu ve takviminizdeki '{calendar.summary_text}' "
        f"etkinliği için {joined_items} seçildi. {rain_reason}"
    )

    return {
        "top_id": best_top["id"] if best_top else None,
        "bottom_id": best_bottom["id"] if best_bottom else None,
        "outer_id": best_outer["id"] if best_outer else None,
        "explanation": explanation,
    }


async def recommend_daily_outfit_async(
    garments: list[dict[str, Any]],
    weather: WeatherContext,
    calendar: CalendarContext,
) -> StylistOutfitRecommendation:
    """
    Kullanıcının aktif kıyafetlerini, hava durumunu ve takvim etkinliğini LLM'e göndererek
    günün kombinini (`top_id`, `bottom_id`, `outer_id`, `explanation`) oluşturur.
    """
    prompt = build_stylist_prompt(
        weather_summary=weather.summary_text,
        calendar_summary=calendar.summary_text,
        garments=garments,
    )

    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if gemini_key:
        raw = await _call_gemini_stylist(prompt, gemini_key)
        if isinstance(raw, dict) and "explanation" in raw:
            raw.setdefault("provider", "gemini-1.5-flash")
            return StylistOutfitRecommendation.model_validate(raw)

    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if openai_key:
        raw = await _call_openai_stylist(prompt, openai_key)
        if isinstance(raw, dict) and "explanation" in raw:
            raw.setdefault("provider", "gpt-4o-mini")
            return StylistOutfitRecommendation.model_validate(raw)

    fallback = _local_stylist_engine(garments, weather, calendar)
    fallback.setdefault("provider", "stylist-llm-engine")
    return StylistOutfitRecommendation.model_validate(fallback)
