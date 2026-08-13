"""
Scraping proxy wrapper — IP engelli/JS-render gerektiren siteler için
(CarrefourSA, Migros, Gratis, Watsons, Sephora, vb.)

İki sağlayıcı destekleniyor, SCRAPINGDOG_API_KEY varsa o öncelikli
kullanılır (ScrapingBee'den ~%20-25 daha ucuz, aynı kredi mantığı):
  - ScrapingDog: https://www.scrapingdog.com  (SCRAPINGDOG_API_KEY)
  - ScrapingBee: https://www.scrapingbee.com  (SCRAPINGBEE_API_KEY)

Kurulum (ScrapingDog, önerilen):
  1. https://www.scrapingdog.com → ücretsiz hesap aç (1000 kredi)
  2. API key'i kopyala
  3. Vercel dashboard → Settings → Environment Variables
     SCRAPINGDOG_API_KEY = <key>

Kullanım:
  html = proxy_get("https://www.carrefoursa.com/search/?text=sut")
  # None döndüyse her iki proxy de devre dışı veya hata var
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

SCRAPINGDOG_KEY = os.getenv("SCRAPINGDOG_API_KEY", "").strip()
SCRAPINGDOG_URL = "https://api.scrapingdog.com/scrape"

SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_API_KEY", "").strip()
SCRAPINGBEE_URL = "https://app.scrapingbee.com/api/v1/"

# Kredi maliyeti (her iki sağlayıcıda da aynı mantık):
#   JS render kapalı → 1 kredi/istek
#   JS render açık   → 5 kredi/istek
DEFAULT_PARAMS = {
    "block_ads": "true",
    "block_resources": "true",  # CSS/resim yükleme → daha hızlı
    "timeout": "8000",
    "country_code": "tr",       # Türk IP ile çek → Türk mağazaları daha iyi yanıt verir
}


def proxy_enabled() -> bool:
    return bool(SCRAPINGDOG_KEY or SCRAPINGBEE_KEY)


def _direct_get(target_url: str, timeout: int) -> str | None:
    """Proxy anahtarı yoksa (local/dev ortam) doğrudan dene."""
    try:
        resp = requests.get(
            target_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "tr-TR,tr;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
            timeout=timeout,
        )
        return resp.text if resp.ok else None
    except Exception as exc:
        logger.warning("direct_get failed (%s): %s", target_url[:60], exc)
        return None


def _record_proxy_used(target_url: str) -> None:
    try:
        from app.admin_metrics import record_event
        record_event("proxy_used", source=target_url[:80])
    except Exception:
        pass


def _scrapingdog_get(target_url: str, render_js: bool, timeout: int) -> str | None:
    params = {
        "api_key": SCRAPINGDOG_KEY,
        "url": target_url,
        "dynamic": "true" if render_js else "false",
    }
    try:
        resp = requests.get(SCRAPINGDOG_URL, params=params, timeout=timeout + 5)
        if resp.status_code == 200:
            logger.info("ScrapingDog OK: %s", target_url[:60])
            _record_proxy_used(target_url)
            return resp.text
        logger.warning("ScrapingDog %s: %s", resp.status_code, target_url[:60])
        return None
    except Exception as exc:
        logger.warning("ScrapingDog error (%s): %s", target_url[:60], exc)
        return None


def _scrapingbee_get(target_url: str, render_js: bool, timeout: int) -> str | None:
    params = {
        **DEFAULT_PARAMS,
        "api_key": SCRAPINGBEE_KEY,
        "url": target_url,
        "render_js": "true" if render_js else "false",
    }
    try:
        resp = requests.get(SCRAPINGBEE_URL, params=params, timeout=timeout + 5)
        if resp.status_code == 200:
            logger.info("ScrapingBee OK: %s", target_url[:60])
            _record_proxy_used(target_url)
            return resp.text
        logger.warning("ScrapingBee %s: %s", resp.status_code, target_url[:60])
        return None
    except Exception as exc:
        logger.warning("ScrapingBee error (%s): %s", target_url[:60], exc)
        return None


def proxy_get(target_url: str, render_js: bool = False, timeout: int = 10) -> str | None:
    """
    Hedef URL'yi proxy üzerinden çek (ScrapingDog varsa öncelikli, yoksa
    ScrapingBee, o da yoksa doğrudan requests). Başarısız olursa None döner.
    """
    if SCRAPINGDOG_KEY:
        return _scrapingdog_get(target_url, render_js, timeout)
    if SCRAPINGBEE_KEY:
        return _scrapingbee_get(target_url, render_js, timeout)
    return _direct_get(target_url, timeout)


def proxy_get_json(target_url: str, timeout: int = 10) -> dict | list | None:
    """JSON döndüren API'ler için."""
    html = proxy_get(target_url, timeout=timeout)
    if not html:
        return None
    try:
        import json
        return json.loads(html)
    except Exception:
        return None
