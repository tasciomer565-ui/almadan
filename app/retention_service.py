"""
RetentionService — Sprint 5: Kullanıcı Tutundurma

Sorumluluklar:
  1. Haftalık tasarruf özeti e-posta / push bildirimi
  2. Gamification: puan kazanma ve harcama
  3. Otomatik digest cron tetikleyicisi

Cron: Her Pazartesi 07:00 UTC → /cron/weekly-digest
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# SMTP ayarları (Vercel env vars)
_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@almadan.app")
_APP_URL    = os.getenv("ALMADAN_APP_URL", "https://almadan.vercel.app").rstrip("/")


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
class DigestPayload:
    user_id: str
    email: str
    display_name: str
    total_saved_week: float
    top_deals: list[dict]
    points_balance: int
    streak_days: int
    watchlist_count: int

    def is_worth_sending(self) -> bool:
        """Boş digest gönderme — en az 1 indirim veya 10 puan kazanılmış olmalı."""
        return bool(self.top_deals or self.points_balance >= 10)


# ── Puan Sistemi ──────────────────────────────────────────────

# Puan kazanma sebeplerine göre puanlar
POINT_RULES: dict[str, int] = {
    "weekly_login":       5,
    "first_save":         50,
    "save_recorded":      10,   # Her tasarruf kaydı
    "share_deal":         20,
    "write_review":       30,
    "invite_friend":      100,
    "streak_7days":       25,
    "streak_30days":      100,
    "app_open":           1,    # Her gün bir kez sayılır
}


def award_points(
    user_id: str,
    reason: str,
    *,
    custom_amount: int | None = None,
    expires_days: int | None = None,
) -> int:
    """
    Kullanıcıya puan verir.
    Döndürür: verilen puan miktarı (0 = hata veya tekrar engeli)
    """
    amount = custom_amount or POINT_RULES.get(reason, 0)
    if amount == 0:
        return 0

    # Günlük tekrar engeli (app_open, weekly_login)
    if reason in {"app_open", "weekly_login"} and _already_rewarded_today(user_id, reason):
        return 0

    row: dict[str, Any] = {
        "user_id": user_id,
        "points": amount,
        "reason": reason,
    }
    if expires_days:
        expiry = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
        row["expires_at"] = expiry

    try:
        r = _req.post(_sb("user_points"), headers=_headers(), json=row, timeout=4)
        return amount if r.ok else 0
    except Exception as exc:
        logger.debug("award_points failed: %s", exc)
        return 0


def get_user_points(user_id: str) -> int:
    """Kullanıcının toplam aktif puanını döndürür."""
    try:
        r = _req.get(
            _sb("user_points_summary"),
            params={"user_id": f"eq.{user_id}", "select": "total_points"},
            headers={**_headers(), "Prefer": ""},
            timeout=4,
        )
        if r.ok and r.json():
            return int(r.json()[0].get("total_points", 0))
    except Exception:
        pass
    return 0


def _already_rewarded_today(user_id: str, reason: str) -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        r = _req.get(
            _sb("user_points"),
            params={
                "user_id": f"eq.{user_id}",
                "reason": f"eq.{reason}",
                "created_at": f"gte.{today}T00:00:00Z",
                "select": "id",
                "limit": "1",
            },
            headers={**_headers(), "Prefer": ""},
            timeout=4,
        )
        return r.ok and bool(r.json())
    except Exception:
        return False


# ── RetentionService ──────────────────────────────────────────

class RetentionService:
    """
    Kullanıcı tutundurma: haftalık digest, push bildirimi, puan yönetimi.
    """

    def run_weekly_digest(self, *, dry_run: bool = False) -> dict[str, int]:
        """
        Tüm aktif kullanıcılar için haftalık özet gönderir.
        Vercel Cron: Her Pazartesi 07:00 UTC → /cron/weekly-digest
        """
        sent = skipped = failed = 0

        users = self._get_active_users()
        logger.info("Weekly digest: %d kullanıcı hedefleniyor", len(users))

        for user in users:
            try:
                payload = self._build_digest(user)
                if not payload.is_worth_sending():
                    skipped += 1
                    continue

                if dry_run:
                    sent += 1
                    continue

                ok = self._send_digest(payload)
                if ok:
                    sent += 1
                    self._log_digest(payload.user_id, "sent")
                    # Haftalık giriş puanı
                    award_points(payload.user_id, "weekly_login")
                else:
                    failed += 1
                    self._log_digest(payload.user_id, "failed")
            except Exception as exc:
                logger.warning("Digest failed for %s: %s", user.get("id"), exc)
                failed += 1

        return {"sent": sent, "skipped": skipped, "failed": failed}

    def send_single_digest(self, user_id: str) -> bool:
        """Tekil kullanıcıya anında digest gönder (test/manuel)."""
        users = self._get_active_users(filter_user_id=user_id)
        if not users:
            return False
        payload = self._build_digest(users[0])
        if not payload.is_worth_sending():
            return False
        ok = self._send_digest(payload)
        if ok:
            self._log_digest(user_id, "sent")
        return ok

    # ── Digest oluşturma ─────────────────────────────────────

    def _build_digest(self, user_row: dict) -> DigestPayload:
        user_id = user_row["id"]
        email = user_row.get("email", "")
        meta = user_row.get("raw_user_meta_data") or {}
        display_name = meta.get("full_name") or meta.get("name") or email.split("@")[0]

        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        # Bu haftanın tasarrufları
        top_deals: list[dict] = []
        total_saved_week = 0.0
        try:
            r = _req.get(
                _sb("user_savings"),
                params={
                    "user_id": f"eq.{user_id}",
                    "recorded_at": f"gte.{week_ago}",
                    "saved_amount": "gt.0",
                    "select": "product_title,store,price,saved_amount,saved_pct",
                    "order": "saved_amount.desc",
                    "limit": "5",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if r.ok:
                top_deals = r.json()
                total_saved_week = sum(float(d.get("saved_amount", 0)) for d in top_deals)
        except Exception:
            pass

        # Watchlist sayısı
        watchlist_count = 0
        try:
            r = _req.get(
                _sb("products"),
                params={"owner_id": f"eq.{user_id}", "select": "id"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if r.ok:
                watchlist_count = len(r.json())
        except Exception:
            pass

        # Puan ve seri
        points = get_user_points(user_id)
        streak = self._get_streak(user_id)

        return DigestPayload(
            user_id=user_id,
            email=email,
            display_name=display_name,
            total_saved_week=total_saved_week,
            top_deals=top_deals,
            points_balance=points,
            streak_days=streak,
            watchlist_count=watchlist_count,
        )

    # ── Gönderim ─────────────────────────────────────────────

    def _send_digest(self, payload: DigestPayload) -> bool:
        """E-posta VE push bildirimi gönderir (mevcut her kanal)."""
        results = []

        # 1. E-posta (SMTP varsa)
        if _SMTP_USER and _SMTP_PASS and payload.email:
            results.append(self._send_email(payload))

        # 2. Push bildirimi
        results.append(self._send_push_digest(payload))

        return any(results)

    def _send_email(self, payload: DigestPayload) -> bool:
        import smtplib, ssl

        subject = f"Bu Hafta ₺{payload.total_saved_week:.2f} Tasarruf Ettin! 🎉"
        html = self._render_email_html(payload)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = _FROM_EMAIL
        msg["To"]      = payload.email
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.login(_SMTP_USER, _SMTP_PASS)
                s.sendmail(_FROM_EMAIL, payload.email, msg.as_bytes())
            return True
        except Exception as exc:
            logger.warning("Email send failed for %s: %s", payload.email, exc)
            return False

    def _send_push_digest(self, payload: DigestPayload) -> bool:
        """Kullanıcının kayıtlı push subscription'larına digest gönderir."""
        push_payload = {
            "title": f"Almadan Haftalık Özet 🛒",
            "body": (
                f"Bu hafta ₺{payload.total_saved_week:.2f} tasarruf ettin! "
                f"{len(payload.top_deals)} indirim bulundu."
            ),
            "icon": "/static/icon-192.png",
            "tag": f"weekly-digest-{payload.user_id[:8]}",
            "data": {"url": f"{_APP_URL}/?tab=savings"},
        }
        try:
            from app.push import send_push
            subs = self._get_push_subscriptions(payload.user_id)
            sent = False
            for sub in subs:
                try:
                    send_push(sub, push_payload)
                    sent = True
                except Exception:
                    pass
            return sent
        except Exception:
            return False

    def _render_email_html(self, p: DigestPayload) -> str:
        deals_html = ""
        for d in p.top_deals:
            name  = d.get("product_title", "")
            store = d.get("store", "").capitalize()
            price = d.get("price", 0)
            saved = d.get("saved_amount", 0)
            pct   = d.get("saved_pct", "")
            deals_html += (
                f"<tr>"
                f"<td style='padding:8px'>{name}</td>"
                f"<td style='padding:8px'>{store}</td>"
                f"<td style='padding:8px;color:#e63946'>₺{price:.2f}</td>"
                f"<td style='padding:8px;color:#2a9d8f'>₺{saved:.2f} ({pct}%)</td>"
                f"</tr>"
            )

        return f"""<!DOCTYPE html>
<html lang="tr">
<head><meta charset="utf-8"><title>Almadan Haftalık Özet</title></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden">
    <div style="background:#e63946;color:#fff;padding:24px;text-align:center">
      <h1 style="margin:0">🛒 Almadan Haftalık Özet</h1>
      <p style="margin:8px 0 0">Merhaba, {p.display_name}!</p>
    </div>
    <div style="padding:24px">
      <div style="display:flex;gap:16px;margin-bottom:24px;text-align:center">
        <div style="flex:1;background:#f0f9f0;border-radius:8px;padding:16px">
          <div style="font-size:28px;font-weight:bold;color:#2a9d8f">₺{p.total_saved_week:.2f}</div>
          <div style="color:#666;font-size:14px">Bu Hafta Tasarruf</div>
        </div>
        <div style="flex:1;background:#fff9e6;border-radius:8px;padding:16px">
          <div style="font-size:28px;font-weight:bold;color:#e9c46a">{p.points_balance}</div>
          <div style="color:#666;font-size:14px">Almadan Puanı</div>
        </div>
        <div style="flex:1;background:#e8f4fd;border-radius:8px;padding:16px">
          <div style="font-size:28px;font-weight:bold;color:#457b9d">{p.streak_days}</div>
          <div style="color:#666;font-size:14px">Gün Serisi 🔥</div>
        </div>
      </div>
      {"<h2>Bu Haftanın En İyi İndirimleri</h2><table width='100%' style='border-collapse:collapse'><tr style='background:#f5f5f5'><th style='padding:8px;text-align:left'>Ürün</th><th style='padding:8px;text-align:left'>Market</th><th style='padding:8px;text-align:left'>Fiyat</th><th style='padding:8px;text-align:left'>Tasarruf</th></tr>" + deals_html + "</table>" if p.top_deals else "<p style='color:#666'>Bu hafta henüz eşleşen indirim yok. Watchlist'ine ürün ekle!</p>"}
      <div style="text-align:center;margin-top:24px">
        <a href="{_APP_URL}" style="background:#e63946;color:#fff;padding:12px 32px;border-radius:24px;text-decoration:none;font-weight:bold">
          Uygulamayı Aç →
        </a>
      </div>
    </div>
    <div style="background:#f5f5f5;padding:16px;text-align:center;color:#999;font-size:12px">
      Almadan — Akıllı Alışveriş Asistanı |
      <a href="{_APP_URL}/unsubscribe?uid={p.user_id}" style="color:#999">Abonelikten Çık</a>
    </div>
  </div>
</body>
</html>"""

    # ── Yardımcılar ──────────────────────────────────────────

    def _get_active_users(self, filter_user_id: str | None = None) -> list[dict]:
        """Son 30 günde uygulamayı açmış kullanıcıları getirir."""
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        try:
            # Son 30 günde etkin kullanıcı ID'leri
            params: dict[str, str] = {
                "event_type": "eq.open_app",
                "created_at": f"gte.{thirty_days_ago}",
                "select": "user_id",
            }
            r = _req.get(_sb("user_analytics_events"), params=params,
                         headers={**_headers(), "Prefer": ""}, timeout=6)
            if not r.ok:
                return []
            active_ids = list({row["user_id"] for row in r.json() if row.get("user_id")})
            if filter_user_id:
                active_ids = [uid for uid in active_ids if uid == filter_user_id]
            if not active_ids:
                return []

            # Supabase admin auth listesi — service_role gerekli
            users: list[dict] = []
            for uid in active_ids[:200]:   # Vercel 10s timeout için sınır
                ru = _req.get(
                    f"{_SUPABASE_URL}/auth/v1/admin/users/{uid}",
                    headers={**_headers(), "apikey": _SUPABASE_KEY},
                    timeout=4,
                )
                if ru.ok:
                    users.append(ru.json())
            return users
        except Exception as exc:
            logger.warning("_get_active_users failed: %s", exc)
            return []

    def _get_push_subscriptions(self, user_id: str) -> list[dict]:
        try:
            r = _req.get(
                _sb("push_subscriptions"),
                params={"owner_id": f"eq.{user_id}", "select": "subscription"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            return [row["subscription"] for row in (r.json() if r.ok else [])]
        except Exception:
            return []

    def _get_streak(self, user_id: str) -> int:
        from datetime import date
        try:
            r = _req.get(
                _sb("user_analytics_events"),
                params={
                    "user_id": f"eq.{user_id}",
                    "event_type": "eq.open_app",
                    "select": "created_at",
                    "order": "created_at.desc",
                    "limit": "30",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if not r.ok:
                return 0
            seen: set[str] = {row["created_at"][:10] for row in r.json() if row.get("created_at")}
            streak = 0
            check = date.today()
            while check.isoformat() in seen:
                streak += 1
                check -= timedelta(days=1)
            return streak
        except Exception:
            return 0

    def _log_digest(self, user_id: str, status: str) -> None:
        row = {"user_id": user_id, "digest_type": "weekly", "status": status}
        try:
            _req.post(_sb("digest_log"), headers=_headers(), json=row, timeout=3)
        except Exception:
            pass


# Singleton
retention_service = RetentionService()
