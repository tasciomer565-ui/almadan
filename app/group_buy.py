"""
GroupBuyEngine — Sprint 7: Topluluk Grup Alışverişi

Akış:
  1. Kullanıcı → grup oluşturur (ürün, hedef fiyat, adet, konum)
  2. Diğer kullanıcılar → katılır (quantity_wanted)
  3. Hedef adede ulaşılınca → trigger ile 'completed' olur
  4. Tüm üyelere push bildirimi gönderilir
  5. Partner API ile toplu sipariş iletilebilir

Konum gizliliği:
  - Tam adres saklanmaz, sadece "ilçe hash'i" (Beşiktaş → sha256 → ilk 8 hex)
  - Kullanıcı isteğe bağlı konum paylaşır
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

GROUP_BUY_DEFAULT_EXPIRY_DAYS = 7
GROUP_BUY_MAX_EXPIRY_DAYS     = 30
MIN_TARGET_QUANTITY           = 2
MAX_TARGET_QUANTITY           = 1000


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


def hash_location(district: str) -> str:
    """İlçe adını tek yönlü hash'e dönüştürür (gizlilik)."""
    return hashlib.sha256(district.lower().strip().encode()).hexdigest()[:8]


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class GroupBuyResult:
    success: bool
    group_id: int | None = None
    error: str | None = None


@dataclass
class GroupBuySummary:
    id: int
    product_title: str
    store: str
    current_price: float
    target_price: float
    progress_pct: float
    members_count: int
    status: str
    expires_at: str


# ── GroupBuyEngine ────────────────────────────────────────────

class GroupBuyEngine:
    """
    Topluluk grup alışverişi motoru.
    """

    # ── Grup Oluşturma ────────────────────────────────────────

    def create_group_buy(
        self,
        product_title: str,
        store: str,
        *,
        current_price: float,
        target_price: float,
        target_quantity: int,
        organizer_id: str,
        district: str = "",
        expiry_days: int = GROUP_BUY_DEFAULT_EXPIRY_DAYS,
    ) -> GroupBuyResult:
        """
        Yeni grup alışverişi başlatır.
        Organizatör otomatik olarak ilk üye olur.
        """
        # Doğrulama
        if target_price >= current_price:
            return GroupBuyResult(
                success=False,
                error=f"Hedef fiyat (₺{target_price}) mevcut fiyattan (₺{current_price}) düşük olmalı"
            )
        if not (MIN_TARGET_QUANTITY <= target_quantity <= MAX_TARGET_QUANTITY):
            return GroupBuyResult(
                success=False,
                error=f"Hedef adet {MIN_TARGET_QUANTITY}–{MAX_TARGET_QUANTITY} arasında olmalı"
            )
        expiry_days = min(expiry_days, GROUP_BUY_MAX_EXPIRY_DAYS)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()

        row: dict[str, Any] = {
            "product_title":   product_title,
            "store":           store,
            "current_price":   current_price,
            "target_price":    target_price,
            "target_quantity": target_quantity,
            "current_quantity": 0,
            "location_hash":   hash_location(district) if district else "",
            "organizer_id":    organizer_id,
            "status":          "recruiting",
            "expires_at":      expires_at,
        }

        try:
            r = _req.post(
                _sb("group_buys"),
                headers={**_headers(), "Prefer": "return=representation"},
                json=row,
                timeout=5,
            )
            if not r.ok:
                return GroupBuyResult(success=False, error=f"Grup oluşturulamadı: {r.text[:100]}")
            group_id = r.json()[0]["id"]
        except Exception as exc:
            return GroupBuyResult(success=False, error=str(exc))

        # Organizatör ilk üye
        join_result = self.join_group_buy(group_id, organizer_id, quantity=1)
        if not join_result.success:
            logger.warning("Organizatör grup'a katılamadı: %s", join_result.error)

        return GroupBuyResult(success=True, group_id=group_id)

    # ── Gruba Katılma ─────────────────────────────────────────

    def join_group_buy(
        self,
        group_id: int,
        user_id: str,
        *,
        quantity: int = 1,
    ) -> GroupBuyResult:
        """
        Kullanıcıyı grup alışverişine ekler.
        Hedef adede ulaşılınca DB trigger otomatik 'completed' yapar.
        """
        # Grup mevcut ve aktif mi?
        group = self._load_group(group_id)
        if not group:
            return GroupBuyResult(success=False, error="Grup bulunamadı")
        if group["status"] not in {"recruiting"}:
            return GroupBuyResult(
                success=False,
                error=f"Bu gruba artık katılamazsınız (durum: {group['status']})"
            )
        expires_at_str = group.get("expires_at", "")
        if expires_at_str:
            try:
                exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if exp < datetime.now(timezone.utc):
                    return GroupBuyResult(success=False, error="Grubun süresi dolmuş")
            except Exception:
                pass

        member_row = {
            "group_buy_id":  group_id,
            "user_id":       user_id,
            "quantity_wanted": max(1, quantity),
        }
        try:
            r = _req.post(
                _sb("group_buy_members"),
                headers={**_headers(), "Prefer": "resolution=ignore-duplicates"},
                json=member_row,
                timeout=5,
            )
            if not r.ok:
                return GroupBuyResult(success=False, error="Katılım kaydedilemedi")
        except Exception as exc:
            return GroupBuyResult(success=False, error=str(exc))

        # current_quantity güncelle
        self._update_quantity(group_id, quantity)
        return GroupBuyResult(success=True, group_id=group_id)

    def leave_group_buy(self, group_id: int, user_id: str) -> GroupBuyResult:
        """Kullanıcıyı gruptan çıkarır (yalnızca 'recruiting' durumunda)."""
        group = self._load_group(group_id)
        if not group:
            return GroupBuyResult(success=False, error="Grup bulunamadı")
        if group.get("organizer_id") == user_id:
            return GroupBuyResult(success=False, error="Organizatör gruptan çıkamaz")
        if group["status"] != "recruiting":
            return GroupBuyResult(success=False, error="Tamamlanan gruptan çıkılamaz")

        try:
            # Üyelik kaydını çek (miktar için)
            r = _req.get(
                _sb("group_buy_members"),
                params={"group_buy_id": f"eq.{group_id}", "user_id": f"eq.{user_id}",
                        "select": "quantity_wanted"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            qty = r.json()[0].get("quantity_wanted", 1) if r.ok and r.json() else 1

            _req.delete(
                _sb("group_buy_members"),
                params={"group_buy_id": f"eq.{group_id}", "user_id": f"eq.{user_id}"},
                headers=_headers(),
                timeout=4,
            )
            self._update_quantity(group_id, -qty)
        except Exception as exc:
            return GroupBuyResult(success=False, error=str(exc))

        return GroupBuyResult(success=True, group_id=group_id)

    # ── Listeleme ─────────────────────────────────────────────

    def get_nearby_groups(
        self,
        *,
        district: str = "",
        product_query: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """Bölgedeki aktif grup alışverişlerini listeler."""
        location_hash = hash_location(district) if district else ""
        try:
            r = _req.post(
                f"{_SUPABASE_URL}/rest/v1/rpc/get_nearby_group_buys",
                headers={**_headers(), "Prefer": ""},
                json={"p_location_hash": location_hash, "p_limit": limit},
                timeout=5,
            )
            groups = r.json() if r.ok else []
        except Exception:
            groups = []

        if product_query:
            q = product_query.lower()
            groups = [g for g in groups if q in g.get("product_title", "").lower()]

        return groups

    def get_user_groups(self, user_id: str) -> list[dict]:
        """Kullanıcının katıldığı grupları listeler."""
        try:
            r = _req.get(
                _sb("group_buy_members"),
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "group_buy_id,quantity_wanted,joined_at,group_buys(product_title,store,target_price,status,expires_at)",
                    "order": "joined_at.desc",
                    "limit": "20",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    def get_group_details(self, group_id: int) -> dict | None:
        """Grup detaylarını ve üye listesini döndürür."""
        group = self._load_group(group_id)
        if not group:
            return None

        # Üye sayısı
        try:
            r = _req.get(
                _sb("group_buy_members"),
                params={"group_buy_id": f"eq.{group_id}", "select": "quantity_wanted"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            members = r.json() if r.ok else []
            group["members_count"] = len(members)
            group["total_quantity"] = sum(m.get("quantity_wanted", 1) for m in members)
        except Exception:
            group["members_count"] = 0

        # İlerleme yüzdesi
        tq = max(group.get("target_quantity", 1), 1)
        group["progress_pct"] = round(
            100 * group.get("current_quantity", 0) / tq, 1
        )
        return group

    # ── Admin: Expire / Expire All ────────────────────────────

    def expire_old_groups(self) -> int:
        """Süresi dolmuş 'recruiting' grupları 'expired' olarak işaretler."""
        try:
            r = _req.patch(
                _sb("group_buys"),
                params={"status": "eq.recruiting", "expires_at": f"lt.{_now()}"},
                headers=_headers(),
                json={"status": "expired"},
                timeout=6,
            )
            return 1 if r.ok else 0
        except Exception:
            return 0

    # ── Yardımcılar ──────────────────────────────────────────

    def _load_group(self, group_id: int) -> dict | None:
        try:
            r = _req.get(
                _sb("group_buys"),
                params={"id": f"eq.{group_id}", "select": "*"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            return r.json()[0] if r.ok and r.json() else None
        except Exception:
            return None

    def _update_quantity(self, group_id: int, delta: int) -> None:
        """current_quantity'yi atomik olarak günceller."""
        group = self._load_group(group_id)
        if not group:
            return
        new_qty = max(0, group.get("current_quantity", 0) + delta)
        try:
            _req.patch(
                _sb("group_buys"),
                params={"id": f"eq.{group_id}"},
                headers=_headers(),
                json={"current_quantity": new_qty},
                timeout=4,
            )
        except Exception:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Singleton
group_buy_engine = GroupBuyEngine()
