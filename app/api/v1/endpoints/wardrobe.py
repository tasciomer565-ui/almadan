"""
Almadan.app - Konum Tabanlı Otonom Kirli Sepeti ve Yıkama Asistanı Uç Noktaları (Aşama 1.11).

Uç Noktalar:
1. `POST /api/v1/wardrobe/laundry-action`:
   - Mobil istemciden (kilit ekranı etkileşimli bildiriminden) `{"action": "laundry" | "closet"}` alır.
   - Kullanıcının bugünkü `outfit_logs` kaydını bulur.
   - `action == "laundry"` ise kombindeki tüm kıyafetlerin (`garment_ids`) `garments` tablosundaki
     durumunu `is_dirty = True` olarak günceller; `"closet"` ise dokunmaz.
2. `GET /api/v1/wardrobe/laundry-basket`:
   - `is_dirty = True` olan kıyafetleri çeker ve kumaş/renk/tür özelliklerine göre
     `Beyazlar`, `Renkliler` ve `Hassaslar` olarak yıkama talimatlarıyla gruplayıp döner.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.v1.endpoints.sync import (
    _RELATIONAL_DB,
    _normalize_dt,
    _supabase_upsert_row,
)
from app.security import require_auth_user
from app.storage import supabase_enabled

router = APIRouter(prefix="/api/v1/wardrobe", tags=["wardrobe-laundry"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Yıkama Grubu ve Talimat Sınıflandırıcı ───────────────────────

_DELICATE_KEYWORDS = (
    "ipek",
    "kaşmir",
    "kasmir",
    "yün",
    "yun",
    "keten",
    "saten",
    "dantel",
    "şifon",
    "sifon",
    "kadife",
    "süet",
    "suet",
    "deri",
    "kaban",
    "ceket",
    "blazer",
    "trençkot",
    "trenckot",
    "hassas",
    "kuru temizleme",
)

_WHITE_COLORS = (
    "beyaz",
    "white",
    "ekru",
    "krem",
    "fildişi",
    "fildisi",
    "ivory",
)

GROUP_CARE_INSTRUCTIONS: dict[str, str] = {
    "Beyazlar": "40°C pamuklu/beyazlar programı, optik parlatıcılı deterjan, 800-1000 devir sıkma",
    "Renkliler": "30°C - 40°C renkliler programı, renk koruyucu sıvı deterjan, ters çevirerek yıkama",
    "Hassaslar": "30°C hassas/elde yıkama programı, düşük sıkma (maks. 400-600 devir), kurutma makinesine atmayın",
}


def classify_laundry_group(garment: dict[str, Any]) -> tuple[str, str]:
    """
    Kıyafetin adı, alt türü, rengi ve etiketlerine göre yıkama grubunu
    (`Beyazlar`, `Renkliler`, `Hassaslar`) ve özel yıkama talimatını belirler.
    """
    name = str(garment.get("name", "")).lower()
    sub_kind = str(garment.get("sub_kind") or "").lower()
    kind = str(garment.get("kind", "")).lower()
    color = str(garment.get("color", "")).lower()
    tags_str = " ".join(str(t).lower() for t in (garment.get("tags") or []))
    combined = f"{name} {sub_kind} {kind} {tags_str}"

    # 1. Hassas Kumaş / Dış Giyim Kontrolü
    if any(kw in combined for kw in _DELICATE_KEYWORDS) or kind in ("dis", "dış", "dış giyim"):
        return "Hassaslar", "30 derece, hassas yıkama (düşük devir, ağartıcı kullanmayın)"

    # 2. Beyazlar Kontrolü
    if any(w in color or w in name for w in _WHITE_COLORS):
        return "Beyazlar", "40 derece, beyazlar programı (benzer açık tonlarla yıkayın)"

    # 3. Renkliler / Koyular
    return "Renkliler", "30 derece, renkliler programı (renk koruyucu ile ters çevirerek yıkayın)"


# ── Pydantic Veri Modelleri ──────────────────────────────────────

class LaundryActionRequest(BaseModel):
    action: Literal["laundry", "closet"] = Field(
        ...,
        description="Etkileşimli bildirim eylemi: 'laundry' (Kirliye Attım) veya 'closet' (Dolaba Astım)",
    )
    target_date: str | None = Field(
        default=None,
        description="Opsiyonel tarih (YYYY-MM-DD); boş bırakılırsa bugünün kombin kaydı baz alınır",
    )


class LaundryActionResponse(BaseModel):
    status: str = "ok"
    action: Literal["laundry", "closet"]
    date: str
    affected_garment_ids: list[str]
    updated_dirty_count: int
    message: str


class DirtyGarmentItem(BaseModel):
    id: str
    name: str
    kind: str
    color: str
    laundry_group: Literal["Beyazlar", "Renkliler", "Hassaslar"]
    care_instructions: str


class LaundryGroupBucket(BaseModel):
    group_name: Literal["Beyazlar", "Renkliler", "Hassaslar"]
    care_instructions: str
    count: int
    items: list[DirtyGarmentItem]


class LaundryBasketResponse(BaseModel):
    user_id: str
    total_dirty_count: int
    groups: dict[str, LaundryGroupBucket]
    dirty_garments: list[DirtyGarmentItem]


# ── 1. POST /api/v1/wardrobe/laundry-action ──────────────────────

@router.post("/laundry-action", response_model=LaundryActionResponse)
async def handle_laundry_action_endpoint(
    payload: LaundryActionRequest,
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> LaundryActionResponse:
    """
    Eve dönüş Geofence bildirimi üzerinden kullanıcının seçtiği eylemi işler:
    - Bugünün `outfit_logs` kayıtlarını bulur.
    - `action == "laundry"` ise kombindeki tüm kıyafetlerin `is_dirty = True` durumunu günceller.
    - `action == "closet"` ise kıyafetleri temiz (`is_dirty = False`) bırakır.
    """
    user_id = str(auth_user["id"])
    now = _utc_now()
    today_str = (payload.target_date or now.strftime("%Y-%m-%d")).strip()[:10]

    user_logs = _RELATIONAL_DB.get("outfit_logs", {}).get(user_id, {})
    user_garments = _RELATIONAL_DB.get("garments", {}).get(user_id, {})

    # Bugünkü tarihli aktif outfit_logs kayıtlarını bul
    todays_garment_ids: list[str] = []
    for log_row in user_logs.values():
        if log_row.get("is_deleted", False):
            continue
        log_dt = _normalize_dt(log_row.get("date"))
        if log_dt.strftime("%Y-%m-%d") == today_str:
            for gid in log_row.get("garment_ids") or []:
                gid_str = str(gid)
                if gid_str not in todays_garment_ids:
                    todays_garment_ids.append(gid_str)

    if payload.action == "closet":
        return LaundryActionResponse(
            status="ok",
            action="closet",
            date=today_str,
            affected_garment_ids=todays_garment_ids,
            updated_dirty_count=0,
            message="Kıyafetler dolaba asıldı olarak işaretlendi, kirli sepetine eklenmedi.",
        )

    # action == "laundry" -> Bugünkü kombindeki kıyafetleri is_dirty = True yap
    updated_count = 0
    supabase_tasks = []
    is_sb_enabled = supabase_enabled()

    for gid in todays_garment_ids:
        garment = user_garments.get(gid)
        if garment and not garment.get("is_deleted", False):
            garment["is_dirty"] = True
            garment["updated_at"] = now
            updated_count += 1
            if is_sb_enabled:
                supabase_tasks.append(_supabase_upsert_row("garments", garment))

    if supabase_tasks:
        await asyncio.gather(*supabase_tasks, return_exceptions=True)

    return LaundryActionResponse(
        status="ok",
        action="laundry",
        date=today_str,
        affected_garment_ids=todays_garment_ids,
        updated_dirty_count=updated_count,
        message=f"Bugünkü kombindeki {updated_count} kıyafet kirli sepetine eklendi.",
    )


# ── 2. GET /api/v1/wardrobe/laundry-basket ───────────────────────

@router.get("/laundry-basket", response_model=LaundryBasketResponse)
async def get_laundry_basket_endpoint(
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> LaundryBasketResponse:
    """
    Kullanıcının `is_dirty = True` olan tüm aktif kıyafetlerini çeker ve
    yıkama talimatlarıyla birlikte `Beyazlar`, `Renkliler`, `Hassaslar` gruplarına ayırarak döner.
    """
    user_id = str(auth_user["id"])
    user_garments = _RELATIONAL_DB.get("garments", {}).get(user_id, {})

    buckets: dict[str, list[DirtyGarmentItem]] = {
        "Beyazlar": [],
        "Renkliler": [],
        "Hassaslar": [],
    }
    all_dirty: list[DirtyGarmentItem] = []

    for g_row in user_garments.values():
        if g_row.get("is_deleted", False) or not g_row.get("is_dirty", False):
            continue

        group_name, item_instruction = classify_laundry_group(g_row)
        group_literal: Literal["Beyazlar", "Renkliler", "Hassaslar"] = (
            group_name if group_name in ("Beyazlar", "Renkliler", "Hassaslar") else "Renkliler"  # type: ignore[assignment]
        )

        dirty_item = DirtyGarmentItem(
            id=str(g_row.get("id")),
            name=str(g_row.get("name", "")),
            kind=str(g_row.get("kind", "ust")),
            color=str(g_row.get("color", "siyah")),
            laundry_group=group_literal,
            care_instructions=item_instruction,
        )
        buckets[group_literal].append(dirty_item)
        all_dirty.append(dirty_item)

    groups_out: dict[str, LaundryGroupBucket] = {}
    for g_key in ("Beyazlar", "Renkliler", "Hassaslar"):
        g_lit: Literal["Beyazlar", "Renkliler", "Hassaslar"] = g_key  # type: ignore[assignment]
        items_in_group = buckets[g_key]
        groups_out[g_key] = LaundryGroupBucket(
            group_name=g_lit,
            care_instructions=GROUP_CARE_INSTRUCTIONS[g_key],
            count=len(items_in_group),
            items=items_in_group,
        )

    return LaundryBasketResponse(
        user_id=user_id,
        total_dirty_count=len(all_dirty),
        groups=groups_out,
        dirty_garments=all_dirty,
    )
