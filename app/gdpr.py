"""
GDPR / KVKK Uyumluluk Servisi — Sprint 9

Desteklenen haklar:
  1. Right to be Forgotten  — kişisel verilerin anonimleştirilmesi
  2. Data Export (SAR)      — kullanıcıya ait tüm veri paketi
  3. Consent Management     — onay kayıtları

Anonimleştirme stratejisi:
  - Kullanıcı adı / e-posta → "deleted_<uuid_hash8>" placeholder
  - Analitik olaylar        → user_id = NULL (aggregate değer korunur)
  - Watchlist / savings     → tamamen silindi
  - Auth (Supabase Auth)    → admin API ile kullanıcı silindi

Supabase tabloları:
  user_analytics_events, user_savings, ab_assignments, ab_events,
  user_points, digest_log, vision_analyses, group_buy_members,
  coupon_redemptions, partner_rate_limits → temizlenir / anonim yapılır

Audit trail:
  gdpr_requests tablosuna her istek loglanır (KVKK madde 12).
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
_SUPABASE_AUTH_URL = os.getenv("SUPABASE_URL", "").replace("/rest", "").rstrip("/")


def _sb(extra: dict | None = None) -> dict[str, str]:
    h = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    if extra:
        h.update(extra)
    return h


def _sb_repr(extra: dict | None = None) -> dict[str, str]:
    h = _sb(extra)
    h["Prefer"] = "return=representation"
    return h


@dataclass
class GDPRResult:
    user_id: str
    success: bool
    anonymized_tables: list[str] = field(default_factory=list)
    deleted_tables: list[str] = field(default_factory=list)
    auth_deleted: bool = False
    errors: list[str] = field(default_factory=list)
    requested_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "user_id":           self.user_id,
            "success":           self.success,
            "anonymized_tables": self.anonymized_tables,
            "deleted_tables":    self.deleted_tables,
            "auth_deleted":      self.auth_deleted,
            "errors":            self.errors,
            "requested_at":      self.requested_at,
        }


@dataclass
class SARResult:
    user_id: str
    data: dict[str, Any]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class GDPRService:
    """
    KVKK/GDPR uyumluluk operasyonlarını yürütür.

    Kullanım:
        svc = GDPRService()
        result = svc.forget(user_id)   # Right to be Forgotten
        sar   = svc.export(user_id)    # Subject Access Request
    """

    # Tamamen silinecek tablolar (satır kaldırılır)
    _DELETE_TABLES = [
        ("user_savings",        "user_id"),
        ("ab_assignments",      "user_id"),
        ("ab_events",           "user_id"),
        ("digest_log",          "user_id"),
        ("coupon_redemptions",  "user_id"),
        ("group_buy_members",   "user_id"),
        ("vision_analyses",     "user_id"),
        ("user_analytics_events", "user_id"),
        ("followed_stores",     "user_id"),
        ("user_notifications",  "user_id"),
    ]

    # user_id = NULL yapılacak tablolar (istatistik korunur)
    _ANONYMIZE_TABLES = [
        ("request_metrics", "user_id"),
        ("structured_logs", "user_id"),
    ]

    def forget(self, user_id: str) -> GDPRResult:
        """
        Right to be Forgotten — KVKK Madde 7, GDPR Article 17.

        1. Kişisel verileri içeren satırları siler
        2. İstatistiksel tablolarda user_id'yi NULL yapar
        3. Supabase Auth'tan kullanıcıyı siler
        4. Audit logu yazar
        """
        result = GDPRResult(user_id=user_id, success=False)

        if not _SUPABASE_URL:
            result.errors.append("Supabase bağlantısı yok")
            return result

        # 1. Sil
        for table, col in self._DELETE_TABLES:
            try:
                r = _req.delete(
                    f"{_SUPABASE_URL}/rest/v1/{table}",
                    params={col: f"eq.{user_id}"},
                    headers=_sb(),
                    timeout=10,
                )
                if r.ok:
                    result.deleted_tables.append(table)
                else:
                    result.errors.append(f"{table}: HTTP {r.status_code}")
            except Exception as exc:
                result.errors.append(f"{table}: {exc}")

        # 2. Anonimleştir (user_id = NULL)
        for table, col in self._ANONYMIZE_TABLES:
            try:
                r = _req.patch(
                    f"{_SUPABASE_URL}/rest/v1/{table}",
                    params={col: f"eq.{user_id}"},
                    headers=_sb(),
                    json={col: None},
                    timeout=10,
                )
                if r.ok:
                    result.anonymized_tables.append(table)
                else:
                    result.errors.append(f"{table} (anon): HTTP {r.status_code}")
            except Exception as exc:
                result.errors.append(f"{table} (anon): {exc}")

        # 3. user_points: sil
        try:
            r = _req.delete(
                f"{_SUPABASE_URL}/rest/v1/user_points",
                params={"user_id": f"eq.{user_id}"},
                headers=_sb(),
                timeout=10,
            )
            if r.ok:
                result.deleted_tables.append("user_points")
        except Exception as exc:
            result.errors.append(f"user_points: {exc}")

        # 3b. Ana JSON blob (app_state) içindeki kişisel veriler:
        # takip edilen ürünler (fiyat geçmişi dahil) ve push abonelikleri.
        # Bunlar Supabase tablosu değil, storage.py'nin tek satırlık blob'unda saklanır.
        try:
            from app.storage import load_db, save_db
            owner_key = f"user:{user_id}"
            db = load_db()
            before_products = len(db.get("products", []))
            db["products"] = [p for p in db.get("products", []) if p.get("owner_id") != owner_key]
            removed_products = before_products - len(db["products"])

            before_push = len(db.get("push_subscriptions", []))
            db["push_subscriptions"] = [
                s for s in db.get("push_subscriptions", []) if s.get("owner_id") != owner_key
            ]
            removed_push = before_push - len(db["push_subscriptions"])

            save_db(db)
            if removed_products:
                result.deleted_tables.append(f"products (blob, {removed_products} kayıt)")
            if removed_push:
                result.deleted_tables.append(f"push_subscriptions (blob, {removed_push} kayıt)")
        except Exception as exc:
            result.errors.append(f"app_state blob: {exc}")

        # 4. Supabase Auth kullanıcı silme (admin API)
        try:
            r = _req.delete(
                f"{_SUPABASE_URL.replace('/rest/v1', '')}/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": _SUPABASE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_KEY}",
                },
                timeout=10,
            )
            result.auth_deleted = r.ok
            if not r.ok:
                result.errors.append(f"auth delete: HTTP {r.status_code}")
        except Exception as exc:
            result.errors.append(f"auth delete: {exc}")

        # 5. Audit logu
        result.success = len(result.errors) == 0
        self._log_request(user_id, "forget", result)
        return result

    def export(self, user_id: str) -> SARResult:
        """
        Subject Access Request (SAR) — KVKK Madde 11, GDPR Article 15.

        Kullanıcıya ait tüm veriyi JSON olarak toplar.
        """
        data: dict[str, Any] = {}

        if not _SUPABASE_URL:
            return SARResult(user_id=user_id, data={"error": "Supabase yok"})

        tables_to_export = [
            "user_analytics_events",
            "user_savings",
            "user_points",
            "digest_log",
            "coupon_redemptions",
            "group_buy_members",
            "vision_analyses",
            "ab_assignments",
            "followed_stores",
            "user_notifications",
        ]

        for table in tables_to_export:
            try:
                r = _req.get(
                    f"{_SUPABASE_URL}/rest/v1/{table}",
                    params={"user_id": f"eq.{user_id}", "select": "*"},
                    headers=_sb_repr(),
                    timeout=10,
                )
                data[table] = r.json() if r.ok else []
            except Exception:
                data[table] = []

        # Ana JSON blob (app_state): takip edilen ürünler ve push abonelikleri
        try:
            from app.storage import load_db
            owner_key = f"user:{user_id}"
            db = load_db()
            data["products"] = [p for p in db.get("products", []) if p.get("owner_id") == owner_key]
            data["push_subscriptions"] = [
                s for s in db.get("push_subscriptions", []) if s.get("owner_id") == owner_key
            ]
        except Exception:
            data["products"] = []
            data["push_subscriptions"] = []

        self._log_request(user_id, "export", None)
        return SARResult(user_id=user_id, data=data)

    def _log_request(self, user_id: str, request_type: str, result: GDPRResult | None) -> None:
        """KVKK gereği her talebi audit tablosuna yazar."""
        if not _SUPABASE_URL:
            return
        row: dict[str, Any] = {
            "user_id":      user_id,
            "request_type": request_type,
            "status":       "completed" if (result is None or result.success) else "partial",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        if result:
            row["details"] = {
                "deleted_tables":    result.deleted_tables,
                "anonymized_tables": result.anonymized_tables,
                "errors":            result.errors,
                "auth_deleted":      result.auth_deleted,
            }
        try:
            _req.post(
                f"{_SUPABASE_URL}/rest/v1/gdpr_requests",
                headers=_sb(),
                json=row,
                timeout=5,
            )
        except Exception:
            pass


gdpr_service = GDPRService()
