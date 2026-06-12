from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.parser import USER_AGENT
from app.storage import utc_now


@dataclass(frozen=True)
class CatalogSource:
    store: str
    title: str
    url: str
    keywords: tuple[str, ...]


CATALOG_SOURCES = (
    CatalogSource(
        "bim",
        "BİM Aktüel Ürünler",
        "https://www.bim.com.tr/categories/100/aktuel-urunler.aspx",
        ("yağ", "şeker", "un", "bakliyat", "makarna", "pirinç", "süt", "peynir"),
    ),
    CatalogSource(
        "a101",
        "A101 Aldın Aldın",
        "https://www.a101.com.tr/aldin-aldin-bu-hafta-brosuru",
        ("deterjan", "sabun", "temizlik", "kağıt", "su", "çay", "kahve"),
    ),
    CatalogSource(
        "a101_yildiz",
        "A101 Haftanın Yıldızları",
        "https://www.a101.com.tr/afisler-haftanin-yildizlari",
        ("yağ", "süt", "peynir", "kahve", "çay", "atıştırmalık", "temizlik"),
    ),
    CatalogSource(
        "sok",
        "Şok Haftanın Fırsatları",
        "https://kurumsal.sokmarket.com.tr/firsatlar/haftanin-firsatlari",
        ("yağ", "süt", "peynir", "yumurta", "deterjan", "makarna", "kahve"),
    ),
    CatalogSource(
        "file",
        "File Market Fırsatları",
        "https://www.file.com.tr/",
        ("et", "tavuk", "süt", "peynir", "zeytin", "kahvaltı", "temizlik"),
    ),
    CatalogSource(
        "metro",
        "Metro Güncel Promosyonlar",
        "https://www.metro-tr.com/promosyonlar",
        ("kg", "litre", "paket", "koli", "deterjan", "kahve", "içecek"),
    ),
    CatalogSource(
        "carrefoursa",
        "CarrefourSA Katalogları",
        "https://www.carrefoursa.com/kataloglar",
        ("meyve", "sebze", "et", "süt", "peynir", "atıştırmalık", "temizlik"),
    ),
    CatalogSource(
        "migros",
        "Migroskop Fırsatları",
        "https://www.migros.com.tr/migroskop-urunleri-dt-3",
        ("money", "yağ", "şeker", "kahve", "çay", "deterjan", "kişisel bakım"),
    ),
    CatalogSource(
        "gratis",
        "Gratis Kampanyaları",
        "https://www.gratis.com/kampanyalar",
        ("şampuan", "krem", "parfüm", "makyaj", "ruj", "maskara", "saç", "bakım"),
    ),
)


def normalize_catalog_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_catalog_items(html: str, limit: int = 80) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(("script", "style", "noscript", "svg")):
        tag.decompose()

    candidates: list[str] = []
    selectors = (
        "h1",
        "h2",
        "h3",
        "h4",
        "[class*='product-name']",
        "[class*='productName']",
        "[class*='title']",
        "[class*='campaign']",
        "[class*='catalog']",
    )
    for selector in selectors:
        for node in soup.select(selector):
            text = normalize_catalog_text(node.get_text(" ", strip=True))
            if 4 <= len(text) <= 140:
                candidates.append(text)

    if not candidates:
        text = normalize_catalog_text(soup.get_text(" ", strip=True))
        candidates = [
            part.strip()
            for part in re.split(r"[|•\n]", text)
            if 4 <= len(part.strip()) <= 140
        ]

    unique: list[str] = []
    seen = set()
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def fetch_catalog(
    source: CatalogSource,
    *,
    timeout: int = 15,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    client = session or requests
    response = client.get(
        source.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    items = extract_catalog_items(response.text)
    normalized = "\n".join(item.casefold() for item in items)
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return {
        "store": source.store,
        "title": source.title,
        "url": str(response.url or source.url),
        "items": items,
        "keywords": list(source.keywords),
        "fingerprint": fingerprint,
        "checked_at": utc_now(),
        "ok": bool(items),
    }


def fetch_all_catalogs() -> list[dict[str, Any]]:
    snapshots_by_store: dict[str, dict[str, Any]] = {}

    def fetch_one(source: CatalogSource) -> dict[str, Any]:
        try:
            return fetch_catalog(source, timeout=8)
        except requests.RequestException as exc:
            return {
                "store": source.store,
                "title": source.title,
                "url": source.url,
                "items": [],
                "keywords": list(source.keywords),
                "fingerprint": None,
                "checked_at": utc_now(),
                "ok": False,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_one, source): source.store
            for source in CATALOG_SOURCES
        }
        for future in as_completed(futures):
            snapshots_by_store[futures[future]] = future.result()

    return [
        snapshots_by_store[source.store]
        for source in CATALOG_SOURCES
    ]


def catalog_matches_product(snapshot: dict[str, Any], product_title: str) -> bool:
    title = product_title.casefold()
    catalog_text = " ".join(snapshot.get("items", [])).casefold()
    significant_words = {
        word
        for word in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", title)
        if len(word) >= 4
    }
    if significant_words and sum(word in catalog_text for word in significant_words) >= min(
        2, len(significant_words)
    ):
        return True
    return any(keyword.casefold() in title for keyword in snapshot.get("keywords", []))
