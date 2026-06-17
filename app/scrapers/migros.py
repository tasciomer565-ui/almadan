"""
MigrosScraper — migros.com.tr ürün araması

Endpoint Stratejisi (sırayla denenir):
  1. /hermes/api/product/search         — Yeni API (2025+)
  2. /rest/search-gateway/v2/product/search — Eski API (yedek)
  3. /rest/search-gateway/v3/product/search — v3 varyant
  4. HTML scraping (ScrapingBee ile)     — Son çare

robots.txt Analizi:
  - /search yolu BLOKLU DEĞİL (sadece Asya botları engellenmiş)
  - API uç noktaları da bloklu değil
  - Crawl-delay belirtilmemiş

Ürün URL Formatı:
  https://www.migros.com.tr/{slug}-p-{sku}
  Örn: /yayla-pirinc-1-kg-p-f69a4
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from app.scrapers.base import BaseScraper, ScraperError, BotDetectedError

# API endpoint adayları — başarılı olan önbelleğe alınır
_API_CANDIDATES = [
    # Format: (url_template, response_parser_key)
    (
        "https://www.migros.com.tr/hermes/api/product/search",
        "hermes_v1",
    ),
    (
        "https://www.migros.com.tr/rest/search-gateway/v2/product/search",
        "rest_v2",
    ),
    (
        "https://www.migros.com.tr/rest/search-gateway/v3/product/search",
        "rest_v3",
    ),
]

_WORKING_ENDPOINT: dict[str, str | None] = {"url": None, "parser": None}


class MigrosScraper(BaseScraper):
    """
    Migros.com.tr ürün araması.

    Kullanım:
        scraper = MigrosScraper()
        products = scraper.search("beyaz peynir 500g")
    """

    name = "migros"
    base_url = "https://www.migros.com.tr"
    category = "GIDA"

    # Migros API nispeten hızlı, kısa bekleme yeterli
    min_delay = 0.5
    max_delay = 1.5

    # ── Public ───────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Migros'ta ürün ara. Boş liste döner, exception fırlatmaz.

        Strateji:
          1. Önbellekte çalışan endpoint varsa direkt kullan
          2. Yoksa tüm adayları sırayla dene
          3. Hepsi başarısız → HTML scraping (ScrapingBee)
        """
        results: list[dict] = []

        # Önbellekte çalışan endpoint var mı?
        if _WORKING_ENDPOINT["url"]:
            try:
                results = self._search_api(
                    query, _WORKING_ENDPOINT["url"], _WORKING_ENDPOINT["parser"], limit
                )
                if results:
                    return results
            except (ScraperError, BotDetectedError, Exception):
                # Endpoint bozulmuş olabilir, sıfırla
                _WORKING_ENDPOINT["url"] = None
                _WORKING_ENDPOINT["parser"] = None

        # Endpoint adaylarını sırayla dene
        for api_url, parser_key in _API_CANDIDATES:
            try:
                results = self._search_api(query, api_url, parser_key, limit)
                if results:
                    # Çalışanı önbelleğe al
                    _WORKING_ENDPOINT["url"] = api_url
                    _WORKING_ENDPOINT["parser"] = parser_key
                    return results
            except ScraperError as e:
                if not e.retryable:
                    continue   # 404 gibi kalıcı hata → sonraki adayı dene
            except Exception:
                continue

        # API başarısız → HTML fallback
        try:
            results = self._search_html(query, limit)
        except Exception:
            pass

        return results

    def get_product(self, sku: str) -> dict | None:
        """SKU ile tekil ürün detayı çek."""
        try:
            data = self._get_json(
                f"{self.base_url}/hermes/api/product/{sku}",
                use_proxy=False,
            )
            return self._parse_hermes_item(data)
        except Exception:
            return None

    # ── API Arama ────────────────────────────────────────────

    def _search_api(
        self, query: str, api_url: str, parser_key: str, limit: int
    ) -> list[dict]:
        params = self._build_params(query, parser_key)
        headers = {
            "Accept":       "application/json, text/plain, */*",
            "Referer":      f"{self.base_url}/",
            "Origin":       self.base_url,
            "x-requested-with": "XMLHttpRequest",
        }
        data = self._get_json(api_url, params=params, headers=headers, use_proxy=False)
        return self._parse_response(data, parser_key, limit)

    @staticmethod
    def _build_params(query: str, parser_key: str) -> dict:
        base = {"query": query, "sayfa": "0", "siralamaTipi": "0"}
        if parser_key == "hermes_v1":
            base = {"q": query, "page": "0", "size": "20", "sort": "RELEVANCE"}
        return base

    def _parse_response(self, data: Any, parser_key: str, limit: int) -> list[dict]:
        if parser_key == "hermes_v1":
            return self._parse_hermes_response(data, limit)
        return self._parse_rest_response(data, limit)

    def _parse_hermes_response(self, data: Any, limit: int) -> list[dict]:
        """Yeni /hermes/api/ yanıt formatı."""
        if not isinstance(data, dict):
            return []
        # Olası anahtar yolları
        items = (
            data.get("products")
            or data.get("data", {}).get("products")
            or data.get("result", {}).get("products")
            or data.get("items")
            or []
        )
        results = []
        for item in items[:limit]:
            product = self._parse_hermes_item(item)
            if product:
                results.append(product)
        return results

    def _parse_hermes_item(self, item: dict) -> dict | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name") or item.get("displayName") or item.get("title", "")
        # Fiyat alanları — yeni API farklı isimler kullanabilir
        price_raw = (
            item.get("shownPrice")
            or item.get("salePrice")
            or item.get("price")
            or (item.get("pricing", {}) or {}).get("currentPrice")
        )
        original_raw = (
            item.get("listPrice")
            or item.get("regularPrice")
            or (item.get("pricing", {}) or {}).get("originalPrice")
        )
        # Görsel
        images = item.get("images") or []
        img = ""
        if images and isinstance(images, list):
            img = images[0].get("url", "") if isinstance(images[0], dict) else str(images[0])
        else:
            img = (
                item.get("imageUrl")
                or item.get("image", {}).get("url", "")
                if isinstance(item.get("image"), dict) else item.get("image", "")
            )
        # URL
        sku  = item.get("sku") or item.get("id") or item.get("productCode", "")
        slug = item.get("url") or item.get("slug") or item.get("prettyName", "")
        if slug and not slug.startswith("http"):
            product_url = f"{self.base_url}/{slug}"
        elif sku:
            product_url = f"{self.base_url}/p/{sku}"
        else:
            product_url = self.base_url

        # Stok
        in_stock = item.get("status", "IN_SALE") in ("IN_SALE", "ACTIVE", "in_stock")

        labels = []
        if item.get("isCampaign") or item.get("hasPromotion"):
            labels.append("Kampanyalı")

        return self._normalize_product(
            title=name,
            price=price_raw,
            original_price=original_raw,
            url=product_url,
            image_url=str(img),
            labels=labels,
            extra_info={"out_of_stock": not in_stock, "sku": str(sku)},
        )

    def _parse_rest_response(self, data: Any, limit: int) -> list[dict]:
        """Eski /rest/search-gateway/ yanıt formatı."""
        if not isinstance(data, dict):
            return []
        items = (
            data.get("data", {}).get("products")
            or data.get("products")
            or []
        )
        results = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            name     = item.get("name") or item.get("title", "")
            price_r  = item.get("salePrice") or item.get("price") or item.get("listPrice")
            orig_r   = item.get("listPrice") if item.get("salePrice") else None
            img      = item.get("imageUrl") or (
                item.get("image", {}).get("url", "")
                if isinstance(item.get("image"), dict) else item.get("image", "")
            )
            slug     = item.get("url") or item.get("slug", "")
            p_url    = (
                f"{self.base_url}/{slug}" if slug and not slug.startswith("http")
                else slug or self.base_url
            )
            labels   = ["Kampanyalı"] if item.get("campaignUnit") else []
            product  = self._normalize_product(
                title=name, price=price_r, original_price=orig_r,
                url=p_url, image_url=str(img), labels=labels,
                extra_info={"out_of_stock": False},
            )
            if product:
                results.append(product)
        return results

    # ── HTML Fallback ────────────────────────────────────────

    def _search_html(self, query: str, limit: int) -> list[dict]:
        """
        ScrapingBee ile Migros arama sayfasını HTML olarak çek.
        JS render gerekebilir (render_js=True).
        """
        url = f"{self.base_url}/arama?q={urllib.parse.quote_plus(query)}"
        try:
            # Önce JS render olmadan dene (1 kredi)
            resp = self._get(url, use_proxy=True)
            soup_html = resp.text
        except Exception:
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(soup_html, "html.parser")

        # Migros 2025 HTML selectors (ürün kartları)
        # Olası sınıf adları — site güncellenince burayı revize et
        selectors = [
            (".product-list-item",        ".product-name",  ".price"),
            ("[data-testid='product']",   "h3",             "[data-testid='price']"),
            (".product-card",             ".name",          ".price"),
        ]

        for card_sel, name_sel, price_sel in selectors:
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
                href = link_el["href"] if link_el else ""
                p_url = (
                    f"{self.base_url}{href}" if href.startswith("/") else href or self.base_url
                )
                img = ""
                if img_el:
                    img = img_el.get("src") or img_el.get("data-src") or ""
                product = self._normalize_product(
                    title=name_el.get_text(strip=True),
                    price=price_el.get_text(strip=True),
                    url=p_url,
                    image_url=img,
                    labels=["HTML Fallback"],
                )
                if product:
                    results.append(product)
            if results:
                return results

        return []
