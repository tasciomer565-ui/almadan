from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.security import require_auth_user
from app.storage import supabase_base_url, supabase_enabled, supabase_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cloud-sync"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(value: datetime | str | None) -> datetime:
    """Tüm tarihleri karşılaştırılabilir UTC aware datetime nesnesine dönüştürür."""
    if value is None:
        return _utc_now()
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            return _utc_now()
    elif isinstance(value, datetime):
        dt = value
    else:
        return _utc_now()

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── İlişkisel Senkronizasyon Veri Modelleri (Pydantic v2) ─────────

class SyncGarmentItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="UUID v4 Primary Key")
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_id", "userId"),
    )
    name: str = Field(..., description="Kıyafet adı")
    brand: str | None = Field(default=None, description="Marka adı (Zara, Massimo Dutti vb.)")
    kind: str = Field(default="ust", description="Ana kategori (ust, alt, dis, ayakkabi, aksesuar)")
    sub_kind: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sub_kind", "subKind"),
    )
    color: str = Field(default="siyah", description="Renk kodu/adı")
    min_temp_c: float = Field(
        default=10.0,
        validation_alias=AliasChoices("min_temp_c", "minTempC"),
    )
    max_temp_c: float = Field(
        default=25.0,
        validation_alias=AliasChoices("max_temp_c", "maxTempC"),
    )
    season: str = Field(default="dortMevsim")
    thickness: str = Field(default="orta")
    waterproof: bool = Field(default=False)
    is_favorite: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_favorite", "isFavorite"),
    )
    is_dirty: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_dirty", "isDirty"),
    )
    storage_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("storage_location", "storageLocation"),
    )
    tags: list[str] = Field(default_factory=list)
    price: float = Field(default=0.0)
    purchase_date: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("purchase_date", "purchaseDate"),
    )
    photo_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("photo_path", "photoPath"),
    )
    image_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("image_path", "imagePath"),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )
    is_deleted: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_deleted", "isDeleted"),
    )


class SyncOutfitLogItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="UUID v4 Primary Key")
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_id", "userId"),
    )
    date: datetime = Field(..., description="Kombinin giyildiği gün")
    garment_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("garment_ids", "garmentIds"),
    )
    evening_answer: str | None = Field(
        default=None,
        validation_alias=AliasChoices("evening_answer", "eveningAnswer"),
    )
    event_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("event_type", "eventType"),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )
    is_deleted: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_deleted", "isDeleted"),
    )


class SyncPinnedDayItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="UUID v4 Primary Key")
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_id", "userId"),
    )
    date: datetime = Field(..., description="Sabitlenen kombin tarihi")
    garment_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("garment_ids", "garmentIds"),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )
    is_deleted: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_deleted", "isDeleted"),
    )


class SyncTripItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="UUID v4 Primary Key")
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_id", "userId"),
    )
    city: str = Field(..., description="Seyahat şehri")
    start_date: datetime = Field(
        ...,
        validation_alias=AliasChoices("start_date", "startDate"),
    )
    end_date: datetime = Field(
        ...,
        validation_alias=AliasChoices("end_date", "endDate"),
    )
    packing_checks: dict[str, bool] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("packing_checks", "packingChecks"),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )
    is_deleted: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_deleted", "isDeleted"),
    )


class SyncPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_id", "userId"),
    )
    client_timestamp: datetime = Field(
        default_factory=_utc_now,
        validation_alias=AliasChoices("client_timestamp", "clientTimestamp"),
    )
    since: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("since", "last_synced_at", "lastSyncedAt"),
    )
    garments: list[SyncGarmentItem] = Field(default_factory=list)
    outfit_logs: list[SyncOutfitLogItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("outfit_logs", "outfitLogs"),
    )
    pinned_days: list[SyncPinnedDayItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("pinned_days", "pinnedDays"),
    )
    trips: list[SyncTripItem] = Field(default_factory=list)


class SyncResponse(BaseModel):
    user_id: str
    server_timestamp: datetime
    pushed_count: int
    pulled_count: int
    conflicts_resolved: int
    garments: list[SyncGarmentItem]
    outfit_logs: list[SyncOutfitLogItem]
    pinned_days: list[SyncPinnedDayItem]
    trips: list[SyncTripItem]


# ── İlişkisel Bellek & Supabase Yedekli Veri Deposu ──────────────
# Yapı: _RELATIONAL_DB[table_name][user_id][record_id] = dict

_RELATIONAL_DB: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
    "users": {},
    "garments": {},
    "outfit_logs": {},
    "pinned_days": {},
    "trips": {},
}


def reset_sync_store() -> None:
    """Test senaryoları için ilişkisel eşitleme deposunu sıfırlar."""
    for table in _RELATIONAL_DB.values():
        table.clear()


async def _supabase_upsert_row(table: str, row: dict[str, Any]) -> None:
    """Supabase ilişkisel tablosuna asenkron Upsert (POST Prefer: resolution=merge-duplicates) yapar."""
    if not supabase_enabled():
        return
    try:
        headers = {
            **supabase_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        # Datetime nesnelerini ISO-8601 string'e çevir
        serialized = {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in row.items()
        }
        async with httpx.AsyncClient(timeout=2.5) as client:
            url = f"{supabase_base_url()}/rest/v1/{table}"
            await client.post(url, headers=headers, json=serialized)
    except Exception as exc:
        logger.debug("Supabase %s upsert hatası (bellek içi depo aktif): %s", table, exc)


def _apply_lww_for_collection(
    table_name: str,
    user_id: str,
    incoming_items: list[BaseModel],
) -> tuple[int, int, list[dict[str, Any]]]:
    """
    Verilen tablo ve kullanıcı için Last-Write-Wins (LWW) + Tombstone algoritmasını işletir.
    Dönüş: (pushed_count, conflicts_resolved, upserted_rows)
    """
    user_bucket = _RELATIONAL_DB[table_name].setdefault(user_id, {})
    pushed = 0
    conflicts = 0
    upserted_rows: list[dict[str, Any]] = []

    for item in incoming_items:
        data = item.model_dump()
        record_id = str(data["id"])
        data["user_id"] = user_id
        incoming_ts = _normalize_dt(data.get("updated_at"))
        data["updated_at"] = incoming_ts
        data["is_deleted"] = bool(data.get("is_deleted", False))

        existing = user_bucket.get(record_id)
        if existing is None:
            # Sunucuda kayıt yok -> Yeni kayıt (veya doğrudan tombstone) ekle
            user_bucket[record_id] = data
            pushed += 1
            upserted_rows.append(data)
        else:
            server_ts = _normalize_dt(existing.get("updated_at"))
            if incoming_ts > server_ts:
                # İstemci verisi daha yeni -> Üzerine yaz (Upsert / Soft Delete Tombstone)
                user_bucket[record_id] = data
                pushed += 1
                upserted_rows.append(data)
            else:
                # İstemci verisi eski veya aynı -> Sunucudaki güncel veriyi koru!
                if incoming_ts < server_ts:
                    conflicts += 1

    return pushed, conflicts, upserted_rows


# ── Çift Yönlü Eşitleme (Two-Way Sync) Uç Noktası ────────────────

@router.post("/sync", response_model=SyncResponse)
async def sync_user_data(
    payload: SyncPayload,
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> SyncResponse:
    """
    Ne Giysem <-> Almadan.app Çift Yönlü Bulut Eşitleme (Two-Way Cloud Sync) Uç Noktası.
    - `require_auth_user` ile doğrulanmış JWT'deki `user_id` zorunlu kılınır (başka kullanıcının verisine erişilemez).
    - `garments`, `outfit_logs`, `pinned_days` ve `trips` tabloları için Last-Write-Wins (LWW) uygulanır.
    - `is_deleted=True` (Tombstone) kayıtları fiziksel silinmez, zaman damgası yeniyse tombstone olarak güncellenir.
    - İşlem sonunda kullanıcının sunucudaki en güncel tüm verileri `SyncResponse` (SyncPayload) olarak geri döner.
    """
    user_id = str(auth_user["id"])
    now = _utc_now()

    # Kullanıcının `users` tablosundaki ana kaydını garantiye al
    users_bucket = _RELATIONAL_DB["users"].setdefault(user_id, {})
    users_bucket[user_id] = {
        "id": user_id,
        "user_id": user_id,
        "email": auth_user.get("email"),
        "updated_at": now,
        "is_deleted": False,
    }

    total_pushed = 0
    total_conflicts = 0
    supabase_tasks = []

    is_sb_enabled = supabase_enabled()

    # 1. Garments LWW
    p_g, c_g, rows_g = _apply_lww_for_collection("garments", user_id, payload.garments)
    total_pushed += p_g
    total_conflicts += c_g
    if is_sb_enabled:
        for r in rows_g:
            supabase_tasks.append(_supabase_upsert_row("garments", r))

    # 2. Outfit Logs LWW
    p_o, c_o, rows_o = _apply_lww_for_collection("outfit_logs", user_id, payload.outfit_logs)
    total_pushed += p_o
    total_conflicts += c_o
    if is_sb_enabled:
        for r in rows_o:
            supabase_tasks.append(_supabase_upsert_row("outfit_logs", r))

    # 3. Pinned Days LWW
    p_p, c_p, rows_p = _apply_lww_for_collection("pinned_days", user_id, payload.pinned_days)
    total_pushed += p_p
    total_conflicts += c_p
    if is_sb_enabled:
        for r in rows_p:
            supabase_tasks.append(_supabase_upsert_row("pinned_days", r))

    # 4. Trips LWW
    p_t, c_t, rows_t = _apply_lww_for_collection("trips", user_id, payload.trips)
    total_pushed += p_t
    total_conflicts += c_t
    if is_sb_enabled:
        for r in rows_t:
            supabase_tasks.append(_supabase_upsert_row("trips", r))

    if supabase_tasks:
        await asyncio.gather(*supabase_tasks, return_exceptions=True)

    # 5. Sunucudaki en güncel verileri topla (since filtresi varsa uygula)
    since_dt = _normalize_dt(payload.since) if payload.since else None

    def _collect(table_name: str, model_cls: type[BaseModel]) -> list[Any]:
        bucket = _RELATIONAL_DB[table_name].get(user_id, {})
        items = []
        for raw in bucket.values():
            if since_dt and _normalize_dt(raw.get("updated_at")) <= since_dt:
                continue
            items.append(model_cls.model_validate(raw))
        return items

    out_garments = _collect("garments", SyncGarmentItem)
    out_logs = _collect("outfit_logs", SyncOutfitLogItem)
    out_pinned = _collect("pinned_days", SyncPinnedDayItem)
    out_trips = _collect("trips", SyncTripItem)

    total_pulled = len(out_garments) + len(out_logs) + len(out_pinned) + len(out_trips)

    return SyncResponse(
        user_id=user_id,
        server_timestamp=now,
        pushed_count=total_pushed,
        pulled_count=total_pulled,
        conflicts_resolved=total_conflicts,
        garments=out_garments,
        outfit_logs=out_logs,
        pinned_days=out_pinned,
        trips=out_trips,
    )
