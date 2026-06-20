"""
Error Notifier — Almadan

Hata bildirimi için iki kanal:
  1. Telegram Bot  — TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env ile aktif
  2. SMTP Email    — SMTP_HOST + NOTIFY_EMAIL env ile aktif

Kullanım:
    from app.notifier import notify_failure, notify_health_result
    notify_failure("Barkod API timeout: 12s > 10s")

Ortam değişkenleri (Vercel'e ekle):
    TELEGRAM_BOT_TOKEN   — BotFather'dan alınan token (ör: 7123456789:AAH...)
    TELEGRAM_CHAT_ID     — Mesajın gideceği chat/grup ID (ör: -1001234567890)
    NOTIFY_EMAIL         — Bildirimlerin gideceği e-posta adresi
    SMTP_HOST            — Mail sunucusu
    SMTP_PORT            — 587 (TLS) veya 465 (SSL)
    SMTP_USER            — SMTP kullanıcı adı
    SMTP_PASS            — SMTP şifresi
    NOTIFY_MIN_LEVEL     — "error" (varsayılan) veya "warning" — ne zaman bildir
"""
from __future__ import annotations

import logging
import os
import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Literal

import requests as _req

logger = logging.getLogger(__name__)

# ── Sabit (restart gerektirmeyen) ────────────────────────────
_APP_URL = os.getenv("ALMADAN_APP_URL", "https://almadan.vercel.app").rstrip("/")
_HOST    = socket.gethostname()


def _cfg() -> dict:
    """Her istek anında env var'ları taze okur — redeploy gerekmez."""
    return {
        "tg_token":     os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "tg_chat":      os.getenv("TELEGRAM_CHAT_ID",   "").strip(),
        "notify_email": os.getenv("NOTIFY_EMAIL",       "").strip(),
        "smtp_host":    os.getenv("SMTP_HOST",          "").strip(),
        "smtp_port":    int(os.getenv("SMTP_PORT", "587")),
        "smtp_user":    os.getenv("SMTP_USER",          "").strip(),
        "smtp_pass":    os.getenv("SMTP_PASS",          "").strip(),
    }


# ── Ana Arayüz ────────────────────────────────────────────────

def notify_failure(reason: str, *, test_name: str = "health_check") -> dict[str, bool]:
    """
    Test/sistem hatası için bildirim gönderir.
    Returns: {"telegram": bool, "email": bool}
    """
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = _build_message(
        title="🔴 Almadan — Test Başarısız",
        body=reason,
        test_name=test_name,
        ts=ts,
        level="error",
    )
    return _dispatch(msg, subject=f"[Almadan] HATA: {test_name}")


def notify_recovery(test_name: str = "health_check") -> dict[str, bool]:
    """Bir önceki hata sonrasında sistem düzeldiğinde bildirir."""
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = _build_message(
        title="🟢 Almadan — Sistem Normale Döndü",
        body="Health check tüm testleri geçti.",
        test_name=test_name,
        ts=ts,
        level="recovery",
    )
    return _dispatch(msg, subject=f"[Almadan] Sistem normale döndü")


def notify_restock_reminder(
    product_title: str,
    *,
    current_price: str | None = None,
    days_until_empty: int = 0,
    product_url: str = "",
) -> dict[str, bool]:
    """
    Ürün stoku bitmek üzereyken hatırlatıcı bildirimi gönderir.
    Notifier'ın tek kanalı yoksa sessiz döner — ürün takip bildirimi
    sisteme bağlı olmayan kullanıcılar için gönderilmez.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    price_line = f"\n<b>Şu anki en iyi fiyat:</b> {current_price}" if current_price else ""
    url_line   = f"\n<b>Ürün:</b> <a href='{product_url}'>{product_url[:60]}</a>" if product_url else ""
    body = (
        f"<b>{product_title}</b> stokun bitmek üzere — "
        f"yaklaşık <b>{days_until_empty} gün</b> kaldı."
        f"{price_line}{url_line}\n\n"
        "Almadan'dan fiyat karşılaştırması yapmak ister misin?"
    )
    msg = (
        f"🛒 <b>Stok Hatırlatıcısı — Almadan</b>\n\n"
        f"{body}\n\n"
        f"<b>Zaman:</b> {ts}\n"
        f"<b>URL:</b> <a href='{_APP_URL}'>{_APP_URL}</a>"
    )
    return _dispatch(msg, subject=f"[Almadan] {product_title} stokun bitmek üzere")


def notify_store_update(
    store_name: str,
    *,
    campaign_title: str = "",
    catalog_url: str = "",
    valid_until: str = "",
    follower_count: int = 0,
) -> dict[str, bool]:
    """
    Mağaza kampanya/bülten bildirimi gönderir.
    Cron job tarafından çağrılır: o mağazayı takip eden tüm kullanıcılar için.
    Kanal başına tek bir mesaj gider (grup bildirimi) — kişi başına değil.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    until_line   = f"\n<b>Son geçerlilik:</b> {valid_until}" if valid_until else ""
    catalog_line = f"\n\n🔗 <a href='{catalog_url}'>Kataloğu İncele</a>" if catalog_url else ""
    title_line   = f"\n<b>Kampanya:</b> {campaign_title}" if campaign_title else ""
    followers_line = f"\n<b>Bilgilendirilen takipçi:</b> {follower_count} kişi" if follower_count else ""

    msg = (
        f"🏪 <b>{store_name} — Yeni Kampanya Başladı!</b>\n"
        f"{title_line}{until_line}{followers_line}\n\n"
        f"Almadan ile en iyi fiyatları karşılaştır."
        f"{catalog_line}\n\n"
        f"<b>Zaman:</b> {ts}"
    )
    return _dispatch(
        msg,
        subject=f"[Almadan] {store_name}'de yeni kampanya başladı!",
    )


def notify_health_result(
    result: Literal["success", "failure"],
    *,
    error: str | None = None,
    prev_result: str | None = None,
) -> dict[str, bool]:
    """
    Health check sonucuna göre uygun bildirimi gönderir.

    Mantık:
      - failure          → her zaman bildir
      - success (prev=failure) → recovery bildirimi gönder
      - success (prev=success) → sessiz kal
    """
    if result == "failure":
        return notify_failure(error or "Bilinmeyen hata", test_name="health_check")
    if result == "success" and prev_result == "failure":
        return notify_recovery()
    return {"telegram": False, "email": False}


# ── Kanal Göndericileri ───────────────────────────────────────

def _dispatch(message: str, *, subject: str) -> dict[str, bool]:
    c = _cfg()
    tg_ok    = _send_telegram(message, c) if c["tg_token"] and c["tg_chat"] else False
    email_ok = _send_email(subject, message, c) if c["smtp_host"] and c["notify_email"] else False

    if not tg_ok and not email_ok:
        logger.warning(
            "Notifier: Hiçbir kanal yapılandırılmamış. "
            "TELEGRAM_BOT_TOKEN veya SMTP_HOST env değişkenlerini ayarlayın."
        )
    return {"telegram": tg_ok, "email": email_ok}


def _send_telegram(text: str, c: dict) -> bool:
    """Telegram Bot API üzerinden mesaj gönderir."""
    url = f"https://api.telegram.org/bot{c['tg_token']}/sendMessage"
    try:
        r = _req.post(
            url,
            json={"chat_id": c["tg_chat"], "text": text, "parse_mode": "HTML"},
            timeout=8,
        )
        if r.ok:
            logger.info("Telegram bildirimi gönderildi.")
            return True
        logger.warning("Telegram HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Telegram gönderilemedi: %s", exc)
    return False


def _send_email(subject: str, body: str, c: dict) -> bool:
    """
    SMTP üzerinden plain-text + HTML e-posta gönderir.
    Port 465 → SMTP_SSL (Resend, vb.)
    Port 587 → SMTP + STARTTLS (Gmail, vb.)
    """
    try:
        from_addr = os.getenv("SMTP_FROM", c["smtp_user"]).strip() or c["smtp_user"]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Almadan <{from_addr}>"
        msg["To"]      = c["notify_email"]

        plain = _strip_html_tags(body)
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        html_body = f"<pre style='font-family:monospace;font-size:13px;'>{body}</pre>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if c["smtp_port"] == 465:
            # SSL — Resend ve benzeri servisler
            with smtplib.SMTP_SSL(c["smtp_host"], 465, timeout=10) as srv:
                srv.login(c["smtp_user"], c["smtp_pass"])
                srv.sendmail(from_addr, c["notify_email"], msg.as_string())
        else:
            # STARTTLS — Gmail (587) ve benzeri
            with smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=10) as srv:
                srv.starttls()
                srv.login(c["smtp_user"], c["smtp_pass"])
                srv.sendmail(from_addr, c["notify_email"], msg.as_string())

        logger.info("Email bildirimi gönderildi: %s → %s", from_addr, c["notify_email"])
        return True
    except Exception as exc:
        logger.warning("Email gönderilemedi: %s", exc)
    return False


def send_user_email(to_email: str, subject: str, html_body: str) -> bool:
    """Belirli bir kullanıcıya SMTP üzerinden email gönderir."""
    c = _load_config()
    if not c["smtp_host"] or not c["smtp_user"] or not to_email:
        return False

    try:
        from_addr = os.getenv("SMTP_FROM", c["smtp_user"]).strip() or c["smtp_user"]
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Almadan <{from_addr}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if c["smtp_port"] == 465:
            with smtplib.SMTP_SSL(c["smtp_host"], 465, timeout=10) as srv:
                srv.login(c["smtp_user"], c["smtp_pass"])
                srv.sendmail(from_addr, to_email, msg.as_string())
        else:
            with smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=10) as srv:
                srv.starttls()
                srv.login(c["smtp_user"], c["smtp_pass"])
                srv.sendmail(from_addr, to_email, msg.as_string())

        logger.info("Kullanıcı emaili gönderildi: %s → %s", from_addr, to_email)
        return True
    except Exception as exc:
        logger.warning("Kullanıcı emaili gönderilemedi (%s): %s", to_email, exc)
    return False


# ── Mesaj Şablonu ─────────────────────────────────────────────

def _build_message(
    title: str,
    body: str,
    *,
    test_name: str,
    ts: str,
    level: str,
) -> str:
    icon = {"error": "🔴", "warning": "🟡", "recovery": "🟢"}.get(level, "⚪")
    return (
        f"<b>{title}</b>\n\n"
        f"<b>Test:</b> {test_name}\n"
        f"<b>Zaman:</b> {ts}\n"
        f"<b>Sunucu:</b> {_HOST}\n"
        f"<b>URL:</b> <a href='{_APP_URL}/api/status'>{_APP_URL}/api/status</a>\n\n"
        f"<b>Detay:</b>\n<code>{body[:800]}</code>"
    )


def _strip_html_tags(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text)


# ── Yapılandırma Durumu ───────────────────────────────────────

def notifier_status() -> dict:
    """Admin dashboard için notifier yapılandırma durumu (canlı env okur)."""
    c = _cfg()
    return {
        "telegram_configured": bool(c["tg_token"] and c["tg_chat"]),
        "email_configured":    bool(c["smtp_host"] and c["notify_email"]),
        "notify_email":        c["notify_email"] or None,
        "telegram_chat":       c["tg_chat"] or None,
        "smtp_host":           c["smtp_host"] or None,
    }
