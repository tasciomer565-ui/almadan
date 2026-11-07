"""
Almadan.app - Otonom Fiyat İzleme Motoru (Price Tracker Worker & Push Dispatcher - Aşama 1.8).

Mimari:
1. Celery + Redis Broker (veya FastAPI BackgroundTasks / Cron Scheduler) üzerinde çalışan
   periyodik asenkron fiyat tarayıcı.
2. `is_active = True` olan tüm `price_alerts` kayıtlarını çeker ve `httpx.AsyncClient` + `asyncio.gather`
   ile ürün URL'lerini paralel olarak tarar.
3. Karar Mekanizması:
   - `new_price <= target_price` ise:
     * `current_price = new_price` ve `is_active = False` olarak günceller (alarmı kapatır).
     * Push Notification servisini tetikler:
       `PUSH NOTIFICATION SENDING: [<user_id>] - <product_name> fiyatı <fiyat> TL'ye düştü!`
   - `new_price > target_price` ise:
     * Yalnızca `current_price = new_price` ve `updated_at` alanlarını günceller, alarm aktif kalır.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any
import urllib.parse

from bs4 import BeautifulSoup
import httpx

from app.storage import supabase_base_url, supabase_enabled, supabase_headers

logger = logging.getLogger(__name__)

# ── Celery + Redis Broker Yapılandırması (Opsiyonel / Graceful Shim) ──

REDIS_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    from celery import Celery  # type: ignore

    celery_app = Celery("almadan_price_tracker", broker=REDIS_BROKER_URL, backend=REDIS_BROKER_URL)
except ImportError:
    celery_app = None


# ── İlişkisel Fiyat Alarmları Veri Deposu ve Bildirim Kayıtları ───
# Yapı: PRICE_ALERTS_STORE[alert_id] = dict

PRICE_ALERTS_STORE: dict[str, dict[str, Any]] = {}
SENT_PUSH_NOTIFICATIONS: list[str] = []


def reset_price_alerts_store() -> None:
    """Test senaryoları için fiyat alarmlarını ve gönderilen bildirim geçmişini sıfırlar."""
    PRICE_ALERTS_STORE.clear()
    SENT_PUSH_NOTIFICATIONS.clear()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_tr_price(price: float) -> str:
    """
    Fiyatı Türkçe binlik ayraçlı formata dönüştürür.
    Örn: 75000.0 -> '75.000', 75450.5 -> '75.450,50'
    """
    if float(price).is_integer():
        return f"{int(price):,}".replace(",", ".")
    formatted = f"{price:,.2f}"
    parts = formatted.split(".")
    integer_part = parts[0].replace(",", ".")
    return f"{integer_part},{parts[1]}"


def infer_product_name_from_url(url: str) -> str:
    """URL içindeki slug yapısından okunabilir ürün başlığı çıkarır."""
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        segments = [s for s in path.split("/") if s and not s.startswith("dp")]
        slug = segments[-1] if segments else "Takip Edilen Ürün"
        # Trendyol/HB sonundaki -p-12345 veya -pm-HBC... kısımlarını temizle
        slug = re.sub(r"-p-\d+.*$", "", slug, flags=re.IGNORECASE)
        slug = re.sub(r"-pm?-hbc[a-z0-9]+.*$", "", slug, flags=re.IGNORECASE)
        words = [w.capitalize() for w in slug.replace("-", " ").replace("_", " ").split() if w]
        return " ".join(words) if words else "Takip Edilen Ürün"
    except Exception:
        return "Takip Edilen Ürün"


# ── Push Notification Servisi ────────────────────────────────────

def send_price_drop_push_notification(
    user_id: str,
    product_name: str,
    new_price: float,
    target_price: float,
    product_url: str,
) -> str:
    """
    Hedef fiyata düşen ürün için Push Notification tetikler ve standart bildirim logunu basar.
    """
    formatted_price = format_tr_price(new_price)
    message = f"PUSH NOTIFICATION SENDING: [{user_id}] - {product_name} fiyatı {formatted_price} TL'ye düştü!"
    print(message)
    logger.info(message)
    SENT_PUSH_NOTIFICATIONS.append(message)
    return message


# ── Asenkron Ürün URL Fiyat Kazıyıcı (Scraper) ───────────────────

_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _parse_tr_number(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d,.]", "", raw or "").strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


async def scrape_product_price_async(
    product_url: str,
    client: httpx.AsyncClient | None = None,
) -> float | None:
    """
    Verilen e-ticaret ürün URL'sini (Trendyol, Hepsiburada, Amazon TR, N11 vb.)
    asenkron olarak tarayarak güncel satış fiyatını (float) döner.
    """
    should_close = False
    if client is None:
        client = httpx.AsyncClient(verify=False, timeout=4.0, follow_redirects=True)
        should_close = True

    try:
        resp = await client.get(product_url, headers=_SCRAPER_HEADERS)
        if resp.status_code != 200:
            return None

        html = resp.text

        # 1. JSON-LD (Schema.org Product offers.price) kontrolü
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "{}")
                blocks = data if isinstance(data, list) else [data]
                for block in blocks:
                    offers = block.get("offers")
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    if isinstance(offers, dict):
                        p_val = offers.get("price") or offers.get("lowPrice")
                        if p_val is not None:
                            parsed_p = _parse_tr_number(str(p_val))
                            if parsed_p:
                                return parsed_p
            except Exception:
                continue

        # 2. Meta OpenGraph / Product Price etiketleri
        meta_price = soup.select_one(
            "meta[property='product:price:amount'], meta[name='twitter:data1']"
        )
        if meta_price and meta_price.get("content"):
            parsed_p = _parse_tr_number(meta_price["content"])
            if parsed_p:
                return parsed_p

        # 3. DOM Fiyat Seçicileri (Trendyol, Hepsiburada, Amazon, N11)
        price_el = soup.select_one(
            ".prc-dsc, [data-test-id='price-current-price'], .a-price .a-offscreen, .newPrice ins"
        )
        if price_el:
            parsed_p = _parse_tr_number(price_el.get_text(strip=True))
            if parsed_p:
                return parsed_p

    except Exception as exc:
        logger.debug("URL fiyat tarama hatası (%s): %s", product_url, exc)
    finally:
        if should_close:
            await client.aclose()

    return None


# ── Supabase Senkronizasyon Yardımcıları ─────────────────────────

async def _supabase_upsert_alert(alert_row: dict[str, Any]) -> None:
    if not supabase_enabled():
        return
    try:
        headers = {
            **supabase_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{supabase_base_url()}/rest/v1/price_alerts",
                headers=headers,
                json=alert_row,
            )
    except Exception as exc:
        logger.debug("Supabase price_alerts upsert hatası: %s", exc)


# ── Asenkron Fiyat Tarayıcı Worker Görevi ────────────────────────

@dataclass
class PriceTrackerRunSummary:
    scanned_count: int = 0
    triggered_count: int = 0
    updated_count: int = 0
    notifications: list[str] = field(default_factory=list)


async def run_price_tracker_scan() -> PriceTrackerRunSummary:
    """
    `is_active = True` olan tüm fiyat alarmlarını çeker, URL'leri paralel tarar:
    - `new_price <= target_price` ise:
      * `is_active = False` yapar (alarmı kapatır), `current_price = new_price` günceller.
      * Push Notification tetikler.
    - `new_price > target_price` ise:
      * Yalnızca `current_price = new_price` günceller, `is_active = True` kalır.
    """
    active_alerts = [
        alert
        for alert in PRICE_ALERTS_STORE.values()
        if alert.get("is_active", False) and not alert.get("is_deleted", False)
    ]

    summary = PriceTrackerRunSummary(scanned_count=len(active_alerts))
    if not active_alerts:
        return summary

    async with httpx.AsyncClient(verify=False, timeout=4.0, follow_redirects=True) as client:
        tasks = [
            scrape_product_price_async(str(alert["product_url"]), client=client)
            for alert in active_alerts
        ]
        scraped_prices = await asyncio.gather(*tasks, return_exceptions=True)

    now_iso = _utc_now_iso()
    supabase_tasks = []

    for alert, scraped_res in zip(active_alerts, scraped_prices):
        if isinstance(scraped_res, Exception) or scraped_res is None or scraped_res <= 0:
            continue

        new_price = round(float(scraped_res), 2)
        target_price = float(alert["target_price"])
        alert["current_price"] = new_price
        alert["updated_at"] = now_iso

        if new_price <= target_price:
            # Hedef fiyata ulaşıldı veya altına düştü -> Alarmı kapat ve Push Notification gönder!
            alert["is_active"] = False
            msg = send_price_drop_push_notification(
                user_id=str(alert["user_id"]),
                product_name=str(alert["product_name"]),
                new_price=new_price,
                target_price=target_price,
                product_url=str(alert["product_url"]),
            )
            summary.triggered_count += 1
            summary.notifications.append(msg)
        else:
            # Hedef fiyattan hala yüksek -> Sadece current_price güncellendi
            summary.updated_count += 1

        if supabase_enabled():
            supabase_tasks.append(_supabase_upsert_alert(alert))

    if supabase_tasks:
        await asyncio.gather(*supabase_tasks, return_exceptions=True)

    return summary


def run_price_tracker_task_sync() -> dict[str, Any]:
    """Celery / APScheduler senkron worker giriş noktası."""
    res = asyncio.run(run_price_tracker_scan())
    return {
        "scanned_count": res.scanned_count,
        "triggered_count": res.triggered_count,
        "updated_count": res.updated_count,
        "notifications": res.notifications,
    }


if celery_app is not None:
    run_price_tracker_celery_task = celery_app.task(name="price_tracker.scan_active_alerts")(
        run_price_tracker_task_sync
    )
else:
    run_price_tracker_celery_task = run_price_tracker_task_sync
