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


def classify_intent(query: str) -> str:
    q = query.lower()
    qn = _normalize_tr(query)  # normalize edilmiş (ş→s, ğ→g, ı→i, ö→o, ü→u, ç→c)

    # Her kategori için (orijinal, normalize) çiftleri
    grocery_keywords = {
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

    tech_keywords = {
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

    cosmetics_keywords = {
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

    fashion_keywords = {
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

    home_keywords = {
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

    if matches(grocery_keywords):
        return "GIDA"
    if matches(tech_keywords):
        return "TEKNOLOJİ"
    if matches(cosmetics_keywords):
        return "KOZMETİK"
    if matches(fashion_keywords):
        return "MODA"
    if matches(home_keywords):
        return "EV"

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

async def marketplace_scan(query: str, fallback: bool = False) -> list[dict]:
    loop = asyncio.get_running_loop()
    from app.comparator import (
        search_n11_direct,
        search_amazon_tr,
        search_trendyol_direct,
        search_hepsiburada_direct,
        search_karaca, search_watsons, search_gratis,
        search_mediamarkt, search_teknosa,
        search_boyner, search_flo, search_decathlon,
        search_lcwaikiki, search_mavi, search_zara,
        search_bim, search_rossmann, search_supplementler,
        search_englishhome, search_a101, search_sokmarket,
        search_temu, search_pazarama, search_ciceksepeti,
        search_xiaomi, search_huawei, search_hp, search_lenovo, search_evkur,
        search_penti, search_colins, search_twist, search_ltb, search_modanisa,
        search_nike, search_puma, search_newbalance, search_sportive,
        search_flormar, search_goldenrose,
        search_istikbal, search_bellona, search_madamecoco, search_korkmaz,
        search_kitapyurdu, search_dr, search_idefix,
        search_bebek, search_ebebek, search_toyzz,
        search_tefal, search_arnica, search_arzum, search_schafer, search_fakir, search_bosch,
        search_evidea, search_vivense, search_kelebek, search_dogtas,
        search_bauhaus,
        search_petlebi,
        search_proteinocean, search_bigjoy, search_runnutrition,
        search_pierrecardin,
        search_vatanbilgisayar, search_itopya, search_casper,
        search_remzi,
        search_tazedirekt, search_bizimtoptan, search_tarimkredi,
        search_defacto,
        search_kutahyaporselen, search_beymen, search_vakko, search_network,
        search_philips, search_farmasi, search_dsmart, search_miniso, search_action,
        search_turkcell, search_hopi, search_pandora, search_altinyildiz,
        search_derimod, search_lescon, search_namet, search_dardanel,
        search_shein, search_aliexpress,
        search_hm, search_sephora, search_koctas, search_adidas, search_metro,
        search_gamegaraj, search_ofissepeti, search_muzikdunyasi,
        search_reebok, search_bershka, search_ulker, search_lego,
        search_epson, search_sarar, search_damattween, search_yargici,
        search_sony, search_lg, search_canon,
        search_oyundeposu, search_frigg, search_asusrog,
        search_melodika, search_ufukkirtasiye,
        search_evpet, search_zopet, search_petbis,
    )

    category = classify_intent(query)

    # Always run main 4
    ty_task  = loop.run_in_executor(None, search_trendyol_direct, query)
    hb_task  = loop.run_in_executor(None, search_hepsiburada_direct, query)
    n11_task = loop.run_in_executor(None, search_n11_direct, query)
    amz_task = loop.run_in_executor(None, search_amazon_tr, query)

    # Category-specific extras
    extra_tasks = []

    q_lower = query.lower()

    if category in ("KOZMETİK", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_watsons, query))
        extra_tasks.append(loop.run_in_executor(None, search_gratis, query))
        extra_tasks.append(loop.run_in_executor(None, search_rossmann, query))
        extra_tasks.append(loop.run_in_executor(None, search_flormar, query))
        extra_tasks.append(loop.run_in_executor(None, search_goldenrose, query))

    if category in ("EV", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_karaca, query))
        extra_tasks.append(loop.run_in_executor(None, search_englishhome, query))
        extra_tasks.append(loop.run_in_executor(None, search_istikbal, query))
        extra_tasks.append(loop.run_in_executor(None, search_bellona, query))
        extra_tasks.append(loop.run_in_executor(None, search_madamecoco, query))
        extra_tasks.append(loop.run_in_executor(None, search_korkmaz, query))

    if category in ("TEKNOLOJİ", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_mediamarkt, query))
        extra_tasks.append(loop.run_in_executor(None, search_teknosa, query))
        extra_tasks.append(loop.run_in_executor(None, search_xiaomi, query))
        extra_tasks.append(loop.run_in_executor(None, search_huawei, query))
        extra_tasks.append(loop.run_in_executor(None, search_hp, query))
        extra_tasks.append(loop.run_in_executor(None, search_lenovo, query))
        extra_tasks.append(loop.run_in_executor(None, search_evkur, query))

    if category in ("MODA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_boyner, query))
        extra_tasks.append(loop.run_in_executor(None, search_flo, query))
        extra_tasks.append(loop.run_in_executor(None, search_lcwaikiki, query))
        extra_tasks.append(loop.run_in_executor(None, search_mavi, query))
        extra_tasks.append(loop.run_in_executor(None, search_zara, query))
        extra_tasks.append(loop.run_in_executor(None, search_penti, query))
        extra_tasks.append(loop.run_in_executor(None, search_colins, query))
        extra_tasks.append(loop.run_in_executor(None, search_twist, query))
        extra_tasks.append(loop.run_in_executor(None, search_ltb, query))
        extra_tasks.append(loop.run_in_executor(None, search_modanisa, query))

    is_sport = any(w in q_lower for w in ["spor", "koşu", "kosu", "ayakkabı", "ayakkabi", "forma", "antrenman", "fitness", "gym"])
    if is_sport or category in ("SPOR", "GENEL", "MODA"):
        extra_tasks.append(loop.run_in_executor(None, search_decathlon, query))
        extra_tasks.append(loop.run_in_executor(None, search_nike, query))
        extra_tasks.append(loop.run_in_executor(None, search_puma, query))
        extra_tasks.append(loop.run_in_executor(None, search_newbalance, query))
        extra_tasks.append(loop.run_in_executor(None, search_sportive, query))

    if category in ("GIDA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_bim, query))
        extra_tasks.append(loop.run_in_executor(None, search_a101, query))
        extra_tasks.append(loop.run_in_executor(None, search_sokmarket, query))

    if category in ("SUPPLEMENT", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_supplementler, query))

    # GENEL marketplace extras
    extra_tasks.append(loop.run_in_executor(None, search_temu, query))
    extra_tasks.append(loop.run_in_executor(None, search_pazarama, query))
    extra_tasks.append(loop.run_in_executor(None, search_ciceksepeti, query))

    # Kitap kategorisi
    is_book = any(w in q_lower for w in ["kitap", "roman", "yazar", "hikaye", "dergi", "ansiklopedi"])
    if is_book or category == "KİTAP":
        extra_tasks.append(loop.run_in_executor(None, search_kitapyurdu, query))
        extra_tasks.append(loop.run_in_executor(None, search_dr, query))
        extra_tasks.append(loop.run_in_executor(None, search_idefix, query))
        extra_tasks.append(loop.run_in_executor(None, search_remzi, query))

    # Bebek & Çocuk kategorisi
    is_bebek = any(w in q_lower for w in ["bebek", "oyuncak", "çocuk", "cocuk", "bez"])
    if is_bebek or category == "BEBEK":
        extra_tasks.append(loop.run_in_executor(None, search_bebek, query))
        extra_tasks.append(loop.run_in_executor(None, search_ebebek, query))
        extra_tasks.append(loop.run_in_executor(None, search_toyzz, query))

    # Ev aletleri & mutfak
    if category in ("EV", "GENEL", "TEKNOLOJİ"):
        extra_tasks.append(loop.run_in_executor(None, search_tefal, query))
        extra_tasks.append(loop.run_in_executor(None, search_arnica, query))
        extra_tasks.append(loop.run_in_executor(None, search_arzum, query))
        extra_tasks.append(loop.run_in_executor(None, search_schafer, query))
        extra_tasks.append(loop.run_in_executor(None, search_fakir, query))
        extra_tasks.append(loop.run_in_executor(None, search_bosch, query))

    # Mobilya & ev dekor
    if category in ("EV", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_evidea, query))
        extra_tasks.append(loop.run_in_executor(None, search_vivense, query))
        extra_tasks.append(loop.run_in_executor(None, search_kelebek, query))
        extra_tasks.append(loop.run_in_executor(None, search_dogtas, query))
        extra_tasks.append(loop.run_in_executor(None, search_bauhaus, query))

    # Pet
    is_pet = any(w in q_lower for w in ["kedi", "köpek", "kopek", "kuş", "kus", "balik", "balık", "pet", "hayvan", "mama", "tasma", "kafes"])
    if is_pet:
        extra_tasks.append(loop.run_in_executor(None, search_petlebi, query))

    # Supplement ek
    if category in ("SUPPLEMENT", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_proteinocean, query))
        extra_tasks.append(loop.run_in_executor(None, search_bigjoy, query))
        extra_tasks.append(loop.run_in_executor(None, search_runnutrition, query))

    # Moda ek
    if category in ("MODA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_pierrecardin, query))
        extra_tasks.append(loop.run_in_executor(None, search_defacto, query))

    # Teknoloji ek
    if category in ("TEKNOLOJİ", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_vatanbilgisayar, query))
        extra_tasks.append(loop.run_in_executor(None, search_itopya, query))
        extra_tasks.append(loop.run_in_executor(None, search_casper, query))

    # Gida ek
    if category in ("GIDA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_tazedirekt, query))
        extra_tasks.append(loop.run_in_executor(None, search_bizimtoptan, query))
        extra_tasks.append(loop.run_in_executor(None, search_tarimkredi, query))

    # Yeni mağazalar - EV/Porselen
    if category in ("EV", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_kutahyaporselen, query))
        extra_tasks.append(loop.run_in_executor(None, search_koctas, query))

    # Yeni mağazalar - MODA
    if category in ("MODA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_beymen, query))
        extra_tasks.append(loop.run_in_executor(None, search_vakko, query))
        extra_tasks.append(loop.run_in_executor(None, search_network, query))
        extra_tasks.append(loop.run_in_executor(None, search_altinyildiz, query))
        extra_tasks.append(loop.run_in_executor(None, search_derimod, query))
        extra_tasks.append(loop.run_in_executor(None, search_lescon, query))
        extra_tasks.append(loop.run_in_executor(None, search_shein, query))
        extra_tasks.append(loop.run_in_executor(None, search_hm, query))

    # Yeni mağazalar - KOZMETİK
    if category in ("KOZMETİK", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_farmasi, query))
        extra_tasks.append(loop.run_in_executor(None, search_sephora, query))

    # Yeni mağazalar - TEKNOLOJİ
    if category in ("TEKNOLOJİ", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_philips, query))
        extra_tasks.append(loop.run_in_executor(None, search_dsmart, query))
        extra_tasks.append(loop.run_in_executor(None, search_turkcell, query))
        extra_tasks.append(loop.run_in_executor(None, search_aliexpress, query))

    # Yeni mağazalar - GENEL
    extra_tasks.append(loop.run_in_executor(None, search_miniso, query))
    extra_tasks.append(loop.run_in_executor(None, search_action, query))
    extra_tasks.append(loop.run_in_executor(None, search_hopi, query))

    # Yeni mağazalar - GIDA
    if category in ("GIDA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_namet, query))
        extra_tasks.append(loop.run_in_executor(None, search_dardanel, query))
        extra_tasks.append(loop.run_in_executor(None, search_metro, query))

    # Pandora - sadece takı sorgularında
    is_jewelry = any(w in q_lower for w in ["yuzuk", "yüzük", "kolye", "bileklik", "kupe", "küpe", "taki", "takı", "pandora"])
    if is_jewelry:
        extra_tasks.append(loop.run_in_executor(None, search_pandora, query))

    # Adidas - spor veya moda
    if is_sport or category in ("MODA", "GENEL"):
        extra_tasks.append(loop.run_in_executor(None, search_adidas, query))

    # Gaming / Ofis / Müzik / Hobi
    is_gaming = any(w in q_lower for w in ["oyun", "game", "gaming", "konsol", "ps", "xbox", "pc", "mouse", "klavye", "kulaklık"])
    is_ofis = any(w in q_lower for w in ["kalem", "defter", "ofis", "kırtasiye", "yazici", "printer", "toner"])
    is_muzik = any(w in q_lower for w in ["gitar", "piyano", "müzik", "muzik", "enstruman", "bateri", "keman"])
    is_hobi = any(w in q_lower for w in ["lego", "oyuncak", "model", "puzzle", "hobi"])

    if is_gaming or category in ("TEKNOLOJİ", "GENEL"):
        extra_tasks += [
            loop.run_in_executor(None, search_gamegaraj, query),
            loop.run_in_executor(None, search_oyundeposu, query),
            loop.run_in_executor(None, search_frigg, query),
            loop.run_in_executor(None, search_asusrog, query),
        ]
    if is_ofis or category in ("TEKNOLOJİ", "GENEL"):
        extra_tasks += [
            loop.run_in_executor(None, search_ofissepeti, query),
            loop.run_in_executor(None, search_ufukkirtasiye, query),
        ]
    if is_muzik or category == "GENEL":
        extra_tasks += [
            loop.run_in_executor(None, search_muzikdunyasi, query),
            loop.run_in_executor(None, search_melodika, query),
        ]
    if is_pet:
        extra_tasks += [
            loop.run_in_executor(None, search_evpet, query),
            loop.run_in_executor(None, search_zopet, query),
            loop.run_in_executor(None, search_petbis, query),
        ]
    if is_hobi or category in ("BEBEK", "GENEL"):
        extra_tasks += [loop.run_in_executor(None, search_lego, query)]
    if category in ("MODA", "SPOR", "GENEL"):
        extra_tasks += [
            loop.run_in_executor(None, search_reebok, query),
            loop.run_in_executor(None, search_bershka, query),
            loop.run_in_executor(None, search_sarar, query),
            loop.run_in_executor(None, search_damattween, query),
            loop.run_in_executor(None, search_yargici, query),
        ]
    if category in ("GIDA", "GENEL"):
        extra_tasks += [loop.run_in_executor(None, search_ulker, query)]
    if category in ("TEKNOLOJİ", "GENEL"):
        extra_tasks += [
            loop.run_in_executor(None, search_epson, query),
            loop.run_in_executor(None, search_sony, query),
            loop.run_in_executor(None, search_lg, query),
            loop.run_in_executor(None, search_canon, query),
        ]

    results_raw = await asyncio.gather(ty_task, hb_task, n11_task, amz_task, *extra_tasks, return_exceptions=True)

    ty_res   = results_raw[0] if not isinstance(results_raw[0], Exception) else []
    hb_res   = results_raw[1] if not isinstance(results_raw[1], Exception) else []
    n11_raw  = results_raw[2] if not isinstance(results_raw[2], Exception) else ([], "")
    amz_res  = results_raw[3] if not isinstance(results_raw[3], Exception) else []

    n11_products = n11_raw[0] if isinstance(n11_raw, tuple) else (n11_raw if isinstance(n11_raw, list) else [])
    ty_products  = ty_res  if isinstance(ty_res,  list) else []
    hb_products  = hb_res  if isinstance(hb_res,  list) else []
    amz_products = amz_res if isinstance(amz_res, list) else []

    extra_products = []
    for res in results_raw[4:]:
        if not isinstance(res, Exception) and isinstance(res, list):
            extra_products.extend(res)

    all_products = []
    seen_urls = set()
    for p in ty_products + hb_products + n11_products + amz_products + extra_products:
        url_clean = p.get("url", "").split("?")[0].strip()
        if url_clean:
            if url_clean in seen_urls:
                continue
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
                if category == "GENEL":
                    results = await marketplace_scan(query)
                elif category == "GIDA":
                    from app.comparator import search_n11_direct
                    n11_task = loop.run_in_executor(None, search_n11_direct, query)
                    migros_task = loop.run_in_executor(None, search_migros_proxy, query)
                    carrefour_task = loop.run_in_executor(None, search_carrefoursa, query)
                    (n11_res, _), migros_res, carrefour_res = await asyncio.gather(
                        n11_task, migros_task, carrefour_task
                    )
                    seen = set()
                    for p in carrefour_res + migros_res + n11_res:
                        key = p["url"].split("?")[0]
                        if key not in seen:
                            seen.add(key)
                            results.append(p)
                else:
                    results = await marketplace_scan(query)
            elif mode == "local":
                local_res = await scan_worker(query, category)
                results = [r for r in local_res if r["source"] in LOCAL_SOURCES]
            else:  # hybrid
                if category == "GENEL":
                    results = await marketplace_scan(query)
                elif category == "GIDA":
                    from app.comparator import search_n11_direct
                    n11_task = loop.run_in_executor(None, search_n11_direct, query)
                    migros_task = loop.run_in_executor(None, search_migros_proxy, query)
                    carrefour_task = loop.run_in_executor(None, search_carrefoursa, query)
                    (n11_res, _), migros_res, carrefour_res = await asyncio.gather(
                        n11_task, migros_task, carrefour_task
                    )
                    seen = set()
                    for p in carrefour_res + migros_res + n11_res:
                        key = p["url"].split("?")[0]
                        if key not in seen:
                            seen.add(key)
                            results.append(p)
                else:
                    results = await marketplace_scan(query)
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
