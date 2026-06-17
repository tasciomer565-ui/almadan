"""
ScrapingBee proxy wrapper — IP engelli siteler için (CarrefourSA, Migros, vb.)

Kurulum:
  1. https://www.scrapingbee.com → ücretsiz hesap aç (1000 kredi/ay)
  2. API key'i kopyala
  3. Vercel dashboard → Settings → Environment Variables
     SCRAPINGBEE_API_KEY = <key>

Kullanım:
  html = proxy_get("https://www.carrefoursa.com/search/?text=sut")
  # None döndüyse ScrapingBee devre dışı veya hata var
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_API_KEY", "").strip()
SCRAPINGBEE_URL = "https://app.scrapingbee.com/api/v1/"

# ScrapingBee kredi maliyeti:
#   render_js=false → 1 kredi/istek
#   render_js=true  → 5 kredi/istek (JS render gerekirse)
DEFAULT_PARAMS = {
    "render_js": "false",
    "block_ads": "true",
    "block_resources": "true",  # CSS/resim yükleme → daha hızlı
    "timeout": "8000",
    "country_code": "tr",       # Türk IP ile çek → Türk mağazaları daha iyi yanıt verir
}


def proxy_enabled() -> bool:
    return bool(SCRAPINGBEE_KEY)


def proxy_get(target_url: str, render_js: bool = False, timeout: int = 10) -> str | None:
    """
    Hedef URL'yi ScrapingBee üzerinden çek.
    ScrapingBee yoksa doğrudan requests ile dene (local/dev ortam).
    Başarısız olursa None döndür.
    """
    if not proxy_enabled():
        # ScrapingBee key yoksa — doğrudan dene (Vercel dışında çalışabilir)
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
            return resp.text
        logger.warning("ScrapingBee %s: %s", resp.status_code, target_url[:60])
        return None
    except Exception as exc:
        logger.warning("ScrapingBee error (%s): %s", target_url[:60], exc)
        return None


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
