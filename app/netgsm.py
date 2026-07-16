from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

# Netgsm SMS API (XML/GET tabanlı "sms/send/get" ucu). Kredi satın alınıp
# Netgsm panelinden kullanıcı adı/şifre/başlık (msgheader) alınınca bu üç
# ortam değişkeni Vercel'e eklenmesi yeterli -- kod tarafı zaten hazır.
NETGSM_USERCODE = os.getenv("NETGSM_USERCODE", "").strip()
NETGSM_PASSWORD = os.getenv("NETGSM_PASSWORD", "").strip()
NETGSM_MSGHEADER = os.getenv("NETGSM_MSGHEADER", "").strip()
NETGSM_API_URL = "https://api.netgsm.com.tr/sms/send/get"


def netgsm_enabled() -> bool:
    return bool(NETGSM_USERCODE and NETGSM_PASSWORD and NETGSM_MSGHEADER)


def _normalize_phone(phone: str) -> str:
    """Netgsm '90' ülke koduyla, '+' ve boşluksuz 12 haneli numara bekler
    (ör. 905551234567). WhatsApp modülündeki _normalize_phone ile aynı
    girdi formatını (E.164, +90...) kabul edip Netgsm'in beklediği hale çevirir."""
    digits = phone.strip().lstrip("+").replace(" ", "").replace("-", "")
    if digits.startswith("0"):
        digits = "90" + digits[1:]
    elif not digits.startswith("90"):
        digits = "90" + digits
    return digits


def send_netgsm_sms(to_phone: str, message: str) -> bool:
    """Serbest metin SMS gönderir -- WhatsApp'ın aksine önceden onaylı
    şablon gerektirmez, mesaj metni doğrudan gönderilir."""
    if not netgsm_enabled():
        return False
    to = _normalize_phone(to_phone)
    try:
        resp = requests.get(
            NETGSM_API_URL,
            params={
                "usercode": NETGSM_USERCODE,
                "password": NETGSM_PASSWORD,
                "gsmno": to,
                "message": message,
                "msgheader": NETGSM_MSGHEADER,
                "dil": "TR",
            },
            timeout=15,
        )
        # Netgsm 200 OK ile "00 <bulkid>" (basarili) veya hata kodu (20, 30, 40...)
        # donduren duz metin/XML bir govde donduruyor -- HTTP durum kodu tek basina
        # yeterli degil, govdeyi de kontrol etmek gerekiyor.
        ok = resp.ok and resp.text.strip().startswith("00")
        if not ok:
            logger.warning("Netgsm SMS gonderim hatasi: %s", resp.text[:200])
        return ok
    except Exception as exc:
        logger.warning("Netgsm SMS gonderim exception: %s", exc)
        return False
