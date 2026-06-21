import urllib.parse
import re
import requests
from bs4 import BeautifulSoup
from app.parser import parse_product_url, detect_source, USER_AGENT
from app.storage import load_db, save_db

YAHOO_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"

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
    
    has_cooking_query = any(t in query_lower for t in cooking_oil_terms)
    has_motor_query = any(t in query_lower for t in motor_oil_terms)
    
    if has_cooking_query:
        if any(t in title_lower for t in motor_oil_terms) and not has_motor_query:
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
    """Trendyol arama API'sini direkt çağırır."""
    try:
        url = (
            "https://public.trendyol.com/discovery-web-searchgw-service/v2/api/infinite-scroll/sr"
            f"?q={urllib.parse.quote_plus(query)}&qt={urllib.parse.quote_plus(query)}"
            "&st=SEARCH&os=1&pi=1&culture=tr-TR&userGenderId=2&pId=0&scoringAlgorithmId=2&categoryRelevanceEnabled=False"
        )
        headers = {
            "User-Agent": YAHOO_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "tr-TR,tr;q=0.9",
            "Origin": "https://www.trendyol.com",
            "Referer": "https://www.trendyol.com/",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        data = r.json()
        products = (data.get("result") or {}).get("products") or []
        results = []
        for p in products[:12]:
            name = p.get("name") or p.get("title") or ""
            if not name:
                continue
            price_info = p.get("price") or {}
            price = price_info.get("sellingPrice") or price_info.get("originalPrice") or 0
            orig = price_info.get("originalPrice")
            slug = p.get("url") or ""
            prod_url = f"https://www.trendyol.com{slug}" if slug.startswith("/") else slug
            img = ""
            imgs = p.get("images") or []
            if imgs:
                img = f"https://cdn.dsmcdn.com/{imgs[0]}" if not imgs[0].startswith("http") else imgs[0]
            results.append({
                "title": name,
                "price": float(price),
                "original_price": float(orig) if orig else None,
                "image_url": img,
                "source": "trendyol",
                "url": prod_url,
                "labels": ["Önerilen"],
                "extra_info": {"out_of_stock": price == 0},
            })
        return results
    except Exception:
        return []


def search_hepsiburada_direct(query: str) -> list[dict]:
    """Hepsiburada arama sayfasını scrape eder."""
    try:
        url = f"https://www.hepsiburada.com/ara?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": YAHOO_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "tr-TR,tr;q=0.9",
        }
        r = requests.get(url, headers=headers, timeout=8)
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li[data-test-id='product-card-item']") or soup.select("li.productListContent-item")
        if not items:
            # JSON içinde veri ara
            import json as _json
            m = re.search(r'__NEXT_DATA__.*?=\s*(\{.*?\})\s*;?\s*</script>', r.text, re.DOTALL)
            if m:
                try:
                    nd = _json.loads(m.group(1))
                    prods = nd.get("props", {}).get("pageProps", {}).get("products") or []
                    results = []
                    for p in prods[:10]:
                        name = p.get("name") or p.get("displayName") or ""
                        price = p.get("price") or p.get("salePrice") or 0
                        sku = p.get("sku") or ""
                        prod_url = f"https://www.hepsiburada.com/{sku}" if sku else ""
                        img = p.get("images", [""])[0] if p.get("images") else ""
                        if name and price:
                            results.append({
                                "title": name, "price": float(price), "original_price": None,
                                "image_url": img, "source": "hepsiburada", "url": prod_url,
                                "labels": ["Önerilen"], "extra_info": {"out_of_stock": False},
                            })
                    return results
                except Exception:
                    pass
        results = []
        for item in items[:10]:
            name_el = item.select_one("[data-test-id='product-card-name']") or item.select_one("h3") or item.select_one(".product-title")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            price_el = item.select_one("[data-test-id='price-current-price']") or item.select_one(".price-value")
            price = parse_price(price_el.get_text(strip=True)) if price_el else 0
            link_el = item.select_one("a")
            href = link_el.get("href", "") if link_el else ""
            prod_url = f"https://www.hepsiburada.com{href}" if href.startswith("/") else href
            img_el = item.select_one("img")
            img = img_el.get("src") or img_el.get("data-src") or "" if img_el else ""
            results.append({
                "title": name, "price": float(price or 0), "original_price": None,
                "image_url": img, "source": "hepsiburada", "url": prod_url,
                "labels": ["Önerilen"], "extra_info": {"out_of_stock": price == 0},
            })
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

def search_products_by_name(
    query: str,
    category: str = "general",
    lat: float = None,
    lon: float = None,
    mode: str = "hybrid"
) -> list[dict]:
    # 1. Run Kuantum Arama Orkestratörü
    from app.search_orchestrator import master_search
    all_products = run_async(master_search(query, selected_category=category, lat=lat, lon=lon, mode=mode))
    corrected_query = query
    
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
    # Ensure at least one returned product contains at least one word from the query or corrected query
    # (prevents random N11 fallback results for bogus queries)
    query_words = [w.strip() for w in corrected_query.lower().split() if len(w.strip()) > 2]
    if query_words and filtered_products:
        has_any_match = False
        for p in filtered_products:
            p_title_lower = p["title"].lower()
            if any(w in p_title_lower for w in query_words):
                has_any_match = True
                break
        if not has_any_match:
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
    valid_prices = [p["price"] for p in output_in_stock if p["price"] > 0]
    if len(valid_prices) >= 3:
        sorted_prices = sorted(valid_prices)
        n = len(sorted_prices)
        median_price = sorted_prices[n // 2] if n % 2 != 0 else (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2.0
        
        for p in output:
            if not p["extra_info"].get("out_of_stock") and p["price"] > 0:
                if p["price"] < 0.6 * median_price:
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


def lookup_barcode(barcode: str) -> dict | None:
    barcode_clean = barcode.strip()
    return BARCODE_DATABASE.get(barcode_clean)
