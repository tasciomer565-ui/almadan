"""Yavaş (ScrapingBee render_js=True) mağazaları canlı aramanın 7 saniyelik
bütçesinden bağımsız, arka planda önceden tarayıp cache'e yazar.

Neden gerekli: render_js=True istekleri 10-20s sürebiliyor. Bunları canlı
aramadaki (marketplace_scan) diğer hızlı scraper'larla aynı 7s bütçeye
sokarsak, neredeyse hiç zamanında bitmiyorlar (tutarsız/genelde boş sonuç).
Bu modül onun yerine popüler sorgular için bu mağazaları ayrı, uzun süreli
(Vercel Hobby artık 60s'e kadar izin veriyor, bkz. vercel.json maxDuration)
bir cron içinde tarar ve product_cache'e yazar — böylece canlı arama,
cache_get() üzerinden bu sonuçları anında (0 gecikmeyle) bulur.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

_WARM_EXECUTOR = ThreadPoolExecutor(max_workers=8)

# category -> [(fonksiyon_adı, kaynak_adı), ...] — comparator.py'de tanımlı
_SLOW_JS_STORES: dict[str, list[str]] = {
    "KOZMETİK": [
        "search_gratis", "search_watsons", "search_sephora",
        "search_goldenrose", "search_farmasi",
    ],
    "BEBEK": [
        "search_toyzz", "search_bebek",
    ],
    "EV": [
        "search_koctas", "search_bauhaus", "search_korkmaz", "search_bosch",
        "search_istikbal", "search_madamecoco", "search_philips",
    ],
    "TEKNOLOJİ": [
        "search_huawei", "search_xiaomi", "search_lenovo", "search_asusrog",
        "search_sony", "search_hp", "search_canon", "search_epson", "search_dsmart",
    ],
    "MODA": [
        "search_boyner", "search_hm", "search_bershka", "search_vakko",
        "search_twist", "search_penti", "search_derimod", "search_damattween",
        "search_decathlon", "search_adidas", "search_puma", "search_newbalance",
        "search_sportive", "search_lescon", "search_pandora",
    ],
    "GENEL": [
        "search_idefix", "search_petlebi",
    ],
}

# Kategori başına ısıtılacak popüler sorgular (catalog_crawler.py'deki
# listeyle aynı ruhta, kısıtlı tutuldu — her sorgu ayrı bir cache satırı)
_WARM_QUERIES: dict[str, list[str]] = {
    "KOZMETİK": [
        "ruj", "maskara", "fondöten", "parfüm", "şampuan", "krem", "oje",
    ],
    "BEBEK": [
        "bebek bezi", "bebek maması", "oyuncak", "emzik", "bebek arabası",
    ],
    "EV": [
        "tencere", "boya", "matkap", "çamaşır makinesi", "koltuk",
    ],
    "TEKNOLOJİ": [
        "telefon", "laptop", "televizyon", "yazıcı", "kamera",
    ],
    "MODA": [
        "tişört", "pantolon", "elbise", "ayakkabı", "ceket",
    ],
    "GENEL": [
        "roman", "kedi maması", "köpek maması",
    ],
}


async def warm_slow_stores(max_calls: int = 2, per_call_timeout: float = 20.0) -> dict:
    """Bir sonraki sırada bekleyen (kategori, sorgu, mağaza) üçlülerinden
    en fazla max_calls kadarını işler, cache'e yazar. İlerleme db'de
    saklanan bir imleçle takip edilir (her çağrı kaldığı yerden devam eder)."""
    from app import comparator
    from app.storage import load_db, save_db
    from app.cache import make_cache_key, cache_get, cache_set

    # (kategori, sorgu, fonksiyon_adı) düz listesi
    jobs: list[tuple[str, str, str]] = []
    for category, fn_names in _SLOW_JS_STORES.items():
        for query in _WARM_QUERIES.get(category, []):
            for fn_name in fn_names:
                jobs.append((category, query, fn_name))

    if not jobs:
        return {"processed": 0}

    db = load_db()
    state = db.setdefault("slow_store_warmer_state", {"cursor": 0})
    cursor = state.get("cursor", 0) % len(jobs)
    batch = [jobs[(cursor + i) % len(jobs)] for i in range(min(max_calls, len(jobs)))]
    state["cursor"] = (cursor + len(batch)) % len(jobs)
    db["slow_store_warmer_state"] = state
    save_db(db)

    loop = asyncio.get_running_loop()
    processed = []
    for category, query, fn_name in batch:
        fn = getattr(comparator, fn_name, None)
        if fn is None:
            continue
        try:
            new_products = await asyncio.wait_for(
                loop.run_in_executor(_WARM_EXECUTOR, fn, query),
                timeout=per_call_timeout,
            )
        except Exception:
            new_products = []
        if not isinstance(new_products, list):
            new_products = []

        cache_key = make_cache_key(query, category)
        existing = cache_get(cache_key, query=query, category=category) or []
        existing = [p for p in existing if isinstance(p, dict) and p.get("title")]
        # Bu mağazanın eski sonuçlarını çıkar, yenileriyle değiştir
        source_name = fn_name.replace("search_", "")
        existing = [p for p in existing if p.get("source") != source_name]
        merged = existing + new_products
        if merged:
            cache_set(cache_key, query, category, merged)

        processed.append({
            "category": category, "query": query, "store": source_name,
            "new_results": len(new_products),
        })

    return {"processed": len(processed), "details": processed, "cursor": state["cursor"]}


async def background_warm_query(query: str, category: str) -> None:
    """Arka planda (FastAPI Background Task) belirtilen sorgu için 
    yavaş çalışan mağazaları paralel tarar ve cache'e ekler."""
    from app import comparator
    from app.cache import make_cache_key, cache_get, cache_set
    
    cat_upper = category.upper()
    if cat_upper == "GENERAL":
        cat_upper = "GENEL"
    elif cat_upper == "GROCERY":
        cat_upper = "GIDA"
    elif cat_upper == "ELECTRONICS":
        cat_upper = "TEKNOLOJİ"
    elif cat_upper == "COSMETICS":
        cat_upper = "KOZMETİK"
    elif cat_upper == "FASHION":
        cat_upper = "MODA"
    elif cat_upper == "HOME":
        cat_upper = "EV"
        
    fn_names = _SLOW_JS_STORES.get(cat_upper)
    if not fn_names:
        return
        
    loop = asyncio.get_running_loop()
    tasks = []
    
    for fn_name in fn_names:
        fn = getattr(comparator, fn_name, None)
        if fn:
            tasks.append(
                asyncio.wait_for(
                    loop.run_in_executor(_WARM_EXECUTOR, fn, query),
                    timeout=25.0
                )
            )
            
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    new_products = []
    for res in results:
        if isinstance(res, list):
            new_products.extend([p for p in res if isinstance(p, dict) and p.get("title")])
            
    if not new_products:
        return
        
    cache_key = make_cache_key(query, cat_upper)
    existing = cache_get(cache_key, query=query, category=cat_upper) or []
    existing = [p for p in existing if isinstance(p, dict) and p.get("title")]
    
    new_sources = {p["source"] for p in new_products}
    existing = [p for p in existing if p.get("source") not in new_sources]
    
    merged = existing + new_products
    cache_set(cache_key, query, cat_upper, merged)
