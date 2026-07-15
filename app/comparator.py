import urllib.parse
import re
import json
import requests
from bs4 import BeautifulSoup
from app.parser import parse_product_url, detect_source, USER_AGENT
from app.storage import load_db, save_db

YAHOO_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"

_STD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


_PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?)\s*(?:TL|₺)")

# "100TL üzeri alışverişe özel", "150 TL üzeri kargo bedava" gibi kargo/kampanya
# esik metinleri de _PRICE_RE ile eslesiyor -- gercek urun fiyati sanilip yanlis
# fiyat gosterilmesine yol aciyordu (orn. Rossmann'da gercek fiyat 329 TL iken
# sayfadaki "100TL uzeri..." rozeti urun fiyati sanilip 100 TL gosterilmisti).
_PRICE_THRESHOLD_CONTEXT_RE = re.compile(
    r"üzeri|üzerinde|ve üzeri|kargo\s*bedava|ücretsiz\s*kargo|indirim\s*kod",
    re.IGNORECASE,
)


def _heuristic_price_card_scan(soup: "BeautifulSoup", source: str, base_url: str) -> list[dict]:
    """JSON-LD bulunamadığında son çare: fiyat deseni (₺/TL) içeren ve içinde
    bir link barındıran en küçük tekrarlayan konteynerleri ürün kartı olarak
    dener. JS-render edilen modern SPA'larda (Vue/React) JSON-LD hiç olmayabilir
    ama render sonrası HTML'de fiyatlar düz metin olarak bulunur."""
    results = []
    seen_urls = set()
    price_nodes = [
        el for el in soup.find_all(string=_PRICE_RE)
        if el.strip()
    ]
    for text_node in price_nodes[:40]:
        price_match = _PRICE_RE.search(text_node)
        if not price_match:
            continue
        if _PRICE_THRESHOLD_CONTEXT_RE.search(text_node):
            continue
        try:
            price = float(price_match.group(1).replace(".", "").replace(" ", "").replace(",", "."))
        except Exception:
            continue
        if price <= 0:
            continue
        # En yakın atadan (üst) bir <a href> ve makul uzunlukta bir başlık bul
        container = text_node.parent
        link_el = None
        title = ""
        for _ in range(6):
            if container is None:
                break
            if link_el is None:
                link_el = container.find("a", href=True)
            img_el = container.find("img")
            candidate_title = (
                (img_el.get("alt", "").strip() if img_el else "")
                or (link_el.get("title", "").strip() if link_el else "")
            )
            if candidate_title and len(candidate_title) > len(title):
                title = candidate_title
            container = container.parent
        if not link_el or not title or len(title) < 3:
            continue
        href = link_el.get("href", "")
        if not href:
            continue
        prod_url = href if href.startswith("http") else urllib.parse.urljoin(base_url, href)
        if prod_url in seen_urls:
            continue
        seen_urls.add(prod_url)
        img_el = link_el.find("img") or (link_el.parent.find("img") if link_el.parent else None)
        img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
        results.append({
            "title": title, "price": price, "original_price": None,
            "image_url": img, "source": source, "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            "verified": False,  # sezgisel (heuristik) fiyat tahmini -- JSON-LD yok
        })
        if len(results) >= 10:
            break

    if results:
        return results

    # İkinci geçiş: bazı sitelerde fiyat tek bir metin düğümünde değil,
    # birden fazla küçük etikete bölünmüş oluyor (ör. <span>18</span>
    # <span>,90</span><span>TL</span>). Bu durumda küçük konteynerlerin
    # birleşik metnini (join ile) tarıyoruz.
    for el in soup.find_all(["div", "li", "article", "a", "span", "p"]):
        if len(el.find_all()) > 15:
            continue  # çok büyük konteyner, ürün kartı değil
        text = el.get_text(" ", strip=True)
        price_match = _PRICE_RE.search(text)
        if not price_match:
            continue
        if _PRICE_THRESHOLD_CONTEXT_RE.search(text):
            continue
        try:
            price = float(price_match.group(1).replace(".", "").replace(" ", "").replace(",", "."))
        except Exception:
            continue
        if price <= 0:
            continue
        link_el = el if el.name == "a" and el.get("href") else el.find("a", href=True)
        title = ""
        if not link_el:
            # Link fiyat elemanının altında değilse üst atalarda ara
            container = el.parent
            for _ in range(6):
                if container is None:
                    break
                if link_el is None:
                    link_el = container.find("a", href=True)
                img_el = container.find("img")
                candidate_title = (img_el.get("alt", "").strip() if img_el else "") or (
                    link_el.get("title", "").strip() if link_el else ""
                )
                if candidate_title and len(candidate_title) > len(title):
                    title = candidate_title
                if link_el and title:
                    break
                container = container.parent
        if not link_el:
            continue
        if not title:
            img_el = el.find("img")
            title = (img_el.get("alt", "").strip() if img_el else "") or link_el.get("title", "").strip()
        if not title or len(title) < 3:
            continue
        href = link_el.get("href", "")
        prod_url = href if href.startswith("http") else urllib.parse.urljoin(base_url, href)
        if prod_url in seen_urls:
            continue
        seen_urls.add(prod_url)
        img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
        results.append({
            "title": title, "price": price, "original_price": None,
            "image_url": img, "source": source, "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            "verified": False,  # sezgisel (heuristik) fiyat tahmini -- JSON-LD yok
        })
        if len(results) >= 10:
            break
    return results


def _scrape_jsonld_itemlist(url: str, source: str, render_js: bool = False, timeout: int = 10) -> list[dict]:
    """JSON-LD ItemList olan sayfalardan ürün çeker. ScrapingBee varsa proxy kullanır.
    JSON-LD bulunamazsa (modern JS-SPA'larda sık) fiyat-deseni sezgisel taramasına düşer."""
    from app.scraping_proxy import proxy_get, proxy_enabled
    html = None
    if proxy_enabled():
        html = proxy_get(url, render_js=render_js, timeout=timeout + 5)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=timeout)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if data.get("@type") != "ItemList":
                continue
            for item in data.get("itemListElement", [])[:10]:
                prod = item.get("item", item)
                name = prod.get("name", "")
                if not name:
                    continue
                offers = prod.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0]
                try:
                    price = float(str(offers.get("price", 0)).replace(",", "."))
                except Exception:
                    continue
                if price <= 0:
                    continue
                prod_url = prod.get("url", "")
                img = prod.get("image", "")
                if isinstance(img, list):
                    img = img[0] if img else ""
                results.append({
                    "title": name, "price": price, "original_price": None,
                    "image_url": img, "source": source, "url": prod_url,
                    "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                    "verified": True,  # JSON-LD -- mağazanın kendi yapılandırılmış verisi
                })
            if results:
                return results
        except Exception:
            continue
    if not results:
        try:
            results = _heuristic_price_card_scan(soup, source, url)
        except Exception:
            results = []
    return results

def clean_product_title(title: str) -> str:
    # Remove suffix patterns
    text = title.split(" - ")[0].split(" | ")[0]
    # Remove non-alphanumeric except spaces, dots, percent and hyphens
    text = re.sub(r"[^\w\s\.\-]", " ", text)
    return " ".join(text.split())

def extract_yahoo_url(href: str) -> str | None:
    if not href:
        return None
    try:
        if "/RU=" in href:
            parts = href.split("/RU=", 1)[1].split("/", 1)
            if parts:
                return urllib.parse.unquote(parts[0])
    except Exception:
        pass
    return href

def is_valid_product_url(url: str, store: str) -> bool:
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        
        # Homepage or empty path
        if not path:
            return False
            
        # Search page or generic list page
        if path in ("s", "search", "ara", "kategori", "c"):
            return False
            
        # Specific stores check to avoid category/brand list/homepage pages
        if store == "trendyol":
            return "-p-" in url or "/p-" in url
        elif store == "hepsiburada":
            return "-p-" in url or "-pm-" in url or "/p-" in url or "/pm-" in url
        elif store == "n11":
            return "-p-" in url or "/urun/" in url or path.startswith("urun")
        elif store == "amazon":
            return "/dp/" in url or "/gp/product/" in url or "/gp/" in url
        elif store == "supplementler":
            return "/urun/" in url
        elif store == "proteinocean":
            return "/urun/" in url or "/products/" in url
        elif store == "gratis" or store == "rossmann":
            return "/p/" in url or "/urun/" in url or "-p-" in url
        elif store == "vatanbilgisayar" or store == "itopya":
            return "/urun/" in url or "-p-" in url or ".html" in url
        elif store in {"karaca", "lcwaikiki", "defacto", "mediamarkt", "teknosa", "zara", "migros", "boyner", "koton", "mavi", "bim", "a101", "sok", "file", "metro", "carrefoursa"}:
            return "/p/" in url or "-p-" in url or "/p-" in url or "/urun/" in url or "/product/" in url or ".html" in url or "/dp/" in url or "/gida/" in url or "/urunler/" in url
    except Exception:
        pass
    return True

def _query_yahoo(query: str, exclude_source: str) -> dict[str, str]:
    url = f"https://search.yahoo.com/search?q={urllib.parse.quote_plus(query)}"
    headers = {
        "User-Agent": YAHOO_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    
    links = {}
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select(".algo-srch") or soup.select(".compTitle") or soup.select("h3.title a")
            
            for result in results:
                link_el = result.find("a") if hasattr(result, "find") else result
                if not link_el:
                    continue
                href = link_el.get("href")
                actual_url = extract_yahoo_url(href)
                if not actual_url:
                    continue
                    
                store = detect_source(actual_url)
                if store != "manual" and store != exclude_source and store not in links:
                    if is_valid_product_url(actual_url, store):
                        links[store] = actual_url
    except Exception:
        pass
    return links

def get_target_stores(exclude_source: str) -> list[str]:
    store_to_category = {
        "supplementler": "supplement",
        "proteinocean": "supplement",
        "vatanbilgisayar": "electronics",
        "itopya": "electronics",
        "mediamarkt": "electronics",
        "teknosa": "electronics",
        "gratis": "personal_care",
        "rossmann": "personal_care",
        "lcwaikiki": "fashion",
        "defacto": "fashion",
        "zara": "fashion",
        "boyner": "fashion",
        "koton": "fashion",
        "mavi": "fashion",
        "karaca": "home",
        "migros": "grocery",
        "bim": "grocery",
        "a101": "grocery",
        "sok": "grocery",
        "file": "grocery",
        "metro": "grocery",
        "carrefoursa": "grocery",
        "trendyol": "general",
        "hepsiburada": "general",
        "amazon": "general",
        "n11": "general"
    }
    
    source_cat = store_to_category.get(exclude_source, "general")
    
    general_stores = ["trendyol", "hepsiburada", "amazon", "n11"]
    targets = []
    
    if source_cat == "general":
        targets.extend(list(store_to_category.keys()))
    elif source_cat == "supplement":
        targets.extend(["supplementler", "proteinocean"])
        targets.extend(general_stores)
    elif source_cat == "electronics":
        targets.extend(["vatanbilgisayar", "itopya", "mediamarkt", "teknosa"])
        targets.extend(general_stores)
    elif source_cat == "personal_care":
        targets.extend(["gratis", "rossmann"])
        targets.extend(general_stores)
    elif source_cat == "fashion":
        targets.extend(["lcwaikiki", "defacto", "zara", "boyner", "koton", "mavi"])
        targets.extend(general_stores)
    elif source_cat == "home":
        targets.extend(["karaca"])
        targets.extend(general_stores)
    elif source_cat == "grocery":
        targets.extend(["migros"])
        targets.extend(general_stores)
    
    unique_targets = []
    for t in targets:
        if t != exclude_source and t not in unique_targets:
            unique_targets.append(t)
            
    return unique_targets

def format_yahoo_query(query: str) -> str:
    # 1. Suffix cleaning and normalization to make it easier for search engines
    word_replacements = {
        "telefonu": "telefon",
        "kulaklığı": "kulaklık",
        "kulakligi": "kulaklık",
        "yağı": "yağ",
        "yagi": "yağ",
        "tozu": "toz",
        "makinesi": "makine",
        "makinası": "makine",
        "televizyonu": "televizyon",
        "deterjanı": "deterjan",
        "şampuanı": "şampuan",
        "sampuanı": "şampuan",
        "bilgisayarı": "bilgisayar",
        "saati": "saat",
    }
    
    words = query.split()
    formatted_words = []
    for w in words:
        clean_w = w.strip('"\'')
        lower_clean = clean_w.lower()
        if lower_clean in word_replacements:
            clean_w = word_replacements[lower_clean]
            
        # If the word 'matrix' (case-insensitive) is in the query, wrap it in double quotes to prevent Yahoo 500 errors.
        if clean_w.lower().startswith("matri"):
            formatted_words.append(f'"{clean_w}"')
        else:
            formatted_words.append(clean_w)
    return " ".join(formatted_words)

def find_comparison_links(title: str, exclude_source: str) -> dict[str, str]:
    clean_title = clean_product_title(title)
    formatted_title = format_yahoo_query(clean_title)
    
    # 1. Try search with quoted title for high accuracy product matching (no site query to avoid blocks)
    query_quoted = f'"{formatted_title}"'
    links = _query_yahoo(query_quoted, exclude_source)
    
    # 2. If no valid links found, fall back to unquoted title search
    if not links:
        links = _query_yahoo(formatted_title, exclude_source)
        
    return links

def titles_match(original_title: str, candidate_title: str) -> bool:
    if not original_title or not candidate_title:
        return False
    def get_words(t: str) -> set[str]:
        t_clean = re.sub(r"[^\w\s]", " ", t.lower())
        return {w for w in t_clean.split() if len(w) > 1}
        
    orig_words = get_words(original_title)
    cand_words = get_words(candidate_title)
    
    if not orig_words:
        return True
        
    overlap = orig_words.intersection(cand_words)
    ratio = len(overlap) / len(orig_words)
    return ratio >= 0.50

def compare_prices(title: str, exclude_source: str) -> list[dict]:
    links = find_comparison_links(title, exclude_source)
    
    results = []
    for store, url in links.items():
        try:
            parsed = parse_product_url(url)
            if parsed.price and parsed.title:
                # Verify that the parsed product title matches the original query title
                if titles_match(title, parsed.title):
                    results.append({
                        "store": store,
                        "title": parsed.title,
                        "price": parsed.price,
                        "url": parsed.canonical_url,
                        "image_url": parsed.image_url
                    })
        except Exception:
            pass
            
    # Sort cheapest first
    results.sort(key=lambda x: x["price"])
    return results

def update_product_comparison(product_id: str) -> None:
    db = load_db()
    product = next((p for p in db["products"] if p["id"] == product_id), None)
    if not product:
        return
        
    comparison = compare_prices(product["title"], product["source"])
    product["price_comparison"] = comparison
    save_db(db)

def _fetch_yahoo_urls(query: str) -> list[str]:
    url = f"https://search.yahoo.com/search?q={urllib.parse.quote_plus(query)}"
    headers = {
        "User-Agent": YAHOO_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    found_urls = []
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select(".algo-srch") or soup.select(".compTitle") or soup.select("h3.title a")
            for result in results:
                link_el = result.find("a") if hasattr(result, "find") else result
                if not link_el:
                    continue
                href = link_el.get("href")
                actual_url = extract_yahoo_url(href)
                if not actual_url:
                    continue
                store = detect_source(actual_url)
                if store != "manual" and is_valid_product_url(actual_url, store):
                    if actual_url not in found_urls:
                        found_urls.append(actual_url)
    except Exception:
        pass
    return found_urls

def detect_query_category(query: str) -> str:
    query_lower = query.lower()
    grocery_keywords = {"yağ", "yag", "seker", "şeker", "un", "bakliyat", "makarna", "pirinc", "pirinç", "mercimek", "salca", "salça", "cay", "çay", "kahve", "sut", "süt", "peynir", "zeytin", "yumurta", "deterjan", "sampuan", "şampuan", "sabun", "market", "gida", "gıda", "zeytinyağı", "ayçiçek", "sivi", "sıvı"}
    electronics_keywords = {"tv", "televizyon", "telefon", "kulaklik", "kulaklık", "laptop", "bilgisayar", "ekran", "kart", "gpu", "cpu", "islemci", "işlemci", "anakart", "ram", "ssd", "klavye", "mouse", "fare", "tablet", "kamera", "fotograf", "fotoğraf", "kulaklık"}
    fashion_keywords = {"elbise", "pantolon", "gomlek", "gömlek", "tshirt", "tişört", "ceket", "mont", "kaban", "hırka", "hirka", "kazak", "yelek", "ayakkabi", "ayakkabı", "bot", "cizme", "çizme", "terlik", "corap", "çorap", "pantolon", "etek", "sort", "şort", "takim", "takım"}
    supplement_keywords = {"whey", "protein", "creatine", "kreatin", "gainer", "bcaa", "arginine", "arjinin", "supplement", "takviye", "karbonhidrat", "glutamine", "glutamin"}
    
    words = set(re.findall(r"\w+", query_lower))
    if words.intersection(grocery_keywords):
        return "grocery"
    if words.intersection(electronics_keywords):
        return "electronics"
    if words.intersection(fashion_keywords):
        return "fashion"
    if words.intersection(supplement_keywords):
        return "supplement"
    return "general"

def is_logical_product(query: str, product_title: str) -> bool:
    query_lower = query.lower()
    title_lower = product_title.lower()
    
    # Prevent cooking oils and motor oils from mismatching
    cooking_oil_terms = {
        "yudum", "biryağ", "biryag", "komili", "orkide", "evin", "abalı", "abali", 
        "salat", "safya", "sole", "vera", "ayçiçek", "aycicek", "zeytinyağı", 
        "zeytinyagi", "mısırözü", "misirozu", "kırlangıç", "kirlangic", "sıvı yağ", "sivi yag"
    }
    motor_oil_terms = {
        "motor yağı", "motor yagi", "şanzıman", "sanziman", "sentetik", "5w-30", 
        "5w30", "10w-40", "10w40", "5w-40", "5w40", "castrol", "motul", "mobil 1", 
        "shell helix", "liqui moly", "lubex"
    }
    
    # Temizlik/kozmetik urunler yemeklik yag adiyla pazarlaniyor olabilir
    # (orn. "zeytinyagli sivi sabun") -- bu, yemeklik yag aramasinda alakasiz
    # sonuc olarak cikmamali.
    cleaning_cosmetic_terms = {
        "sabun", "deterjan", "şampuan", "sampuan", "losyon", "krem",
        "duş jeli", "dus jeli", "saç bakım", "sac bakim", "vücut yağı", "vucut yagi",
    }

    has_cooking_query = any(t in query_lower for t in cooking_oil_terms)
    has_motor_query = any(t in query_lower for t in motor_oil_terms)
    has_cleaning_query = any(t in query_lower for t in cleaning_cosmetic_terms)

    if has_cooking_query:
        if any(t in title_lower for t in motor_oil_terms) and not has_motor_query:
            return False
        if any(t in title_lower for t in cleaning_cosmetic_terms) and not has_cleaning_query:
            return False

    if has_motor_query:
        if any(t in title_lower for t in cooking_oil_terms) and not has_cooking_query:
            return False

    # Cihaz aramasinda (orn. "laptop") o cihaz icin canta/kilif gibi bir
    # aksesuar cikmamali -- baslikta hem cihaz adi hem aksesuar kelimesi
    # AYRI AYRI geciyorsa (tam ifade degil, AliExpress tarzi basliklarda
    # "Women's Laptop & Briefcase" gibi) bu genelde asil cihaz degildir.
    device_terms = {"laptop", "notebook", "telefon", "phone", "tablet"}
    accessory_terms = {
        "bag", "case", "sleeve", "briefcase", "backpack",
        "çanta", "canta", "kılıf", "kilif",
    }
    has_device_query = any(t in query_lower for t in device_terms)
    has_accessory_query = any(t in query_lower for t in accessory_terms)
    if has_device_query and not has_accessory_query:
        if any(t in title_lower for t in device_terms) and any(t in title_lower for t in accessory_terms):
            return False

    irrelevant_terms = [
        "bezi", "spreyi", "solüsyonu", "temizleme",
        "kılıfı", "kutusu", "kabı", "kılıf", "kapak",
        "ipi", "askı", "askısı", "zinciri", "aparat", "aparatı", "standı",
        "cam koruyucu", "ekran koruyucu", "kırılmaz cam",
        "şarj kablosu", "yedek parça", "aksesuar",
        "tornavida", "yedek cam", "vidası", "vida",
        "temizleyici", "koruyucu", "kutusu", "çantası", "çanta",
        "kordonu", "kordon", "kılıfı", "askı aparatı", "temizleme mendili",
        "taşıyıcı", "taşıyıcısı", "vantuz",
    ]
    
    for term in irrelevant_terms:
        if term in title_lower and term not in query_lower:
            return False
            
    return True

def apply_gender_to_query(query: str, user_gender: str | None) -> str:
    if not user_gender or user_gender not in ("erkek", "kadın"):
        return query
    query_lower = query.lower()
    gender_keywords = ["erkek", "kadın", "kız", "bayan", "bay", "unisex", "kadin", "kiz"]
    for keyword in gender_keywords:
        if keyword in query_lower:
            return query
    return f"{user_gender} {query}"


def normalize_turkish_search_query(query: str) -> str:
    """Sık yazılan ASCII Türkçe ürün kelimelerini arama biçimine getir."""
    replacements = {
        "sut": "süt",
        "sampuan": "şampuan",
        "camasir": "çamaşır",
        "bulasik": "bulaşık",
        "yogurt": "yoğurt",
        "peynir": "peynir",
        "pirinc": "pirinç",
        "seker": "şeker",
        "cay": "çay",
        "kahvaltilik": "kahvaltılık",
        "kulaklik": "kulaklık",
        "ayakkabi": "ayakkabı",
        "gomlek": "gömlek",
        "canta": "çanta",
        "corap": "çorap",
        "supurge": "süpürge",
        "catal": "çatal",
        "kasik": "kaşık",
        "bicak": "bıçak",
        "carsaf": "çarşaf",
        "yastik": "yastık",
        "hali": "halı",
        "firin": "fırın",
    }
    normalized = str(query or "").strip()
    for plain, turkish in replacements.items():
        normalized = re.sub(
            rf"(?<!\w){re.escape(plain)}(?!\w)",
            turkish,
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized

def detect_brand_in_query(query: str) -> str | None:
    query_lower = query.lower()
    brands = [
        "ray-ban", "rayban", "police", "mustang", "inesta", "ossee", "hawk", "prada", "gucci", "vogue", "oakley", "lacoste", "tommy hilfiger", "calvin klein",
        "apple", "iphone", "ipad", "macbook", "samsung", "xiaomi", "redmi", "huawei", "oppo", "realme", "vivo", "asus", "lenovo", "hp", "dell", "acer", "monster", "msi", "sony", "philips", "jbl", "bose", "sennheiser", "anker", "logitech", "razer", "steelseries", "corsair",
        "hardline", "bigjoy", "supplementler", "proteinocean", "optimum", "scitec", "grenade", "olimp", "weider", "mysupplement", "runnutrition",
        "karaca", "tefal", "arnica", "fakir", "braun", "arçelik", "arcelik", "beko", "vestel", "bosch", "siemens", "profilo",
        "defacto", "koton", "mavi", "lc waikiki", "lcw", "zara", "mango", "nike", "adidas", "puma", "reebok", "under armour", "skechers", "columbia"
    ]
    for brand in brands:
        if re.search(rf"\b{re.escape(brand)}\b", query_lower):
            return brand
    return None

def extract_corrected_query(html_content: str, default_query: str) -> str:
    spelled_match = re.search(r'"spelledQuery"\s*:\s*"([^"]*)"', html_content)
    if spelled_match and spelled_match.group(1).strip():
        return spelled_match.group(1).strip()
    search_text_match = re.search(r'"searchTextInfo"\s*:\s*"([^"]+)"', html_content)
    if search_text_match and search_text_match.group(1).strip():
        return search_text_match.group(1).strip()
    return default_query

def parse_price(val_str: str) -> float | None:
    if not val_str:
        return None
    val_str = re.sub(r"[^\d,\.]", "", val_str)
    if not val_str:
        return None
    if "," in val_str and "." in val_str:
        if val_str.rfind(",") > val_str.rfind("."):
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            val_str = val_str.replace(",", "")
    elif "," in val_str:
        val_str = val_str.replace(".", "").replace(",", ".")
    else:
        parts = val_str.split(".")
        if len(parts) > 2:
            val_str = "".join(parts)
        elif len(parts) == 2 and len(parts[1]) == 3:
            val_str = "".join(parts)
    try:
        return float(val_str)
    except ValueError:
        return None

def _fetch_aol_urls(query: str) -> list[str]:
    # AOL is a reliable Yahoo proxy for finding product details across multiple stores
    modified_query = f'{query} "sepete ekle" (site:trendyol.com OR site:hepsiburada.com OR site:n11.com OR site:amazon.com.tr OR site:gratis.com OR site:rossmann.com.tr OR site:migros.com.tr OR site:carrefoursa.com OR site:sokmarket.com.tr OR site:metro-tr.com OR site:vatanbilgisayar.com OR site:itopya.com OR site:mediamarkt.com.tr OR site:teknosa.com)'
    url = f"https://search.aol.com/aol/search?q={urllib.parse.quote_plus(modified_query)}"
    headers = {
        "User-Agent": YAHOO_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    found_urls = []
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select(".algo-srch") or soup.select(".compTitle") or soup.select("h3.title a") or soup.select("h3 a")
            for result in results:
                link_el = result.find("a") if hasattr(result, "find") else result
                if not link_el:
                    continue
                href = link_el.get("href")
                actual_url = extract_yahoo_url(href)
                if not actual_url:
                    continue
                store = detect_source(actual_url)
                if store != "manual" and is_valid_product_url(actual_url, store):
                    if actual_url not in found_urls:
                        found_urls.append(actual_url)
    except Exception:
        pass
    return found_urls

def search_n11_direct(query: str) -> tuple[list[dict], str]:
    url = f"https://www.n11.com/arama?q={urllib.parse.quote_plus(query)}"
    headers = {
        "User-Agent": YAHOO_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    parsed_results = []
    corrected_query = query
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            corrected_query = extract_corrected_query(r.text, query)
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("a.product-item")
            
            for item in items:
                href = item.get("href")
                if not href:
                    continue
                product_url = urllib.parse.urljoin("https://www.n11.com", href)
                
                title_el = item.select_one(".product-item-title")
                title = title_el.get_text(" ", strip=True) if title_el else ""
                if not title:
                    img_el = item.select_one("img.listing-items-image")
                    title = img_el.get("alt", "") if img_el else ""
                
                if not title:
                    continue
                    
                img_el = item.select_one("img.listing-items-image") or item.select_one("img")
                image_url = ""
                if img_el:
                    image_url = img_el.get("data-src") or img_el.get("src") or img_el.get("data-original") or ""
                    
                price_el = item.select_one(".price-currency") or item.select_one("h3.price-currency")
                price = parse_price(price_el.get_text(" ", strip=True)) if price_el else None
                
                is_out_of_stock = price is None or price == 0
                price_val = price if not is_out_of_stock else 0
                
                old_price_el = item.select_one(".old-price")
                original_price = parse_price(old_price_el.get_text(" ", strip=True)) if old_price_el else None
                
                parsed_results.append({
                    "title": title,
                    "price": price_val,
                    "original_price": original_price,
                    "image_url": image_url,
                    "source": "n11",
                    "url": product_url,
                    "labels": ["Stokta Yok"] if is_out_of_stock else ["Önerilen"],
                    "extra_info": {
                        "out_of_stock": is_out_of_stock
                    }
                })
    except Exception:
        pass
        
    return parsed_results, corrected_query

def search_trendyol_direct(query: str) -> list[dict]:
    """
    Trendyol arama — gerçek veri kaynağı: HTML'e SSR ile gömülü
    window["__single-search-result__PROPS"].data.products (2026-07 itibarıyla
    doğrulandı; mobil API ve eski __SEARCH_APP_INITIAL_STATE__ artık kapalı/farklı).
    """
    import json as _json
    from app.scraping_proxy import proxy_get, proxy_enabled

    url = f"https://www.trendyol.com/sr?q={urllib.parse.quote_plus(query)}"
    html = None
    if proxy_enabled():
        # Trendyol artık doğrudan isteklerde Cloudflare JS zorluğu ("Just a
        # moment...") gösteriyor; bunu çözmek için render_js=True gerekiyor.
        html = proxy_get(url, render_js=True, timeout=20)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html or "Just a moment" in html[:2000]:
        return []

    m = re.search(r'window\["__single-search-result__PROPS"\]\s*=\s*(\{.+?\})\s*;?\s*</script>', html, re.DOTALL)
    if not m:
        return []
    try:
        state = _json.loads(m.group(1))
    except Exception:
        return []

    prods = (state.get("data") or {}).get("products") or []
    results = []
    for p in prods[:10]:
        name = p.get("name") or ""
        if not name:
            continue
        pi = p.get("price") or {}
        price = pi.get("discountedPrice") or pi.get("current") or pi.get("originalPrice") or 0
        original = pi.get("original") or pi.get("originalPrice") or None
        slug = (p.get("url") or "").split("?")[0]
        prod_url = f"https://www.trendyol.com{slug}" if slug.startswith("/") else ""
        img = p.get("image") or ""
        if img and not img.startswith("http"):
            img = f"https://cdn.dsmcdn.com/{img}"
        results.append({
            "title": name, "price": float(price),
            "original_price": float(original) if original and original != price else None,
            "image_url": img, "source": "trendyol", "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": price == 0},
        })
    return results


def _extract_balanced_json(text: str, start_idx: int) -> str | None:
    """text[start_idx] '{' ile baslamali; esli parantezi (string/escape'lere
    dikkat ederek) bulup dengeli JSON alt-dizesini dondurur."""
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_idx:i + 1]
    return None


def _extract_balanced_escaped_json(text: str, start_idx: int) -> str | None:
    """Hepsiburada'nin STATE blogu gibi bastan sona \\" ile kacisli (disinda
    sarici tirnak olmayan) ham metinler icin dengeli parca cikarir.
    Not: ic ice kacis da olabiliyor (orn. 15.3\\\" boyut ifadesi, yani bir
    string DEGERININ icinde kacisli tirnak) -- bu yuzden '"' bazli string
    durumu takibi guvenilir degil (yanlis pozitif toggle olusturuyor).
    Bunun yerine: her '\\X' cifti (ne olursa olsun) opak kabul edilip
    atlanir; sadece KACISSIZ (bare) '{'/'}' karakterleri yapisal sayilir --
    JSON'da suslu parantezler asla escape gerektirmedigi icin bu guvenilir
    bir ayirt edicidir."""
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
        return None
    depth = 0
    i = start_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_idx:i + 1]
        i += 1
    return None




def search_hepsiburada_direct(query: str) -> list[dict]:
    """
    Hepsiburada arama — gerçek veri kaynağı: HTML'e SSR ile gömülü
    "window.MORIA.VERTICALFILTER = Object.assign(window.MORIA.VERTICALFILTER
    || {}, {'<uuid>': {'STATE': {"data":{"products":[...]}}}})" script bloğu
    (2026-07 itibarıyla doğrulandı). Dış sarmalayıcı JS obje literali
    (tek tırnaklı) ama 'STATE' degeri gecerli cift-tirnakli JSON oldugu icin
    dogrudan o kismi parantez dengeleyerek cikarip json.loads ediyoruz.
    """
    import json as _json
    from app.scraping_proxy import proxy_get, proxy_enabled

    url = f"https://www.hepsiburada.com/ara?q={urllib.parse.quote_plus(query)}"
    html = None
    if proxy_enabled():
        # Doğrudan istekler 403 (bot koruması) alabiliyor; ScrapingBee
        # render_js=True ile gerçek tarayıcı üzerinden dener.
        html = proxy_get(url, render_js=True, timeout=20)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
        return []

    products = None
    search_pos = 0
    while True:
        idx = html.find("VERTICALFILTER", search_pos)
        if idx == -1:
            break
        search_pos = idx + 1
        state_idx = html.find("'STATE':", idx)
        if state_idx == -1 or state_idx - idx > 500:
            continue
        # 'STATE' degerinin ici bastan sona \" ile kacisli ham metin (disinda
        # sarici tirnak yok). Icerikte bazen gercekten kacisli backslash da
        # var (orn. 15.3\" boyut ifadesi) -- naif \" -> " degisimi bunlari
        # bozuyordu. Tek gecisli, sirali unescape (\\ -> \, \" -> ") dogru
        # sonucu veriyor.
        brace_idx = html.find("{", state_idx)
        data = None
        if brace_idx != -1:
            json_str = _extract_balanced_escaped_json(html, brace_idx)
            if json_str:
                cleaned = re.sub(
                    r'\\\\|\\"',
                    lambda m: "\\" if m.group(0) == "\\\\" else '"',
                    json_str,
                )
                try:
                    data = _json.loads(cleaned)
                except Exception:
                    data = None
        if data is None:
            continue
        prods = (data.get("data") or {}).get("products")
        if prods:
            products = prods
            break
    if not products:
        return []

    results = []
    for p in products[:10]:
        try:
            variants = p.get("variantList") or []
            if not variants:
                continue
            v = variants[0]
            name = v.get("name") or ""
            if not name:
                continue
            listing = v.get("listing") or {}
            price_info = listing.get("priceInfo") or {}
            price = price_info.get("price") or 0
            original = price_info.get("originalPrice")
            slug = (v.get("url") or "").split("?")[0]
            prod_url = f"https://www.hepsiburada.com{slug}" if slug.startswith("/") else (slug or "")
            imgs = v.get("images") or {}
            if isinstance(imgs, dict):
                img = imgs.get("0") or (list(imgs.values())[0] if imgs else "")
            elif isinstance(imgs, list):
                img = imgs[0] if imgs else ""
            else:
                img = ""
            if isinstance(img, dict):
                img = img.get("link") or img.get("url") or ""
            if img and "{size}" in img:
                img = img.replace("{size}", "216x216")
            results.append({
                "title": name, "price": float(price),
                "original_price": float(original) if original and original != price else None,
                "image_url": img, "source": "hepsiburada", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": price == 0},
            })
        except Exception:
            continue
    return results


def search_amazon_tr(query: str) -> list[dict]:
    """Amazon.com.tr arama — HTML parse, geniş katalog."""
    _UA_LIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]
    import random as _r
    for attempt in range(3):
        try:
            url = f"https://www.amazon.com.tr/s?k={urllib.parse.quote_plus(query)}&language=tr_TR"
            headers = {
                "User-Agent": _r.choice(_UA_LIST),
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Referer": "https://www.google.com/",
            }
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 503:
                continue
            if not r.ok:
                return []
            # Handle meta-refresh redirect
            if 'meta http-equiv="refresh"' in r.text or "meta http-equiv='refresh'" in r.text:
                import re as _re
                m_url = _re.search(r'content=["\'][^"\']*URL=["\']?([^"\'>\s]+)', r.text, _re.IGNORECASE)
                if m_url:
                    redirect_url = m_url.group(1)
                    if redirect_url.startswith('/'):
                        redirect_url = 'https://www.amazon.com.tr' + redirect_url
                    r = requests.get(redirect_url, headers=headers, timeout=10)
                    if not r.ok:
                        continue
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("div[data-component-type='s-search-result']")
            if not items:
                continue
            results = []
            for item in items[:10]:
                name_el = item.select_one("h2 span")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue
                # Try .a-offscreen first (most reliable), then .a-price-whole
                price = 0.0
                offscreen = item.select_one(".a-price .a-offscreen")
                if offscreen:
                    raw = offscreen.get_text(strip=True).replace("\xa0", "").replace("TL", "").replace("₺", "").strip()
                    raw = raw.replace(".", "").replace(",", ".")
                    try:
                        price = float(raw)
                    except Exception:
                        pass
                if not price:
                    price_whole = item.select_one(".a-price-whole")
                    price_frac = item.select_one(".a-price-fraction")
                    if price_whole:
                        pw = price_whole.get_text(strip=True).replace(".", "").replace(",", "")
                        pf = price_frac.get_text(strip=True).replace(",", "") if price_frac else "0"
                        try:
                            price = float(f"{pw}.{pf}")
                        except Exception:
                            price = 0.0
                # Build URL from data-asin (more reliable than href which is a tracking link)
                asin = item.get("data-asin", "")
                prod_url = f"https://www.amazon.com.tr/dp/{asin}" if asin else ""
                if not prod_url:
                    link_el = item.select_one("h2 a")
                    href = link_el.get("href", "") if link_el else ""
                    prod_url = f"https://www.amazon.com.tr{href}" if href.startswith("/") else href
                img_el = item.select_one("img.s-image")
                img = img_el.get("src", "") if img_el else ""
                results.append({
                    "title": name, "price": price, "original_price": None,
                    "image_url": img, "source": "amazon", "url": prod_url,
                    "labels": ["Önerilen"], "extra_info": {"out_of_stock": price == 0},
                })
            if results:
                return results
        except Exception:
            pass
    return []


def search_karaca(query: str) -> list[dict]:
    """Karaca — eski /search?q= adresi 404 veriyordu, gerçek arama rotası
    /product/search?q= (anasayfa arama formundan doğrulandı)."""
    return _scrape_jsonld_itemlist(
        f"https://www.karaca.com/product/search?q={urllib.parse.quote_plus(query)}",
        "karaca", render_js=False, timeout=12
    )

def search_watsons(query: str) -> list[dict]:
    """Watsons ürün araması — doğrudan istekte 403 (bot koruması) alıyor,
    ScrapingBee render_js=True ile JS render edilmiş sayfa üzerinden dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.watsons.com.tr/search?text={urllib.parse.quote_plus(query)}",
        "watsons", render_js=True, timeout=15
    )

def search_gratis(query: str) -> list[dict]:
    """Gratis ürün araması — modern JS-SPA, statik HTML'de JSON-LD/fiyat yok,
    ScrapingBee render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.gratis.com/search?q={urllib.parse.quote_plus(query)}",
        "gratis", render_js=True, timeout=15
    )

def search_mediamarkt(query: str) -> list[dict]:
    """MediaMarkt Türkiye ürün araması — JSON-LD ItemList."""
    try:
        url = f"https://www.mediamarkt.com.tr/tr/search.html?query={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data.get("itemListElement", [])
                if not items:
                    continue
                for item in items[:10]:
                    prod = item.get("item", item)
                    name = prod.get("name", "")
                    if not name:
                        continue
                    offers = prod.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    try:
                        price = float(str(offers.get("price", 0)).replace(",", "."))
                    except Exception:
                        continue
                    if price <= 0:
                        continue
                    prod_url = prod.get("url", "")
                    image = prod.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""
                    results.append({
                        "title": name, "price": price, "original_price": None,
                        "image_url": image, "source": "mediamarkt", "url": prod_url,
                        "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                    })
                if results:
                    break
            except Exception:
                continue
        return results
    except Exception:
        return []


def search_teknosa(query: str) -> list[dict]:
    """Teknosa ürün araması — JSON-LD ItemList."""
    try:
        url = f"https://www.teknosa.com/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data.get("itemListElement", [])
                if not items:
                    continue
                for item in items[:10]:
                    prod = item.get("item", item)
                    name = prod.get("name", "")
                    if not name:
                        continue
                    offers = prod.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    try:
                        price = float(str(offers.get("price", 0)).replace(",", "."))
                    except Exception:
                        continue
                    if price <= 0:
                        continue
                    prod_url = prod.get("url", "")
                    if prod_url and not prod_url.startswith("http"):
                        prod_url = "https://www.teknosa.com" + prod_url
                    image = prod.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""
                    results.append({
                        "title": name, "price": price, "original_price": None,
                        "image_url": image, "source": "teknosa", "url": prod_url,
                        "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                    })
                if results:
                    break
            except Exception:
                continue
        return results
    except Exception:
        return []


def search_boyner(query: str) -> list[dict]:
    """Boyner ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.boyner.com.tr/arama?searchTerm={urllib.parse.quote_plus(query)}",
        "boyner", render_js=True, timeout=15
    )

def search_flo(query: str) -> list[dict]:
    """FLO ürün araması — data-gtm-product JSON attribute."""
    try:
        url = f"https://www.flo.com.tr/search?q={urllib.parse.quote_plus(query)}"
        r = requests.get(url, headers=_STD_HEADERS, timeout=10)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product.product-list[data-gtm-product]")[:10]:
            try:
                gtm = json.loads(item.get("data-gtm-product", "{}"))
            except Exception:
                continue
            name = gtm.get("name", "")
            if not name:
                continue
            try:
                price = float(str(gtm.get("price", 0)).replace(",", "."))
            except Exception:
                continue
            if price <= 0:
                continue
            href = gtm.get("url", "")
            prod_url = f"https://www.flo.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("src") or "") if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "flo", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []

def search_decathlon(query: str) -> list[dict]:
    """Decathlon ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.decathlon.com.tr/search?Ntt={urllib.parse.quote_plus(query)}",
        "decathlon", render_js=True, timeout=15
    )

def search_lcwaikiki(query: str) -> list[dict]:
    """
    LC Waikiki ürün araması — gerçek veri kaynağı: HTML'e SSR ile gömülü
    "var catalogModel = {...}" script bloğu (2026-07 itibarıyla doğrulandı;
    eski /tr-TR/TR/search/index.aspx yolu artık ana sayfaya düşüyor).
    """
    import json as _json
    from app.scraping_proxy import proxy_get, proxy_enabled

    url = f"https://www.lcw.com/arama?q={urllib.parse.quote_plus(query)}"
    html = None
    if proxy_enabled():
        html = proxy_get(url, render_js=False, timeout=12)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
        return []

    m = re.search(r'var\s+catalogModel\s*=\s*(\{.+?\})\s*;\s*(?:var|\n\s*</script>)', html, re.DOTALL)
    if not m:
        return []
    try:
        state = _json.loads(m.group(1))
    except Exception:
        return []

    items = ((state.get("CatalogList") or {}).get("Items")) or []
    results = []
    for p in items[:10]:
        name = p.get("ProductDescription") or ""
        if not name:
            continue
        price = p.get("PriceValue") or 0
        old_price = p.get("MinOldPrice") or p.get("MaxCurrentPrice")
        slug = p.get("ModelUrl") or ""
        prod_url = f"https://www.lcw.com{slug}" if slug.startswith("/") else ""
        imgs = p.get("OptionImageUrlList") or []
        img = imgs[0] if imgs else ""
        results.append({
            "title": name, "price": float(price),
            "original_price": float(old_price) if old_price and old_price != price else None,
            "image_url": img, "source": "lcwaikiki", "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": price == 0},
        })
    return results


def search_mavi(query: str) -> list[dict]:
    """
    Mavi ürün araması — gerçek veri kaynağı: sayfadaki application/ld+json
    script'i, mainEntity.offers['@graph'].itemListElement (2026-07 itibarıyla
    doğrulandı; eski /search?q= yolu artık /search/?text= olarak çalışıyor).
    """
    import json as _json
    from app.scraping_proxy import proxy_get, proxy_enabled

    url = f"https://www.mavi.com/search/?text={urllib.parse.quote_plus(query)}"
    html = None
    if proxy_enabled():
        html = proxy_get(url, render_js=False, timeout=12)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "{}")
            graph = ((data.get("mainEntity") or {}).get("offers") or {}).get("@graph") or {}
            elems = graph.get("itemListElement") or []
            if elems:
                items = elems
                break
        except Exception:
            continue
    if not items:
        return []

    results = []
    for elem in items[:10]:
        p = elem.get("item") or {}
        name = p.get("name") or ""
        if not name:
            continue
        offers = p.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        try:
            price = float(offers.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        prod_url = offers.get("url") or ""
        img = p.get("image") or ""
        if isinstance(img, list):
            img = img[0] if img else ""
        results.append({
            "title": name, "price": price, "original_price": None,
            "image_url": img, "source": "mavi", "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
        })
    return results

def search_zara(query: str) -> list[dict]:
    """Zara — URL doğru, eski selector'lar sitenin güncel yapısıyla
    eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.zara.com/tr/tr/search?searchTerm={urllib.parse.quote_plus(query)}",
        "zara", render_js=False, timeout=12
    )


def search_bim(query: str) -> list[dict]:
    """BIM ürün araması."""
    try:
        url = f"https://www.bim.com.tr/search.aspx?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, .item, [class*='product-card']")[:10]:
            name_el = item.select_one(".product-name, .item-name, h3, h4, [class*='name']")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price, .item-price")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True).replace("TL","").replace("₺","").replace(".","").replace(",",".").strip()
            raw = re.sub(r"[^\d.]","", raw)
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href","") if link_el else ""
            prod_url = f"https://www.bim.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bim", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_rossmann(query: str) -> list[dict]:
    """Rossmann ürün araması — Magento platformu, doğru arama URL'si
    catalogsearch/result/ (eski /ara?q= adresi 404 veriyordu)."""
    return _scrape_jsonld_itemlist(
        f"https://www.rossmann.com.tr/catalogsearch/result/?q={urllib.parse.quote_plus(query)}",
        "rossmann", render_js=False, timeout=12
    )

def search_supplementler(query: str) -> list[dict]:
    """Supplementler.com — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.supplementler.com/search/?q={urllib.parse.quote_plus(query)}",
        "supplementler", render_js=False, timeout=12
    )


def search_englishhome(query: str) -> list[dict]:
    """English Home — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu."""
    return _scrape_jsonld_itemlist(
        f"https://www.englishhome.com/?q={urllib.parse.quote_plus(query)}",
        "englishhome", render_js=False, timeout=12
    )


def search_a101(query: str) -> list[dict]:
    """
    A101 ürün araması — DOM tabanlı (2026-07 itibarıyla doğrulandı).
    URL: /arama?k= (eski ?q= geçersiz). JSON-LD/__NEXT_DATA__ yok, ürün
    kartları .dashboard-product-container, fiyat "₺" ile başlıyor,
    indirimli üründe eski fiyat "line-through" class'ıyla ayırt ediliyor.
    """
    from app.scraping_proxy import proxy_get, proxy_enabled

    url = f"https://www.a101.com.tr/arama?k={urllib.parse.quote_plus(query)}"
    html = None
    if proxy_enabled():
        # A101 ürün listesini tamamen client-side render ediyor (statik HTML'de
        # kart yok) — render_js=True şart, yoksa 0 sonuç döner.
        html = proxy_get(url, render_js=True, timeout=20)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select(".dashboard-product-container")[:10]:
        name_el = card.select_one("h3")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue
        price_spans = [s for s in card.find_all("span") if "₺" in s.get_text()]
        if not price_spans:
            continue
        current_el = next((s for s in price_spans if "line-through" not in (s.get("class") or [])), price_spans[-1])
        original_el = next((s for s in price_spans if "line-through" in (s.get("class") or [])), None)
        price = parse_price(current_el.get_text(strip=True))
        original = parse_price(original_el.get_text(strip=True)) if original_el else None
        if not price or price <= 0:
            continue
        link_el = card.find_parent("a") or card.select_one("a[href]")
        href = link_el.get("href", "") if link_el else ""
        prod_url = f"https://www.a101.com.tr{href}" if href.startswith("/") else href
        img_el = card.select_one("img")
        img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
        results.append({
            "title": name, "price": price,
            "original_price": original if original and original != price else None,
            "image_url": img, "source": "a101", "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
        })
    return results


def search_sokmarket(query: str) -> list[dict]:
    """
    ŞOK Market ürün araması — DOM tabanlı (2026-07 itibarıyla doğrulandı).
    URL zaten doğruydu (/arama?q=), sadece selector'lar CSS Modules ile
    değişmiş (kısmi class eşleşmesiyle stabil: CProductCard-module_*,
    CPriceBox-module_*). İçerik SSR, render_js gerekmiyor.
    """
    try:
        url = f"https://www.sokmarket.com.tr/arama?q={urllib.parse.quote_plus(query)}"
        html = None
        try:
            from app.scraping_proxy import proxy_get, proxy_enabled
            if proxy_enabled():
                # Vercel'in ust taramada uyguladigi 7s'lik sinirdan once bitmesi
                # sart -- yoksa istek gonderilmeden container donduruluyor.
                html = proxy_get(url, render_js=False, timeout=5)
        except Exception:
            html = None
        if not html:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for item in soup.select("[class*='CProductCard-module_productCardWrapper']")[:10]:
            name_el = item.select_one("[class*='CProductCard-module_title']")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='CPriceBox-module_price']")
            if not price_el:
                continue
            price = parse_price(price_el.get_text(strip=True))
            if not price or price <= 0:
                continue
            link_el = item.select_one("a[href]") or item.find_parent("a")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.sokmarket.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "sokmarket", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_temu(query: str) -> list[dict]:
    """temu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.temu.com/tr/search_result.html?search_key={urllib.parse.quote_plus(query)}",
        "temu", render_js=False, timeout=12
    )


def search_pazarama(query: str) -> list[dict]:
    """pazarama — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.pazarama.com/search?q={urllib.parse.quote_plus(query)}",
        "pazarama", render_js=True, timeout=15
    )


def search_ciceksepeti(query: str) -> list[dict]:
    try:
        url = f"https://www.ciceksepeti.com/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True).replace("TL","").replace("₺","").replace(".","").replace(",",".").strip()
            raw = re.sub(r"[^\d.]","", raw)
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href","") if link_el else ""
            prod_url = f"https://www.ciceksepeti.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "ciceksepeti", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_xiaomi(query: str) -> list[dict]:
    """xiaomi — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.mi.com/tr/search/?keyword={urllib.parse.quote_plus(query)}",
        "xiaomi", render_js=True, timeout=15
    )


def search_huawei(query: str) -> list[dict]:
    """huawei — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://consumer.huawei.com/tr/search/?keywords={urllib.parse.quote_plus(query)}",
        "huawei", render_js=True, timeout=15
    )


def search_hp(query: str) -> list[dict]:
    """hp — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.hp.com/tr-tr/search/results.html?query={urllib.parse.quote_plus(query)}",
        "hp", render_js=True, timeout=15
    )


def search_lenovo(query: str) -> list[dict]:
    """lenovo — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.lenovo.com/tr/tr/search?q={urllib.parse.quote_plus(query)}",
        "lenovo", render_js=True, timeout=15
    )


def search_evkur(query: str) -> list[dict]:
    try:
        url = f"https://www.evkur.com.tr/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .urun")[:10]:
            name_el = item.select_one(".product-name, [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True).replace("TL","").replace("₺","").replace(".","").replace(",",".").strip()
            raw = re.sub(r"[^\d.]","", raw)
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href","") if link_el else ""
            prod_url = f"https://www.evkur.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "evkur", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_penti(query: str) -> list[dict]:
    """penti — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.penti.com/tr/search?q={urllib.parse.quote_plus(query)}",
        "penti", render_js=True, timeout=15
    )


def search_colins(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.colins.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "colins", render_js=False, timeout=12
    )

def search_twist(query: str) -> list[dict]:
    """Twist — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.twist.com.tr/?s={urllib.parse.quote_plus(query)}",
        "twist", render_js=True, timeout=15
    )


def search_ltb(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.ltb.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "ltb", render_js=False, timeout=12
    )

def search_modanisa(query: str) -> list[dict]:
    """Modanisa — URL doğru, eski selector'lar sitenin güncel yapısıyla
    eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.modanisa.com/search?q={urllib.parse.quote_plus(query)}",
        "modanisa", render_js=False, timeout=12
    )


def search_nike(query: str) -> list[dict]:
    try:
        url = f"https://www.nike.com/tr/w?q={urllib.parse.quote_plus(query)}&vst={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-card")[:10]:
            name_el = item.select_one("[class*='product-title'], [class*='title'], [class*='subtitle'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True).replace("TL","").replace("₺","").replace(".","").replace(",",".").strip()
            raw = re.sub(r"[^\d.]","", raw)
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href","") if link_el else ""
            prod_url = f"https://www.nike.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "nike", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_puma(query: str) -> list[dict]:
    """Puma — eski URL (/tr/tr/search) 404 veriyordu, gerçek arama rotası
    /search?q=. Yine de yeterli statik ürün verisi yok, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://tr.puma.com/search?q={urllib.parse.quote_plus(query)}",
        "puma", render_js=True, timeout=15
    )

def search_newbalance(query: str) -> list[dict]:
    """New Balance — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.newbalance.com.tr/?s={urllib.parse.quote_plus(query)}",
        "newbalance", render_js=True, timeout=15
    )


def search_sportive(query: str) -> list[dict]:
    """Sportive — eski /search?q= 404 veriyordu, gerçek arama rotası
    /arama?q= (15 gerçek fiyat bulundu)."""
    return _scrape_jsonld_itemlist(
        f"https://www.sportive.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "sportive", render_js=False, timeout=12
    )

def search_flormar(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.flormar.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "flormar", render_js=False, timeout=12
    )

def search_goldenrose(query: str) -> list[dict]:
    """Golden Rose — www.goldenrose.com.tr sadece tanıtım sitesi, asıl
    mağaza shop.goldenrose.com.tr'de (meta-refresh ile yönlendiriyordu,
    eski kod yanlış domain'i kullanıyordu). Vue.js tabanlı dinamik arama
    (dynamic-search) kullandığı için render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://shop.goldenrose.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "goldenrose", render_js=True, timeout=15
    )


def search_istikbal(query: str) -> list[dict]:
    try:
        url = f"https://www.istikbal.com.tr/ara?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .product")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True).replace("TL","").replace("₺","").replace(".","").replace(",",".").strip()
            raw = re.sub(r"[^\d.]","", raw)
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href","") if link_el else ""
            prod_url = f"https://www.istikbal.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "istikbal", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_bellona(query: str) -> list[dict]:
    """bellona — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.bellona.com.tr/ara?q={urllib.parse.quote_plus(query)}",
        "bellona", render_js=False, timeout=12
    )


def search_madamecoco(query: str) -> list[dict]:
    """Madame Coco — eski URL (/?q=) ana sayfaya düşüyordu, gerçek arama
    rotası /list?q= ama sonuçlar istemci tarafında render ediliyor
    (statik HTML'deki TL eşleşmeleri gerçek ürün değil, gömülü JS config).
    render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.madamecoco.com/list?q={urllib.parse.quote_plus(query)}",
        "madamecoco", render_js=True, timeout=15
    )


def search_korkmaz(query: str) -> list[dict]:
    """Korkmaz — statik HTML'de arama formu/sonucu bulunamadı (JS-render
    edilen bir SPA olabilir), ScrapingBee render_js=True ile dener."""
    try:
        return _scrape_jsonld_itemlist(
            f"https://www.korkmaz.com.tr/search?q={urllib.parse.quote_plus(query)}",
            "korkmaz", render_js=True, timeout=15
        )
    except Exception:
        return []


def search_kitapyurdu(query: str) -> list[dict]:
    """KitapYurdu ürün araması — .ky-product HTML selector."""
    try:
        url = f"https://www.kitapyurdu.com/index.php?route=product/search&filter_name={urllib.parse.quote_plus(query)}"
        r = requests.get(url, headers=_STD_HEADERS, timeout=10)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".ky-product")[:10]:
            name_el = item.select_one(".ky-product-title")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_els = item.select("[class*=price]")
            price = None
            for pel in price_els:
                raw = re.sub(r"[^\d,.]", "", pel.get_text(strip=True)).replace(",", ".")
                try:
                    v = float(raw)
                    if v > 0:
                        price = v
                        break
                except Exception:
                    continue
            if not price:
                continue
            link_el = item.select_one("a[href]")
            prod_url = link_el.get("href", "") if link_el else ""
            img_el = item.select_one("img")
            img = (img_el.get("src") or "") if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "kitapyurdu", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []

def search_dr(query: str) -> list[dict]:
    """D&R ürün araması — data-gtm attribute JSON."""
    try:
        url = f"https://www.dr.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[data-gtm-product], .product-card[data-gtm]")[:20]:
            try:
                gtm = json.loads(item.get("data-gtm", "{}"))
            except Exception:
                continue
            name = gtm.get("item_name", gtm.get("name", ""))
            if not name:
                continue
            try:
                price = float(str(gtm.get("price", 0)).replace(",", "."))
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.dr.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "dr", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
            if len(results) >= 10:
                break
        return results
    except Exception:
        return []


def search_idefix(query: str) -> list[dict]:
    """Idefix — statik HTML'de gerçek fiyat var ama JSON-LD/sezgisel
    tarayıcı yakalayamıyor, render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.idefix.com/Search?q={urllib.parse.quote_plus(query)}",
        "idefix", render_js=True, timeout=15
    )

def search_bebek(query: str) -> list[dict]:
    """bebek.com — Next.js App Router, statik HTML'de ürün/fiyat yok
    (istemci tarafında render ediliyor), ScrapingBee render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.bebek.com/arama?q={urllib.parse.quote_plus(query)}",
        "bebek", render_js=True, timeout=15
    )


def search_ebebek(query: str) -> list[dict]:
    """e-bebek ürün araması — JSON-LD ItemList."""
    try:
        url = f"https://www.ebebek.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data.get("itemListElement", [])
                if not items:
                    continue
                for item in items[:10]:
                    prod = item.get("item", item)
                    name = prod.get("name", "")
                    if not name:
                        continue
                    offers = prod.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    try:
                        price = float(str(offers.get("price", 0)).replace(",", "."))
                    except Exception:
                        continue
                    if price <= 0:
                        continue
                    prod_url = prod.get("url", "")
                    image = prod.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""
                    results.append({
                        "title": name, "price": price, "original_price": None,
                        "image_url": image, "source": "ebebek", "url": prod_url,
                        "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                    })
                if results:
                    break
            except Exception:
                continue
        return results
    except Exception:
        return []


def search_toyzz(query: str) -> list[dict]:
    """Toyzz Shop — statik HTML'de fiyat yok (no-cache başlıkları ve boş
    yapı JS-render edildiğini gösteriyor), ScrapingBee render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.toyzzshop.com/arama?q={urllib.parse.quote_plus(query)}",
        "toyzz", render_js=True, timeout=15
    )


# EV ALETLERİ & MUTFAK
def search_tefal(query: str) -> list[dict]:
    """Tefal — URL doğru, eski selector'lar sitenin güncel yapısıyla
    eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.tefal.com.tr/?s={urllib.parse.quote_plus(query)}",
        "tefal", render_js=False, timeout=12
    )


def search_arnica(query: str) -> list[dict]:
    try:
        url = f"https://www.arnica.com.tr/?s={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product, .product-item, [class*='product']")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True)
            raw = re.sub(r"[^\d,.]", "", raw).replace(",", ".")
            try:
                price = float(raw.split(".")[0] + ("." + raw.split(".")[-1] if raw.count(".") == 1 else ""))
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.arnica.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "arnica", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_arzum(query: str) -> list[dict]:
    """arzum — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.arzum.com.tr/?s={urllib.parse.quote_plus(query)}",
        "arzum", render_js=False, timeout=12
    )


def search_schafer(query: str) -> list[dict]:
    """schafer — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.schafer.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "schafer", render_js=False, timeout=12
    )


def search_fakir(query: str) -> list[dict]:
    try:
        url = f"https://www.fakir.com.tr/?s={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product, .product-item, [class*='product']")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True)
            raw = re.sub(r"[^\d,.]", "", raw).replace(",", ".")
            try:
                price = float(raw.split(".")[0] + ("." + raw.split(".")[-1] if raw.count(".") == 1 else ""))
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.fakir.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "fakir", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_bosch(query: str) -> list[dict]:
    """Bosch Home — eski kod yanlış domain kullanıyordu (bosch-home.com
    global sitesi .tr'ye 404 veriyor), gerçek Türkiye sitesi
    bosch-home.com.tr. Statik HTML'de arama sonucu bulunamadığından
    render_js=True ile dener."""
    try:
        return _scrape_jsonld_itemlist(
            f"https://www.bosch-home.com.tr/arama?q={urllib.parse.quote_plus(query)}",
            "bosch", render_js=True, timeout=15
        )
    except Exception:
        return []


# MOBİLYA & EV DEKOR
def search_evidea(query: str) -> list[dict]:
    try:
        url = f"https://www.evidea.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        # Evidea araması gevşek eşleşiyor (koltuk → halı/koltuk yıkama makinesi);
        # tüm sorgu kelimeleri başlıkta geçmeli (TR karakterler normalize edilir)
        _tr = str.maketrans("şğıöüçâî", "sgioucai")
        query_words = {w for w in re.findall(r"\w+", query.lower().translate(_tr)) if len(w) > 2}
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            title_words = set(re.findall(r"\w+", name.lower().translate(_tr)))
            if query_words and not query_words.issubset(title_words):
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            price = parse_price(price_el.get_text(strip=True))
            if not price or price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.evidea.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "evidea", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_vivense(query: str) -> list[dict]:
    """Vivense ürün araması — data-product-name/price attribute."""
    try:
        url = f"https://www.vivense.com/ara?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[data-product-name][data-product-price]")[:10]:
            name = item.get("data-product-name", "")
            if not name:
                continue
            try:
                price = float(str(item.get("data-product-price", "0")).replace(",", "."))
            except Exception:
                continue
            if price <= 0:
                continue
            href = item.get("data-url", "")
            prod_url = f"https://www.vivense.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "vivense", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_kelebek(query: str) -> list[dict]:
    """kelebek — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.kelebek.com/arama?q={urllib.parse.quote_plus(query)}",
        "kelebek", render_js=False, timeout=12
    )


def search_dogtas(query: str) -> list[dict]:
    """Doğtaş — eski /?s= adresi neredeyse boş dönüyordu, gerçek arama
    rotası /arama?q= (statik HTML'de 60+ gerçek fiyat bulundu)."""
    return _scrape_jsonld_itemlist(
        f"https://www.dogtas.com/arama?q={urllib.parse.quote_plus(query)}",
        "dogtas", render_js=False, timeout=12
    )


# YAPI MARKET
def search_bauhaus(query: str) -> list[dict]:
    """Bauhaus — doğrudan istekte 403 (bot koruması) alıyor,
    ScrapingBee render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.bauhaus.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "bauhaus", render_js=True, timeout=15
    )


# PET
def search_petlebi(query: str) -> list[dict]:
    """Petlebi — eski /search?q= yeterli veri döndürmüyordu (site canlı
    bir öneri API'sine sahip ama arama sayfası JS-render), gerçek arama
    parametresi query'e düzeltildi + render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.petlebi.com/search?query={urllib.parse.quote_plus(query)}",
        "petlebi", render_js=True, timeout=15
    )


# SUPPLEMENT EK
def search_proteinocean(query: str) -> list[dict]:
    """proteinocean — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.proteinocean.com/search?q={urllib.parse.quote_plus(query)}",
        "proteinocean", render_js=False, timeout=12
    )


def search_bigjoy(query: str) -> list[dict]:
    """bigjoy — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.bigjoy.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "bigjoy", render_js=False, timeout=12
    )


def search_runnutrition(query: str) -> list[dict]:
    """Run Nutrition — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.runnutrition.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "runnutrition", render_js=False, timeout=12
    )


# MODA EK
def search_pierrecardin(query: str) -> list[dict]:
    try:
        url = f"https://www.pierrecardin.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True)
            raw = re.sub(r"[^\d,.]", "", raw).replace(",", ".")
            try:
                price = float(raw.split(".")[0] + ("." + raw.split(".")[-1] if raw.count(".") == 1 else ""))
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.pierrecardin.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "pierrecardin", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# TEKNOLOJİ EK
def search_vatanbilgisayar(query: str) -> list[dict]:
    """vatanbilgisayar — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.vatanbilgisayar.com/?s={urllib.parse.quote_plus(query)}",
        "vatanbilgisayar", render_js=False, timeout=12
    )


def search_itopya(query: str) -> list[dict]:
    """itopya — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.itopya.com/?s={urllib.parse.quote_plus(query)}",
        "itopya", render_js=False, timeout=12
    )


def search_casper(query: str) -> list[dict]:
    """casper — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.casper.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "casper", render_js=False, timeout=12
    )


# KİTAP EK
def search_remzi(query: str) -> list[dict]:
    """Remzikitabevi ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.remzi.com/arama?q={urllib.parse.quote_plus(query)}",
        "remzi", render_js=False, timeout=12
    )

def search_tazedirekt(query: str) -> list[dict]:
    """Tazedirekt — URL doğru (?s=, statik HTML'de gerçek fiyatlar var),
    eski selector'lar sitenin güncel yapısıyla eşleşmiyordu."""
    return _scrape_jsonld_itemlist(
        f"https://www.tazedirekt.com/?s={urllib.parse.quote_plus(query)}",
        "tazedirekt", render_js=False, timeout=12
    )


def search_bizimtoptan(query: str) -> list[dict]:
    """Bizim Toptan — URL doğru (/search?q=, form action'ından doğrulandı),
    eski selector'lar sitenin güncel yapısıyla eşleşmiyordu."""
    return _scrape_jsonld_itemlist(
        f"https://www.bizimtoptan.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "bizimtoptan", render_js=False, timeout=12
    )


def search_tarimkredi(query: str) -> list[dict]:
    try:
        url = f"https://www.tarimkredi.org.tr/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .urun")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = price_el.get_text(strip=True)
            raw = re.sub(r"[^\d,.]", "", raw).replace(",", ".")
            try:
                price = float(raw.split(".")[0] + ("." + raw.split(".")[-1] if raw.count(".") == 1 else ""))
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.tarimkredi.org.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "tarimkredi", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# ScrapingBee-gated
def search_defacto(query: str) -> list[dict]:
    """
    Defacto ürün araması — DOM tabanlı (2026-07 itibarıyla doğrulandı).
    JSON-LD'de ürün listesi yok (bozuk/çoklu-obje script + sadece BreadcrumbList),
    ürün kartları .catalog-products__item olarak sunucu tarafında render ediliyor.
    URL: /arama (eski /search artık kategori sayfasına yönlendiriyor).
    """
    from app.scraping_proxy import proxy_get, proxy_enabled

    url = f"https://www.defacto.com.tr/arama?q={urllib.parse.quote_plus(query)}"
    html = None
    if proxy_enabled():
        html = proxy_get(url, render_js=False, timeout=12)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select(".catalog-products__item")[:10]:
        name_el = card.select_one(".product-card__title")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue
        discounted_el = card.select_one(".campaing-base-price")
        base_els = card.select(".base-price")
        if discounted_el:
            price = parse_price(discounted_el.get_text(strip=True))
            original_els = [e for e in base_els if e is not discounted_el]
            original = parse_price(original_els[0].get_text(strip=True)) if original_els else None
        else:
            price = parse_price(base_els[0].get_text(strip=True)) if base_els else None
            original = None
        if not price or price <= 0:
            continue
        link_el = card.select_one("a[href]")
        href = link_el.get("href", "") if link_el else ""
        prod_url = f"https://www.defacto.com.tr{href}" if href.startswith("/") else href
        img_el = card.select_one("img")
        img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
        results.append({
            "title": name, "price": price,
            "original_price": original if original and original != price else None,
            "image_url": img, "source": "defacto", "url": prod_url,
            "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
        })
    return results

def search_kutahyaporselen(query: str) -> list[dict]:
    try:
        url = f"https://www.kutahyaporselen.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.kutahyaporselen.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "kutahyaporselen", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_beymen(query: str) -> list[dict]:
    """beymen — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.beymen.com/tr/search?q={urllib.parse.quote_plus(query)}",
        "beymen", render_js=False, timeout=12
    )


def search_vakko(query: str) -> list[dict]:
    """Vakko — statik HTML'de yeterli ürün verisi bulunamadı (küçük
    yanıt, JS-SPA), ScrapingBee render_js=True ile dener."""
    try:
        return _scrape_jsonld_itemlist(
            f"https://www.vakko.com/search?q={urllib.parse.quote_plus(query)}",
            "vakko", render_js=True, timeout=15
        )
    except Exception:
        return []


def search_network(query: str) -> list[dict]:
    try:
        url = f"https://www.network.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.network.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "network", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_philips(query: str) -> list[dict]:
    """Philips TR — statik HTML'deki TL eşleşmeleri gerçek ürün değil
    (gömülü meta config), kurumsal site istemci tarafında render ediliyor.
    render_js=True gerekiyor."""
    try:
        return _scrape_jsonld_itemlist(
            f"https://www.philips.com.tr/?s={urllib.parse.quote_plus(query)}",
            "philips", render_js=True, timeout=15
        )
    except Exception:
        return []


def search_farmasi(query: str) -> list[dict]:
    """Farmasi — Next.js sayfası ama arama sonuçları sunucu tarafında
    render edilmiyor (pageProps boş, client-side fetch ile geliyor).
    ScrapingBee render_js=True ile JS çalıştırılmış hali üzerinden dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.farmasi.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "farmasi", render_js=True, timeout=15
    )


def search_dsmart(query: str) -> list[dict]:
    """dsmart — statik HTML'de yeterli ürün verisi bulunamadı (küçük sayfa,
    muhtemelen JS-SPA), ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.dsmart.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "dsmart", render_js=True, timeout=15
    )


def search_miniso(query: str) -> list[dict]:
    try:
        url = f"https://www.miniso.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.miniso.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "miniso", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_action(query: str) -> list[dict]:
    try:
        url = f"https://www.action.com/tr-tr/arama/?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], .product-item, [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='product-title'], [class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.action.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "action", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_turkcell(query: str) -> list[dict]:
    """turkcell — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.turkcell.com.tr/cihazlar?q={urllib.parse.quote_plus(query)}",
        "turkcell", render_js=False, timeout=12
    )


def search_hopi(query: str) -> list[dict]:
    try:
        url = f"https://www.hopi.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.hopi.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "hopi", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_pandora(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://tr.pandora.net/search?q={urllib.parse.quote_plus(query)}",
        "pandora", render_js=True, timeout=15
    )

def search_altinyildiz(query: str) -> list[dict]:
    """Altınyıldız Classics — URL doğru, eski selector'lar sitenin güncel
    yapısıyla eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    try:
        return _scrape_jsonld_itemlist(
            f"https://www.altinyildizclassics.com/search?q={urllib.parse.quote_plus(query)}",
            "altinyildiz", render_js=False, timeout=12
        )
    except Exception:
        return []


def search_derimod(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.derimod.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "derimod", render_js=True, timeout=15
    )

def search_lescon(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.lescon.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "lescon", render_js=True, timeout=15
    )

def search_namet(query: str) -> list[dict]:
    try:
        url = f"https://www.namet.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .product")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.namet.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "namet", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_dardanel(query: str) -> list[dict]:
    try:
        url = f"https://www.dardanel.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .product")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.dardanel.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "dardanel", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_shein(query: str) -> list[dict]:
    try:
        url = f"https://tr.shein.com/pdsearch/{urllib.parse.quote_plus(query)}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], [class*='goods-item']")[:10]:
            name_el = item.select_one("[class*='product-title'], [class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://tr.shein.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "shein", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_aliexpress(query: str) -> list[dict]:
    """aliexpress — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://tr.aliexpress.com/wholesale?SearchText={urllib.parse.quote_plus(query)}",
        "aliexpress", render_js=True, timeout=15
    )


def search_hm(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www2.hm.com/tr_tr/search-results.html?q={urllib.parse.quote_plus(query)}",
        "hm", render_js=True, timeout=15
    )

def search_sephora(query: str) -> list[dict]:
    """Sephora TR — eski /search?q= adresi 404 veriyordu; gerçek arama rotası
    /catalogsearch/result/ (Magento benzeri) ama doğrudan istekte 403 (bot
    koruması) alıyor, ScrapingBee proxy + render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.sephora.com.tr/catalogsearch/result/?q={urllib.parse.quote_plus(query)}",
        "sephora", render_js=True, timeout=15
    )

def search_koctas(query: str) -> list[dict]:
    """Koçtaş — doğrudan istekte 403 (bot koruması) alıyor; eski kod ayrıca
    proxy_get()'in döndürdüğü string'i yanlışlıkla requests.Response gibi
    (r.ok/r.text) kullanıyordu, bu her zaman istisna fırlatıp sessizce boş
    dönüyordu. _scrape_jsonld_itemlist proxy_get'i doğru kullanıyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.koctas.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "koctas", render_js=True, timeout=15
    )


def search_adidas(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.adidas.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "adidas", render_js=True, timeout=15
    )

def search_metro(query: str) -> list[dict]:
    try:
        from app.scraping_proxy import proxy_get
        url = f"https://www.metro.com.tr/arama?q={urllib.parse.quote_plus(query)}"
        html = proxy_get(url, render_js=False, timeout=15)

        if not html:

            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price']")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.metro.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "metro", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def run_async(coro):
    import asyncio
    import threading
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        result = [None]
        err = [None]
        def runner():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result[0] = new_loop.run_until_complete(coro)
            except Exception as e:
                err[0] = e
            finally:
                new_loop.close()
        t = threading.Thread(target=runner)
        t.start()
        t.join()
        if err[0]:
            raise err[0]
        return result[0]
    else:
        return loop.run_until_complete(coro)

def _call_railway_scraper(query: str, category: str) -> list[dict] | None:
    """Railway scraper API'sini çağır — env var set edilmişse kullan."""
    import requests as _req, os as _os
    url = _os.getenv("RAILWAY_SCRAPER_URL", "").rstrip("/")
    secret = _os.getenv("SCRAPER_SECRET", "")
    if not url:
        return None
    try:
        r = _req.get(
            f"{url}/scrape",
            params={"query": query, "category": category, "secret": secret},
            timeout=55,
        )
        if r.ok:
            data = r.json()
            return data.get("products") or []
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Railway scraper hata: %s", e)
    return None


def search_products_by_name(
    query: str,
    category: str = "general",
    lat: float = None,
    lon: float = None,
    mode: str = "hybrid"
) -> list[dict]:
    # Railway scraper varsa onu kullan (tüm mağazalar, sınırsız süre)
    railway_products = _call_railway_scraper(query, category)
    if railway_products is not None:
        all_products = railway_products
    else:
        # 1. Lokal orkestratör (sadece N11+Amazon)
        from app.search_orchestrator import master_search
        all_products = run_async(master_search(query, selected_category=category, lat=lat, lon=lon, mode=mode))
    try:
        from app.query_intelligence import correct_query
        corrected_query = correct_query(query)
    except Exception:
        corrected_query = query

    # Cache'ten (Supabase) gelen kayitlar eski sema olabilir -- eksik alanlari
    # tamamla, aksi halde asagidaki post-processing KeyError ile 500 doner.
    # Bazi scraper'lar dict olmayan ogeler de sizdirabiliyor (orn. N11'in
    # tuple donusu) -- once bunlari ele.
    all_products = [p for p in all_products if isinstance(p, dict)]

    # Güven filtresi: JSON-LD/yapılandırılmış veri olmayan sayfalarda son
    # çare olarak devreye giren sezgisel fiyat tarayıcı (verified=False)
    # yanlış eşleşme riski taşıyor (bkz. Rossmann "100TL üzeri kargo"
    # olayı). Kullanıcıya kesin sonuç vaadi verdiğimiz için bu sonuçlar
    # şimdilik gösterilmiyor; mağaza özelinde doğrulanınca kaldırılabilir.
    all_products = [p for p in all_products if p.get("verified", True)]

    for p in all_products:
        if not isinstance(p.get("extra_info"), dict):
            p["extra_info"] = {}
        if not isinstance(p.get("labels"), list):
            p["labels"] = []
        p.setdefault("original_price", None)
        if not isinstance(p.get("price"), (int, float)):
            p["price"] = 0
        p.setdefault("title", "")
        p.setdefault("url", "")

    # 5. Filter out accessory/irrelevant products (like cloth, case, cables)
    filtered_products = [p for p in all_products if is_logical_product(corrected_query, p["title"])]
    
    # 6. Apply brand filter if specified in the query
    brand = detect_brand_in_query(corrected_query)
    if brand:
        brand_lower = brand.lower().replace("-", "")
        brand_filtered = []
        for p in filtered_products:
            title_clean = p["title"].lower().replace("-", "")
            if brand_lower in title_clean:
                brand_filtered.append(p)
    # Sorgu kelimelerinden hicbirini icermeyen tek tek urunleri ele --
    # eskiden bu kontrol tum listeye "en az bir eslesme var mi" seklinde
    # bakiyordu, listede bir-iki alakasiz urun (orn. "makarna" aramasinda
    # bir maskara) diger gercek eslesmeler yuzunden gozden kaciyordu.
    query_words = [w.strip() for w in corrected_query.lower().split() if len(w.strip()) > 2]
    if query_words:
        matching = [p for p in filtered_products if any(w in p["title"].lower() for w in query_words)]
        # Hicbiri eslesmiyorsa (bogus sorgu) tum listeyi degil, orijinali koru
        # -- eslesen varsa sadece eslesmeyenleri disarida birak.
        if matching:
            filtered_products = matching
        else:
            filtered_products = []

    # Title bazlı deduplicate: aynı ürün farklı satıcıdan geliyorsa en ucuzunu tut
    def _title_key(title: str) -> str:
        import re
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', title.lower().strip()))[:60]

    seen_titles: dict[str, dict] = {}
    for p in filtered_products:
        tk = _title_key(p.get("title", ""))
        if tk not in seen_titles or p["price"] < seen_titles[tk]["price"]:
            seen_titles[tk] = p
    filtered_products = list(seen_titles.values())

    # Separate into in-stock and out-of-stock
    in_stock = [p for p in filtered_products if not p["extra_info"].get("out_of_stock")]
    out_of_stock = [p for p in filtered_products if p["extra_info"].get("out_of_stock")]
            
    # 7. Generic vs Specific Query details limit
    has_details = brand is not None or any(x in corrected_query.lower() for x in [" l", "gr", "kg", "gb", "tb", "ml"])
    limit = 5 if has_details else 20

    # 8. Sort in-stock by price (cheapest first) if generic query
    if not brand:
        in_stock.sort(key=lambda x: x["price"])

        # Magaza cesitliligi: tek bir magazanin ucuz varyantlari (ayni urunun
        # farkli renk/beden secenekleri gibi) tum listeyi doldurup diger
        # magazalari (Gratis, Watsons, Boyner...) ekrandan tamamen disarida
        # birakmasin. Magaza basina en fazla 2 urun alacak sekilde en
        # ucuzdan baslayip round-robin dagitiyoruz -- boylece hem ucuzluk
        # onceligi korunuyor hem de kullaniciya birden fazla magaza gosteriliyor.
        max_per_source = 2
        by_source: dict[str, list[dict]] = {}
        for p in in_stock:
            by_source.setdefault(p.get("source", ""), []).append(p)

        diversified: list[dict] = []
        while len(diversified) < limit and any(by_source.values()):
            progressed = False
            for items in by_source.values():
                if len(diversified) >= limit:
                    break
                taken = sum(1 for d in diversified if d.get("source") == items[0].get("source")) if items else 0
                if items and taken < max_per_source:
                    diversified.append(items.pop(0))
                    progressed = True
            if not progressed:
                break
        diversified.sort(key=lambda x: x["price"])
        in_stock = diversified

    output_in_stock = in_stock[:limit]
    output_out_of_stock = out_of_stock[:2] if limit == 15 else out_of_stock[:1]
    
    output = (output_in_stock + output_out_of_stock)[:limit]
    
    # 9. Suspicious Price Warning Check (extreme low price drop alert)
    # Not: karisik sonuc listesinde (farkli varyant/boyut/gramaj) dogal fiyat
    # farki normaldir -- 0.6 esigi "En Ucuz" etiketli gercek urunleri bile
    # sahte indirim sanip yanlis damgaliyordu. Sadece gercekten anormal
    # (medyanin 1/4'unden az) ve yeterince genis bir ornek (>=5) varsa uyar.
    valid_prices = [p["price"] for p in output_in_stock if p["price"] > 0]
    if len(valid_prices) >= 5:
        sorted_prices = sorted(valid_prices)
        n = len(sorted_prices)
        median_price = sorted_prices[n // 2] if n % 2 != 0 else (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2.0

        for p in output:
            if not p["extra_info"].get("out_of_stock") and p["price"] > 0:
                if p["price"] < 0.25 * median_price:
                    p["extra_info"]["suspicious"] = True
                    p["extra_info"]["suspicious_warning"] = "Güvenlik Uyarısı: Bu fiyat piyasa ortalamasının şüpheli derecede altındadır. Güvenliğiniz için dikkatli olmanızı öneririz."
                    if "Şüpheli Fiyat" not in p["labels"]:
                        p["labels"].append("Şüpheli Fiyat")
                        
    # 10. Enrich labels (En Ucuz, En Yüksek İndirim)
    if output_in_stock:
        non_suspicious_in_stock = [p for p in output_in_stock if not p["extra_info"].get("suspicious")]
        cheapest_pool = non_suspicious_in_stock if non_suspicious_in_stock else output_in_stock
        cheapest = min(cheapest_pool, key=lambda x: x["price"])
        for r in output:
            if r["url"] == cheapest["url"] and not r["extra_info"].get("out_of_stock"):
                if "En Ucuz" not in r["labels"]:
                    r["labels"].append("En Ucuz")
                if "Önerilen" in r["labels"]:
                    r["labels"].remove("Önerilen")
                
        def get_discount_pct(r):
            if r["original_price"] and r["original_price"] > r["price"]:
                return (r["original_price"] - r["price"]) / r["original_price"]
            return 0
            
        most_discounted = max(output_in_stock, key=get_discount_pct)
        if get_discount_pct(most_discounted) > 0.05:
            for r in output:
                if r["url"] == most_discounted["url"] and not r["extra_info"].get("out_of_stock"):
                    if "En Yüksek İndirim" not in r["labels"]:
                        r["labels"].append("En Yüksek İndirim")
                    if "Önerilen" in r["labels"] and len(r["labels"]) > 1:
                        r["labels"].remove("Önerilen")
                        
    # Calculate unit prices and assign best unit price label if applicable
    for p in output:
        if not p["extra_info"].get("out_of_stock") and p["price"] > 0:
            volume_info = extract_volume_info(p["title"])
            if volume_info:
                val, unit = volume_info
                unit_price = p["price"] / val
                p["extra_info"]["unit_price"] = round(unit_price, 2)
                p["extra_info"]["unit"] = unit
                p["extra_info"]["volume_val"] = val

    # Label the best unit price product and identify price risks
    for unit_type in ("L", "kg", "GB", "servis", "adet"):
        same_unit_products = [
            p for p in output 
            if not p["extra_info"].get("out_of_stock") 
            and p["price"] > 0 
            and p["extra_info"].get("unit") == unit_type
        ]
        if len(same_unit_products) >= 2:
            best_p = min(same_unit_products, key=lambda x: x["extra_info"]["unit_price"])
            best_p["extra_info"]["best_unit_price"] = True
            if "Birim Fiyat Avantajı" not in best_p["labels"]:
                best_p["labels"].append("Birim Fiyat Avantajı")
                if "Önerilen" in best_p["labels"] and len(best_p["labels"]) > 1:
                    best_p["labels"].remove("Önerilen")
            
            best_unit_price = best_p["extra_info"]["unit_price"]
            for p in same_unit_products:
                if p["extra_info"]["unit_price"] / best_unit_price >= 1.5:
                    if "Birim Fiyat Riski" not in p["labels"]:
                        p["labels"].append("Birim Fiyat Riski")
                        if "Önerilen" in p["labels"] and len(p["labels"]) > 1:
                            p["labels"].remove("Önerilen")

    # Gerçek sonuç yoksa boş dön — frontend "Arama Sonucu Bulunamadı" gösterir

    # Fallback items are created after the first analysis pass. Enrich the
    # final output so every supported comparison type behaves consistently.
    for p in output:
        if not p["extra_info"].get("out_of_stock") and p["price"] > 0:
            volume_info = extract_volume_info(p["title"])
            if volume_info:
                val, unit = volume_info
                p["extra_info"]["unit_price"] = round(p["price"] / val, 2)
                p["extra_info"]["unit"] = unit
                p["extra_info"]["volume_val"] = val

    for unit_type in ("L", "kg", "GB", "servis", "adet"):
        comparable = [
            p for p in output
            if p["extra_info"].get("unit") == unit_type
            and not p["extra_info"].get("out_of_stock")
            and p["price"] > 0
        ]
        if len(comparable) >= 2:
            best = min(comparable, key=lambda x: x["extra_info"]["unit_price"])
            best["extra_info"]["best_unit_price"] = True
            if "Birim Fiyat Avantajı" not in best["labels"]:
                best["labels"].append("Birim Fiyat Avantajı")
                if "Önerilen" in best["labels"] and len(best["labels"]) > 1:
                    best["labels"].remove("Önerilen")
            
            best_unit_price = best["extra_info"]["unit_price"]
            for p in comparable:
                if p["extra_info"]["unit_price"] / best_unit_price >= 1.5:
                    if "Birim Fiyat Riski" not in p["labels"]:
                        p["labels"].append("Birim Fiyat Riski")
                        if "Önerilen" in p["labels"] and len(p["labels"]) > 1:
                            p["labels"].remove("Önerilen")

    return output

def generate_search_suggestion(query: str) -> str | None:
    query_lower = query.lower().strip()
    if not query_lower:
        return None
        
    synonyms = {
        "sut": "süt",
        "sampuan": "şampuan",
        "yogurt": "yoğurt",
        "pirinc": "pirinç",
        "seker": "şeker",
        "cay": "çay",
        "ipone": "iphone",
        "iphne": "iphone",
        "ipon": "iphone",
        "ayfon": "iphone",
        "samung": "samsung",
        "samsun": "samsung",
        "karacaa": "karaca",
        "karca": "karaca",
        "vestel": "televizyon",
        "arcelik": "çamaşır makinesi",
        "arçelik": "çamaşır makinesi",
        "proteinocean": "protein tozu",
        "supplementler": "protein tozu",
        "aple": "apple",
        "adidas": "ayakkabı",
        "nike": "ayakkabı",
        "macbok": "macbook",
        "asuz": "asus",
        "lenova": "lenovo",
        "xioami": "xiaomi",
        "huavei": "huawei",
        "gübeş": "güneş",
        "gözlügü": "gözlüğü",
        "ayakkabi": "ayakkabı",
        "kullaklık": "kulaklık"
    }
    
    for k, v in synonyms.items():
        if k in query_lower:
            return query_lower.replace(k, v)
            
    match = re.search(r"(\b[a-zA-Z\s]+)\s+(\d+)\b", query)
    if match:
        name = match.group(1).strip()
        num = int(match.group(2))
        
        if name.lower() == "iphone" and num > 16:
            return f"{name} 16"
        elif name.lower() == "iphone" and num > 15:
            return f"{name} 15"
        elif num > 1:
            return f"{name} {num - 1}"
            
    words = query.split()
    if len(words) > 1:
        return " ".join(words[:-1])
        
    return None


def extract_volume_info(title: str) -> tuple[float, str] | None:
    if not title:
        return None
    title_lower = title.lower()
    
    # 1. Litre/ML eşlemeleri
    match_l = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:l|lt|litre)\b", title_lower)
    if match_l:
        try:
            val = float(match_l.group(1).replace(",", "."))
            if val > 0:
                return val, "L"
        except ValueError:
            pass
            
    match_ml = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:ml|mililitre)\b", title_lower)
    if match_ml:
        try:
            val = float(match_ml.group(1).replace(",", "."))
            if val > 0:
                return val / 1000.0, "L"
        except ValueError:
            pass

    # 2. Kilogram/Gram eşlemeleri
    match_kg = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:kg|kgr|kilogram|kilo)\b", title_lower)
    if match_kg:
        try:
            val = float(match_kg.group(1).replace(",", "."))
            if val > 0:
                return val, "kg"
        except ValueError:
            pass

    match_g = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:g|gr|gram)\b", title_lower)
    if match_g:
        try:
            val = float(match_g.group(1).replace(",", "."))
            if val > 0:
                return val / 1000.0, "kg"
        except ValueError:
            pass

    # 3. GB/TB eşlemeleri (Elektronik Kapasite)
    match_tb = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:tb|terabayt)\b", title_lower)
    if match_tb:
        try:
            val = float(match_tb.group(1).replace(",", "."))
            if val > 0:
                return val * 1000.0, "GB"
        except ValueError:
            pass

    match_gb = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:gb|gigabayt)\b", title_lower)
    if match_gb:
        try:
            val = float(match_gb.group(1).replace(",", "."))
            if val > 0:
                return val, "GB"
        except ValueError:
            pass

    # 4. Servis/Porsiyon eşlemeleri (Sporcu Gıdaları)
    match_serv = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:servis|porsiyon)\b", title_lower)
    if match_serv:
        try:
            val = float(match_serv.group(1).replace(",", "."))
            if val > 0:
                return val, "servis"
        except ValueError:
            pass

    # 5. Adet/Çoklu Paket eşlemeleri (Giyim/Moda, Kozmetik)
    match_pack = re.search(r"(\d+)\s*(?:'li|'lü|lu|lü|li)\s*(?:paket|set|adet|ürün)\b", title_lower)
    if match_pack:
        try:
            val = float(match_pack.group(1))
            if val > 0:
                return val, "adet"
        except ValueError:
            pass

    return None


BARCODE_DATABASE = {
    "8690506390074": {
        "title": "Yudum Ayçiçek Yağı 5 L",
        "search_query": "Yudum ayçiçek yağı 5 L"
    },
    "8690506390081": {
        "title": "Yudum Ayçiçek Yağı 2 L",
        "search_query": "Yudum ayçiçek yağı 2 L"
    },
    "8690632034071": {
        "title": "Hardline Whey 3 Matrix 2300 Gr",
        "search_query": "Hardline Whey 3 Matrix 2300 Gr"
    },
    "8690632034088": {
        "title": "Hardline Whey 3 Matrix 908 Gr",
        "search_query": "Hardline Whey 3 Matrix 908 Gr"
    },
    "8690506000010": {
        "title": "Migros Süt 1 L",
        "search_query": "Migros süt 1 L"
    },
    "8690605061033": {
        "title": "İpana 3D White Diş Macunu 75 ml",
        "search_query": "İpana 3D White Diş Macunu 75 ml"
    },
    "8696001002003": {
        "title": "Samsung T7 Portable SSD 1 TB",
        "search_query": "Samsung T7 Portable SSD 1 TB"
    },
    "8697001003004": {
        "title": "Defacto Erkek Çorap 3'lü Paket",
        "search_query": "Defacto Erkek Çorap 3'lü Paket"
    }
}


def search_gamegaraj(query: str) -> list[dict]:
    try:
        url = f"https://www.gamegaraj.com/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.gamegaraj.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "gamegaraj", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_ofissepeti(query: str) -> list[dict]:
    try:
        url = f"https://www.ofissepeti.com/ara?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.ofissepeti.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "ofissepeti", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_muzikdunyasi(query: str) -> list[dict]:
    try:
        url = f"https://www.muzikdunyasi.com/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .product")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.muzikdunyasi.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "muzikdunyasi", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_reebok(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.reebok.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "reebok", render_js=False, timeout=12
    )

def search_bershka(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.bershka.com/tr/search?q={urllib.parse.quote_plus(query)}",
        "bershka", render_js=True, timeout=15
    )

def search_ulker(query: str) -> list[dict]:
    try:
        url = f"https://www.ulker.com.tr/tr/arama?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el:
                continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.ulker.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "ulker", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_lego(query: str) -> list[dict]:
    """LEGO TR — URL doğru (lego.tr'ye yönleniyor, statik HTML'de gerçek
    fiyatlar var) ama eski selector'lar sitenin güncel yapısıyla eşleşmiyordu.
    Paylaşılan sezgisel fiyat-kart tarayıcısına geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.lego.com/tr-tr/search?q={urllib.parse.quote_plus(query)}",
        "lego", render_js=False, timeout=12
    )


def search_epson(query: str) -> list[dict]:
    """epson — statik HTML'de yeterli ürün verisi bulunamadı, ScrapingBee
    render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.epson.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "epson", render_js=True, timeout=15
    )


def search_sarar(query: str) -> list[dict]:
    """Sarar — URL doğru, eski selector'lar sitenin güncel yapısıyla
    eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.sarar.com/arama?q={urllib.parse.quote_plus(query)}",
        "sarar", render_js=False, timeout=12
    )


def search_damattween(query: str) -> list[dict]:
    """DamatTween — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://www.damattween.com/search?q={urllib.parse.quote_plus(query)}",
        "damattween", render_js=True, timeout=15
    )


def search_yargici(query: str) -> list[dict]:
    """Yargıcı ürün araması — JSON-LD ItemList."""
    try:
        url = f"https://www.yargici.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data.get("itemListElement", [])
                if not items:
                    continue
                for item in items[:10]:
                    prod = item.get("item", item)
                    name = prod.get("name", "")
                    if not name:
                        continue
                    offers = prod.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    try:
                        price = float(str(offers.get("price", 0)).replace(",", "."))
                    except Exception:
                        continue
                    if price <= 0:
                        continue
                    prod_url = prod.get("url", "")
                    image = prod.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""
                    results.append({
                        "title": name, "price": price, "original_price": None,
                        "image_url": image, "source": "yargici", "url": prod_url,
                        "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                    })
                if results:
                    break
            except Exception:
                continue
        return results
    except Exception:
        return []


def search_sony(query: str) -> list[dict]:
    """Sony TR — doğrudan istekte 403 (bot koruması) alıyor, ScrapingBee
    render_js=True ile dener; paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.sony.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "sony", render_js=True, timeout=15
    )


def search_lg(query: str) -> list[dict]:
    """LG TR — URL doğru, statik HTML'de gerçek fiyat var, eski selector'lar
    eşleşmiyordu — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.lg.com/tr/search/?search={urllib.parse.quote_plus(query)}",
        "lg", render_js=False, timeout=12
    )


def search_canon(query: str) -> list[dict]:
    """Canon TR — doğrudan istekte 403 (bot koruması) alıyor, ScrapingBee
    render_js=True ile dener; paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.canon.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "canon", render_js=True, timeout=15
    )


def search_oyundeposu(query: str) -> list[dict]:
    try:
        url = f"https://www.oyundeposu.com.tr/?s={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product, .product-item, [class*='product-card']")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name: continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el: continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try: price = float(raw)
            except: continue
            if price <= 0: continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.oyundeposu.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "oyundeposu", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_frigg(query: str) -> list[dict]:
    """Frigg — WordPress/WooCommerce arama URL'si doğru, eski selector'lar
    eşleşmiyordu. Paylaşılan sezgisel fiyat-kart tarayıcısına geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.frigg.com.tr/?s={urllib.parse.quote_plus(query)}",
        "frigg", render_js=False, timeout=12
    )


def search_asusrog(query: str) -> list[dict]:
    """ASUS ROG — statik HTML'de yeterli ürün verisi bulunamadı,
    ScrapingBee render_js=True ile dener."""
    return _scrape_jsonld_itemlist(
        f"https://rog.asus.com/tr/search/?q={urllib.parse.quote_plus(query)}",
        "asusrog", render_js=True, timeout=15
    )


def search_melodika(query: str) -> list[dict]:
    try:
        url = f"https://www.melodika.net/?s={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product, .product-item, [class*='product-card']")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name: continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el: continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try: price = float(raw)
            except: continue
            if price <= 0: continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.melodika.net{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "melodika", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_ufukkirtasiye(query: str) -> list[dict]:
    """ufukkirtasiye — paylaşılan sezgisel tarayıcıya geçirildi."""
    return _scrape_jsonld_itemlist(
        f"https://www.ufukkirtasiye.com/search?q={urllib.parse.quote_plus(query)}",
        "ufukkirtasiye", render_js=True, timeout=15
    )


def search_evpet(query: str) -> list[dict]:
    try:
        url = f"https://www.evpet.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name: continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el: continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try: price = float(raw)
            except: continue
            if price <= 0: continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.evpet.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "evpet", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_zopet(query: str) -> list[dict]:
    try:
        url = f"https://www.zopet.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name: continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el: continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try: price = float(raw)
            except: continue
            if price <= 0: continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.zopet.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "zopet", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_petbis(query: str) -> list[dict]:
    try:
        url = f"https://www.petbis.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard']")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name: continue
            price_el = item.select_one("[class*='price'], .price")
            if not price_el: continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try: price = float(raw)
            except: continue
            if price <= 0: continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.petbis.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "petbis", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_kinetix(query: str) -> list[dict]:
    """Kinetix ürün araması — JSON-LD ItemList (ikinci script)."""
    try:
        url = f"https://www.kinetix.com.tr/search?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if data.get("@type") != "ItemList":
                    continue
                items = data.get("itemListElement", [])
                for item in items[:10]:
                    prod = item.get("item", item)
                    name = prod.get("name", "")
                    if not name:
                        continue
                    offers = prod.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    try:
                        price = float(str(offers.get("price", 0)).replace(",", "."))
                    except Exception:
                        continue
                    if price <= 0:
                        continue
                    prod_url = prod.get("url", "")
                    image = prod.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""
                    results.append({
                        "title": name, "price": price, "original_price": None,
                        "image_url": image, "source": "kinetix", "url": prod_url,
                        "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                    })
                if results:
                    break
            except Exception:
                continue
        return results
    except Exception:
        return []


# ── 2026-07-13: "yakında" listesinden aktif edilmeye aday yeni scraper'lar ──
# Hepsi paylasilan _scrape_jsonld_itemlist uzerinden calisiyor (render_js=True
# -- domain kontrolu curl ile yapildi ama cogu site JS-SPA oldugu icin
# gercek fiyat verisi ancak ScrapingBee render sonrasi test edilebilir).
# Canliya cikinca gunluk scraper_healthcheck.py otomatik dogruluyor --
# "HAZIR" rozeti cikana kadar admin panelden takip edilmeli.

def search_koton(query: str) -> list[dict]:
    """Koton — React SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.koton.com/arama?q={urllib.parse.quote_plus(query)}",
        "koton", render_js=True, timeout=15
    )

def search_kigili(query: str) -> list[dict]:
    """Kiğılı — SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.kigili.com/arama?q={urllib.parse.quote_plus(query)}",
        "kigili", render_js=True, timeout=15
    )

def search_mac(query: str) -> list[dict]:
    """MAC Cosmetics — SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.maccosmetics.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "mac", render_js=True, timeout=15
    )

def search_instreet(query: str) -> list[dict]:
    """In Street — SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.instreet.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "instreet", render_js=True, timeout=15
    )

def search_pullandbear(query: str) -> list[dict]:
    """Pull&Bear — Inditex grubu SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.pullandbear.com/tr/search?q={urllib.parse.quote_plus(query)}",
        "pullandbear", render_js=True, timeout=15
    )

def search_stradivarius(query: str) -> list[dict]:
    """Stradivarius — Inditex grubu SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.stradivarius.com/tr/search?q={urllib.parse.quote_plus(query)}",
        "stradivarius", render_js=True, timeout=15
    )

def search_massimodutti(query: str) -> list[dict]:
    """Massimo Dutti — Inditex grubu SPA, render_js=True gerekiyor."""
    return _scrape_jsonld_itemlist(
        f"https://www.massimodutti.com/tr/search?q={urllib.parse.quote_plus(query)}",
        "massimodutti", render_js=True, timeout=15
    )

def search_hatemoglu(query: str) -> list[dict]:
    """Hatemoğlu — domain hatemoglu.com (hatemoglu.com.tr yönleniyor)."""
    return _scrape_jsonld_itemlist(
        f"https://www.hatemoglu.com/arama?q={urllib.parse.quote_plus(query)}",
        "hatemoglu", render_js=True, timeout=15
    )

def search_machka(query: str) -> list[dict]:
    """Machka — statik HTML'de JSON-LD dogrulandi (curl ile 200 + ld+json)."""
    return _scrape_jsonld_itemlist(
        f"https://www.machka.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "machka", render_js=False, timeout=12
    )

def search_suvari(query: str) -> list[dict]:
    """Süvari — render_js=True gerekiyor (ilk denemede yönlendirme cikti)."""
    return _scrape_jsonld_itemlist(
        f"https://www.suvari.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "suvari", render_js=True, timeout=15
    )

def search_tudors(query: str) -> list[dict]:
    """Tudors — domain tudors.com (tudors.com.tr calismiyordu)."""
    return _scrape_jsonld_itemlist(
        f"https://www.tudors.com/arama?q={urllib.parse.quote_plus(query)}",
        "tudors", render_js=True, timeout=15
    )

def search_ipekyol(query: str) -> list[dict]:
    """İpekyol — JSON-LD ItemList var ama fiyatsiz (sadece ad/url), sezgisel
    tarayiciya dusecek -- verified=False olarak isaretlenip filtrelenecek,
    guvenilir hale gelmesi icin ozel DOM parser gerekebilir."""
    return _scrape_jsonld_itemlist(
        f"https://www.ipekyol.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "ipekyol", render_js=True, timeout=15
    )

def search_deichmann(query: str) -> list[dict]:
    """Deichmann Türkiye — dogru yol /tr-tr altinda."""
    return _scrape_jsonld_itemlist(
        f"https://www.deichmann.com/tr-tr/search?q={urllib.parse.quote_plus(query)}",
        "deichmann", render_js=True, timeout=15
    )

def search_troy(query: str) -> list[dict]:
    """Troy (ayakkabi) — domain troy.com.tr."""
    return _scrape_jsonld_itemlist(
        f"https://www.troy.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "troy", render_js=True, timeout=15
    )

def search_bernardo(query: str) -> list[dict]:
    """Bernardo — ayakkabi/deri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.bernardo.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "bernardo", render_js=True, timeout=15
    )

def search_linens(query: str) -> list[dict]:
    """Linens — ev tekstili, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.linens.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "linens", render_js=True, timeout=15
    )

def search_pasabahce(query: str) -> list[dict]:
    """Paşabahçe — cam/kristal ev urunleri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.pasabahce.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "pasabahce", render_js=True, timeout=15
    )

def search_porland(query: str) -> list[dict]:
    """Porland — porselen/servis takimlari, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.porland.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "porland", render_js=True, timeout=15
    )

def search_tekzen(query: str) -> list[dict]:
    """Tekzen — yapi/bahce market, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.tekzen.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "tekzen", render_js=True, timeout=15
    )

def search_hakmar(query: str) -> list[dict]:
    """Hakmar — market zinciri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.hakmar.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "hakmar", render_js=True, timeout=15
    )

def search_happycenter(query: str) -> list[dict]:
    """Happy Center — market zinciri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.happycenter.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "happycenter", render_js=True, timeout=15
    )

def search_jumbo(query: str) -> list[dict]:
    """Jumbo — market zinciri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.jumbo.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "jumbo", render_js=True, timeout=15
    )

def search_mopas(query: str) -> list[dict]:
    """Mopaş — market zinciri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.mopas.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "mopas", render_js=True, timeout=15
    )

def search_onurmarket(query: str) -> list[dict]:
    """Onur Market — market zinciri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.onurmarket.com/arama?q={urllib.parse.quote_plus(query)}",
        "onurmarket", render_js=True, timeout=15
    )

def search_yvesrocher(query: str) -> list[dict]:
    """Yves Rocher — dogrudan istekte bot korumasi (403), render_js=True sart."""
    return _scrape_jsonld_itemlist(
        f"https://www.yvesrocher.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "yvesrocher", render_js=True, timeout=15
    )

def search_eveshop(query: str) -> list[dict]:
    """Eve Shop — kozmetik, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.eveshop.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "eveshop", render_js=True, timeout=15
    )

def search_atasunoptik(query: str) -> list[dict]:
    """Atasun Optik — render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.atasunoptik.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "atasunoptik", render_js=True, timeout=15
    )

def search_mertoptik(query: str) -> list[dict]:
    """Mert Optik — domain mertoptik.com, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.mertoptik.com/arama?q={urllib.parse.quote_plus(query)}",
        "mertoptik", render_js=True, timeout=15
    )

def search_babymall(query: str) -> list[dict]:
    """BabyMall — anne/bebek urunleri, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.babymall.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "babymall", render_js=True, timeout=15
    )

def search_gnc(query: str) -> list[dict]:
    """GNC Türkiye — takviye/vitamin, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.gnc.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "gnc", render_js=True, timeout=15
    )

def search_ozdilek(query: str) -> list[dict]:
    """Özdilek — AVM/tekstil, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.ozdilek.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "ozdilek", render_js=True, timeout=15
    )

def search_superstep(query: str) -> list[dict]:
    """SuperStep — spor ayakkabi, render_js=True."""
    return _scrape_jsonld_itemlist(
        f"https://www.superstep.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "superstep", render_js=True, timeout=15
    )


def lookup_barcode(barcode: str) -> dict | None:
    barcode_clean = barcode.strip()
    return BARCODE_DATABASE.get(barcode_clean)
