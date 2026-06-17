"""
CouponEngine — Sprint 7: Kupon & Puan Dönüşüm Motoru

Akış:
  1. Kullanıcı puan biriktirir (RetentionService.award_points)
  2. Kullanıcı puanını kupona dönüştürür (exchange_points_for_coupon)
  3. Kupon partner'da kullanılır (redeem_coupon)
  4. İsteğe bağlı: partner webhook ile onay bildirim alır

Dönüşüm oranı: POINTS_TO_TL = 0.05  →  100 puan = ₺5

Kupon kodu formatı: "ALMADAN-{partner_prefix}-{6 random char}"
Örnek: "ALMADAN-AURA-XY9Z1K"
"""
from __future__ import annotations

import logging
import os
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# Dönüşüm oranı
POINTS_TO_TL: float = 0.05          # 1 puan = ₺0.05
MIN_EXCHANGE_POINTS: int = 100       # Minimum dönüşüm: 100 puan = ₺5
COUPON_VALIDITY_DAYS: int = 30       # Kuponu kullanım süresi

_ALPHABET = string.ascii_uppercase + string.digits


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class CouponResult:
    success: bool
    code: str | None = None
    discount_amount: float | None = None
    discount_pct: float | None = None
    partner_id: str | None = None
    expires_at: str | None = None
    error: str | None = None


@dataclass
class RedemptionResult:
    success: bool
    discount_applied: float = 0.0
    error: str | None = None


# ── Yardımcılar ───────────────────────────────────────────────

def _gen_code(partner_id: str) -> str:
    """Benzersiz kupon kodu üretir."""
    prefix = (partner_id.upper()[:6]).replace("-", "")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    return f"ALMADAN-{prefix}-{suffix}"


def _get_user_points(user_id: str) -> int:
    try:
        r = _req.get(
            _sb("user_points_summary"),
            params={"user_id": f"eq.{user_id}", "select": "total_points"},
            headers={**_headers(), "Prefer": ""},
            timeout=4,
        )
        return int(r.json()[0]["total_points"]) if r.ok and r.json() else 0
    except Exception:
        return 0


def _deduct_points(user_id: str, points: int, coupon_id: int, exchange_rate: float) -> bool:
    """Puanı negatif kayıt olarak düşür ve point_exchanges'e yaz."""
    deduct_row = {
        "user_id": user_id,
        "points": -points,
        "reason": "coupon_exchange",
    }
    exchange_row = {
        "user_id":       user_id,
        "points_spent":  points,
        "coupon_id":     coupon_id,
        "exchange_rate": exchange_rate,
    }
    try:
        r1 = _req.post(_sb("user_points"), headers=_headers(), json=deduct_row, timeout=4)
        r2 = _req.post(_sb("point_exchanges"), headers=_headers(), json=exchange_row, timeout=4)
        return r1.ok and r2.ok
    except Exception:
        return False


# ── CouponEngine ─────────────────────────────────────────────

class CouponEngine:
    """
    Puan dönüşümü, kupon oluşturma ve kullanım motoru.
    """

    # ── Puan → Kupon Dönüşümü ────────────────────────────────

    def exchange_points_for_coupon(
        self,
        user_id: str,
        points_to_spend: int,
        *,
        partner_id: str = "almadan",
        coupon_type: str = "fixed",
        validity_days: int = COUPON_VALIDITY_DAYS,
    ) -> CouponResult:
        """
        Kullanıcının puanlarını kupona dönüştürür.

        Örnek: 200 puan → ₺10 indirim kuponu
        """
        if points_to_spend < MIN_EXCHANGE_POINTS:
            return CouponResult(
                success=False,
                error=f"Minimum dönüşüm {MIN_EXCHANGE_POINTS} puan "
                      f"(₺{MIN_EXCHANGE_POINTS * POINTS_TO_TL:.2f})"
            )

        # Kullanıcının yeterli puanı var mı?
        balance = _get_user_points(user_id)
        if balance < points_to_spend:
            return CouponResult(
                success=False,
                error=f"Yetersiz puan: {balance} mevcut, {points_to_spend} gerekli"
            )

        discount_amount = round(points_to_spend * POINTS_TO_TL, 2)
        code = _gen_code(partner_id)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat()

        # Kuponu oluştur
        coupon_row: dict[str, Any] = {
            "code":            code,
            "partner_id":      partner_id,
            "coupon_type":     coupon_type,
            "discount_amount": discount_amount,
            "min_spend":       0,
            "max_uses":        1,
            "points_cost":     points_to_spend,
            "expires_at":      expires_at,
            "is_active":       True,
            "metadata":        {"source": "points_exchange", "user_id": user_id},
        }
        try:
            r = _req.post(
                _sb("coupons"),
                headers={**_headers(), "Prefer": "return=representation"},
                json=coupon_row,
                timeout=5,
            )
            if not r.ok:
                return CouponResult(success=False, error="Kupon oluşturulamadı")
            coupon_id = r.json()[0]["id"]
        except Exception as exc:
            return CouponResult(success=False, error=str(exc))

        # Puanı düş
        ok = _deduct_points(user_id, points_to_spend, coupon_id, POINTS_TO_TL)
        if not ok:
            logger.error("Puan düşülemedi — kupon oluşturuldu ama puan kalmadı: %s", code)

        return CouponResult(
            success=True,
            code=code,
            discount_amount=discount_amount,
            partner_id=partner_id,
            expires_at=expires_at,
        )

    # ── Admin: Partner için Kupon Oluştur ─────────────────────

    def create_partner_coupon(
        self,
        partner_id: str,
        *,
        coupon_type: str = "percentage",
        discount_pct: float | None = None,
        discount_amount: float | None = None,
        min_spend: float = 0,
        max_uses: int = 100,
        validity_days: int = 30,
        metadata: dict | None = None,
    ) -> CouponResult:
        """Admin veya partner API üzerinden toplu kupon oluşturur."""
        if coupon_type == "percentage" and not discount_pct:
            return CouponResult(success=False, error="Yüzde indirim için discount_pct gerekli")
        if coupon_type == "fixed" and not discount_amount:
            return CouponResult(success=False, error="Sabit indirim için discount_amount gerekli")

        code = _gen_code(partner_id)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat()
        row: dict[str, Any] = {
            "code":            code,
            "partner_id":      partner_id,
            "coupon_type":     coupon_type,
            "discount_pct":    discount_pct,
            "discount_amount": discount_amount,
            "min_spend":       min_spend,
            "max_uses":        max_uses,
            "expires_at":      expires_at,
            "is_active":       True,
            "metadata":        metadata or {},
        }
        try:
            r = _req.post(
                _sb("coupons"),
                headers={**_headers(), "Prefer": "return=representation"},
                json=row,
                timeout=5,
            )
            return CouponResult(
                success=r.ok,
                code=code,
                discount_pct=discount_pct,
                discount_amount=discount_amount,
                partner_id=partner_id,
                expires_at=expires_at,
                error=None if r.ok else r.text[:200],
            )
        except Exception as exc:
            return CouponResult(success=False, error=str(exc))

    # ── Kupon Kullanımı ───────────────────────────────────────

    def validate_coupon(self, code: str, *, user_id: str, order_total: float) -> CouponResult:
        """
        Kuponu doğrular — kullanmaz, yalnızca kontrol eder.
        Ön ödeme sayfasında indirim hesaplamak için kullanılır.
        """
        coupon = self._load_coupon(code)
        if not coupon:
            return CouponResult(success=False, error="Kupon bulunamadı veya geçersiz")

        error = self._check_coupon_usability(coupon, user_id, order_total)
        if error:
            return CouponResult(success=False, error=error)

        discount = self._calc_discount(coupon, order_total)
        return CouponResult(
            success=True,
            code=code,
            discount_amount=discount,
            discount_pct=coupon.get("discount_pct"),
            partner_id=coupon.get("partner_id"),
        )

    def redeem_coupon(
        self,
        code: str,
        *,
        user_id: str,
        order_total: float,
    ) -> RedemptionResult:
        """
        Kuponu kullanır (geri alınamaz).
        Başarılıysa coupon_redemptions'a kaydeder ve uses_count'u artırır.
        """
        coupon = self._load_coupon(code)
        if not coupon:
            return RedemptionResult(success=False, error="Kupon bulunamadı")

        error = self._check_coupon_usability(coupon, user_id, order_total)
        if error:
            return RedemptionResult(success=False, error=error)

        discount = self._calc_discount(coupon, order_total)
        coupon_id = coupon["id"]

        # Kullanım kaydı (UNIQUE → aynı user+coupon ikinci kez giremez)
        redemption_row = {
            "coupon_id":       coupon_id,
            "user_id":         user_id,
            "order_total":     order_total,
            "discount_applied": discount,
        }
        try:
            r = _req.post(_sb("coupon_redemptions"), headers=_headers(),
                          json=redemption_row, timeout=5)
            if not r.ok:
                return RedemptionResult(success=False, error="Kullanım kaydedilemedi")
        except Exception as exc:
            return RedemptionResult(success=False, error=str(exc))

        # Kullanım sayacını artır
        try:
            _req.patch(
                _sb("coupons"),
                params={"id": f"eq.{coupon_id}"},
                headers=_headers(),
                json={"uses_count": coupon["uses_count"] + 1},
                timeout=4,
            )
        except Exception:
            pass

        return RedemptionResult(success=True, discount_applied=discount)

    def get_user_coupons(self, user_id: str) -> list[dict]:
        """Kullanıcının kullanabileceği tüm aktif kuponları listeler."""
        try:
            r = _req.post(
                f"{_SUPABASE_URL}/rest/v1/rpc/get_user_coupons",
                headers={**_headers(), "Prefer": ""},
                json={"p_user_id": user_id},
                timeout=5,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    # ── Yardımcılar ──────────────────────────────────────────

    def _load_coupon(self, code: str) -> dict | None:
        try:
            r = _req.get(
                _sb("coupons"),
                params={"code": f"eq.{code}", "select": "*"},
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            return r.json()[0] if r.ok and r.json() else None
        except Exception:
            return None

    def _check_coupon_usability(
        self, coupon: dict, user_id: str, order_total: float
    ) -> str | None:
        """None döndürürse kullanılabilir demektir."""
        if not coupon.get("is_active"):
            return "Kupon aktif değil"

        expires_at = coupon.get("expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp < datetime.now(timezone.utc):
                    return "Kuponun süresi dolmuş"
            except Exception:
                pass

        if coupon.get("uses_count", 0) >= coupon.get("max_uses", 1):
            return "Kupon kullanım limiti doldu"

        min_spend = float(coupon.get("min_spend") or 0)
        if order_total < min_spend:
            return f"Minimum harcama ₺{min_spend:.2f} (sipariş: ₺{order_total:.2f})"

        # Aynı kullanıcı daha önce kullandı mı?
        try:
            r = _req.get(
                _sb("coupon_redemptions"),
                params={"coupon_id": f"eq.{coupon['id']}", "user_id": f"eq.{user_id}",
                        "select": "id", "limit": "1"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if r.ok and r.json():
                return "Bu kuponu zaten kullandınız"
        except Exception:
            pass

        return None

    @staticmethod
    def _calc_discount(coupon: dict, order_total: float) -> float:
        ctype = coupon.get("coupon_type", "fixed")
        if ctype == "percentage":
            pct = float(coupon.get("discount_pct") or 0)
            return round(order_total * pct / 100, 2)
        return round(float(coupon.get("discount_amount") or 0), 2)


# Singleton
coupon_engine = CouponEngine()
