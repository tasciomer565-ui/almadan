"""
A101Scraper — a101.com.tr ürün araması

Durum: a101.com.tr robots.txt → 403 (tamamen bloklu)
Sayfa: Dinamik React/Next.js — JS render zorunlu

Strateji:
  1. A101 dahili API adayları (Next.js data fetching endpoint'leri)
  2. ScrapingBee render_js=True
  3. A101 genellikle indirim broşürü satışı yapar — fiyat karşılaştırması sınırlıdır

NOT: A101/BİM/ŞOK çoğunlukla fiziksel mağaza odaklı zincirlerdir.
     Online alışveriş katalogları sınırlıdır.
     Başarı oranı Migros/Carrefour'dan düşük beklenmelidir.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from app.scrapers.base import BaseScraper, ScraperError

_API_CANDIDATES = [
    "https://www.a101.com.tr/api/products/search",
    "https://www.a101.com.tr/_next/data/search",
    "https://www.a101.com.tr/api/search",
]


class A101Scraper(BaseScraper):

    name = "a101"
    base_url = "https://www.a101.com.tr"
    category = "GIDA"

    min_delay = 2.0
    max_delay = 5.0
    max_retries = 2

    def search(self, query: str, limit: int = 10) -> list[dict]:
        # 1. API adayları
        for api_url in _API_CANDIDATES:
            try:
                results = self._try_json_api(query, api_url, limit)
                if results:
                    return results
            except Exception:
                continue

        # 2. JS render
        if self._proxy_enabled:
            try:
                return self._search_js_render(query, limit)
            except Exception:
                pass

        return []

    def _try_json_api(self, query: str, api_url: str, limit: int) -> list[dict]:
        params = {"q": query, "query": query, "page": "1", "limit": str(limit)}
        data   = self._get_json(api_url, params=params, use_proxy=False)
        return self._parse(data, limit)

    def _parse(self, data: Any, limit: int) -> list[dict]:
        if not isinstance(data, dict):
            return []
        items = (
            data.get("products")
            or data.get("data", {}).get("products")
            or data.get("items")
            or data.get("results")
            or []
        )
        results = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            name      = item.get("name") or item.get("title", "")
            price_raw = item.get("price") or item.get("salePrice") or item.get("currentPrice")
            orig_raw  = item.get("originalPrice") or item.get("listPrice")
            img       = item.get("imageUrl") or item.get("image", "")
            slug      = item.get("url") or item.get("slug", "")
            p_url     = (
                f"{self.base_url}/{slug.lstrip('/')}" if slug else self.base_url
            )
            product = self._normalize_product(
                title=name, price=price_raw, original_price=orig_raw,
                url=p_url, image_url=str(img) if img else "",
                labels=["A101"],
            )
            if product:
                results.append(product)
        return results

    def _search_js_render(self, query: str, limit: int) -> list[dict]:
        import os
        import requests as _req
        from bs4 import BeautifulSoup

        api_key = os.getenv("SCRAPINGBEE_API_KEY", "")
        if not api_key:
            return []

        url = f"{self.base_url}/arama/?q={urllib.parse.quote_plus(query)}"
        params = {
            "api_key":         api_key,
            "url":             url,
            "render_js":       "true",
            "wait":            "4000",
            "block_ads":       "true",
            "block_resources": "true",
            "country_code":    "tr",
            "premium_proxy":   "true",
        }
        try:
            resp = _req.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=30)
        except Exception:
            return []

        if not resp.ok:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        selectors = [
            (".product-card",  ".product-title",   ".price"),
            (".product-item",  ".product-name",    ".product-price"),
            ("article",        "h2",               "[class*='price']"),
        ]
        for card_sel, name_sel, price_sel in selectors:
            cards = soup.select(card_sel)
            if not cards:
                continue
            results = []
            for card in cards[:limit]:
                n_el = card.select_one(name_sel)
                p_el = card.select_one(price_sel)
                l_el = card.select_one("a[href]")
                i_el = card.select_one("img")
                if not n_el or not p_el:
                    continue
                href  = l_el["href"] if l_el else ""
                p_url = f"{self.base_url}{href}" if href.startswith("/") else href or self.base_url
                img   = (i_el.get("src") or i_el.get("data-src") or "") if i_el else ""
                product = self._normalize_product(
                    title=n_el.get_text(strip=True),
                    price=p_el.get_text(strip=True),
                    url=p_url, image_url=img,
                )
                if product:
                    results.append(product)
            if results:
                return results
        return []
