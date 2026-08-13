from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# SMTP ortam değişkenleri -- app/retention_service.py'nin (mevcut haftalık
# özet e-postası) kullandığı DEĞİŞKEN ADLARIYLA AYNI (SMTP_PASS, FROM_EMAIL)
# tutuldu. Farklı isimler kullansaydık kullanıcı tek bir SMTP_PASSWORD/
# SMTP_PASS ayarlayıp diğer sistemin sessizce çalışmadığını fark etmezdi.
# whatsapp.py/netgsm.py'deki "enabled() kontrolü" pattern'i: credential
# yoksa gönderim sessizce atlanır.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASS", "").strip()
SMTP_FROM = os.getenv("FROM_EMAIL", "").strip() or SMTP_USER


def smtp_enabled() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_smtp_email(recipient: str, subject: str, message: str, html: str | None = None) -> bool:
    """Basit SMTP e-posta gönderimi. Credential yoksa (SMTP_USER/SMTP_PASS
    eksikse) sessizce atlar ve False döner -- whatsapp.py'deki
    whatsapp_enabled() pattern'iyle aynı yaklaşım."""
    if not smtp_enabled() or not recipient:
        return False

    try:
        msg = MIMEText(html, "html", "utf-8") if html else MIMEText(message, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = recipient

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(SMTP_FROM, [recipient], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("SMTP e-posta gönderim hatası (%s): %s", recipient, exc)
        return False
