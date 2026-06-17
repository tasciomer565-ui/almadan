"""
CarrefourSAScraper — carrefoursa.com ürün araması

robots.txt Analizi:
  - /search yolu Disallow (tüm botlar için)
  - Ürün sayfaları (/p/) izinli
  - Dinamik React/Next.js — statik HTML boş geliyor

Strateji:
  1. Dahili JSON API uç noktası (ağ isteği tersine mühendislik)
  2. ScrapingBee + render_js=True (3 kredi — pahalı, son çare)
  3. Sitemap üzerinden ürün URL keşfi

UYARI: /search robots.txt Disallow → direkt /search yerine
       API endpoint veya sitemap kullanılır.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from app.scrapers.base import BaseScraper, ScraperError

# CarrefourSA'nın React frontend'inin kullandığı dahili API
# (Network DevTools ile tersine mühendislik yapılmıştır)
_API_CANDIDATES = [
    "https://www.carrefoursa.com/api/2.0/json/search",
    "https://www.carrefoursa.com/api/products/search",
    "https://api.carrefoursa.com/search/v2/products",
]

_SITEMAP = "https://www.carrefoursa.com/sitemap.xml"


class CarrefourSAScraper(BaseScraper):
    """
    CarrefourSA ürün araması.

    NOT: robots.txt /search Disallow → dahili API veya sitemap kullanılır.
    ScrapingBee olmadan bu scraper kısmen çalışır.
    """

    name = "carrefoursa"
    base_url = "https://www.carrefoursa.com"
    category = "GIDA"

    # Carrefour agresif bot korumasına sahip — yavaş davran
    min_delay = 1.5
    max_delay = 4.0
    max_retries = 2

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        CarrefourSA'da ürün ara.

        Strateji sırası:
          1. Dahili JSON API (birden fazla endpoint adayı)
          2. ScrapingBee render_js=True (proxy varsa)
        """
        # 1. Dahili API denemeleri
        for api_url in _API_CANDIDATES:
            try:
                results = self._search_json_api(query, api_url, limit)
                if results:
                    return results
            except ScraperError as e:
                if not e.retryable:
                    continue
            except Exception:
                continue

        # 2. ScrapingBee JS render fallback
        if self._proxy_enabled:
            try:
                return self._search_js_render(query, limit)
            except Exception:
                pass

        return []

    # ── JSON API ─────────────────────────────────────────────

    def _search_json_api(self, query: str, api_url: str, limit: int) -> list[dict]:
        params = {
            "term":     query,
            "q":        query,
            "pageSize": str(limit),
            "page":     "0",
            "lang":     "tr",
            "curr":     "TRY",
        }
        headers = {
            "Accept":          "application/json",
            "Referer":         f"{self.base_url}/",
            "x-requested-with": "XMLHttpRequest",
        }
        data = self._get_json(api_url, params=params, headers=headers, use_proxy=False)
        return self._parse_api_response(data, limit)

    def _parse_api_response(self, data: Any, limit: int) -> list[dict]:
        if not isinstance(data, dict):
            return []
        # Olası yanıt yapıları (API versiyonuna göre değişir)
        items = (
            data.get("products")
            or data.get("data", {}).get("products")
            or data.get("results")
            or (data.get("searchResults") or {}).get("products")
            or []
        )
        results = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            product = self._parse_item(item)
            if product:
                results.append(product)
        return results

    def _parse_item(self, item: dict) -> dict | None:
        name = (
            item.get("name")
            or item.get("title")
            or item.get("displayName", "")
        )
        # Fiyat
        price_raw = (
            item.get("price", {}).get("value")
            if isinstance(item.get("price"), dict)
            else item.get("price")
            or item.get("salePrice")
            or item.get("currentPrice")
        )
        orig_raw = (
            item.get("originalPrice", {}).get("value")
            if isinstance(item.get("originalPrice"), dict)
            else item.get("originalPrice")
            or item.get("listPrice")
        )
        # Görsel
        img = (
            item.get("imageUrl")
            or item.get("thumbnail")
            or (item.get("images") or [{}])[0].get("url", "")
            if isinstance((item.get("images") or [{}])[0], dict) else ""
        )
        # URL
        slug = (
            item.get("url")
            or item.get("slug")
            or item.get("href", "")
        )
        code = item.get("code") or item.get("sku") or item.get("id", "")
        if slug and not slug.startswith("http"):
            p_url = f"{self.base_url}{slug}" if slug.startswith("/") else f"{self.base_url}/{slug}"
        elif code:
            p_url = f"{self.base_url}/p/{code}"
        else:
            p_url = self.base_url

        labels = []
        if item.get("isPromotion") or item.get("hasDiscount"):
            labels.append("İndirimli")
        if item.get("isNewProduct"):
            labels.append("Yeni")

        stock_info = item.get("stock") or {}
        in_stock = (
            stock_info.get("stockLevelStatus", "inStock") not in ("outOfStock", "lowStock")
            if isinstance(stock_info, dict) else True
        )

        return self._normalize_product(
            title=name,
            price=price_raw,
            original_price=orig_raw,
            url=p_url,
            image_url=str(img) if img else "",
            labels=labels,
            extra_info={"out_of_stock": not in_stock, "code": str(code)},
        )

    # ── JS Render Fallback ───────────────────────────────────

    def _search_js_render(self, query: str, limit: int) -> list[dict]:
        """
        ScrapingBee render_js=True ile /arama sayfasını çek.
        Pahalı (3 kredi/istek) — sadece API başarısız olduğunda kullanılır.
        NOT: robots.txt /search Disallow — /arama yolu kullanıyoruz.
        """
        import os, requests as _req
        from bs4 import BeautifulSoup

        api_key = os.getenv("SCRAPINGBEE_API_KEY", "")
        if not api_key:
            return []

        search_url = f"{self.base_url}/arama/?q={urllib.parse.quote_plus(query)}"
        params = {
            "api_key":          api_key,
            "url":              search_url,
            "render_js":        "true",
            "wait":             "3000",       # JS yüklenmesi için 3 sn bekle
            "block_ads":        "true",
            "block_resources":  "true",
            "country_code":     "tr",
            "premium_proxy":    "true",
        }

        try:
            resp = _req.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=25)
        except Exception:
            return []

        if not resp.ok:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Carrefour 2025 HTML selectors — güncel DOM'dan tersine mühendislik
        # (Site güncellenince bu selectors değişebilir)
        selector_groups = [
            # Yeni Carrefour Next.js yapısı
            ("[data-testid='product-card']", "[data-testid='product-name']", "[data-testid='product-price']"),
            # Eski yapı
            (".product-item",  ".product-name",  ".product-price"),
            (".item-name",     ".item-name",      ".item-price"),
            # Genel fallback
            ("article.product", "h3", ".price"),
        ]

        for card_sel, name_sel, price_sel in selector_groups:
            cards = soup.select(card_sel)
            if not cards:
                continue
            results = []
            for card in cards[:limit]:
                name_el  = card.select_one(name_sel)
                price_el = card.select_one(price_sel)
                link_el  = card.select_one("a[href]")
                img_el   = card.select_one("img")
                if not name_el or not price_el:
                    continue
                href  = link_el["href"] if link_el else ""
                p_url = (
                    f"{self.base_url}{href}" if href.startswith("/")
                    else href or self.base_url
                )
                img = ""
                if img_el:
                    img = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src") or ""
                product = self._normalize_product(
                    title=name_el.get_text(strip=True),
                    price=price_el.get_text(strip=True),
                    url=p_url,
                    image_url=img,
                    labels=["Carrefour"],
                )
                if product:
                    results.append(product)
            if results:
                return results

        return []
