"""
BaseScraper — Tüm market scraperları bu sınıftan miras alır.

Özellikler:
  - User-Agent rotasyonu (6 gerçekçi tarayıcı UA)
  - Exponential backoff ile retry (max 3 deneme)
  - Rate limiting (istek arası rastgele bekleme)
  - Bot tespiti algılama (Cloudflare, 403, CAPTCHA)
  - ScrapingBee proxy entegrasyonu (SCRAPINGBEE_API_KEY varsa)
  - Standart ürün dict formatı
  - Fiyat parse edici (TL, virgül/nokta, whitespace toleranslı)
"""
from __future__ import annotations

import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import requests
from bs4 import BeautifulSoup

# ── User-Agent Havuzu ────────────────────────────────────────
# Gerçek Chrome/Firefox tarayıcı UA'ları — bot tespitini zorlaştırır
_USER_AGENTS = [
    # Chrome 124 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox 125 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari 17 macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Chrome 124 Android (mobil UA — bazı siteler mobil API'yi daha açık bırakır)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    # Edge 124 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# ── Bot Tespiti Belirteçleri ─────────────────────────────────
_BOT_SIGNALS = [
    "Access Denied",
    "cf-browser-verification",
    "CAPTCHA",
    "captcha",
    "are you human",
    "bot detection",
    "Too Many Requests",
    "Forbidden",
    "blocked",
    "security check",
]

# ── Fiyat Regex ──────────────────────────────────────────────
_PRICE_RE = re.compile(
    r"(\d{1,6}[.,]\d{2}|\d{1,6})"   # Sayı (virgüllü veya tam)
    r"\s*(?:TL|₺|TRY)?",
    re.IGNORECASE,
)


class ScraperError(Exception):
    """Scraper tarafından fırlatılan kontrollü hata."""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class BotDetectedError(ScraperError):
    """Site bot koruması devreye girdi."""
    def __init__(self, url: str):
        super().__init__(f"Bot tespiti: {url}", retryable=True)


class BaseScraper(ABC):
    """
    Tüm market scraperları için soyut temel sınıf.

    Alt sınıflar implement etmeli:
        - name: str         — "migros", "carrefoursa" gibi benzersiz id
        - base_url: str     — "https://www.migros.com.tr"
        - search(query)     — ham ürün listesi döner
    """

    name: str = "base"
    base_url: str = ""

    # Rate limiting: istek arası bekleme (saniye)
    min_delay: float = 0.8
    max_delay: float = 2.5

    # Retry
    max_retries: int = 3
    retry_backoff: float = 1.5   # her denemede bekleme *= backoff

    # Timeout
    request_timeout: int = 12

    def __init__(self):
        self._session = requests.Session()
        self._last_request_at: float = 0.0
        self._proxy_enabled: bool = self._check_proxy()

    # ── Public API ───────────────────────────────────────────

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """
        Verilen sorgu için ürün listesi döner.
        Her öğe standart ürün dict formatında olmalı (_normalize_product kullan).
        Hiçbir şey bulunamazsa boş liste döner, exception fırlatma.
        """
        ...

    # ── HTTP Katmanı ─────────────────────────────────────────

    def _get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        use_proxy: bool | None = None,
        timeout: int | None = None,
    ) -> requests.Response:
        """
        Retry + rate-limit + UA rotasyonlu GET isteği.
        use_proxy=None → proxy varsa otomatik kullan.
        """
        use_proxy = self._proxy_enabled if use_proxy is None else use_proxy
        timeout = timeout or self.request_timeout

        wait = self.min_delay + random.random() * (self.max_delay - self.min_delay)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < wait:
            time.sleep(wait - elapsed)

        merged_headers = self._default_headers()
        if headers:
            merged_headers.update(headers)

        last_exc: Exception | None = None
        delay = 1.0

        for attempt in range(self.max_retries):
            try:
                if use_proxy:
                    response = self._proxy_get(url, params=params, headers=merged_headers, timeout=timeout)
                else:
                    self._session.headers.update(merged_headers)
                    response = self._session.get(url, params=params, timeout=timeout)

                self._last_request_at = time.monotonic()

                if response.status_code == 429:
                    # Rate-limit: bekle ve tekrar dene
                    retry_after = int(response.headers.get("Retry-After", delay * 2))
                    time.sleep(retry_after)
                    delay *= self.retry_backoff
                    continue

                if response.status_code in (403, 503):
                    raise BotDetectedError(url)

                if response.status_code == 404:
                    raise ScraperError(f"404: {url}", retryable=False)

                self._assert_not_bot(response.text, url)
                return response

            except (BotDetectedError, requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= self.retry_backoff
                    merged_headers["User-Agent"] = random.choice(_USER_AGENTS)

        raise ScraperError(
            f"{self.name} scraper {self.max_retries} denemede başarısız: {last_exc}",
            retryable=False,
        ) from last_exc

    def _get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        use_proxy: bool | None = None,
    ) -> Any:
        """JSON API isteği — Response.json() döner."""
        extra = {"Accept": "application/json", "Content-Type": "application/json"}
        if headers:
            extra.update(headers)
        resp = self._get(url, params=params, headers=extra, use_proxy=use_proxy)
        return resp.json()

    def _get_soup(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        use_proxy: bool | None = None,
    ) -> BeautifulSoup:
        """HTML GET → BeautifulSoup döner."""
        resp = self._get(url, params=params, headers=headers, use_proxy=use_proxy)
        return BeautifulSoup(resp.text, "html.parser")

    # ── ScrapingBee Proxy ────────────────────────────────────

    @staticmethod
    def _check_proxy() -> bool:
        import os
        return bool(os.getenv("SCRAPINGBEE_API_KEY", "").strip())

    def _proxy_get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: int = 15,
        render_js: bool = False,
    ) -> requests.Response:
        import os
        api_key = os.getenv("SCRAPINGBEE_API_KEY", "")
        proxy_params = {
            "api_key":          api_key,
            "url":              url,
            "render_js":        "true" if render_js else "false",
            "block_ads":        "true",
            "block_resources":  "true",
            "country_code":     "tr",
            "premium_proxy":    "true",
        }
        if params:
            # Query string'i URL'e ekle, ScrapingBee url param'ına göm
            import urllib.parse
            proxy_params["url"] = f"{url}?{urllib.parse.urlencode(params)}"
        if headers:
            import json
            proxy_params["custom_google"] = "false"
            proxy_params["forward_headers"] = "true"
            # ScrapingBee header forwarding formatı
        resp = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params=proxy_params,
            timeout=timeout + 5,
        )
        return resp

    # ── Yardımcılar ──────────────────────────────────────────

    def _default_headers(self) -> dict:
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Referer": self.base_url + "/",
        }

    @staticmethod
    def _assert_not_bot(html: str, url: str) -> None:
        for signal in _BOT_SIGNALS:
            if signal.lower() in html.lower():
                raise BotDetectedError(url)

    @staticmethod
    def parse_price(raw: str | float | int | None) -> float | None:
        """
        Türkçe fiyat string'ini float'a çevirir.
        "49,90 TL" → 49.90
        "1.299,00" → 1299.0
        "1299"     → 1299.0
        """
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return float(raw) if raw > 0 else None
        text = str(raw).strip()
        # Binlik ayracı nokta, ondalık virgül (Türkçe format)
        if re.search(r"\d\.\d{3}", text):      # 1.299 → 1299
            text = text.replace(".", "")
        text = text.replace(",", ".").replace("₺", "").replace("TL", "").replace("TRY", "").strip()
        m = _PRICE_RE.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                return None
        return None

    def _normalize_product(
        self,
        title: str,
        price: float | str | None,
        url: str,
        image_url: str = "",
        original_price: float | str | None = None,
        source: str | None = None,
        labels: list[str] | None = None,
        extra_info: dict | None = None,
    ) -> dict | None:
        """
        Standart ürün dict'i üretir.
        Geçersiz fiyat veya boş başlık için None döner.
        """
        title = (title or "").strip()
        if not title:
            return None
        parsed_price = self.parse_price(price)
        if not parsed_price or parsed_price <= 0:
            return None
        return {
            "title":          title,
            "price":          parsed_price,
            "original_price": self.parse_price(original_price),
            "image_url":      (image_url or "").strip(),
            "source":         source or self.name,
            "url":            url or self.base_url,
            "labels":         labels or [],
            "extra_info":     extra_info or {},
            "category":       getattr(self, "category", None),
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
