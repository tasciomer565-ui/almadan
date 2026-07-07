from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_API_URL = "https://graph.facebook.com/v21.0"


def whatsapp_enabled() -> bool:
    return bool(WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID)


def _normalize_phone(phone: str) -> str:
    """WhatsApp API '+' olmadan, ulke koduyla baslayan numara bekler."""
    return phone.strip().lstrip("+").replace(" ", "").replace("-", "")


def send_whatsapp_template(
    to_phone: str,
    template_name: str,
    lang: str = "tr",
    params: list[str] | None = None,
    button_param: str | None = None,
) -> bool:
    """
    Onaylanmis bir WhatsApp sablonunu (template) gonderir. Business-initiated
    mesajlar (kullanicinin 24 saattir yazmadigi durumlar) SADECE onceden Meta
    tarafindan onaylanmis sablonlarla gonderilebilir -- serbest metin degil.

    button_param: sablonda dinamik URL butonu varsa (orn. price_alert
    sablonundaki "Urunu Gor" butonu https://www.almadan.app/{{1}}), butonun
    {{1}} kismina eklenecek yol/parca (orn. "urun/samsung-galaxy-s24").
    """
    if not whatsapp_enabled():
        return False
    to = _normalize_phone(to_phone)
    body = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
        },
    }
    components = []
    if params:
        components.append(
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
        )
    if button_param:
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": button_param}],
        })
    if components:
        body["template"]["components"] = components
    try:
        resp = requests.post(
            f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=10,
        )
        if not resp.ok:
            logger.warning("WhatsApp gonderim hatasi (%s): %s", resp.status_code, resp.text[:300])
        return resp.ok
    except Exception as exc:
        logger.warning("WhatsApp gonderim exception: %s", exc)
        return False


def send_whatsapp_text(to_phone: str, message: str) -> bool:
    """
    Serbest metin mesaji -- SADECE kullanici son 24 saat icinde bize
    WhatsApp'tan yazdiysa gonderilebilir (musteri hizmet penceresi).
    Fiyat alarmi gibi proaktif bildirimler icin send_whatsapp_template kullan.
    """
    if not whatsapp_enabled():
        return False
    to = _normalize_phone(to_phone)
    body = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    try:
        resp = requests.post(
            f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=10,
        )
        if not resp.ok:
            logger.warning("WhatsApp gonderim hatasi (%s): %s", resp.status_code, resp.text[:300])
        return resp.ok
    except Exception as exc:
        logger.warning("WhatsApp gonderim exception: %s", exc)
        return False
