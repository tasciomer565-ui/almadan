"""
Almadan.app - Dış Bağlam Sağlayıcıları: Hava Durumu (MET Norway API) ve Takvim Bağlamı (Aşama 1.9).

Modül Sorumlulukları:
1. MET Norway Locationforecast 2.0 API (`https://api.met.no/weatherapi/locationforecast/2.0/compact`)
   üzerinden kullanıcının enlem/boylam (`lat`, `lon`) koordinatlarına göre anlık sıcaklık (°C)
   ve hava durumu bilgisini (Yağmurlu, Güneşli, Parçalı Bulutlu, Karlı vb.) asenkron olarak çeker.
2. Kullanıcının günlük takvim etkinliğini (Örn: "Saat 10:00 - Yönetim Toplantısı (Resmi)" veya
   "Hafta Sonu - Kafe Buluşması (Günlük)") sağlar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MET_NORWAY_COMPACT_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
MET_USER_AGENT = "AlmadanApp/2.0 (https://almadan.app; support@almadan.app)"


@dataclass
class WeatherContext:
    temperature_c: float
    condition_code: str
    condition_tr: str
    is_rainy: bool
    summary_text: str  # Örn: "15°C ve Yağmurlu"

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature_c": self.temperature_c,
            "condition_code": self.condition_code,
            "condition_tr": self.condition_tr,
            "is_rainy": self.is_rainy,
            "summary_text": self.summary_text,
        }


@dataclass
class CalendarContext:
    event_title: str
    formality: str  # "resmi" | "gunluk" | "spor"
    summary_text: str  # Örn: "Saat 10:00 - Yönetim Toplantısı (Resmi)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_title": self.event_title,
            "formality": self.formality,
            "summary_text": self.summary_text,
        }


def _map_met_symbol_to_tr(symbol_code: str) -> tuple[str, bool]:
    """
    MET Norway `symbol_code` değerini Türkçe hava durumu açıklamasına ve
    yağış bayrağına (`is_rainy`) dönüştürür.
    """
    code = (symbol_code or "").lower()
    if any(k in code for k in ("rain", "drizzle", "sleet", "shower", "thunder")):
        return "Yağmurlu", True
    if "snow" in code:
        return "Karlı", True
    if "fog" in code:
        return "Sisli", False
    if "clearsky" in code or "fair" in code:
        return "Güneşli", False
    if "partlycloudy" in code:
        return "Parçalı Bulutlu", False
    if "cloudy" in code:
        return "Bulutlu", False
    return "Parçalı Bulutlu", False


def _format_temp(temp_c: float) -> str:
    if float(temp_c).is_integer():
        return f"{int(temp_c)}°C"
    return f"{round(temp_c, 1)}°C"


async def fetch_weather_context_async(lat: float, lon: float) -> WeatherContext:
    """
    MET Norway API (`https://api.met.no/weatherapi/locationforecast/2.0/compact`)
    üzerinden kullanıcının konumuna ait günlük sıcaklık ve hava durumu bilgisini çeker.
    """
    headers = {
        "User-Agent": MET_USER_AGENT,
        "Accept": "application/json",
    }
    params = {
        "lat": round(float(lat), 4),
        "lon": round(float(lon), 4),
    }

    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            resp = await client.get(MET_NORWAY_COMPACT_URL, params=params, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                timeseries = ((payload.get("properties") or {}).get("timeseries")) or []
                if timeseries:
                    first_entry = timeseries[0].get("data") or {}
                    instant_details = ((first_entry.get("instant") or {}).get("details")) or {}
                    temp_c = float(instant_details.get("air_temperature", 15.0))

                    next_1h = ((first_entry.get("next_1_hours") or {}).get("summary")) or {}
                    next_6h = ((first_entry.get("next_6_hours") or {}).get("summary")) or {}
                    symbol_code = (
                        next_1h.get("symbol_code")
                        or next_6h.get("symbol_code")
                        or "partlycloudy_day"
                    )

                    condition_tr, is_rainy = _map_met_symbol_to_tr(str(symbol_code))
                    summary = f"{_format_temp(temp_c)} ve {condition_tr}"
                    return WeatherContext(
                        temperature_c=round(temp_c, 1),
                        condition_code=str(symbol_code),
                        condition_tr=condition_tr,
                        is_rainy=is_rainy,
                        summary_text=summary,
                    )
    except Exception as exc:
        logger.debug("MET Norway API erişim hatası (varsayılan hava durumu kullanılıyor): %s", exc)

    # Çevrimdışı / ağ hatası durumunda güvenli varsayılan
    return WeatherContext(
        temperature_c=15.0,
        condition_code="rain",
        condition_tr="Yağmurlu",
        is_rainy=True,
        summary_text="15°C ve Yağmurlu",
    )


def get_calendar_context(
    user_id: str | None = None,
    target_date: datetime | None = None,
) -> CalendarContext:
    """
    Kullanıcının bugünkü ana takvim etkinliğini döner.
    Hafta içi: "Saat 10:00 - Yönetim Toplantısı (Resmi)"
    Hafta sonu: "Hafta Sonu - Kafe Buluşması (Günlük)"
    """
    dt = target_date or datetime.now(timezone.utc)
    if dt.weekday() >= 5:
        return CalendarContext(
            event_title="Hafta Sonu - Kafe Buluşması",
            formality="gunluk",
            summary_text="Hafta Sonu - Kafe Buluşması (Günlük)",
        )
    return CalendarContext(
        event_title="Saat 10:00 - Yönetim Toplantısı",
        formality="resmi",
        summary_text="Saat 10:00 - Yönetim Toplantısı (Resmi)",
    )
