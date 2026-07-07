import asyncio
import urllib.parse
import re
import requests
import math
import hashlib
import random
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from app.comparator import (
    extract_yahoo_url,
    detect_source,
    is_valid_product_url,
    parse_product_url,
    is_logical_product
)

LOCAL_SOURCES = {"migros", "carrefoursa", "sokmarket", "metro"}

# marketplace_scan artık kategori başına 10-40 paralel istek atabiliyor;
# asyncio'nun varsayılan executor'ı (~CPU sayısı+4) bu kadar isteği paralel
# çalıştıramaz, sıraya girip toplam süreyi katlar. Kendi geniş havuzumuzu kullanıyoruz.
_SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=48, thread_name_prefix="scan")

YAHOO_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

WORKER_SITES = {
    # Yalnızca online sipariş veren mağazalar
    "GIDA": ["migros.com.tr", "carrefoursa.com", "sokmarket.com.tr", "metro-tr.com"],
    "TEKNOLOJİ": ["teknosa.com", "mediamarkt.com.tr", "vatanbilgisayar.com", "itopya.com"],
    "KOZMETİK": ["gratis.com", "rossmann.com.tr", "watsons.com.tr", "sephora.com.tr"],
    "MODA": ["lcwaikiki.com", "defacto.com.tr", "koton.com", "mavi.com", "boyner.com.tr", "zara.com"],
    "EV": ["karaca.com", "englishhome.com.tr", "madamecoco.com", "ikea.com.tr", "koctas.com.tr"],
    "MARKETPLACE": ["trendyol.com", "hepsiburada.com", "amazon.com.tr", "n11.com"],
    "MARKETPLACE_NO_N11": ["trendyol.com", "hepsiburada.com", "amazon.com.tr"],
}

POPULAR_FALLBACKS = [
    {
        "title": "Yudum Ayçiçek Yağı 5 L",
        "price": 182.90,
        "original_price": 210.00,
        "image_url": "https://images.deliveryhero.io/image/fd-tr/Products/12869502.jpg",
        "source": "bim",
        "url": "https://www.bim.com.tr/p/yudum-aycicek-yagi-5-l",
        "labels": ["Önerilen Alternatif"],
        "extra_info": {"out_of_stock": False, "fallback": True}
    },
    {
        "title": "Sütaş Süzme Peynir 500 gr",
        "price": 89.50,
        "original_price": 99.90,
        "image_url": "https://images.deliveryhero.io/image/fd-tr/Products/11796120.jpg",
        "source": "migros",
        "url": "https://www.migros.com.tr/p/sutas-suzme-peynir-500g",
        "labels": ["Önerilen Alternatif"],
        "extra_info": {"out_of_stock": False, "fallback": True}
    },
    {
        "title": "Doğuş Filiz Çay 1 Kg",
        "price": 135.00,
        "original_price": 155.00,
        "image_url": "https://images.deliveryhero.io/image/fd-tr/Products/11267812.jpg",
        "source": "metro",
        "url": "https://www.metro-tr.com/p/dogus-filiz-cay-1kg",
        "labels": ["Önerilen Alternatif"],
        "extra_info": {"out_of_stock": False, "fallback": True}
    },
    {
        "title": "Hardline Whey 3 Matrix 2300 Gr",
        "price": 2299.00,
        "original_price": 2499.00,
        "image_url": "https://img.supplementler.com/products/250x250/hardline-whey-3-matrix-2300-gr_10023.jpg",
        "source": "supplementler",
        "url": "https://www.supplementler.com/urun/hardline-whey-3-matrix-2300-gr-10023",
        "labels": ["Önerilen Alternatif"],
        "extra_info": {"out_of_stock": False, "fallback": True}
    },
    {
        "title": "Filiz Makarna 500 Gr",
        "price": 18.50,
        "original_price": 22.00,
        "image_url": "https://images.deliveryhero.io/image/fd-tr/Products/11786190.jpg",
        "source": "a101",
        "url": "https://www.a101.com.tr/p/filiz-makarna",
        "labels": ["Önerilen Alternatif"],
        "extra_info": {"out_of_stock": False, "fallback": True}
    }
]

def _normalize_tr(text: str) -> str:
    """Türkçe karakterleri ve yaygın yazım hatalarını normalize eder."""
    tr_map = str.maketrans("şğıöüçŞĞİÖÜÇ", "sgioucSGIOUC")
    return text.lower().translate(tr_map)


# Kategori anahtar kelime setleri — classify_intent() ve app.query_intelligence
# (fuzzy düzeltme / öğrenilen kelime dağarcığı) tarafından ortak kullanılır.
GROCERY_KEYWORDS = {
        # Süt & süt ürünleri
        "süt", "sut", "süts", "suts", "sutlu", "sütlü",
        "yoğurt", "yogurt", "yoghurt", "yogurt",
        "peynir", "peyniri", "beyaz peynir", "kasar", "kaşar",
        "tereyağ", "tereyag", "tereyağı", "margarin",
        "ayran", "kefir", "krema", "labne",
        # Et & protein
        "et", "kıyma", "kiyma", "kiyme", "köfte", "kofte",
        "tavuk", "tavug", "tavuğu", "pilic", "piliç", "hindi",
        "sucuk", "salam", "sosis", "pastırma", "pastirma",
        "balık", "balik", "somon", "levrek", "çupra", "cupra",
        "yumurta", "yumurta",
        # Tahıl & baklagil
        "ekmek", "ekmegi", "ekmek",
        "makarna", "spagetti", "spaghetti", "eriste", "erişte",
        "pirinç", "pirinc", "bulgur", "irmik", "semolina",
        "un", "nişasta", "nisasta", "yulaf",
        "mercimek", "nohut", "fasulye", "barbunya",
        # Yağ & sos
        "yağ", "yag", "zeytinyağı", "zeytinyagi", "ayçiçek", "aycicek", "mısır yağı",
        "salça", "salca", "ketçap", "ketsap", "mayonez", "hardal",
        "sirke", "sos",
        # Şeker & tatlı
        "şeker", "seker", "bal", "pekmez", "reçel", "recel",
        "çikolata", "cikolata", "biskuvi", "bisküvi", "gofret",
        "kek", "pasta", "puding",
        # İçecek
        "su", "maden suyu", "maden", "soda", "kola", "gazlı içecek",
        "meyve suyu", "limonata", "ayran", "çay", "cay", "kahve", "nes",
        "nescafe", "bitki çayı", "bitki cayi",
        # Sebze & meyve
        "sebze", "meyve", "domates", "salatalık", "salatalik",
        "biber", "patlıcan", "patlican", "kabak", "havuç", "havuc",
        "soğan", "sogan", "sarımsak", "sarimsak", "patates", "ıspanak", "ispanak",
        "elma", "armut", "portakal", "mandalina", "limon", "muz",
        "üzüm", "uzum", "çilek", "cilek", "kiraz", "şeftali", "seftali",
        # Market genel
        "zeytin", "turşu", "tursu", "konserve", "salata",
        "deterjan", "çamaşır", "camasir", "bulaşık", "bulasik",
        "sabun", "şampuan", "sampuan", "saç bakım", "sac bakim",
        "tuvalet kağıdı", "tuvalet kagidi", "kağıt havlu", "kagit havlu",
        "cips", "çips", "çekirdek", "cekirdek", "kuruyemiş", "kuruyemis",
        "market", "aktüel", "gıda", "gida",
    }

TECH_KEYWORDS = {
    # Cihazlar
    "telefon", "cep telefonu", "akıllı telefon", "akilli telefon",
    "bilgisayar", "laptop", "dizüstü", "dizustu", "masaüstü", "masaustu",
    "tablet", "ipad", "e-kitap okuyucu",
    "tv", "televizyon", "smart tv", "oled", "qled",
    "monitör", "monitor", "ekran",
    "kulaklık", "kulaklik", "headphone", "airpods", "earbuds", "hoparlör", "hoparlor",
    "kamera", "fotoğraf makinesi", "fotograf makinesi", "lens", "drone",
    "akıllı saat", "akilli saat", "smartwatch", "watch",
    # Bilgisayar parçaları
    "ram", "ssd", "hdd", "harddisk", "hard disk", "nvme", "m.2",
    "gpu", "ekran kartı", "ekran karti", "anakart", "cpu", "işlemci", "islemci",
    "kasa", "psu", "güç kaynağı", "guc kaynagi", "soğutucu", "sogutucu",
    # Aksesuar & çevre birimleri
    "mouse", "maus", "klavye", "keyboard", "mousepad",
    "kablo", "hdmi", "usb", "adaptör", "adaptor", "şarj", "sarj", "powerbank",
    "router", "modem", "switch", "ağ", "ag",
    "yazıcı", "yazici", "printer", "tarayıcı", "tarayici", "scanner",
    # Markalar
    "samsung", "apple", "iphone", "macbook", "ipad",
    "xiaomi", "redmi", "poco", "realme", "oppo", "vivo",
    "huawei", "honor", "oneplus",
    "lenovo", "asus", "hp", "dell", "acer", "msi", "toshiba",
    "sony", "lg", "philips", "vestel", "arcelik", "arçelik",
    "logitech", "corsair", "razer", "hyperx",
    "itopya", "vatanbilgisayar", "teknosa", "mediamarkt",
    # Genel
    "elektronik", "teknoloji", "gadget",
}

COSMETICS_KEYWORDS = {
    "ruj", "rujum", "lipstick", "lip",
    "rimel", "maskara", "mascara",
    "allık", "allik", "ruj", "far", "göz farı", "goz fari", "eyeliner",
    "fondöten", "fondoten", "foundation", "bb krem", "cc krem",
    "makyaj", "makeup", "make-up", "kozmetik",
    "cilt", "cilt bakım", "cilt bakim", "serum", "nemlendirici",
    "krem", "losyon", "tonik", "yüz yıkama", "yuz yikama",
    "güneş kremi", "gunes kremi", "spf",
    "parfüm", "parfum", "cologne", "kolonya",
    "deodorant", "roll-on", "antiperspirant",
    "oje", "tırnak", "tirnak", "nail",
    "maske", "peeling", "scrub",
    "saç", "sac", "şampuan", "sampuan", "saç bakım", "sac bakim",
    "saç boyası", "sac boyasi", "boya", "keratin",
    "epilasyon", "ağda", "agda", "tıraş", "tras", "jilet",
    "gratis", "rossmann", "watsons", "sephora",
}

FASHION_KEYWORDS = {
    # Üst giyim
    "tişört", "tisort", "tshirt", "t-shirt", "tee",
    "gömlek", "gomlek", "shirt", "bluz", "blouse",
    "kazak", "sweatshirt", "hoodie", "hırka", "hirka", "triko",
    "ceket", "mont", "kaban", "parka", "yağmurluk", "yagmurluk",
    "yelek", "vest",
    # Alt giyim
    "pantolon", "jean", "jeans", "denim", "tayt", "tayt",
    "şort", "sort", "bermuda",
    "etek", "skirt",
    # Elbise & tulum
    "elbise", "dress", "tulum", "overall",
    # Ayakkabı & çanta
    "ayakkabı", "ayakkabi", "shoe", "sneaker", "spor ayakkabı",
    "bot", "çizme", "cizme", "boot", "sandalet", "terlik",
    "çanta", "canta", "bag", "sırt çantası", "sirt cantasi", "cüzdan", "cuzdan",
    # İç giyim & çorap
    "iç çamaşır", "ic camasir", "külot", "kulot", "sütyen", "sutyen",
    "çorap", "corap", "sock",
    # Aksesuar
    "kemer", "kravat", "fular", "şapka", "sapka", "bere", "eldiven",
    "gözlük", "gozluk", "saat",
    # Markalar & genel
    "lcw", "lcwaikiki", "defacto", "koton", "mavi", "zara", "h&m",
    "boyner", "vakko", "pierre cardin",
    "giyim", "kıyafet", "kiyafet", "moda", "fashion",
}

HOME_KEYWORDS = {
    # Mutfak
    "tencere", "tava", "düdüklü", "duduklu", "wok",
    "tabak", "kase", "bardak", "çatal", "catal", "kaşık", "kasik", "bıçak", "bicak",
    "bıçak seti", "bicak seti", "çatal bıçak", "catal bicak",
    "blender", "mikser", "toaster", "fırın", "firin", "microdalga", "mikrodalga",
    "kahve makinesi", "çay makinesi", "cay makinesi", "kettle",
    "buzdolabı", "buzdolabi", "çamaşır makinesi", "camasir makinesi",
    "bulaşık makinesi", "bulasik makinesi", "fırın", "ocak",
    # Yatak odası
    "nevresim", "yorgan", "yastık", "yastik", "çarşaf", "carsaf",
    "battaniye", "pike",
    # Oturma odası
    "koltuk", "kanepe", "couch", "sofa", "puf",
    "halı", "hali", "kilim", "rug",
    "perde", "stor perde", "tül",
    "avize", "lamba", "abajur", "led",
    # Mobilya & dekorasyon
    "masa", "sandalye", "dolap", "raf", "kitaplık", "kitaplik",
    "mobilya", "furniture", "dekorasyon", "çerçeve", "cerceve",
    # Temizlik & ev bakım
    "elektrikli süpürge", "elektrikli supurge", "süpürge", "supurge",
    "robot süpürge", "robot supurge", "mop", "paspas",
    "ütü", "utu", "iron",
    # Banyo
    "havlu", "bornoz", "banyo", "duş", "dus", "tuvalet",
    # Markalar
    "ikea", "karaca", "korkmaz", "tefal", "beko", "arçelik", "arcelik",
    "vestel", "bosch", "siemens", "philips", "arzum",
    "english home", "madame coco", "koçtaş", "koctas",
    "ev", "home", "mutfak", "yatak",
}

# Kategori adı → anahtar kelime seti (query_intelligence tarafından da kullanılır)
CATEGORY_KEYWORD_SETS = {
    "GIDA": GROCERY_KEYWORDS,
    "TEKNOLOJİ": TECH_KEYWORDS,
    "KOZMETİK": COSMETICS_KEYWORDS,
    "MODA": FASHION_KEYWORDS,
    "EV": HOME_KEYWORDS,
}


def classify_intent(query: str) -> str:
    q = query.lower()
    qn = _normalize_tr(query)  # normalize edilmiş (ş→s, ğ→g, ı→i, ö→o, ü→u, ç→c)

    words = set(re.findall(r"\w+", q))
    words_n = set(re.findall(r"\w+", qn))

    def matches(kw_set):
        # normalize edilmiş keyword seti
        kw_norm = {_normalize_tr(k) for k in kw_set}
        # kelime bazlı eşleşme
        if words.intersection(kw_set) or words_n.intersection(kw_norm):
            return True
        # substring eşleşme yalnızca çok kelimeli kalıplar için (tek kelimeler yanlış eşleşmesin: "su" in "samsung")
        for kw in kw_norm:
            if " " in kw and kw in qn:
                return True
        return False

    for category, kw_set in CATEGORY_KEYWORD_SETS.items():
        if matches(kw_set):
            return category

    # Statik listelerde yok — cron ile günlük büyütülen (gerçek ürün
    # başlıklarından çıkarılan) öğrenilmiş kelime dağarcığına da bak.
    try:
        from app.query_intelligence import classify_from_learned_vocabulary
        learned = classify_from_learned_vocabulary(q, qn)
        if learned:
            return learned
    except Exception:
        pass

    return "GENEL"

def fetch_aol_urls_for_sites(query: str, sites: list[str], cart_filter: bool = True) -> list[str]:
    site_query = " OR ".join([f"site:{s}" for s in sites])
    if cart_filter:
        modified_query = f'{query} "sepete ekle" ({site_query})'
    else:
        modified_query = f'{query} ({site_query})'
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

def search_carrefoursa(query: str) -> list[dict]:
    """CarrefourSA arama sayfasını scrape eder.
    ScrapingBee varsa proxy üzerinden çeker (Vercel IP engeli aşılır).
    """
    from app.scraping_proxy import proxy_get
    url = f"https://www.carrefoursa.com/search/?text={urllib.parse.quote_plus(query)}"
    results = []
    try:
        html = proxy_get(url, timeout=12)
        if not html:
            return results
        soup = BeautifulSoup(html, "html.parser")

        names = soup.select(".item-name")
        prices = soup.select(".item-price")
        links = soup.select("a.product-url")
        imgs = soup.select(".product-img img")

        for i, name_el in enumerate(names[:10]):
            name = name_el.get_text(strip=True)
            if not name:
                continue
            price_text = prices[i].get_text(strip=True) if i < len(prices) else ""
            price_text = price_text.replace("TL", "").replace("\xa0", "").replace(".", "").replace(",", ".").strip()
            try:
                price = float(price_text)
            except ValueError:
                continue
            link_el = links[i] if i < len(links) else None
            href = link_el.get("href", "") if link_el else ""
            product_url = f"https://www.carrefoursa.com{href}" if href else url
            img_el = imgs[i] if i < len(imgs) else None
            img = (img_el.get("src") or img_el.get("data-src") or "") if img_el else ""
            results.append({
                "title": name,
                "price": price,
                "original_price": None,
                "image_url": img,
                "source": "carrefoursa",
                "url": product_url,
                "labels": ["Önerilen"],
                "extra_info": {"out_of_stock": False},
            })
    except Exception:
        pass
    return results


def search_migros_proxy(query: str) -> list[dict]:
    """Migros ürün araması — ScrapingBee üzerinden JSON API."""
    from app.scraping_proxy import proxy_get_json
    results = []
    try:
        api_url = (
            f"https://www.migros.com.tr/rest/search-gateway/v2/product/search"
            f"?query={urllib.parse.quote_plus(query)}&sayfa=0&siralamaTipi=0"
        )
        data = proxy_get_json(api_url, timeout=10)
        if not data:
            return results
        items = (
            data.get("data", {}).get("products", [])
            or data.get("products", [])
            or []
        )
        for item in items[:10]:
            name = item.get("name") or item.get("title", "")
            if not name:
                continue
            price_raw = (
                item.get("salePrice")
                or item.get("price")
                or item.get("listPrice", 0)
            )
            try:
                price = float(str(price_raw).replace(",", ".").replace("TL", "").strip())
            except (ValueError, TypeError):
                continue
            slug = item.get("url") or item.get("slug", "")
            product_url = (
                f"https://www.migros.com.tr/{slug}" if slug and not slug.startswith("http") else slug
            ) or "https://www.migros.com.tr"
            img = item.get("imageUrl") or item.get("image", {}).get("url", "") if isinstance(item.get("image"), dict) else item.get("image", "")
            results.append({
                "title": name,
                "price": price,
                "original_price": None,
                "image_url": img,
                "source": "migros",
                "url": product_url,
                "labels": ["Online Sipariş"],
                "extra_info": {"out_of_stock": False},
            })
    except Exception:
        pass
    return results


async def scan_worker(query: str, category: str, fallback: bool = False) -> list[dict]:
    sites = WORKER_SITES.get(category, WORKER_SITES["MARKETPLACE"])
    loop = asyncio.get_running_loop()
    # GIDA için "sepete ekle" filtresi olmadan ara — Türk market siteleri bu ifadeyle indexlenmez
    use_cart_filter = category not in ("GIDA",)
    aol_urls = await loop.run_in_executor(None, fetch_aol_urls_for_sites, query, sites, use_cart_filter)
    
    aol_products = []
    if aol_urls:
        candidates = aol_urls[:8]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(parse_product_url, u): u for u in candidates}
            for future in futures:
                try:
                    parsed = future.result()
                    if parsed.title:
                        is_out_of_stock = parsed.price is None or parsed.price == 0
                        price_val = parsed.price if not is_out_of_stock else 0
                        
                        extra_info = parsed.extra_info or {}
                        if fallback:
                            extra_info["fallback"] = True
                            
                        # Format labels
                        labels = ["Stokta Yok"] if is_out_of_stock else (["Önerilen Alternatif"] if fallback else ["Önerilen"])
                        if fallback:
                            labels.append("Lokal Fallback")
                            
                        aol_products.append({
                            "title": parsed.title,
                            "price": price_val,
                            "original_price": parsed.original_price,
                            "image_url": parsed.image_url,
                            "source": parsed.source,
                            "url": parsed.canonical_url,
                            "labels": labels,
                            "extra_info": {
                                **extra_info,
                                "out_of_stock": is_out_of_stock
                            }
                        })
                except Exception:
                    pass
    
    # Filter products
    filtered_products = [p for p in aol_products if is_logical_product(query, p["title"])]
    return filtered_products

async def marketplace_scan(query: str, fallback: bool = False, forced_category: str = None) -> list[dict]:
    """Paralel arama — çalışan kaynaklar (Vercel 10s limiti)."""
    loop = asyncio.get_running_loop()
    from app.comparator import (
        search_n11_direct, search_amazon_tr,
        search_trendyol_direct, search_hepsiburada_direct,
        # Teknoloji
        search_mediamarkt, search_teknosa, search_vatanbilgisayar, search_itopya,
        search_casper, search_huawei, search_xiaomi, search_lenovo, search_asusrog,
        search_lg, search_sony, search_hp, search_canon, search_epson,
        search_turkcell, search_dsmart,
        # Bebek/oyuncak
        search_ebebek, search_toyzz, search_bebek, search_lego, search_frigg,
        # Ev/mobilya
        search_vivense, search_evidea, search_karaca, search_englishhome,
        search_madamecoco, search_koctas, search_bauhaus, search_istikbal,
        search_bellona, search_dogtas, search_kelebek, search_schafer,
        search_korkmaz, search_bosch, search_tefal, search_arzum, search_fakir,
        search_philips,
        # Moda/spor
        search_yargici, search_kinetix, search_flo, search_lcwaikiki, search_mavi,
        search_boyner, search_zara, search_hm, search_bershka, search_colins,
        search_ltb, search_vakko, search_beymen, search_sarar, search_twist,
        search_penti, search_pierrecardin, search_altinyildiz, search_derimod,
        search_damattween, search_shein, search_modanisa, search_bigjoy,
        search_decathlon, search_nike, search_adidas, search_puma, search_reebok,
        search_newbalance, search_sportive, search_lescon, search_pandora,
        # Kozmetik
        search_gratis, search_rossmann, search_watsons, search_sephora,
        search_flormar, search_goldenrose, search_farmasi,
        # Gıda/market
        search_bim, search_a101, search_sokmarket, search_tarimkredi,
        search_metro, search_bizimtoptan, search_tazedirekt,
        # Kitap/genel
        search_kitapyurdu, search_dr, search_remzi, search_idefix,
        search_muzikdunyasi, search_ufukkirtasiye, search_ofissepeti,
        # Pazaryeri (uluslararası)
        search_pazarama, search_aliexpress, search_temu,
        # Ek: evcil hayvan, takviye
        search_evpet, search_petbis, search_petlebi, search_zopet,
        search_proteinocean, search_supplementler, search_runnutrition,
    )

    category = forced_category or classify_intent(query)

    # Pazaryerleri her kategoride çalışır
    base_tasks = [
        loop.run_in_executor(_SCAN_EXECUTOR, search_n11_direct, query),
        loop.run_in_executor(_SCAN_EXECUTOR, search_amazon_tr, query),
        loop.run_in_executor(_SCAN_EXECUTOR, search_trendyol_direct, query),
        loop.run_in_executor(_SCAN_EXECUTOR, search_hepsiburada_direct, query),
        loop.run_in_executor(_SCAN_EXECUTOR, search_pazarama, query),
        loop.run_in_executor(_SCAN_EXECUTOR, search_aliexpress, query),
        loop.run_in_executor(_SCAN_EXECUTOR, search_temu, query),
    ]

    # Kategoriye göre uzman mağazalar
    extra_tasks = []
    if category == "TEKNOLOJİ":
        for fn in (search_mediamarkt, search_teknosa, search_vatanbilgisayar,
                   search_itopya, search_casper, search_huawei, search_xiaomi,
                   search_lenovo, search_asusrog, search_lg, search_sony,
                   search_hp, search_canon, search_epson, search_turkcell,
                   search_dsmart):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    elif category == "BEBEK":
        # search_toyzz/search_bebek render_js=True gerektiriyor (10-20s),
        # canli taramadan cikarildi -- bkz. app/slow_store_cache_warmer.py
        for fn in (search_ebebek, search_lego, search_frigg):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    elif category in ("EV", "MOBİLYA"):
        for fn in (search_vivense, search_evidea, search_karaca, search_englishhome,
                   search_madamecoco, search_koctas, search_bauhaus, search_istikbal,
                   search_bellona, search_dogtas, search_kelebek, search_schafer,
                   search_korkmaz, search_bosch, search_tefal, search_arzum,
                   search_fakir, search_philips):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    elif category in ("MODA", "SPOR"):
        for fn in (search_yargici, search_kinetix, search_flo, search_lcwaikiki,
                   search_mavi, search_boyner, search_zara, search_hm, search_bershka,
                   search_colins, search_ltb, search_vakko, search_beymen, search_sarar,
                   search_twist, search_penti, search_pierrecardin, search_altinyildiz,
                   search_derimod, search_damattween, search_shein, search_modanisa,
                   search_bigjoy, search_decathlon, search_nike, search_adidas,
                   search_puma, search_reebok, search_newbalance, search_sportive,
                   search_lescon, search_pandora):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    elif category == "KOZMETİK":
        # search_gratis/watsons/sephora/goldenrose/farmasi canli taramadan
        # cikarildi: render_js=True ScrapingBee istegi 10-20s surebiliyor,
        # bu da diger hizli scraper'larla ayni 7s butceyi paylasinca
        # tutarsiz (bazen var bazen yok) sonuca yol aciyor. Bu magazalar
        # artik app/slow_store_cache_warmer.py'deki ayri, zaman siniri
        # olmayan cron ile onceden taranip cache'e yaziliyor.
        for fn in (search_rossmann, search_flormar):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    elif category == "GIDA":
        # search_a101 canli taramadan cikarildi: render_js=True ScrapingBee
        # istegi 10-20s surebiliyor, Vercel Hobby'nin kesin 10s fonksiyon
        # limitiyle yapisal olarak uyusmuyor -- istek container donana kadar
        # tamamlanamiyor ve hic ScrapingBee'ye ulasmiyor. Cron/toplu tarama
        # icin fonksiyon comparator.py'de duruyor.
        for fn in (search_bim, search_sokmarket, search_tarimkredi,
                   search_metro, search_bizimtoptan, search_tazedirekt,
                   search_migros_proxy, search_carrefoursa):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    elif category in ("GENEL", "KİTAP"):
        for fn in (search_kitapyurdu, search_dr, search_remzi, search_idefix,
                   search_muzikdunyasi, search_ufukkirtasiye, search_ofissepeti,
                   search_evpet, search_petbis, search_petlebi, search_zopet,
                   search_proteinocean, search_supplementler, search_runnutrition):
            extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, fn, query))
    else:
        # GENEL/bilinmeyen → MediaMarkt + Teknosa da dene
        extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, search_mediamarkt, query))
        extra_tasks.append(loop.run_in_executor(_SCAN_EXECUTOR, search_teknosa, query))

    all_tasks = base_tasks + extra_tasks
    try:
        # Kategori başına 10-40 mağaza aranabiliyor; yavaş/yanıt vermeyen birkaç
        # kaynak tüm isteği bekletmesin diye üst süre sınırı koyuyoruz.
        results_raw = await asyncio.wait_for(
            asyncio.gather(*all_tasks, return_exceptions=True), timeout=7.0
        )
    except asyncio.TimeoutError:
        # Süre dolduğunda o ana kadar biten task'ların sonucunu kullan, geri kalanı iptal et.
        results_raw = []
        for t in all_tasks:
            if t.done() and not t.cancelled():
                exc = t.exception()
                results_raw.append(exc if exc else t.result())
            else:
                t.cancel()

    all_products = []
    seen_urls = set()
    for res in results_raw:
        if isinstance(res, Exception):
            continue
        # N11 returns tuple (products, query_str)
        if isinstance(res, tuple):
            res = res[0] if res else []
        if not isinstance(res, list):
            continue
        for p in res:
            url_clean = p.get("url", "").split("?")[0].strip()
            if url_clean and url_clean in seen_urls:
                continue
            if url_clean:
                seen_urls.add(url_clean)
            all_products.append(p)

    return all_products

def get_simulated_location(title: str, source: str, lat: float, lon: float):
    # Stabil tohumlama
    seed_str = f"{title}_{source}"
    h = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    r = random.Random(h)
    
    # 3 km içinde offset (yaklaşık 0.02 derece limit)
    lat_offset = r.uniform(-0.015, 0.015)
    lon_offset = r.uniform(-0.02, 0.02)
    
    branch_lat = lat + lat_offset
    branch_lon = lon + lon_offset
    
    # Haversine mesafe hesabı
    dlat = math.radians(branch_lat - lat)
    dlon = math.radians(branch_lon - lon)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(branch_lat)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance_km = 6371.0 * c
    
    # Teslimat süresi: 30-60 dakika
    delivery_time_mins = int(30 + distance_km * 10)
    delivery_time_mins = max(30, min(60, delivery_time_mins))
    
    return branch_lat, branch_lon, distance_km, delivery_time_mins

def generate_local_fallback_results(query: str, category: str, lat: float = None, lon: float = None) -> list[dict]:
    if category == "GIDA":
        sources = [("Migros (Lokal Spektrum)", "migros", 189.90), ("CarrefourSA (Lokal Spektrum)", "carrefoursa", 199.90)]
    elif category == "TEKNOLOJİ":
        sources = [("Teknosa (Lokal Spektrum)", "teknosa", 4299.00), ("MediaMarkt (Lokal Spektrum)", "mediamarkt", 4499.00)]
    elif category == "KOZMETİK":
        sources = [("Gratis (Lokal Spektrum)", "gratis", 189.90), ("Rossmann (Lokal Spektrum)", "rossmann", 199.90)]
    elif category == "MODA":
        sources = [("LCW (Lokal Spektrum)", "lcwaikiki", 499.90), ("Defacto (Lokal Spektrum)", "defacto", 529.90)]
    elif category == "EV":
        sources = [("Karaca (Lokal Spektrum)", "karaca", 899.90), ("Ikea (Lokal Spektrum)", "ikea", 949.90)]
    else:
        sources = [("Pazaryeri (Lokal Spektrum)", "trendyol", 299.90), ("Amazon (Lokal Spektrum)", "amazon", 319.90)]

    results = []
    for i, (source_name, source_key, price) in enumerate(sources):
        labels = ["Sistem, lokal rezonans verisi kullanıyor", "Önerilen Alternatif"]
        if i == 0:
            labels.append("En Ucuz")
            
        res_item = {
            "title": f"{query} ({'Lokal Rezonans' if i == 0 else 'Alternatif Enerji'})",
            "price": price,
            "original_price": round(price * 1.2, 2),
            "image_url": "",
            "source": source_key,
            "url": f"https://www.{source_key}.com.tr/local-fallback/{urllib.parse.quote(query)}",
            "labels": labels,
            "extra_info": {
                "out_of_stock": False,
                "fallback": True,
                "local_resonance": True
            }
        }
        
        # Coğrafi alanları zenginleştir
        is_local = source_key in LOCAL_SOURCES
        if is_local and lat is not None and lon is not None:
            branch_lat, branch_lon, distance_km, delivery_time_mins = get_simulated_location(res_item["title"], source_key, lat, lon)
            res_item["delivery_type"] = "local"
            res_item["delivery_time"] = f"{delivery_time_mins} Dakika"
            res_item["distance_km"] = round(distance_km, 2)
            res_item["latitude"] = round(branch_lat, 6)
            res_item["longitude"] = round(branch_lon, 6)
            res_item["delivery_cost"] = "29.90 TL"
        else:
            res_item["delivery_type"] = "global"
            res_item["delivery_time"] = "2 İş Günü"
            res_item["distance_km"] = None
            res_item["latitude"] = None
            res_item["longitude"] = None
            res_item["delivery_cost"] = "Ücretsiz Kargo"
            
        results.append(res_item)
    return results

def get_popular_fallbacks(query: str) -> list[dict]:
    words = [w for w in query.lower().split() if len(w) > 2]
    matches = []
    if words:
        for item in POPULAR_FALLBACKS:
            title_lower = item["title"].lower()
            if any(w in title_lower for w in words):
                matches.append(item)
    return matches if matches else POPULAR_FALLBACKS

async def master_search(
    query: str,
    selected_category: str = "general",
    lat: float = None,
    lon: float = None,
    mode: str = "hybrid"
) -> list[dict]:
    # Yazım hatası toleranslı düzeltme (rapidfuzz + statik/öğrenilmiş
    # kelime dağarcığı) — kategori sınıflandırma ve tarama bu düzeltilmiş
    # sorguyla yapılır, kullanıcıya gösterilen orijinal metin değişmez.
    try:
        from app.query_intelligence import correct_query
        query = correct_query(query)
    except Exception:
        pass

    category = classify_intent(query)
    if category == "GENEL" and selected_category != "general":
        category_map = {
            "grocery": "GIDA",
            "electronics": "TEKNOLOJİ",
            "cosmetics": "KOZMETİK",
            "fashion": "MODA",
            "home": "EV"
        }
        category = category_map.get(selected_category, "GENEL")

    # ── Cache-first lookup ──────────────────────────────────────────────────
    from app.cache import make_cache_key, cache_get, cache_set, cache_get_stale
    _cache_key = make_cache_key(query, category)
    cached = cache_get(_cache_key, query=query, category=category)
    # Eski/bozuk semali cache kayitlari (dict olmayan oge, bos liste vb.)
    # gecerli sayilmasin -- yoksa taze taramaya hic gecilmez, kalici bos
    # sonuc donmeye devam eder.
    cached = [p for p in cached if isinstance(p, dict) and p.get("title") and p.get("url")] if cached else None
    if cached:
        return cached
    # cache miss → metrik kaydet
    try:
        from app.admin_metrics import record_event
        record_event("cache_miss", query=query, category=category)
    except Exception:
        pass
    # ───────────────────────────────────────────────────────────────────────
    # ───────────────────────────────────────────────────────────────────────

    results = []
    loop = asyncio.get_running_loop()

    try:
        async with asyncio.timeout(8.0):
            if mode == "global" or lat is None or lon is None:
                results = await marketplace_scan(query, forced_category=category)
            elif mode == "local":
                local_res = await scan_worker(query, category)
                results = [r for r in local_res if r["source"] in LOCAL_SOURCES]
            else:  # hybrid
                results = await marketplace_scan(query, forced_category=category)
    except (asyncio.TimeoutError, Exception):
        results = []

    # ── Canlı kaynaklar başarısız → normal fallback dene ──────────────────
    if not results and mode == "local":
        fallback_res = await scan_worker(query, "MARKETPLACE_NO_N11", fallback=True)
        for r in fallback_res:
            r["delivery_type"] = "global"
            r["delivery_time"] = "2 İş Günü"
            r["distance_km"] = None
            r["latitude"] = None
            r["longitude"] = None
            r["delivery_cost"] = "Ücretsiz Kargo"
            if "Konum aralığı genişletiliyor..." not in r["labels"]:
                r["labels"].append("Konum aralığı genişletiliyor...")
        results = fallback_res

    if not results:
        if category == "GENEL":
            results = await marketplace_scan(query, fallback=True)
        else:
            short_query = query.split()[0] if " " in query else query
            results = await scan_worker(short_query, category, fallback=True)
            if not results:
                results = await scan_worker(query, "MARKETPLACE_NO_N11", fallback=True)

    # ── Son çare: Süresi dolmuş cache (stale fallback) ─────────────────────
    if not results:
        stale = cache_get_stale(_cache_key)
        if stale:
            try:
                from app.admin_metrics import record_event
                record_event("stale_fallback", query=query, category=category)
            except Exception:
                pass
            return stale
    # ───────────────────────────────────────────────────────────────────────
        
    # Coğrafi alanları ve teslimat bilgilerini her ürün için ekle/güncelle
    for item in results:
        is_local = item["source"] in LOCAL_SOURCES
        if is_local and lat is not None and lon is not None:
            branch_lat, branch_lon, distance_km, delivery_time_mins = get_simulated_location(item["title"], item["source"], lat, lon)
            item["delivery_type"] = "local"
            item["delivery_time"] = f"{delivery_time_mins} Dakika"
            item["distance_km"] = round(distance_km, 2)
            item["latitude"] = round(branch_lat, 6)
            item["longitude"] = round(branch_lon, 6)
            item["delivery_cost"] = "29.90 TL"
        else:
            item["delivery_type"] = "global"
            item["delivery_time"] = "2 İş Günü"
            item["distance_km"] = None
            item["latitude"] = None
            item["longitude"] = None
            item["delivery_cost"] = "Ücretsiz Kargo"

    # Sıralama: Yerel ürünler (mesafeye göre) en üste, global ürünler (fiyata göre) alta
    if lat is not None and lon is not None:
        local_items = [r for r in results if r["delivery_type"] == "local"]
        global_items = [r for r in results if r["delivery_type"] != "local"]
        local_items.sort(key=lambda x: x.get("distance_km", 999.0))
        global_items.sort(key=lambda x: x.get("price", 999999.0))
        results = local_items + global_items

    # ── Fiyat geçmişi kaydet + trendleri ekle ─────────────────────────────
    if results:
        try:
            from app.price_history import record_prices, enrich_with_trends
            record_prices(results)
            results = enrich_with_trends(results)
        except Exception:
            pass
    # ───────────────────────────────────────────────────────────────────────

    # ── Cache'e kaydet (boş sonuçları kaydetme) ────────────────────────────
    if results:
        cache_set(_cache_key, query, category, results)
    # ───────────────────────────────────────────────────────────────────────

    return results
