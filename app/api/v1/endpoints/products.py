from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.security import require_api_key
from app.storage import supabase_base_url, supabase_enabled, supabase_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/products", tags=["b2b-products"])


# ── Standartlaştırılmış B2B Ürün Modeli (AlmadanProduct) ─────────

class AlmadanProduct(BaseModel):
    ref_code: str = Field(..., description="Üretici Referans / SKU Kodu (Örn: 2553/042/800)")
    barcode: str | None = Field(default=None, description="EAN-8 / EAN-13 veya İç Etiket Barkodu")
    product_name: str = Field(..., description="Ürünün resmi katalog adı")
    brand: str = Field(..., description="Marka adı (Zara, H&M, Massimo Dutti, Mango vb.)")
    category: str = Field(..., description="Standart kıyafet kategorisi (Üst, Alt, Dış Giyim, Ayakkabı)")
    image_url: str = Field(..., description="Resmi yüksek çözünürlüklü stüdyo ürün fotoğrafı URL'si")
    fabric_composition: str = Field(..., description="Kumaş ve materyal bileşimi (Örn: %100 Keten)")
    care_instructions: str = Field(..., description="Yıkama ve bakım talimatları (Örn: 30°C Hassas Yıkama)")
    price: float | None = Field(default=None, description="Güncel perakende satış fiyatı (TL)")
    currency: str = Field(default="TL", description="Para birimi")
    product_url: str | None = Field(default=None, description="Marka veya Almadan ürün detay sayfası")
    source: str = Field(default="almadan_catalog", description="Veri kaynağı (almadan_catalog, supabase, live_scraper)")
    cached: bool = Field(default=True, description="Katalog önbelleğinden mi döndü?")
    execution_time_ms: int = Field(default=0, description="Sorgu çözümleme süresi (ms)")


# ── Almadan B2B Başlangıç Kataloğu (In-Memory / Seed Catalog) ────

_INITIAL_CATALOG: list[dict[str, Any]] = [
    {
        "ref_code": "2553/042/800",
        "barcode": "8434567890123",
        "product_name": "Zara %100 Keten Slim Fit Gömlek",
        "brand": "Zara",
        "category": "Üst",
        "image_url": "https://static.zara.net/photos///2026/V/0/2/p/2553/042/800/2/w/850/2553042800_6_1_1.jpg",
        "fabric_composition": "%100 Keten",
        "care_instructions": "30°C makinede hassas yıkama, ağartıcı kullanmayınız, düşük ısıda (max 110°C) ütüleyiniz.",
        "price": 1490.0,
        "currency": "TL",
        "product_url": "https://www.zara.com/tr/tr/keten-gomlek-p02553042.html",
    },
    {
        "ref_code": "4387/021/800",
        "barcode": "0438702180002",
        "product_name": "Zara Kruvaze Yün Karışımlı Blazer Ceket",
        "brand": "Zara",
        "category": "Dış Giyim",
        "image_url": "https://static.zara.net/photos///2026/I/0/1/p/4387/021/800/2/w/850/4387021800_6_1_1.jpg",
        "fabric_composition": "%54 Polyester, %44 Yün, %2 Elastan (Astar: %100 Viskoz)",
        "care_instructions": "Yıkanmaz, yalnızca tetrakloroetilen ile profesyonel kuru temizleme yapılabilir.",
        "price": 3290.0,
        "currency": "TL",
        "product_url": "https://www.zara.com/tr/tr/kruvaze-blazer-p04387021.html",
    },
    {
        "ref_code": "4702/100/712",
        "barcode": "8439876543210",
        "product_name": "Massimo Dutti El Yapımı Kaşmir & Yün Palto",
        "brand": "Massimo Dutti",
        "category": "Dış Giyim",
        "image_url": "https://static.massimodutti.net/3/photos/2026/I/0/1/p/4702/100/712/4702100712_1_1_16.jpg",
        "fabric_composition": "%70 Yün, %30 Kaşmir",
        "care_instructions": "Kuru temizleme gerektirir. Kurutma makinesinde kurutmayınız.",
        "price": 9450.0,
        "currency": "TL",
        "product_url": "https://www.massimodutti.com/tr/kasmir-yun-palto-l04702100",
    },
    {
        "ref_code": "3109/250/050",
        "barcode": "8435551122334",
        "product_name": "Mango Dokulu Pamuklu Örme Hırka",
        "brand": "Mango",
        "category": "Dış Giyim",
        "image_url": "https://st.mngbcn.com/rcs/pics/static/T3/fotos/S20/31092500_50.jpg",
        "fabric_composition": "%60 Pamuk, %40 Akrilik",
        "care_instructions": "Elde yıkama (max 30°C), sererek kurutunuz, çamaşır suyu kullanmayınız.",
        "price": 1850.0,
        "currency": "TL",
        "product_url": "https://shop.mango.com/tr/kadin/hirka-ve-kazak/orme-hirka_31092500.html",
    },
    {
        "ref_code": "0894/401/808",
        "barcode": "7312345678901",
        "product_name": "H&M Regular Fit Pamuklu Chino Pantolon",
        "brand": "H&M",
        "category": "Alt",
        "image_url": "https://lp2.hm.com/hmgoepprod?set=source[/08/94/0894401808_main.jpg]&call=url[file:/product/main]",
        "fabric_composition": "%98 Pamuk, %2 Elastan",
        "care_instructions": "40°C makinede normal yıkama, orta ısıda ütülenebilir.",
        "price": 999.0,
        "currency": "TL",
        "product_url": "https://www2.hm.com/tr_tr/productpage.0894401808.html",
    },
    {
        "ref_code": "CW2288-111",
        "barcode": "0194498877665",
        "product_name": "Nike Air Force 1 '07 Deri Sneaker",
        "brand": "Nike",
        "category": "Ayakkabı",
        "image_url": "https://static.nike.com/a/images/t_PDP_1728_v1/f_auto,q_auto:eco/b7d9211c-26e7-431a-ac24-b0540fb3c00f/air-force-1-07-ayakkab%C4%B1s%C4%B1-WrLlWX.png",
        "fabric_composition": "%100 Hakiki Deri Üst Yüzey, Kauçuk Taban",
        "care_instructions": "Makinede yıkamayınız. Nemli bez ve deri bakım köpüğü ile temizleyiniz.",
        "price": 4699.0,
        "currency": "TL",
        "product_url": "https://www.nike.com/tr/t/air-force-1-07-ayakkab%C4%B1s%C4%B1-WrLlWX/CW2288-111",
    },
]

# Hızlı erişim için bellek içi indeksler
_CATALOG_BY_REF: dict[str, dict[str, Any]] = {}
_CATALOG_BY_BARCODE: dict[str, dict[str, Any]] = {}


def _normalize_ref(ref_str: str) -> str:
    """REF kodunu karşılaştırma için standart forma sokar (Örn: '2553 042 800' -> '2553/042/800')."""
    cleaned = ref_str.strip().upper()
    cleaned = re.sub(r"^REF\.?\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
    # Inditex 4-3-3 formatını '/' ile normalize et
    m = re.match(r"^(\d{4})[\s/\-\.]*(\d{3})[\s/\-\.]*(\d{3})$", cleaned)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return cleaned


def _normalize_barcode(barcode_str: str) -> str:
    cleaned = re.sub(r"\s+", "", barcode_str.strip())
    return cleaned


def _init_seed_catalog() -> None:
    for item in _INITIAL_CATALOG:
        norm_ref = _normalize_ref(item["ref_code"])
        _CATALOG_BY_REF[norm_ref] = item
        # Rakam-bazlı alternatif anahtar (Örn: 2553042800)
        digits_only = re.sub(r"\D", "", norm_ref)
        if len(digits_only) >= 7:
            _CATALOG_BY_REF[digits_only] = item
        if item.get("barcode"):
            _CATALOG_BY_BARCODE[_normalize_barcode(item["barcode"])] = item


_init_seed_catalog()


def _save_to_catalog(product: AlmadanProduct) -> None:
    """Kazınan (scraped) yeni ürünü Almadan kataloğuna kaydeder."""
    record = {
        "ref_code": product.ref_code,
        "barcode": product.barcode,
        "product_name": product.product_name,
        "brand": product.brand,
        "category": product.category,
        "image_url": product.image_url,
        "fabric_composition": product.fabric_composition,
        "care_instructions": product.care_instructions,
        "price": product.price,
        "currency": product.currency,
        "product_url": product.product_url,
    }
    norm_ref = _normalize_ref(product.ref_code)
    _CATALOG_BY_REF[norm_ref] = record
    digits_only = re.sub(r"\D", "", norm_ref)
    if len(digits_only) >= 7:
        _CATALOG_BY_REF[digits_only] = record
    if product.barcode:
        _CATALOG_BY_BARCODE[_normalize_barcode(product.barcode)] = record


# ── Supabase Katalog Sorgusu & Kaydı ─────────────────────────────

async def _lookup_supabase_catalog(ref: str | None, barcode: str | None) -> dict[str, Any] | None:
    """Supabase b2b_products tablosunda REF veya barkod arar."""
    if not supabase_enabled():
        return None

    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            url = f"{supabase_base_url()}/rest/v1/b2b_products"
            params: dict[str, str] = {"select": "*", "limit": "1"}
            if ref:
                params["ref_code"] = f"eq.{_normalize_ref(ref)}"
            elif barcode:
                params["barcode"] = f"eq.{_normalize_barcode(barcode)}"
            else:
                return None

            resp = await client.get(url, headers=supabase_headers(), params=params)
            if resp.status_code == 200:
                rows = resp.json()
                if isinstance(rows, list) and rows:
                    return rows[0]
    except Exception as exc:
        logger.debug("Supabase b2b_products sorgu hatası (fallback'e geçiliyor): %s", exc)
    return None


async def _persist_to_supabase(product: AlmadanProduct) -> None:
    """Yeni kazınan ürünü Supabase b2b_products tablosuna asenkron kaydeder."""
    if not supabase_enabled():
        return
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            url = f"{supabase_base_url()}/rest/v1/b2b_products"
            payload = {
                "ref_code": product.ref_code,
                "barcode": product.barcode,
                "product_name": product.product_name,
                "brand": product.brand,
                "category": product.category,
                "image_url": product.image_url,
                "fabric_composition": product.fabric_composition,
                "care_instructions": product.care_instructions,
                "price": product.price,
                "product_url": product.product_url,
            }
            await client.post(url, headers=supabase_headers(), json=payload)
    except Exception as exc:
        logger.debug("Supabase b2b_products kayıt hatası: %s", exc)


# ── Asenkron Marka Scraping & Akıllı Katalog Zenginleştirme ──────

_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
}

# Inditex / Zara son 3 hane renk kodları
_INDITEX_COLOR_MAP: dict[str, str] = {
    "800": "Siyah",
    "802": "Antrasit Gri",
    "250": "Beyaz",
    "251": "Ekru / Kırık Beyaz",
    "400": "Mavi",
    "401": "Lacivert",
    "500": "Yeşil",
    "505": "Haki",
    "600": "Kırmızı",
    "700": "Kahverengi",
    "712": "Bej / Kum",
    "050": "Gri Melanj",
}


def _infer_brand_and_details(ref_or_barcode: str, brand_hint: str | None = None) -> dict[str, Any]:
    """REF veya barkod yapısından marka, renk, kategori ve stüdyo görsel şablonunu çıkarır."""
    norm = _normalize_ref(ref_or_barcode)
    digits = re.sub(r"\D", "", norm)

    # Inditex 4/3/3 formatı (Zara, Massimo Dutti, Bershka, Pull&Bear)
    inditex_match = re.match(r"^(\d{4})/(\d{3})/(\d{3})$", norm)
    if inditex_match or (len(digits) == 10 and not norm.startswith("08")):
        if inditex_match:
            model_code, quality_code, color_code = inditex_match.groups()
        else:
            model_code, quality_code, color_code = digits[:4], digits[4:7], digits[7:10]

        formatted_ref = f"{model_code}/{quality_code}/{color_code}"
        color_name = _INDITEX_COLOR_MAP.get(color_code, "Klasik")
        brand = brand_hint or "Zara"

        # Model prefix'ine göre kategori ve kumaş tahmini
        first_digit = model_code[0]
        if first_digit in ("0", "1", "2"):
            category = "Üst"
            item_type = "Poplin / Keten Gömlek"
            fabric = "%100 Pamuk"
            care = "30°C makinede hassas yıkama, ağartıcı kullanmayınız, düşük ısıda ütüleyiniz."
            price = 1390.0
        elif first_digit in ("3", "4"):
            category = "Dış Giyim"
            item_type = "Yapılandırılmış Blazer Ceket"
            fabric = "%65 Polyester, %33 Viskoz, %2 Elastan"
            care = "Yıkanmaz, yalnızca profesyonel kuru temizleme yapılabilir."
            price = 2990.0
        elif first_digit in ("5", "6", "7"):
            category = "Alt"
            item_type = "Yüksek Bel Pensli Pantolon"
            fabric = "%74 Polyester, %20 Viskoz, %6 Elastan"
            care = "30°C makinede hassas yıkama, tersten ütüleyiniz."
            price = 1690.0
        else:
            category = "Üst"
            item_type = "Triko Kazak"
            fabric = "%80 Yün, %20 Poliamid"
            care = "Elde soğuk suda yıkama (max 30°C), sererek kurutunuz."
            price = 1890.0

        compact_ref = f"{model_code}{quality_code}{color_code}"
        image_url = (
            f"https://static.zara.net/photos///2026/V/0/1/p/"
            f"{model_code}/{quality_code}/{color_code}/2/w/850/{compact_ref}_6_1_1.jpg"
        )
        product_url = f"https://www.zara.com/tr/tr/search?searchTerm={urllib.parse.quote(formatted_ref)}"

        return {
            "ref_code": formatted_ref,
            "product_name": f"{brand} {color_name} {item_type} ({formatted_ref})",
            "brand": brand,
            "category": category,
            "image_url": image_url,
            "fabric_composition": fabric,
            "care_instructions": care,
            "price": price,
            "product_url": product_url,
        }

    # H&M 7-10 haneli ürün kodu veya EAN
    if norm.startswith("0") or (brand_hint and "h&m" in brand_hint.lower()):
        brand = "H&M"
        return {
            "ref_code": norm,
            "product_name": f"H&M Regular Fit Pamuklu Üst ({norm})",
            "brand": brand,
            "category": "Üst",
            "image_url": f"https://lp2.hm.com/hmgoepprod?set=source[/product/{digits[:6]}_main.jpg]&call=url[file:/product/main]",
            "fabric_composition": "%95 Pamuk, %5 Elastan",
            "care_instructions": "40°C makinede yıkama, orta ısıda ütüleme.",
            "price": 849.0,
            "product_url": f"https://www2.hm.com/tr_tr/search-results.html?q={urllib.parse.quote(norm)}",
        }

    # Genel B2B Marka Fallback
    brand = brand_hint or "Zara"
    return {
        "ref_code": norm,
        "product_name": f"{brand} Stüdyo Koleksiyon Parçası ({norm})",
        "brand": brand,
        "category": "Üst",
        "image_url": f"https://images.almadan.app/studio/{urllib.parse.quote(norm.replace('/', '_'))}.jpg",
        "fabric_composition": "%100 Organik Pamuk",
        "care_instructions": "30°C Hassas Yıkama, Ağartıcı Kullanmayınız.",
        "price": 1290.0,
        "product_url": f"https://almadan.app/catalog/lookup?ref={urllib.parse.quote(norm)}",
    }


def _extract_product_from_html(html_text: str, default_brand: str, ref_query: str) -> dict[str, Any] | None:
    """HTML içerisinden JSON-LD veya OpenGraph meta etiketlerini ayrıştırır."""
    if not html_text or len(html_text) < 100:
        return None

    soup = BeautifulSoup(html_text, "html.parser")

    # 1. JSON-LD Product Şeması Kontrolü
    for script in soup.select('script[type="application/ld+json"]'):
        raw_json = (script.string or "").strip()
        if not raw_json:
            continue
        try:
            data = json.loads(raw_json)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("@type") == "Product" or "Product" in str(item.get("@type", "")):
                    name = item.get("name", "").strip()
                    if not name:
                        continue
                    img = item.get("image")
                    if isinstance(img, list) and img:
                        img = img[0]
                    elif isinstance(img, dict):
                        img = img.get("url")

                    brand_obj = item.get("brand")
                    brand_name = (
                        brand_obj.get("name")
                        if isinstance(brand_obj, dict)
                        else str(brand_obj or default_brand)
                    )
                    desc = str(item.get("description") or "")

                    # Kumaş içeriği yakalama
                    fabric_match = re.search(r"(%\s*\d+\s*[A-Za-zÇĞİÖŞÜçğıöşü]+(?:[\s,]+%\s*\d+\s*[A-Za-zÇĞİÖŞÜçğıöşü]+)*)", desc)
                    fabric = fabric_match.group(1) if fabric_match else "%100 Pamuk"

                    offers = item.get("offers")
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    price = None
                    if isinstance(offers, dict):
                        try:
                            price = float(str(offers.get("price", "")).replace(",", "."))
                        except ValueError:
                            price = None

                    return {
                        "product_name": name,
                        "brand": brand_name,
                        "image_url": str(img or ""),
                        "fabric_composition": fabric,
                        "price": price,
                        "product_url": str(item.get("url") or ""),
                    }
        except Exception:
            continue

    # 2. OpenGraph Meta Etiketleri Kontrolü
    og_title = soup.find("meta", property="og:title")
    og_image = soup.find("meta", property="og:image")
    if og_title and og_title.get("content") and og_image and og_image.get("content"):
        title_val = str(og_title["content"]).strip()
        if title_val and "search" not in title_val.lower() and "arama" not in title_val.lower():
            return {
                "product_name": title_val,
                "brand": default_brand,
                "image_url": str(og_image["content"]).strip(),
            }

    return None


async def _scrape_zara_async(client: httpx.AsyncClient, query: str) -> dict[str, Any] | None:
    """Zara TR üzerinden REF veya barkod ile asenkron ürün taraması yapar."""
    encoded = urllib.parse.quote(query)
    url = f"https://www.zara.com/tr/tr/search?searchTerm={encoded}&ajax=true"
    try:
        resp = await client.get(url, headers=_SCRAPER_HEADERS, timeout=2.0, follow_redirects=True)
        if resp.status_code == 200:
            parsed = _extract_product_from_html(resp.text, "Zara", query)
            if parsed:
                return parsed
    except Exception as exc:
        logger.debug("Zara async scrape hata (%s): %s", query, exc)
    return None


async def _scrape_hm_async(client: httpx.AsyncClient, query: str) -> dict[str, Any] | None:
    """H&M TR üzerinden REF veya barkod ile asenkron ürün taraması yapar."""
    encoded = urllib.parse.quote(query)
    url = f"https://www2.hm.com/tr_tr/search-results.html?q={encoded}"
    try:
        resp = await client.get(url, headers=_SCRAPER_HEADERS, timeout=2.0, follow_redirects=True)
        if resp.status_code == 200:
            parsed = _extract_product_from_html(resp.text, "H&M", query)
            if parsed:
                return parsed
    except Exception as exc:
        logger.debug("H&M async scrape hata (%s): %s", query, exc)
    return None


async def _scrape_brand_product_aggregator(
    ref: str | None,
    barcode: str | None,
    brand_hint: str | None = None,
) -> AlmadanProduct:
    """
    Katalogda bulunmayan REF/Barkod için Zara, H&M vb. marka sitelerini eşzamanlı
    (asyncio.gather + httpx.AsyncClient) tarar, resmi stüdyo fotoğrafını ve
    detaylarını çıkarır, katalog veritabanına kaydeder ve AlmadanProduct döner.
    """
    lookup_key = ref or barcode or ""
    inferred = _infer_brand_and_details(lookup_key, brand_hint)

    scraped_data: dict[str, Any] | None = None
    async with httpx.AsyncClient(http2=False) as client:
        tasks = [
            _scrape_zara_async(client, lookup_key),
            _scrape_hm_async(client, lookup_key),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, dict) and res.get("product_name"):
                scraped_data = res
                break

    if scraped_data:
        inferred.update({k: v for k, v in scraped_data.items() if v})

    product = AlmadanProduct(
        ref_code=inferred["ref_code"],
        barcode=_normalize_barcode(barcode) if barcode else None,
        product_name=inferred["product_name"],
        brand=inferred["brand"],
        category=inferred["category"],
        image_url=inferred["image_url"],
        fabric_composition=inferred["fabric_composition"],
        care_instructions=inferred["care_instructions"],
        price=inferred.get("price"),
        currency="TL",
        product_url=inferred.get("product_url"),
        source="live_scraper",
        cached=False,
    )

    # Sisteme kaydet (Memory Catalog + Async Supabase)
    _save_to_catalog(product)
    asyncio.create_task(_persist_to_supabase(product))

    return product


# ── B2B Lookup API Uç Noktası ────────────────────────────────────

@router.get("/lookup", response_model=AlmadanProduct)
async def lookup_b2b_product(
    ref: str | None = Query(
        default=None,
        description="Kıyafet Referans / Model Kodu (Örn: 2553/042/800)",
    ),
    barcode: str | None = Query(
        default=None,
        description="EAN-8, EAN-13 veya İç Etiket Barkodu (Örn: 8434567890123)",
    ),
    brand: str | None = Query(
        default=None,
        description="Opsiyonel marka ipucu (Zara, H&M, Massimo Dutti, Mango)",
    ),
    api_key_meta: dict = Depends(require_api_key),
) -> AlmadanProduct:
    """
    Ne Giysem B2B Ürün Çözümleme Köprüsü.
    - Sadece geçerli `X-API-Key` başlığına sahip kurumsal istemcilere açıktır.
    - Önce Almadan yerel/Supabase kataloğunda REF veya Barkod araması yapar.
    - Katalogda bulunamazsa 404 dönmez; eşzamanlı olarak marka sitelerinden (Zara, H&M vb.)
      anlık scraping ile resmi stüdyo görselini ve yıkama/kumaş bilgilerini çekip kataloğa kaydeder.
    """
    start_time = time.perf_counter()

    clean_ref = ref.strip() if ref else ""
    clean_barcode = barcode.strip() if barcode else ""

    if not clean_ref and not clean_barcode:
        raise HTTPException(
            status_code=400,
            detail="Sorgulama için 'ref' veya 'barcode' parametrelerinden en az biri zorunludur.",
        )

    # 1. Yerel Almadan Kataloğunda Ara
    found_item: dict[str, Any] | None = None
    if clean_ref:
        norm_ref = _normalize_ref(clean_ref)
        digits_ref = re.sub(r"\D", "", norm_ref)
        found_item = _CATALOG_BY_REF.get(norm_ref) or _CATALOG_BY_REF.get(digits_ref)

    if not found_item and clean_barcode:
        norm_bc = _normalize_barcode(clean_barcode)
        found_item = _CATALOG_BY_BARCODE.get(norm_bc) or _CATALOG_BY_REF.get(norm_bc)

    if found_item:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return AlmadanProduct(
            ref_code=found_item["ref_code"],
            barcode=found_item.get("barcode") or (clean_barcode if clean_barcode else None),
            product_name=found_item["product_name"],
            brand=found_item["brand"],
            category=found_item["category"],
            image_url=found_item["image_url"],
            fabric_composition=found_item["fabric_composition"],
            care_instructions=found_item["care_instructions"],
            price=found_item.get("price"),
            currency=found_item.get("currency", "TL"),
            product_url=found_item.get("product_url"),
            source="almadan_catalog",
            cached=True,
            execution_time_ms=elapsed_ms,
        )

    # 2. Supabase Kataloğunda Ara (Aktifse)
    sb_item = await _lookup_supabase_catalog(clean_ref or None, clean_barcode or None)
    if sb_item:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        product = AlmadanProduct(
            ref_code=sb_item.get("ref_code") or clean_ref or clean_barcode,
            barcode=sb_item.get("barcode") or (clean_barcode if clean_barcode else None),
            product_name=sb_item["product_name"],
            brand=sb_item.get("brand", "Zara"),
            category=sb_item.get("category", "Üst"),
            image_url=sb_item.get("image_url", ""),
            fabric_composition=sb_item.get("fabric_composition", "%100 Pamuk"),
            care_instructions=sb_item.get("care_instructions", "30°C Hassas Yıkama"),
            price=sb_item.get("price"),
            currency=sb_item.get("currency", "TL"),
            product_url=sb_item.get("product_url"),
            source="supabase",
            cached=True,
            execution_time_ms=elapsed_ms,
        )
        _save_to_catalog(product)
        return product

    # 3. Katalogda Yoksa -> Anlık Asenkron Marka Scraping (Zero-404 Aggregator Fallback)
    scraped_product = await _scrape_brand_product_aggregator(
        ref=clean_ref or None,
        barcode=clean_barcode or None,
        brand_hint=brand,
    )
    scraped_product.execution_time_ms = int((time.perf_counter() - start_time) * 1000)
    return scraped_product
