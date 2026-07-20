"""SEO fiyat-terimi sayfalarının (`/fiyat/{slug}`, bkz. app/main.py:price_landing_page)
product_cache'ini arka planda önceden ısıtır.

Neden gerekli: bu sayfalar canlı istekte cache_get() bulamazsa gerçek
zamanlı çoklu mağaza taraması yapar (8s canlı bütçe + stale-cache
fallback). Bir terim DAHA ÖNCE HİÇ taranmamışsa stale fallback de yok
-- canlı tarama 8s'de bitmezse istek (kullanıcı veya Googlebot) gerçek
404 alır. Bir terim en az BİR KEZ başarıyla tarandıktan sonra ise, cache
süresi dolsa bile stale_fallback mekanizması sayesinde 404 riski
pratikte ortadan kalkar (bkz. search_orchestrator.master_search).

Bu yüzden burada amaç sürekli TÜM 795 terimi 6 saatlik TTL içinde taze
tutmak değil (kademeli/GitHub Actions bütçesiyle günler sürer) -- amaç
her terimin en az bir kez ısıtılmış olmasını garanti etmek, TTL sonrası
tazeleme ise bonus. Aynı imleç (cursor) deseni app/catalog_crawler.py
ve app/slow_store_cache_warmer.py ile birebir aynı.
"""
from __future__ import annotations

import asyncio


async def run_price_term_warm_batch(batch_size: int = 6) -> dict:
    from app.storage import load_db, save_db
    from app.comparator import normalize_turkish_search_query, search_products_by_name
    from app.main import get_seo_price_terms

    terms = get_seo_price_terms()
    if not terms:
        return {"processed": 0}

    db = load_db()
    state = db.setdefault("price_term_warmer_state", {"cursor": 0})
    cursor = state.get("cursor", 0) % len(terms)
    batch = [terms[(cursor + i) % len(terms)] for i in range(min(batch_size, len(terms)))]
    state["cursor"] = (cursor + len(batch)) % len(terms)
    db["price_term_warmer_state"] = state
    save_db(db)

    results = []
    for term in batch:
        query = normalize_turkish_search_query(term)
        try:
            products = await asyncio.to_thread(search_products_by_name, query, "general")
        except Exception:
            products = []
        results.append({
            "term": term,
            "count": len(products) if isinstance(products, list) else 0,
        })

    return {
        "processed": len(results),
        "details": results,
        "cursor": state["cursor"],
        "total_terms": len(terms),
        "cycle_progress_pct": round(100.0 * state["cursor"] / len(terms), 1),
    }
