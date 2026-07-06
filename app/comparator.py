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


def _scrape_jsonld_itemlist(url: str, source: str, render_js: bool = False, timeout: int = 10) -> list[dict]:
    """JSON-LD ItemList olan sayfalardan ürün çeker. ScrapingBee varsa proxy kullanır."""
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
                })
            if results:
                return results
        except Exception:
            continue
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

    irrelevant_terms = [
        "bezi", "spreyi", "solüsyonu", "temizleme",
        "kılıfı", "kutusu", "kabı", "kılıf", "kapak",
        "ipi", "askısı", "zinciri", "aparatı", "standı",
        "cam koruyucu", "ekran koruyucu", "kırılmaz cam",
        "şarj kablosu", "yedek parça", "aksesuar",
        "tornavida", "yedek cam", "vidası", "vida",
        "temizleyici", "koruyucu", "kutusu", "çantası", "çanta",
        "kordonu", "kordon", "kılıfı", "askı aparatı", "temizleme mendili"
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
        html = proxy_get(url, render_js=False, timeout=12)
    if not html:
        try:
            r = requests.get(url, headers=_STD_HEADERS, timeout=8)
            html = r.text if r.ok else None
        except Exception:
            return []
    if not html:
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
        html = proxy_get(url, render_js=False, timeout=12)
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
    """Karaca ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.karaca.com/search?q={urllib.parse.quote_plus(query)}",
        "karaca", render_js=False, timeout=12
    )

def search_watsons(query: str) -> list[dict]:
    """Watsons ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.watsons.com.tr/search?text={urllib.parse.quote_plus(query)}",
        "watsons", render_js=False, timeout=12
    )

def search_gratis(query: str) -> list[dict]:
    """Gratis ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.gratis.com/search?q={urllib.parse.quote_plus(query)}",
        "gratis", render_js=False, timeout=12
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
        "boyner", render_js=False, timeout=12
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
        "decathlon", render_js=False, timeout=12
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
    """Zara Türkiye ürün araması."""
    try:
        url = f"https://www.zara.com/tr/tr/search?searchTerm={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-grid-product, [class*='product-grid'], [class*='ProductCard'], li[class*='product']")[:10]:
            name_el = item.select_one("[class*='product-name'], .product-name, h3, [aria-label]")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price, [data-price]")
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
            prod_url = f"https://www.zara.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "zara", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    """Rossmann ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.rossmann.com.tr/ara?q={urllib.parse.quote_plus(query)}",
        "rossmann", render_js=False, timeout=12
    )

def search_supplementler(query: str) -> list[dict]:
    """Supplementler.com ürün araması."""
    try:
        url = f"https://www.supplementler.com/search/?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product'], .item")[:10]:
            name_el = item.select_one(".product-name, .item-name, h3, [class*='name']")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price, .product-price")
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
            prod_url = f"https://www.supplementler.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "supplementler", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_englishhome(query: str) -> list[dict]:
    """English Home ürün araması."""
    try:
        url = f"https://www.englishhome.com/?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, .product-card, [class*='product']")[:10]:
            name_el = item.select_one(".product-name, .product-title, h3, [class*='title']")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], .price, .product-price")
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
            prod_url = f"https://www.englishhome.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "englishhome", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.temu.com/tr/search_result.html?search_key={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='goods-item'], [class*='product-card'], .search-result-item")[:10]:
            name_el = item.select_one("[class*='goods-title'], [class*='title'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[class*='price'], [class*='Price']")
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
            prod_url = f"https://www.temu.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "temu", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_pazarama(query: str) -> list[dict]:
    try:
        url = f"https://www.pazarama.com/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
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
            prod_url = f"https://www.pazarama.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "pazarama", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.mi.com/tr/search/?keyword={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".goods-list-item, [class*='product'], .item")[:10]:
            name_el = item.select_one(".goods-name, [class*='name'], h3, p")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one(".goods-price, [class*='price']")
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
            prod_url = f"https://www.mi.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "xiaomi", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_huawei(query: str) -> list[dict]:
    try:
        url = f"https://consumer.huawei.com/tr/search/?keywords={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-item'], .search-result-item, [class*='card']")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='title'], h3")
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
            prod_url = f"https://consumer.huawei.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "huawei", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_hp(query: str) -> list[dict]:
    try:
        url = f"https://www.hp.com/tr-tr/search/results.html?query={urllib.parse.quote_plus(query)}"
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
            name_el = item.select_one("[class*='product-name'], [class*='title'], h3, h2")
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
            prod_url = f"https://www.hp.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "hp", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_lenovo(query: str) -> list[dict]:
    try:
        url = f"https://www.lenovo.com/tr/tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3, h2")
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
            prod_url = f"https://www.lenovo.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "lenovo", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.penti.com/tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
            name_el = item.select_one(".product-name, [class*='name'], h3")
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
            prod_url = f"https://www.penti.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "penti", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_colins(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.colins.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "colins", render_js=False, timeout=12
    )

def search_twist(query: str) -> list[dict]:
    try:
        url = f"https://www.twist.com.tr/?s={urllib.parse.quote_plus(query)}"
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
            name_el = item.select_one(".product-title, [class*='title'], h3")
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
            prod_url = f"https://www.twist.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "twist", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_ltb(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.ltb.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "ltb", render_js=False, timeout=12
    )

def search_modanisa(query: str) -> list[dict]:
    try:
        url = f"https://www.modanisa.com/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.modanisa.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "modanisa", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://tr.puma.com/tr/tr/search?q={urllib.parse.quote_plus(query)}",
        "puma", render_js=False, timeout=12
    )

def search_newbalance(query: str) -> list[dict]:
    try:
        url = f"https://www.newbalance.com.tr/?s={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.newbalance.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "newbalance", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_sportive(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.sportive.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "sportive", render_js=False, timeout=12
    )

def search_flormar(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.flormar.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "flormar", render_js=False, timeout=12
    )

def search_goldenrose(query: str) -> list[dict]:
    try:
        url = f"https://www.goldenrose.com.tr/?s={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.goldenrose.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "goldenrose", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.bellona.com.tr/ara?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.bellona.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bellona", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_madamecoco(query: str) -> list[dict]:
    try:
        url = f"https://www.madamecoco.com/?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.madamecoco.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "madamecoco", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_korkmaz(query: str) -> list[dict]:
    try:
        url = f"https://www.korkmaz.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product'], .item")[:10]:
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
            prod_url = f"https://www.korkmaz.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src","")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "korkmaz", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
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
    """Idefix ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.idefix.com/Search?q={urllib.parse.quote_plus(query)}",
        "idefix", render_js=False, timeout=12
    )

def search_bebek(query: str) -> list[dict]:
    try:
        url = f"https://www.bebek.com/arama?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.bebek.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bebek", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.toyzzshop.com/arama?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.toyzzshop.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "toyzz", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# EV ALETLERİ & MUTFAK
def search_tefal(query: str) -> list[dict]:
    try:
        url = f"https://www.tefal.com.tr/?s={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product, .product-item, [class*='product-card']")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3, h2")
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
            prod_url = f"https://www.tefal.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "tefal", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.arzum.com.tr/?s={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product, .product-item, [class*='product-card']")[:10]:
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
            prod_url = f"https://www.arzum.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "arzum", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_schafer(query: str) -> list[dict]:
    try:
        url = f"https://www.schafer.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product'], .item")[:10]:
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
            prod_url = f"https://www.schafer.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "schafer", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.bosch-home.com/tr/arama.html?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='title'], h3, h2")
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
            prod_url = f"https://www.bosch-home.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bosch", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
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
    try:
        url = f"https://www.kelebek.com/arama?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
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
            prod_url = f"https://www.kelebek.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "kelebek", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_dogtas(query: str) -> list[dict]:
    try:
        url = f"https://www.dogtas.com/?s={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.dogtas.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "dogtas", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# YAPI MARKET
def search_bauhaus(query: str) -> list[dict]:
    try:
        url = f"https://www.bauhaus.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card'], [class*='ProductCard'], .article")[:10]:
            name_el = item.select_one("[class*='name'], [class*='title'], h3, h2")
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
            prod_url = f"https://www.bauhaus.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bauhaus", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# PET
def search_petlebi(query: str) -> list[dict]:
    try:
        url = f"https://www.petlebi.com/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.petlebi.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "petlebi", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# SUPPLEMENT EK
def search_proteinocean(query: str) -> list[dict]:
    try:
        url = f"https://www.proteinocean.com/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.proteinocean.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "proteinocean", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_bigjoy(query: str) -> list[dict]:
    try:
        url = f"https://www.bigjoy.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
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
            prod_url = f"https://www.bigjoy.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bigjoy", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_runnutrition(query: str) -> list[dict]:
    try:
        url = f"https://www.runnutrition.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.runnutrition.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "runnutrition", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.vatanbilgisayar.com/?s={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-list-item, [class*='product-card'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='name'], [class*='title'], h3")
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
            prod_url = f"https://www.vatanbilgisayar.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "vatanbilgisayar", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_itopya(query: str) -> list[dict]:
    try:
        url = f"https://www.itopya.com/?s={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.itopya.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "itopya", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_casper(query: str) -> list[dict]:
    try:
        url = f"https://www.casper.com.tr/arama?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.casper.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "casper", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


# KİTAP EK
def search_remzi(query: str) -> list[dict]:
    """Remzikitabevi ürün araması — JSON-LD + ScrapingBee render_js."""
    return _scrape_jsonld_itemlist(
        f"https://www.remzi.com/arama?q={urllib.parse.quote_plus(query)}",
        "remzi", render_js=False, timeout=12
    )

def search_tazedirekt(query: str) -> list[dict]:
    try:
        url = f"https://www.tazedirekt.com/?s={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.tazedirekt.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "tazedirekt", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_bizimtoptan(query: str) -> list[dict]:
    try:
        url = f"https://www.bizimtoptan.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.bizimtoptan.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "bizimtoptan", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.beymen.com/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.beymen.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "beymen", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_vakko(query: str) -> list[dict]:
    try:
        url = f"https://www.vakko.com/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
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
            prod_url = f"https://www.vakko.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "vakko", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
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
    try:
        url = f"https://www.philips.com.tr/?s={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='title'], h3, h2")
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
            prod_url = f"https://www.philips.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "philips", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_farmasi(query: str) -> list[dict]:
    try:
        url = f"https://www.farmasi.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.farmasi.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "farmasi", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_dsmart(query: str) -> list[dict]:
    try:
        url = f"https://www.dsmart.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select(".product-item, [class*='product-card']")[:10]:
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
            prod_url = f"https://www.dsmart.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "dsmart", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.turkcell.com.tr/cihazlar?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='name'], [class*='title'], h3, h2")
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
            prod_url = f"https://www.turkcell.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "turkcell", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


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
        "pandora", render_js=False, timeout=12
    )

def search_altinyildiz(query: str) -> list[dict]:
    try:
        url = f"https://www.altinyildizclassics.com/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.altinyildizclassics.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "altinyildiz", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_derimod(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.derimod.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "derimod", render_js=False, timeout=12
    )

def search_lescon(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.lescon.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "lescon", render_js=False, timeout=12
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
    try:
        url = f"https://tr.aliexpress.com/wholesale?SearchText={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-item'], [class*='list-item'], [class*='card']")[:10]:
            name_el = item.select_one("[class*='title'], [class*='name'], h3")
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
            prod_url = f"https://tr.aliexpress.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({
                "title": name, "price": price, "original_price": None,
                "image_url": img, "source": "aliexpress", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
            })
        return results
    except Exception:
        return []


def search_hm(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www2.hm.com/tr_tr/search-results.html?q={urllib.parse.quote_plus(query)}",
        "hm", render_js=False, timeout=12
    )

def search_sephora(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.sephora.com.tr/search?q={urllib.parse.quote_plus(query)}",
        "sephora", render_js=False, timeout=12
    )

def search_koctas(query: str) -> list[dict]:
    try:
        from app.scraping_proxy import proxy_get
        url = f"https://www.koctas.com.tr/arama?q={urllib.parse.quote_plus(query)}"
        r = proxy_get(url, render_js=False, timeout=15)
        if not r or not r.ok:
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
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try:
                price = float(raw)
            except Exception:
                continue
            if price <= 0:
                continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.koctas.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "koctas", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_adidas(query: str) -> list[dict]:
    """ScrapingBee render_js ile JSON-LD araması."""
    return _scrape_jsonld_itemlist(
        f"https://www.adidas.com.tr/arama?q={urllib.parse.quote_plus(query)}",
        "adidas", render_js=False, timeout=12
    )

def search_metro(query: str) -> list[dict]:
    try:
        from app.scraping_proxy import proxy_get
        url = f"https://www.metro.com.tr/arama?q={urllib.parse.quote_plus(query)}"
        r = proxy_get(url, render_js=False, timeout=15)
        if not r or not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
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
    corrected_query = query

    # Cache'ten (Supabase) gelen kayitlar eski sema olabilir -- eksik alanlari
    # tamamla, aksi halde asagidaki post-processing KeyError ile 500 doner.
    # Bazi scraper'lar dict olmayan ogeler de sizdirabiliyor (orn. N11'in
    # tuple donusu) -- once bunlari ele.
    all_products = [p for p in all_products if isinstance(p, dict)]
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
    limit = 5 if has_details else 15
    
    # 8. Sort in-stock by price (cheapest first) if generic query
    if not brand:
        in_stock.sort(key=lambda x: x["price"])
        
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
        "bershka", render_js=False, timeout=12
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
    try:
        url = f"https://www.lego.com/tr-tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-item'], [class*='product-leaf'], [class*='ProductCard']")[:10]:
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
            prod_url = f"https://www.lego.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "lego", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_epson(query: str) -> list[dict]:
    try:
        url = f"https://www.epson.com.tr/search?q={urllib.parse.quote_plus(query)}"
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
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='title'], [class*='name'], h3")
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
            prod_url = f"https://www.epson.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "epson", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_sarar(query: str) -> list[dict]:
    try:
        url = f"https://www.sarar.com/arama?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.sarar.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "sarar", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_damattween(query: str) -> list[dict]:
    try:
        url = f"https://www.damattween.com/search?q={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.damattween.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "damattween", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


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
    try:
        from app.scraping_proxy import proxy_get
        url = f"https://www.sony.com.tr/search?q={urllib.parse.quote_plus(query)}"
        r = proxy_get(url, render_js=False, timeout=15)
        if not r or not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-title'], [class*='name'], [class*='title'], h3")
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
            prod_url = f"https://www.sony.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "sony", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_lg(query: str) -> list[dict]:
    try:
        from app.scraping_proxy import proxy_get
        url = f"https://www.lg.com/tr/search/?search={urllib.parse.quote_plus(query)}"
        r = proxy_get(url, render_js=False, timeout=15)
        if not r or not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], [class*='product-item']")[:10]:
            name_el = item.select_one("[class*='product-title'], [class*='title'], [class*='name'], h3")
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
            prod_url = f"https://www.lg.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "lg", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_canon(query: str) -> list[dict]:
    try:
        from app.scraping_proxy import proxy_get
        url = f"https://www.canon.com.tr/search?q={urllib.parse.quote_plus(query)}"
        r = proxy_get(url, render_js=False, timeout=15)
        if not r or not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-title'], [class*='name'], [class*='title'], h3")
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
            prod_url = f"https://www.canon.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "canon", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.frigg.com.tr/?s={urllib.parse.quote_plus(query)}"
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
            prod_url = f"https://www.frigg.com.tr{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "frigg", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


def search_asusrog(query: str) -> list[dict]:
    try:
        url = f"https://rog.asus.com/tr/search/?q={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select("[class*='product-card'], [class*='ProductCard'], .product-item")[:10]:
            name_el = item.select_one("[class*='product-name'], [class*='title'], [class*='name'], h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name: continue
            price_el = item.select_one("[class*='price']")
            if not price_el: continue
            raw = re.sub(r"[^\d,.]", "", price_el.get_text(strip=True)).replace(",", ".")
            try: price = float(raw)
            except: continue
            if price <= 0: continue
            link_el = item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://rog.asus.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "asusrog", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


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
    try:
        url = f"https://www.ufukkirtasiye.com/search?q={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".product-item, [class*='product-card'], .product")[:10]:
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
            prod_url = f"https://www.ufukkirtasiye.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
            results.append({"title": name, "price": price, "original_price": None, "image_url": img, "source": "ufukkirtasiye", "url": prod_url, "labels": ["Önerilen"], "extra_info": {"out_of_stock": False}})
        return results
    except Exception:
        return []


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


def lookup_barcode(barcode: str) -> dict | None:
    barcode_clean = barcode.strip()
    return BARCODE_DATABASE.get(barcode_clean)
