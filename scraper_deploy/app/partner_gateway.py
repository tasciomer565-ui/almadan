"""
PartnerGateway — Sprint 7: Partner API Gateway

Sorumluluklar:
  1. API key yönetimi (oluştur, doğrula, iptal et)
  2. Rate limiting — sliding window (Redis yerine Supabase)
  3. Scope kontrolü — her partner hangi veriyi okuyabilir/yazabilir?
  4. Signed webhook — partner'a HMAC-SHA256 imzalı olay gönder
  5. Webhook delivery log + yeniden deneme

Mimari:
  - API key: "pk_live_<32 random hex>" formatında
  - DB'de yalnızca SHA-256 hash'i saklanır (düz key asla)
  - Rate limit: sliding 60s pencere, Supabase'e sayaç yaz
  - Scopes: read:prices, read:coupons, write:orders, write:group_buy

Güvenlik:
  - Webhook imzası: HMAC-SHA256(payload_json, webhook_secret)
  - Signature header: "X-Almadan-Signature: sha256=<hex>"
  - Timestamp penceresi: 5 dakikadan eski webhook'lar reddedilir
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# Geçerli scope'lar ve açıklamaları
VALID_SCOPES = {
    "read:prices":      "Ürün fiyatlarını okuma",
    "read:coupons":     "Kuponları okuma",
    "read:group_buys":  "Grup alışverişleri okuma",
    "write:orders":     "Sipariş oluşturma",
    "write:coupons":    "Kupon oluşturma",
    "write:group_buy":  "Grup alışverişine üye ekleme",
    "read:eco_scores":  "Eko-skorları okuma",
}

_KEY_PREFIX_LEN = 12   # "pk_live_abc1" → ilk 12 karakter gösterilir


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
class PartnerKey:
    partner_id: str
    display_name: str
    scopes: list[str]
    rate_limit_rpm: int
    webhook_url: str | None
    is_active: bool

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass
class GatewayRequest:
    partner_id: str
    api_key: str    # Ham key — yalnızca doğrulama için kullanılır
    scope: str
    path: str
    payload: dict | None = None


# ── API Key Yönetimi ──────────────────────────────────────────

def generate_api_key() -> tuple[str, str]:
    """
    Yeni API key üretir.
    Döndürür: (raw_key, key_hash)
      raw_key  → partner'a bir kez gösterilir, tekrar gösterilmez
      key_hash → DB'ye kaydedilir
    """
    raw = "pk_live_" + secrets.token_hex(24)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, key_hash


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_partner(
    partner_id: str,
    display_name: str,
    scopes: list[str],
    *,
    rate_limit_rpm: int = 60,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> dict:
    """
    Yeni partner oluşturur ve API key döndürür.
    Uyarı: raw_key yalnızca bu çağrıda görünür, sonra alınamaz.
    """
    # Scope doğrulama
    invalid = [s for s in scopes if s not in VALID_SCOPES]
    if invalid:
        raise ValueError(f"Geçersiz scope'lar: {invalid}")

    raw_key, key_hash = generate_api_key()
    prefix = raw_key[:_KEY_PREFIX_LEN]

    row = {
        "partner_id":     partner_id,
        "display_name":   display_name,
        "key_hash":       key_hash,
        "key_prefix":     prefix,
        "scopes":         scopes,
        "rate_limit_rpm": rate_limit_rpm,
        "webhook_url":    webhook_url,
        "webhook_secret": webhook_secret,
        "is_active":      True,
    }
    try:
        r = _req.post(_sb("partner_api_keys"), headers=_headers(), json=row, timeout=5)
        r.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Partner oluşturulamadı: {exc}") from exc

    return {
        "partner_id":   partner_id,
        "display_name": display_name,
        "api_key":      raw_key,      # TEK SEFERLIK — kaydet!
        "key_prefix":   prefix,
        "scopes":       scopes,
        "warning":      "Bu API key bir daha gösterilmeyecek. Hemen kaydedin!",
    }


def rotate_key(partner_id: str) -> dict:
    """Partner için yeni API key üretir (eskisi geçersiz olur)."""
    raw_key, key_hash = generate_api_key()
    prefix = raw_key[:_KEY_PREFIX_LEN]
    try:
        r = _req.patch(
            _sb("partner_api_keys"),
            params={"partner_id": f"eq.{partner_id}"},
            headers=_headers(),
            json={"key_hash": key_hash, "key_prefix": prefix},
            timeout=5,
        )
        r.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Key rotate hatası: {exc}") from exc
    return {"partner_id": partner_id, "api_key": raw_key, "key_prefix": prefix}


# ── Doğrulama & Rate Limiting ─────────────────────────────────

class PartnerGateway:
    """
    Partner API isteklerini doğrular ve rate limit uygular.
    """

    def authenticate(self, raw_key: str, required_scope: str) -> PartnerKey:
        """
        API key'i doğrular ve scope kontrolü yapar.
        Başarısızsa PermissionError fırlatır.
        """
        if not raw_key or not raw_key.startswith("pk_live_"):
            raise PermissionError("Geçersiz API key formatı")

        key_hash = hash_key(raw_key)
        partner = self._load_partner(key_hash)

        if partner is None:
            raise PermissionError("API key bulunamadı")
        if not partner.is_active:
            raise PermissionError("Partner hesabı devre dışı")
        if not partner.has_scope(required_scope):
            raise PermissionError(
                f"Yetersiz yetki: '{required_scope}' scope'u gerekli. "
                f"Mevcut: {partner.scopes}"
            )

        # Rate limit kontrolü
        if not self._check_rate_limit(partner.partner_id, partner.rate_limit_rpm):
            raise PermissionError(
                f"Rate limit aşıldı: {partner.rate_limit_rpm} istek/dakika. "
                f"Lütfen bekleyin."
            )

        # last_used_at güncelle (fire and forget)
        self._touch(partner.partner_id)
        return partner

    def _load_partner(self, key_hash: str) -> PartnerKey | None:
        try:
            r = _req.get(
                _sb("partner_api_keys"),
                params={
                    "key_hash": f"eq.{key_hash}",
                    "select": "partner_id,display_name,scopes,rate_limit_rpm,webhook_url,is_active",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if not r.ok or not r.json():
                return None
            row = r.json()[0]
            return PartnerKey(
                partner_id=row["partner_id"],
                display_name=row["display_name"],
                scopes=row.get("scopes") or [],
                rate_limit_rpm=row.get("rate_limit_rpm", 60),
                webhook_url=row.get("webhook_url"),
                is_active=row.get("is_active", True),
            )
        except Exception:
            return None

    def _check_rate_limit(self, partner_id: str, limit_rpm: int) -> bool:
        """
        Sliding window rate limiting (Supabase tabanlı).
        Pencere: şu anki dakika (UTC).
        """
        now = datetime.now(timezone.utc)
        window = now.replace(second=0, microsecond=0).isoformat()
        try:
            # Upsert: pencere yoksa oluştur, varsa artır
            r = _req.post(
                _sb("partner_rate_limits"),
                headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
                json={
                    "partner_id":    partner_id,
                    "window_start":  window,
                    "request_count": 1,
                },
                timeout=4,
            )
            if r.ok:
                rows = r.json()
                current_count = rows[0].get("request_count", 1) if rows else 1
                if current_count > limit_rpm:
                    return False

            # Sayacı artır (merge-duplicates COUNT ile artırmaz, ayrı PATCH gerekli)
            _req.patch(
                _sb("partner_rate_limits"),
                params={"partner_id": f"eq.{partner_id}", "window_start": f"eq.{window}"},
                headers=_headers(),
                json={"request_count": _get_count(partner_id, window) + 1},
                timeout=3,
            )
        except Exception:
            return True   # DB hatasında geç (availability > security)
        return True

    def _touch(self, partner_id: str) -> None:
        try:
            _req.patch(
                _sb("partner_api_keys"),
                params={"partner_id": f"eq.{partner_id}"},
                headers=_headers(),
                json={"last_used_at": datetime.now(timezone.utc).isoformat()},
                timeout=3,
            )
        except Exception:
            pass


def _get_count(partner_id: str, window: str) -> int:
    try:
        r = _req.get(
            _sb("partner_rate_limits"),
            params={"partner_id": f"eq.{partner_id}", "window_start": f"eq.{window}",
                    "select": "request_count"},
            headers={**_headers(), "Prefer": ""},
            timeout=3,
        )
        return r.json()[0]["request_count"] if r.ok and r.json() else 0
    except Exception:
        return 0


# ── Signed Webhook ────────────────────────────────────────────

class WebhookSender:
    """
    Partner'a HMAC-SHA256 imzalı webhook gönderir.

    Signature: HMAC-SHA256(timestamp + "." + payload_json, secret)
    Header:    X-Almadan-Signature: sha256=<hex>
               X-Almadan-Timestamp: <unix_timestamp>
    """

    MAX_ATTEMPTS = 3
    RETRY_DELAYS = [2, 10, 60]   # saniye

    def send(
        self,
        partner_id: str,
        event_type: str,
        payload: dict,
        *,
        webhook_url: str,
        webhook_secret: str,
    ) -> bool:
        """Webhook gönderir. Başarısız olursa yeniden dener."""
        ts = str(int(time.time()))
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        signature = self._sign(ts, payload_json, webhook_secret)

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Almadan-Signature": f"sha256={signature}",
            "X-Almadan-Timestamp": ts,
            "X-Almadan-Event":     event_type,
            "User-Agent":          "Almadan-Webhook/1.0",
        }

        delivered = False
        status_code = 0
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                r = _req.post(
                    webhook_url,
                    data=payload_json.encode("utf-8"),
                    headers=headers,
                    timeout=10,
                )
                status_code = r.status_code
                if r.status_code < 400:
                    delivered = True
                    break
                logger.warning(
                    "Webhook attempt %d failed (HTTP %d): %s",
                    attempt + 1, r.status_code, r.text[:100]
                )
            except Exception as exc:
                logger.warning("Webhook attempt %d error: %s", attempt + 1, exc)

            if attempt < self.MAX_ATTEMPTS - 1:
                time.sleep(self.RETRY_DELAYS[attempt])

        self._log(partner_id, event_type, payload_json, status_code,
                  self.MAX_ATTEMPTS, delivered)
        return delivered

    @staticmethod
    def verify_signature(
        payload_body: bytes,
        signature_header: str,
        timestamp_header: str,
        secret: str,
        *,
        max_age_seconds: int = 300,
    ) -> bool:
        """
        Gelen webhook'un imzasını doğrular.
        Almadan'ın gelen Replicate/partner webhook'larını doğrulamak için kullanılır.
        """
        try:
            # Timestamp penceresi (tekrar saldırısı önleme)
            ts = int(timestamp_header)
            age = abs(time.time() - ts)
            if age > max_age_seconds:
                return False

            expected = WebhookSender._sign(
                timestamp_header,
                payload_body.decode("utf-8"),
                secret,
            )
            provided = signature_header.removeprefix("sha256=")
            return hmac.compare_digest(expected, provided)
        except Exception:
            return False

    @staticmethod
    def _sign(timestamp: str, payload: str, secret: str) -> str:
        msg = f"{timestamp}.{payload}".encode("utf-8")
        return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    def _log(
        self,
        partner_id: str,
        event_type: str,
        payload_json: str,
        status_code: int,
        attempts: int,
        delivered: bool,
    ) -> None:
        row = {
            "partner_id":   partner_id,
            "event_type":   event_type,
            "payload_hash": hashlib.sha256(payload_json.encode()).hexdigest()[:16],
            "status_code":  status_code,
            "attempts":     attempts,
            "delivered_at": datetime.now(timezone.utc).isoformat() if delivered else None,
        }
        try:
            _req.post(_sb("partner_webhook_log"), headers=_headers(), json=row, timeout=3)
        except Exception:
            pass


# Singletons
partner_gateway = PartnerGateway()
webhook_sender  = WebhookSender()
