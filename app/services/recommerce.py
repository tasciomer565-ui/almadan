"""
Almadan.app - Atıl Kıyafet Tespit (Dead-Stock Finder) ve Otonom 2. El Değerleme Motoru (Aşama 1.10).

Modül Sorumlulukları:
1. Otonom Atıl Kıyafet Tespiti (Dead-Stock Finder):
   - Kullanıcının `garments` tablosunu `outfit_logs` (kombin geçmişi) ile karşılaştırır.
   - Son 180 gündür (6 ay) hiçbir kombinde kullanılmayan veya toplamda sadece 1-2 kez giyilip
     aylardır dolapta bekleyen ürünleri "Atıl" (`is_idle=True`) olarak işaretler.
2. Hibrit Amortisman Algoritması (Değer Biçme):
   - Orijinal Fiyat (bilinmiyorsa kategori bazlı varsayılan taban fiyat).
   - Marka Katsayısı: Üst segment (Massimo Dutti vb.) %70, Orta segment (Zara vb.) %60, Alt segment %40.
   - Yıpranma Payı (Wear Factor): `wear_count * %0.5` düşüş.
   - Zaman Aşımı (Time Decay): Sisteme eklendiği/alındığı aydan itibaren her ay için `%1.5` düşüş.
   - Minimum Taban Fiyat: Orijinal fiyatın `%15`'inin altına inmez.
3. LLM Destekli İlan Metni Üretici:
   - `gemini-1.5-flash` veya `gpt-4o-mini` (veya yerel üretken motor) ile dikkat çekici 2. el ilan
     başlığı (`listing_title`) ve açıklaması (`listing_description`) üretir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any

import httpx

from app.api.v1.endpoints.sync import _RELATIONAL_DB, _normalize_dt

logger = logging.getLogger(__name__)

# ── Kategori Bazlı Varsayılan Taban Fiyatlar (Orijinal fiyat bilinmiyorsa) ─

CATEGORY_DEFAULT_PRICES: dict[str, float] = {
    "dis": 2000.0,
    "dış": 2000.0,
    "dış giyim": 2000.0,
    "ayakkabi": 1800.0,
    "ayakkabı": 1800.0,
    "alt": 1200.0,
    "alt giyim": 1200.0,
    "ust": 1000.0,
    "üst": 1000.0,
    "üst giyim": 1000.0,
    "aksesuar": 750.0,
}
FALLBACK_BASE_PRICE = 1000.0

# ── Marka Segment Katsayıları ────────────────────────────────────

PREMIUM_BRANDS = (
    "massimo dutti",
    "vakko",
    "beymen",
    "burberry",
    "tommy hilfiger",
    "lacoste",
    "calvin klein",
    "ralph lauren",
    "network",
    "ipekyol",
    "boss",
    "hugo boss",
    "michael kors",
)

MID_TIER_BRANDS = (
    "zara",
    "mango",
    "h&m",
    "hm",
    "bershka",
    "stradivarius",
    "pull&bear",
    "pull and bear",
    "oysho",
    "mavi",
    "levi's",
    "levis",
    "nike",
    "adidas",
    "puma",
    "new balance",
    "marks & spencer",
    "benetton",
)


def detect_brand_and_multiplier(
    garment_name: str,
    explicit_brand: str | None = None,
    tags: list[str] | None = None,
) -> tuple[str, str, float]:
    """
    Kıyafet adı, marka alanı veya etiketlerden markayı ve segment katsayısını belirler.
    Dönüş: (marka_adı, segment_etiketi, katsayı)
    - Üst segment (Massimo Dutti vb.) -> 0.70 (%70)
    - Orta segment (Zara vb.)         -> 0.60 (%60)
    - Alt segment / Diğer             -> 0.40 (%40)
    """
    combined = " ".join(
        filter(
            None,
            [
                explicit_brand or "",
                garment_name or "",
                " ".join(tags or []),
            ],
        )
    ).lower()

    for b in PREMIUM_BRANDS:
        if b in combined:
            return b.title(), "ust_segment", 0.70

    for b in MID_TIER_BRANDS:
        if b in combined:
            display = "H&M" if b in ("h&m", "hm") else b.title()
            return display, "orta_segment", 0.60

    brand_label = (explicit_brand or "").strip().title() or "Standart Marka"
    return brand_label, "alt_segment", 0.40


# ── 2. Hibrit Amortisman Algoritması ─────────────────────────────

@dataclass
class ResaleValuationResult:
    original_price: float
    brand_name: str
    brand_segment: str
    brand_multiplier: float
    wear_count: int
    wear_deduction_rate: float
    months_owned: int
    time_decay_rate: float
    floor_price: float
    suggested_resale_price: float


def calculate_resale_valuation(
    original_price: float | None,
    kind: str,
    garment_name: str,
    wear_count: int,
    months_owned: int,
    explicit_brand: str | None = None,
    tags: list[str] | None = None,
) -> ResaleValuationResult:
    """
    Deterministik Hibrit Amortisman Algoritması:
    - Orijinal Fiyat: `original_price > 0` ise kullanılır, değilse kategori varsayılanı alınır.
    - Marka Katsayısı: Üst segment %70 (`0.70`), Orta segment %60 (`0.60`), Alt segment %40 (`0.40`).
    - Yıpranma Payı (Wear Factor): `wear_count * %0.5` düşüş (`1 - wear_count * 0.005`).
    - Zaman Aşımı (Time Decay): `months_owned * %1.5` düşüş (`1 - months_owned * 0.015`).
    - Minimum Taban Fiyat: Orijinal fiyatın `%15`'i (`original_price * 0.15`).
    """
    kind_norm = (kind or "ust").strip().lower()
    base_price = (
        float(original_price)
        if original_price is not None and float(original_price) > 0
        else CATEGORY_DEFAULT_PRICES.get(kind_norm, FALLBACK_BASE_PRICE)
    )

    brand_name, brand_segment, brand_multiplier = detect_brand_and_multiplier(
        garment_name=garment_name,
        explicit_brand=explicit_brand,
        tags=tags,
    )

    safe_wears = max(0, int(wear_count))
    safe_months = max(0, int(months_owned))

    wear_deduction_rate = round(safe_wears * 0.005, 4)
    time_decay_rate = round(safe_months * 0.015, 4)

    wear_factor = max(0.0, 1.0 - wear_deduction_rate)
    time_factor = max(0.0, 1.0 - time_decay_rate)

    raw_resale = base_price * brand_multiplier * wear_factor * time_factor
    floor_price = round(base_price * 0.15, 2)
    suggested_price = round(max(raw_resale, floor_price), 2)

    return ResaleValuationResult(
        original_price=round(base_price, 2),
        brand_name=brand_name,
        brand_segment=brand_segment,
        brand_multiplier=brand_multiplier,
        wear_count=safe_wears,
        wear_deduction_rate=wear_deduction_rate,
        months_owned=safe_months,
        time_decay_rate=time_decay_rate,
        floor_price=floor_price,
        suggested_resale_price=suggested_price,
    )


# ── 1. Otonom Atıl Kıyafet Tespiti (Dead-Stock Finder) ───────────

@dataclass
class IdleGarmentAnalysis:
    garment_id: str
    garment: dict[str, Any]
    is_idle: bool
    idle_reason: str
    wear_count: int
    days_since_last_worn: int
    months_owned: int
    valuation: ResaleValuationResult


def find_idle_garments_for_user(
    user_id: str,
    now: datetime | None = None,
) -> list[IdleGarmentAnalysis]:
    """
    Kullanıcının `garments` ve `outfit_logs` tablolarını karşılaştırarak:
    - Son 180 gündür (6 ay) hiçbir kombinde giyilmeyen VEYA
    - Toplamda sadece 1-2 kez giyilip aylardır (`>= 2 ay`) dolapta bekleyen
    atıl kıyafetleri tespit eder ve amortisman değerlemesini hesaplar.
    """
    ref_now = _normalize_dt(now) if now else datetime.now(timezone.utc)
    user_garments = _RELATIONAL_DB.get("garments", {}).get(user_id, {})
    user_logs = _RELATIONAL_DB.get("outfit_logs", {}).get(user_id, {})

    # Her kıyafet için kombin geçmişinden giyilme sayısı ve son giyilme tarihini çıkar
    wear_counts: dict[str, int] = {}
    last_worn_map: dict[str, datetime] = {}

    for log in user_logs.values():
        if log.get("is_deleted", False):
            continue
        log_dt = _normalize_dt(log.get("date") or log.get("updated_at"))
        for gid in log.get("garment_ids") or []:
            gid_str = str(gid)
            wear_counts[gid_str] = wear_counts.get(gid_str, 0) + 1
            prev_dt = last_worn_map.get(gid_str)
            if prev_dt is None or log_dt > prev_dt:
                last_worn_map[gid_str] = log_dt

    idle_results: list[IdleGarmentAnalysis] = []

    for gid, g_row in user_garments.items():
        if g_row.get("is_deleted", False):
            continue

        gid_str = str(gid)
        wear_count = wear_counts.get(gid_str, 0)
        last_worn_dt = last_worn_map.get(gid_str)

        # Ürün sahiplik süresi (ay)
        purchase_dt_raw = g_row.get("purchase_date")
        origin_dt = _normalize_dt(purchase_dt_raw) if purchase_dt_raw else _normalize_dt(g_row.get("updated_at"))
        days_owned = max(0, (ref_now - origin_dt).days)
        months_owned = max(1, round(days_owned / 30.0)) if days_owned >= 15 else 0

        if last_worn_dt is not None:
            days_since_last_worn = max(0, (ref_now - last_worn_dt).days)
        else:
            # Hiç giyilmemişse satın alınma tarihinden bu yana geçen gün
            days_since_last_worn = max(days_owned, 180 if months_owned >= 6 else days_owned)

        # Atıl (Idle) Karar Kuralı:
        # 1) Son 180 gündür (6 ay) hiç giyilmemiş olması VEYA
        # 2) Sadece 0-2 kez giyilip en az 2 aydır (60 gün) dolapta bekliyor olması
        is_idle = False
        idle_reason = ""

        if days_since_last_worn >= 180:
            is_idle = True
            idle_reason = f"Son {days_since_last_worn} gündür (6+ ay) hiçbir kombinde giyilmedi."
        elif wear_count <= 2 and (days_owned >= 60 or days_since_last_worn >= 60):
            is_idle = True
            idle_reason = f"Sadece {wear_count} kez giyildi ve {months_owned} aydır dolapta bekliyor."

        if not is_idle:
            continue

        valuation = calculate_resale_valuation(
            original_price=g_row.get("price"),
            kind=str(g_row.get("kind", "ust")),
            garment_name=str(g_row.get("name", "")),
            wear_count=wear_count,
            months_owned=months_owned,
            explicit_brand=g_row.get("brand"),
            tags=g_row.get("tags"),
        )

        idle_results.append(
            IdleGarmentAnalysis(
                garment_id=gid_str,
                garment=g_row,
                is_idle=True,
                idle_reason=idle_reason,
                wear_count=wear_count,
                days_since_last_worn=days_since_last_worn,
                months_owned=months_owned,
                valuation=valuation,
            )
        )

    return idle_results


# ── 3. LLM Destekli 2. El İlan Metni Üretici ─────────────────────

async def generate_resale_listing_async(
    garment_name: str,
    brand_name: str,
    color: str,
    kind: str,
    wear_count: int,
    suggested_price: float,
) -> dict[str, str]:
    """
    `gemini-1.5-flash` veya `gpt-4o-mini` kullanarak 2. el platformları (Dolap, Gardrops, Letgo)
    için dikkat çekici bir ilan başlığı (`listing_title`) ve açıklaması (`listing_description`) üretir.
    """
    prompt = (
        "Sen profesyonel bir 2. el moda satış uzmanısın. Aşağıdaki kıyafet için dikkat çekici bir "
        "ilan başlığı ve güven veren kısa bir açıklama yaz.\n"
        f"Ürün: {garment_name}, Marka: {brand_name}, Renk: {color}, Kategori: {kind}, "
        f"Kullanım: {wear_count} kez giyildi, Önerilen Fiyat: {suggested_price} TL.\n"
        'Çıktı formatı: JSON ({"listing_title": "...", "listing_description": "..."})'
    )

    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if gemini_key:
        try:
            model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post(
                    url,
                    params={"key": gemini_key},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
                    },
                )
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates") or []
                    if candidates:
                        parts = (candidates[0].get("content") or {}).get("parts") or []
                        if parts and "text" in parts[0]:
                            parsed = json.loads(parts[0]["text"])
                            if "listing_title" in parsed and "listing_description" in parsed:
                                return {
                                    "listing_title": str(parsed["listing_title"]),
                                    "listing_description": str(parsed["listing_description"]),
                                }
        except Exception as exc:
            logger.debug("Gemini Re-Commerce ilan üretimi hatası: %s", exc)

    # Yerel Üretken İlan Metni Motoru
    cond_prefix = (
        "Etiketli ayarında, neredeyse hiç giyilmemiş"
        if wear_count <= 2
        else "Çok az kullanılmış, kusursuz"
    )
    color_cap = (color or "").strip().capitalize()
    clean_name = garment_name.strip()
    if brand_name.lower() not in clean_name.lower() and brand_name != "Standart Marka":
        title = f"{cond_prefix} {brand_name} {color_cap} {clean_name}".replace("  ", " ").strip()
    else:
        title = f"{cond_prefix} {color_cap} {clean_name}".replace("  ", " ").strip()

    description = (
        f"Gardırop detoksu nedeniyle satılıktır. Yalnızca {wear_count} kez özenle kullanıldı; "
        f"herhangi bir deformasyonu, lekesi veya söküğü yoktur. Orijinal {brand_name} kalitesinde, "
        f"kuru temizlemesi yapılmış şekilde yeni sahibini bekliyor."
    )
    return {
        "listing_title": title,
        "listing_description": description,
    }
