from __future__ import annotations

import json
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import requests
def BeautifulSoup(markup, features="html.parser", **kwargs):
    from bs4 import BeautifulSoup as _BS
    return _BS(markup, features, **kwargs)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

TRACKING_QUERY_KEYS = {
    "adjust_campaign",
    "adjust_t",
    "gads",
    "savetranslate",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def normalize_product_url(url: str) -> str:
    """Kopyalanmış/deep-link ürün adresini kararlı bir HTTPS adresine çevir."""
    value = translate_deep_link(str(url or "").strip())
    if not value:
        return value
    if "://" not in value and "." in value:
        value = f"https://{value.lstrip('/')}"

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        return value

    host = parsed.netloc.lower()
    if host == "trendyol.com":
        host = "www.trendyol.com"

    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=False)
        if key.casefold() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit(("https", host, parsed.path or "/", urlencode(query), ""))


def product_fetch_url(url: str, source: str) -> str:
    """Mağazanın sunucu bölgesine göre yanlış locale'e yönlenmesini engelle."""
    if source != "trendyol":
        return url
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"countryCode": "TR", "language": "tr", "storefrontId": "1"})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def title_from_product_url(url: str) -> str | None:
    """Mağaza HTML'i engellenirse ürün slug'ından güvenli başlık üret."""
    path = unquote(urlsplit(url).path).strip("/")
    if not path:
        return None
    slug = path.split("/")[-1]
    slug = re.sub(r"\.html?$", "", slug, flags=re.IGNORECASE)  # uzantıyı at
    slug = re.sub(r"-p-\d+(?:/.*)?$", "", slug, flags=re.IGNORECASE)
    # DR/KitapYurdu: önce ISBN/kod tespiti (sondaki -\d strip'ten ÖNCE)
    # "suc-ve-ceza" (2 tire) > "roman" > "edebiyat" — en bileşik segmenti al
    _SKIP_SEGS = {"kitap", "urun", "product", "kategori", "category", "p", "tr"}
    if (re.match(r"^(dr|p|urun|product)[-_]\d{5,}", slug, re.IGNORECASE)
            or re.match(r"^\d{5,}$", slug)):
        all_parts = [seg for seg in path.split("/") if seg]
        candidates = [re.sub(r"\.html?$", "", seg, flags=re.IGNORECASE)
                      for seg in all_parts[:-1]
                      if len(seg) > 2 and seg.lower().split(".")[0] not in _SKIP_SEGS
                      and not re.match(r"^\d+$", seg.split(".")[0])]
        if candidates:
            slug = max(candidates, key=lambda s: s.count("-") * 10 + len(s))
        slug = re.sub(r"-p-\d+(?:/.*)?$", "", slug, flags=re.IGNORECASE)
    else:
        slug = re.sub(r"-\d{5,}$", "", slug)  # N11/diğer: sondaki ürün ID'sini at
    words = [word for word in slug.replace("_", "-").split("-") if word]
    # Ardışık tekrarları at: "nike-nike-cosmic" → "nike cosmic" (FLO marka tekrarı)
    deduped_words = [w for i, w in enumerate(words) if i == 0 or w.lower() != words[i - 1].lower()]
    if len(deduped_words) < 2:
        return None
    return " ".join(deduped_words).title()


def is_public_product_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(address[4][0]).is_global
        for address in addresses
    )


def safe_product_get(url: str, **kwargs):
    """SSRF ve redirect ile özel ağa geçişi engelleyerek sayfayı indir."""
    current = url
    for _ in range(5):
        if not is_public_product_url(current):
            raise requests.RequestException("Güvenli olmayan ürün adresi")
        response = requests.get(current, allow_redirects=False, **kwargs)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = urljoin(current, location)
    raise requests.TooManyRedirects("Çok fazla yönlendirme")


@dataclass
class ParsedProduct:
    title: str | None
    price: float | None
    image_url: str | None
    source: str
    canonical_url: str
    confidence: int
    warnings: list[str]
    original_price: float | None = None
    extra_info: dict = None

def translate_deep_link(url: str) -> str:
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        
        if scheme in {"http", "https"}:
            return url
            
        query_params = {}
        if parsed.query:
            from urllib.parse import parse_qsl
            query_params = dict(parse_qsl(parsed.query))
            
        query_params = {k.lower(): v for k, v in query_params.items()}
        
        if scheme == "trendyol":
            content_id = query_params.get("contentid")
            if content_id:
                return f"https://www.trendyol.com/p-{content_id}"
                
        elif scheme == "hepsiburada":
            product_id = query_params.get("productid")
            if product_id:
                return f"https://www.hepsiburada.com/p-{product_id}"
                
        elif scheme == "n11":
            product_id = query_params.get("productid")
            if product_id:
                return f"https://www.n11.com/p-{product_id}"
    except Exception:
        pass
    return url


def resolve_short_url(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return url
        
    try:
        host = urlparse(url).netloc.lower()
        short_domains = {
            "ty.gl", "amzn.to", "amzn.eu", "bit.ly", "tinyurl.com", 
            "rebrand.ly", "hepsiburada.ly", "hb.gl", "n11.co", "n11.ly"
        }
        
        is_short = host in short_domains or any(host.endswith("." + d) for d in short_domains)
        if is_short:
            headers = {"User-Agent": USER_AGENT}
            response = safe_product_get(url, headers=headers, stream=True, timeout=8)
            return response.url or url
    except Exception:
        pass
    return url


def detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()

    if "trendyol" in host:
        return "trendyol"
    if "hepsiburada" in host:
        return "hepsiburada"
    if "amazon" in host:
        return "amazon"
    if "n11" in host:
        return "n11"
    if "gratis" in host:
        return "gratis"
    if "rossmann" in host:
        return "rossmann"
    if "supplementler" in host:
        return "supplementler"
    if "proteinocean" in host:
        return "proteinocean"
    if "vatanbilgisayar" in host:
        return "vatanbilgisayar"
    if "itopya" in host:
        return "itopya"
    if "karaca" in host:
        return "karaca"
    if "lcwaikiki" in host or "lcw" in host:
        return "lcwaikiki"
    if "defacto" in host:
        return "defacto"
    if "mediamarkt" in host:
        return "mediamarkt"
    if "teknosa" in host:
        return "teknosa"
    if "zara" in host:
        return "zara"
    if "migros" in host:
        return "migros"
    if "boyner" in host:
        return "boyner"
    if "koton" in host:
        return "koton"
    if "mavi" in host:
        return "mavi"
    if "bim.com" in host:
        return "bim"
    if "a101" in host:
        return "a101"
    if "sokmarket" in host:
        return "sok"
    if "file.com" in host:
        return "file"
    if "metro" in host:
        return "metro"
    if "carrefoursa" in host:
        return "carrefoursa"
    if "flo.com" in host:
        return "flo"
    if "kinetix" in host:
        return "kinetix"
    if "yargici" in host:
        return "yargici"
    if "kitapyurdu" in host:
        return "kitapyurdu"
    if "dr.com" in host:
        return "dr"
    if "ebebek" in host:
        return "ebebek"
    if "vivense" in host:
        return "vivense"
    if "evidea" in host:
        return "evidea"
    if "decathlon" in host:
        return "decathlon"
    if "adidas" in host:
        return "adidas"
    if "puma" in host:
        return "puma"
    if "nike" in host:
        return "nike"
    if "colins" in host:
        return "colins"
    if "ltb" in host:
        return "ltb"
    if "watsons" in host:
        return "watsons"
    if "sephora" in host:
        return "sephora"
    if "idefix" in host:
        return "idefix"
    if "remzi" in host:
        return "remzi"
    if "pandora" in host:
        return "pandora"
    if "derimod" in host:
        return "derimod"
    if "english" in host and "home" in host:
        return "englishhome"
    if "madamecoco" in host:
        return "madamecoco"
    if "ikea" in host:
        return "ikea"
    if "koctas" in host:
        return "koctas"

    return "manual"


def parse_price(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, int | float):
        return float(value)

    text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\d,\.]", "", text)

    if not text:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        parts = text.split(".")
        if len(parts) > 2:
            text = "".join(parts)
        elif len(parts) == 2 and len(parts[1]) == 3:
            text = "".join(parts)

    try:
        return float(text)
    except ValueError:
        return None


def first_meta(soup: BeautifulSoup, names: list[str]) -> str | None:
    for name in names:
        selectors = [
            f"meta[property='{name}']",
            f"meta[name='{name}']",
            f"meta[itemprop='{name}']",
        ]

        for selector in selectors:
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                return tag["content"].strip()

    return None


def iter_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if isinstance(data, list):
            items.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                items.extend(item for item in graph if isinstance(item, dict))
            items.append(data)

    return items


def extract_from_json_ld(soup: BeautifulSoup) -> tuple[str | None, float | None, str | None]:
    for item in iter_json_ld(soup):
        item_type = item.get("@type")
        if isinstance(item_type, list):
            is_product = any(str(value).lower() == "product" for value in item_type)
        else:
            is_product = str(item_type).lower() == "product"

        if not is_product:
            continue

        title = item.get("name")
        image = item.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url") or image.get("contentUrl") or image.get("@id")

        offers = item.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None

        price = None
        if isinstance(offers, dict):
            price = parse_price(offers.get("price") or offers.get("lowPrice"))

        return title, price, image

    return None, None, None


def walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def extract_from_embedded_json(soup: BeautifulSoup) -> tuple[str | None, float | None, str | None]:
    price_keys = (
        "discountedPrice",
        "salePrice",
        "sellingPrice",
        "currentPrice",
        "price",
    )
    title_keys = ("name", "title", "productName")
    image_keys = ("image", "imageUrl", "imageURL")

    for script in soup.select("script"):
        raw = script.string or script.get_text(strip=True)
        if not raw or len(raw) > 5_000_000:
            continue

        data = None
        if script.get("type") == "application/json" or script.get("id") in {
            "__NEXT_DATA__",
            "__NUXT_DATA__",
        }:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                pass

        if data is not None:
            for item in walk_json(data):
                price = next(
                    (parse_price(item.get(key)) for key in price_keys if item.get(key) is not None),
                    None,
                )
                if not price:
                    continue

                title = next(
                    (str(item.get(key)).strip() for key in title_keys if item.get(key)),
                    None,
                )
                image = next(
                    (item.get(key) for key in image_keys if item.get(key)),
                    None,
                )
                if isinstance(image, list):
                    image = image[0] if image else None
                if isinstance(image, dict):
                    image = image.get("url")

                return title, price, image

        for key in price_keys:
            match = re.search(
                rf'["\']{re.escape(key)}["\']\s*:\s*["\']?([\d.,]+)',
                raw,
                flags=re.IGNORECASE,
            )
            if match:
                price = parse_price(match.group(1))
                if price:
                    return None, price, None

    return None, None, None


def extract_visible_price(soup: BeautifulSoup, source: str) -> float | None:
    selectors = {
        "trendyol": [
            ".prc-dsc",
            ".prc-slg",
            "[data-testid='price-current-price']",
            "[class*='product-price']",
        ],
        "hepsiburada": [
            "[data-test-id='price-current-price']",
            "[data-test-id='price']",
            "[class*='price']",
        ],
        "amazon": [
            "#corePrice_feature_div .a-offscreen",
            ".a-price .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
        ],
        "n11": [
            ".newPrice ins",
            ".priceContainer ins",
            "[class*='newPrice']",
        ],
        "gratis": [
            ".price",
            "[class*='price']",
            ".product-price",
        ],
        "rossmann": [
            ".price",
            "[class*='price']",
            ".product-price",
        ],
        "supplementler": [
            ".price",
            ".product-price",
            "[class*='price']",
        ],
        "proteinocean": [
            ".price",
            ".product-price",
            "[class*='price']",
        ],
        "vatanbilgisayar": [
            ".product-list__price",
            "[class*='price']",
            ".price",
        ],
        "itopya": [
            ".price",
            "#productPrice",
            "[class*='price']",
        ],
        "karaca": [
            ".current-price",
            "span.price",
            ".product-price",
            ".price",
        ],
        "lcwaikiki": [
            ".advanced-price",
            "span.price",
            ".price",
        ],
        "defacto": [
            ".product-card__price",
            ".product-card__price--new",
            ".product-price",
            ".price",
        ],
        "mediamarkt": [
            "[class*='Price']",
            "span.price",
            ".price",
        ],
        "teknosa": [
            ".prc-dsc",
            ".price",
            ".current-price",
        ],
        "zara": [
            ".price__amount",
            ".price",
        ],
        "migros": [
            "fe-product-price",
            ".price",
        ],
        "boyner": [
            ".product-price",
            ".price",
        ],
        "koton": [
            ".normalPrice",
            ".price",
        ],
        "mavi": [
            ".price-current",
            ".price",
        ],
        "flo": [
            ".product-detail-price",
            ".price-new",
            "[class*='price']",
        ],
        "kinetix": [
            ".prc-dsc",
            ".price",
            "[class*='price']",
        ],
        "yargici": [
            ".product-price",
            ".price",
            "[class*='price']",
        ],
        "kitapyurdu": [
            ".price-new",
            ".pd-price",
            "[class*=price]",
        ],
        "dr": [
            ".price-value",
            ".product-price",
            "[class*=price]",
        ],
        "ebebek": [
            ".price",
            ".product-price",
            "[class*=price]",
        ],
        "vivense": [
            ".price",
            "[class*=price]",
        ],
        "decathlon": [
            ".price",
            "[class*=price]",
        ],
        "adidas": [
            ".gl-price",
            "[class*=price]",
        ],
        "nike": [
            ".product-price",
            "[class*=price]",
        ],
    }

    for selector in selectors.get(source, []):
        element = soup.select_one(selector)
        if not element:
            continue

        price = parse_price(element.get("content") or element.get_text(" ", strip=True))
        if price:
            return price

    return None


def extract_original_price(soup: BeautifulSoup, source: str) -> float | None:
    selectors = {
        "trendyol": [".prc-org"],
        "hepsiburada": ["[data-test-id='price-prev-price']", ".price-prev"],
        "amazon": [".a-text-strike", "span.a-price.a-text-price span.a-offscreen"],
        "n11": [".oldPrice", ".old-price"],
        "gratis": [".price-crossed", ".original-price"],
        "rossmann": [".original-price", ".old-price"],
        "supplementler": [".old-price", ".strike"],
        "proteinocean": [".old-price"],
        "vatanbilgisayar": [".product-list__price-crossed"],
        "itopya": [".old-price", ".oldPrice"],
        "karaca": [".old-price", "span.old-price", "span.strike"],
        "lcwaikiki": [".raw-price", ".old-price"],
        "defacto": [".product-card__price--old", ".old-price"],
        "mediamarkt": ["span.old-price"],
        "teknosa": [".prc-org", ".old-price"],
        "boyner": [".old-price", ".strike"],
        "koton": [".old-price", ".crossed-price"],
        "mavi": [".price-old", ".old-price"],
    }
    
    for selector in selectors.get(source, []):
        element = soup.select_one(selector)
        if not element:
            continue
        price = parse_price(element.get("content") or element.get_text(" ", strip=True))
        if price:
            return price
            
    return None


def extract_servings_from_soup(soup: BeautifulSoup, source: str) -> int | None:
    if not soup:
        return None
        
    try:
        if source == "supplementler":
            # 1. spec-service-size class'ını dene
            el = soup.select_one(".spec-service-size")
            if el:
                txt = el.get_text(strip=True)
                match = re.search(r"(\d+)", txt)
                if match:
                    return int(match.group(1))
                    
            # 2. Porsiyon sayısı içeren metinleri ara
            for tag in soup.find_all(string=re.compile("porsiyon sayısı", re.IGNORECASE)):
                parent = tag.parent
                if parent:
                    curr = parent
                    for _ in range(3):
                        txt = curr.get_text(" ", strip=True)
                        match = re.search(r"(?:porsiyon sayısı|porsiyon sayısı\s*:)\s*(\d+)", txt, re.IGNORECASE)
                        if match:
                            return int(match.group(1))
                        if not curr.parent:
                            break
                        curr = curr.parent
                        
        elif source == "proteinocean":
            text = soup.get_text(" ", strip=True)
            matches = re.findall(r"(\d+)\s*(?:servis|porsiyon|ölçek|paket)", text, re.IGNORECASE)
            if matches:
                return int(matches[0])
    except Exception:
        pass
    return None


def estimate_servings_from_title(title: str) -> int | None:
    if not title:
        return None
    title_lower = title.lower()
    
    # 1. Gramajı bul (Gr veya G)
    weight_g = None
    match_gr = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:gr|g|gram)\b", title_lower)
    if match_gr:
        try:
            val_str = match_gr.group(1).replace(",", ".")
            weight_g = float(val_str)
        except ValueError:
            pass
            
    # 2. Kilogram bul (Kg, kilo, kilogram)
    if not weight_g:
        match_kg = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:kg|kilogram|kilo)\b", title_lower)
        if match_kg:
            try:
                val_str = match_kg.group(1).replace(",", ".")
                weight_g = float(val_str) * 1000
            except ValueError:
                pass
                
    if not weight_g:
        return None
        
    # 3. Kategoriye göre standart porsiyon boyutu (gram cinsinden)
    serving_size = 30 # Varsayılan: Protein tozu porsiyon boyutu (30 gr)
    
    if "creatine" in title_lower or "kreatin" in title_lower:
        serving_size = 5
    elif "glutamine" in title_lower or "glutamin" in title_lower:
        serving_size = 5
    elif "bcaa" in title_lower:
        serving_size = 10
    elif "pre-workout" in title_lower or "preworkout" in title_lower or "nox" in title_lower:
        serving_size = 10
    elif "gainer" in title_lower or "karbonhidrat" in title_lower or "mass" in title_lower:
        serving_size = 100
    elif "arjinin" in title_lower or "arginine" in title_lower:
        serving_size = 5
    elif "carnitine" in title_lower or "karnitin" in title_lower:
        serving_size = 3
        
    servings = round(weight_g / serving_size)
    return servings if servings > 0 else None


def extract_extra_info(title: str, source: str, soup: BeautifulSoup = None) -> dict:
    info = {}
    if not title:
        return info
    title_lower = title.lower()
    
    # 1. Supplement porsiyon ayıklama
    if source in {"supplementler", "proteinocean"}:
        info["category"] = "supplement"
        
        # Önce başlıktan dene
        match = re.search(r"(\d+)\s*(servis|ölçek|kapsül|tablet|porsiyon|şase|paket|adet|ad|tb|kp)", title_lower)
        if match:
            info["servings"] = int(match.group(1))
        else:
            servings = None
            if soup:
                # Başlıkta yoksa HTML'den çek
                servings = extract_servings_from_soup(soup, source)
            
            # HTML'de de bulunamazsa gramaja göre tahmini porsiyon hesapla
            if not servings:
                servings = estimate_servings_from_title(title)
                
            if servings:
                info["servings"] = servings
            
    # 2. PC donanım uyumluluk ayıklama (Vatan, Itopya)
    elif source in {"vatanbilgisayar", "itopya"}:
        info["category"] = "pc_component"
        if "am5" in title_lower or "b650" in title_lower or "x670" in title_lower or "a620" in title_lower:
            info["socket"] = "AM5"
            info["ram_type"] = "DDR5"
            info["compatibility_info"] = "AM5 Soket İşlemciler (Ryzen 7000/8000/9000) ve DDR5 Bellekler ile uyumludur."
        elif "am4" in title_lower or "b450" in title_lower or "b550" in title_lower or "x570" in title_lower or "a320" in title_lower:
            info["socket"] = "AM4"
            info["ram_type"] = "DDR4"
            info["compatibility_info"] = "AM4 Soket İşlemciler (Ryzen 3000/4000/5000) ve DDR4 Bellekler ile uyumludur."
        elif "lga1700" in title_lower or "h610" in title_lower or "b760" in title_lower or "z790" in title_lower or "z690" in title_lower:
            info["socket"] = "LGA1700"
            info["compatibility_info"] = "Intel 12./13./14. Nesil İşlemciler (LGA1700) ile uyumludur."
            if "ddr5" in title_lower:
                info["ram_type"] = "DDR5"
            elif "ddr4" in title_lower:
                info["ram_type"] = "DDR4"
        elif "ddr5" in title_lower:
            info["ram_type"] = "DDR5"
            info["compatibility_info"] = "DDR5 destekli anakartlar ve DDR5 uyumlu işlemciler ile kullanılmalıdır."
        elif "ddr4" in title_lower:
            info["ram_type"] = "DDR4"
            info["compatibility_info"] = "DDR4 destekli anakartlar ve DDR4 uyumlu işlemciler ile kullanılmalıdır."
            
    return info


def is_generic_title(title_str: str | None) -> bool:
    if not title_str:
        return True
    title_lower = title_str.lower()
    blocked_words = {
        "cloudflare", "just a moment", "attention required", "access denied",
        "access forbidden", "robot olmadığınızı", "güvenlik doğrulaması",
        "hata", "error", "403 forbidden", "404 not found", "distil networks",
        "yasak", "güvenlik önlemi", "geçici olarak engellendi",
        "checking your browser", "recaptcha", "captcha", "doğrulama gerekiyor",
        "bir dakika", "verifying you are human", "please wait",
    }
    if any(word in title_lower for word in blocked_words):
        return True
    return title_lower.strip() in {"trendyol", "hepsiburada", "amazon", "n11", "gratis", "rossmann"}


def is_challenge_page(soup: BeautifulSoup) -> bool:
    text = soup.get_text(" ", strip=True).lower()
    signals = (
        "captcha",
        "access denied",
        "robot olmadığınızı",
        "güvenlik doğrulaması",
        "verify you are human",
    )
    return any(signal in text for signal in signals)


def _parse_hepsiburada_api(url: str) -> "ParsedProduct | None":
    """Hepsiburada ürün sayfasını mobil user-agent ile çeker."""
    import re as _re
    match = _re.search(r"[-/](HB[A-Z0-9]+)", url)
    if not match:
        return None
    sku = match.group(1)
    api_url = f"https://www.hepsiburada.com/api/product/detail/{sku}"
    try:
        resp = requests.get(
            api_url,
            headers={
                "User-Agent": "HepsiburadaAndroid/5.9.0 (Android 13; SM-S918B)",
                "Accept": "application/json",
                "Accept-Language": "tr-TR",
            },
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            product = data.get("product") or data
            title = product.get("name") or product.get("displayName")
            price = product.get("price") or product.get("salePrice")
            original_price = product.get("listPrice") or product.get("originalPrice")
            if original_price and price and float(original_price) <= float(price):
                original_price = None
            images = product.get("images") or []
            image_url = images[0] if images else None
            if title and price:
                return ParsedProduct(
                    title=str(title).strip(),
                    price=float(price),
                    image_url=image_url,
                    source="hepsiburada",
                    canonical_url=url,
                    confidence=90,
                    warnings=[],
                    original_price=float(original_price) if original_price else None,
                    extra_info={},
                )
    except Exception:
        pass
    return None


def parse_product_url(url: str) -> ParsedProduct:
    url = normalize_product_url(url)
    url = normalize_product_url(resolve_short_url(url))

    warnings: list[str] = []
    source = detect_source(url)

    # Hepsiburada için önce API dene (HTML bloke sorunu). Trendyol'un kendi
    # public.trendyol.com API'si kapatıldı (DNS'te artık kayıtlı değil) --
    # her çağrıda garanti başarısız olup gereksiz gecikme eklediği için
    # kaldırıldı; Trendyol artık doğrudan HTML+JSON-LD yoluna düşer.
    if source == "hepsiburada":
        api_result = _parse_hepsiburada_api(url)
        if api_result and api_result.price:
            return api_result

    try:
        fetch_url = product_fetch_url(url, source)
        from app.scraping_proxy import proxy_enabled, proxy_get
        if proxy_enabled():
            html = proxy_get(fetch_url, render_js=False, timeout=15)
            if html:
                response_text = html
            else:
                raise requests.RequestException("Proxy ile sayfa içeriği çekilemedi.")
        else:
            response = safe_product_get(
                fetch_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Referer": "https://www.google.com/",
                },
                cookies={"countryCode": "TR", "language": "tr", "storefrontId": "1"},
                timeout=8,
            )
            response.raise_for_status()
            response_text = response.text
    except requests.RequestException as e:
        fallback_title = title_from_product_url(url)
        return ParsedProduct(
            title=fallback_title,
            price=None,
            image_url=None,
            source=source,
            canonical_url=url,
            confidence=30 if fallback_title else 0,
            warnings=[
                "Mağaza sayfasına şu anda ulaşılamadı. Ürün adı linkten çıkarıldı; fiyatı elle tamamlayabilirsin."
                if fallback_title
                else "Mağaza sayfasına şu anda ulaşılamadı. Bağlantıyı kontrol edip tekrar deneyebilirsin."
            ],
            original_price=None,
            extra_info={},
        )

    soup = BeautifulSoup(response_text, "lxml")
    canonical_url = first_meta(soup, ["og:url"]) or url

    title, price, image_url = extract_from_json_ld(soup)
    embedded_title, embedded_price, embedded_image = extract_from_embedded_json(soup)

    title = title or embedded_title or first_meta(soup, ["og:title", "twitter:title", "title"])
    if is_generic_title(title):
        title = None

    visible_price = extract_visible_price(soup, source)
    price = visible_price or price or parse_price(
        first_meta(
            soup,
            [
                "product:price:amount",
                "price",
                "og:price:amount",
                "twitter:data1",
            ],
        )
    )
    price = price or embedded_price
    image_url = (
        image_url
        or embedded_image
        or first_meta(soup, ["og:image", "twitter:image", "image"])
    )

    if is_generic_title(title) and soup.title:
        title = soup.title.get_text(" ", strip=True)
        if is_generic_title(title):
            title = None

    if not title:
        title = title_from_product_url(url)
        if title:
            warnings.append("Ürün adı bağlantı adresinden çıkarıldı.")

    # Mağaza/pazarlama eklerini temizle: "... Fiyatı ve Özellikleri", "... | Teknosa" vb.
    if title:
        title = re.sub(
            r"\s*[-|–]\s*(teknosa|mediamarkt|hepsiburada|trendyol|n11|amazon\.com\.tr|vatan bilgisayar)\s*$",
            "", title, flags=re.IGNORECASE)
        title = re.sub(
            r"\s+(fiyatı( ve özellikleri)?|fiyatları( ve modelleri)?|özellikleri( ve fiyatı)?)\s*$",
            "", title, flags=re.IGNORECASE).strip() or title

    # Orijinal üstü çizili fiyatı çek
    original_price = extract_original_price(soup, source)
    # Eğer orijinal fiyat satış fiyatından düşük veya eşitse, yok say (hatalı veri önleme)
    if original_price and price and original_price <= price:
        original_price = None

    confidence = 20
    if title:
        confidence += 30

    extra_info = {}
    if source == "trendyol":
        import json
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "window.__INITIAL_STATE__=" in script_text:
                try:
                    json_str = script_text.split("window.__INITIAL_STATE__=")[1]
                    if ";window.__SEARCH_APP_INITIAL_STATE__=" in json_str:
                        json_str = json_str.split(";window.__SEARCH_APP_INITIAL_STATE__=")[0]
                    elif ";window.__" in json_str:
                        json_str = json_str.split(";window.__")[0]
                    else:
                        json_str = json_str.rsplit(";", 1)[0]
                    
                    state = json.loads(json_str.strip())
                    merchants = state.get("product", {}).get("productDetails", {}).get("otherMerchants", [])
                    parsed_merchants = []
                    for merchant in merchants:
                        merch_price = merchant.get("price", {}).get("discountedPrice", {}).get("value")
                        merch_name = merchant.get("merchant", {}).get("name")
                        merch_url = merchant.get("merchant", {}).get("sellerLink", "")
                        merch_score = merchant.get("merchant", {}).get("sellerScore")
                        merch_delivery = merchant.get("deliveryInformation", {}).get("fastDeliveryOptions", [])
                        if merch_price and merch_name:
                            parsed_merchants.append({
                                "title": title or "",
                                "price": float(merch_price),
                                "url": f"https://www.trendyol.com{merch_url}" if merch_url else url,
                                "source": f"Trendyol ({merch_name})",
                                "extra_info": {
                                    "rating": merch_score,
                                    "fast_delivery": bool(merch_delivery)
                                }
                            })
                    if parsed_merchants:
                        extra_info["otherMerchants"] = parsed_merchants
                except Exception:
                    pass
                break
    # NOT: "else: warnings.append(...)" kaldırıldı - başlık yok uyarısı aşağıda fiyat bölümünde işleniyor

    if price:
        confidence += 35
    else:
        if is_challenge_page(soup):
            warnings.append("Mağaza otomatik erişimi engelledi. Fiyatı elle yazabilirsin.")
        else:
            warnings.append("Fiyat otomatik bulunamadı. Fiyatı elle yazabilirsin.")

    if image_url:
        confidence += 15

    # Çıkış tiplerini Pydantic doğrulama hatalarını önlemek için temizle ve garantiye al
    if isinstance(image_url, dict):
        image_url = image_url.get("url") or image_url.get("contentUrl") or image_url.get("@id")
    elif isinstance(image_url, list):
        image_url = image_url[0] if image_url else None
    
    if image_url is not None:
        image_url = str(image_url).strip()
        if not image_url.startswith(("http://", "https://")):
            image_url = None

    if title is not None:
        title = str(title).strip()

    if isinstance(canonical_url, dict):
        canonical_url = canonical_url.get("url") or url
    elif isinstance(canonical_url, list):
        canonical_url = canonical_url[0] if canonical_url else url

    if not isinstance(canonical_url, str):
        canonical_url = str(canonical_url or url)

    # extract_extra_info ile görüntrüür bilgileri al, ancak otherMerchants gibi önceden doldurulmuş
    # alanları silme (birleştirme yap)
    base_extra = extract_extra_info(title, source, soup)
    base_extra.update(extra_info)  # extra_info (otherMerchants) öncelikli
    extra_info = base_extra

    return ParsedProduct(
        title=title,
        price=price,
        image_url=image_url,
        source=source,
        canonical_url=canonical_url,
        confidence=min(confidence, 100),
        warnings=warnings,
        original_price=original_price,
        extra_info=extra_info,
    )
