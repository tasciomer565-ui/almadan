"""Proaktif "popüler ürün" kelime dağarcığı crawler'ı.

Kullanıcı aramasını beklemeden, kategori başına düzenlenmiş popüler
arama terimi listesini (marka + ürün tipi kombinasyonları) mevcut
scraper altyapısı (marketplace_scan) üzerinden tarar ve gerçek ürün
başlıklarından kelime dağarcığını büyütür (app/query_intelligence.py).

Engellenme riskini azaltmak için:
  - Kademeli ramp: başlangıçtan (_LAUNCH_DATE) itibaren geçen gün sayısına
    göre günlük sorgu bütçesi kademeli artar (hafta 1: ~100 sorgu/gün,
    3. haftadan itibaren ~700 sorgu/gün → hedef ~100.000 kelime gözlemi/gün).
  - Sık ama küçük parçalar halinde çalışır (her cron çağrısında az sayıda
    sorgu), Vercel'in fonksiyon süre limitini aşmaz.
  - Sorgular arasında bekleme uygulanır, tüm mağazalara aynı anda yüklenmez.
  - Bir mağaza art arda 0 sonuç vermeye başlarsa (olası engellenme),
    app/scraper_healthcheck.py zaten bunu admin'e Telegram/e-posta ile
    bildiriyor — bu crawl aynı mağaza fonksiyonlarını kullandığı için
    o alarm sistemi burayı da kapsıyor.
"""
from __future__ import annotations

import asyncio
import datetime

_LAUNCH_DATE = datetime.date(2026, 7, 7)

# (gün eşiği, günlük sorgu bütçesi) — kademeli artış
_RAMP_SCHEDULE = [
    (0, 100),   # 0-6. gün
    (7, 250),   # 7-13. gün
    (14, 450),  # 14-20. gün
    (21, 700),  # 21+. gün (~100.000+ kelime gözlemi/gün)
]

_INVOCATIONS_PER_DAY = 48  # her 30 dakikada bir cron
_PER_QUERY_DELAY_SECONDS = 1.5

_POPULAR_QUERIES: dict[str, list[str]] = {
    "GIDA": [
        "süt", "yoğurt", "peynir", "tavuk", "kıyma", "makarna", "pirinç",
        "zeytinyağı", "ayçiçek yağı", "şeker", "çay", "kahve", "ekmek",
        "yumurta", "un", "bulgur", "mercimek", "sabun", "şampuan", "deterjan",
        "bebek bezi", "bebek maması", "meyve suyu", "kola", "çikolata",
        "bisküvi", "salça", "ketçap", "mayonez", "tuvalet kağıdı",
    ],
    "TEKNOLOJİ": [
        "iphone", "samsung telefon", "xiaomi telefon", "laptop", "macbook",
        "kulaklık", "airpods", "klavye", "mouse", "monitör", "tablet",
        "powerbank", "şarj aleti", "akıllı saat", "televizyon", "soundbar",
        "ssd", "harici disk", "oyuncu bilgisayarı", "yazıcı", "webcam",
        "router", "modem", "drone", "kamera", "playstation", "xbox",
    ],
    "MODA": [
        "tişört", "gömlek", "pantolon", "jean", "elbise", "ceket", "mont",
        "ayakkabı", "spor ayakkabı", "bot", "çanta", "sırt çantası",
        "kazak", "hırka", "şort", "etek", "mayo", "iç çamaşır", "çorap",
        "kemer", "gözlük", "saat", "atkı", "bere", "eldiven", "terlik",
    ],
    "KOZMETİK": [
        "parfüm", "ruj", "fondöten", "maskara", "far", "oje", "şampuan",
        "saç boyası", "krem", "nemlendirici", "serum", "güneş kremi",
        "deodorant", "tıraş köpüğü", "diş macunu", "sabun", "el kremi",
        "makyaj fırçası", "gölgelik",
    ],
    "EV": [
        "tencere", "tava", "bıçak seti", "blender", "mikser", "kahve makinesi",
        "elektrikli süpürge", "robot süpürge", "ütü", "nevresim takımı",
        "yastık", "battaniye", "halı", "perde", "koltuk", "sandalye", "masa",
        "avize", "lamba", "dolap", "havlu", "bornoz",
    ],
}


def _days_since_launch() -> int:
    return max(0, (datetime.date.today() - _LAUNCH_DATE).days)


def _daily_query_budget() -> int:
    days = _days_since_launch()
    budget = _RAMP_SCHEDULE[0][1]
    for threshold, value in _RAMP_SCHEDULE:
        if days >= threshold:
            budget = value
    return budget


def _queries_per_invocation() -> int:
    return max(1, round(_daily_query_budget() / _INVOCATIONS_PER_DAY))


def _all_queries() -> list[tuple[str, str]]:
    flat = []
    for category, terms in _POPULAR_QUERIES.items():
        for term in terms:
            flat.append((category, term))
    return flat


async def run_catalog_batch() -> dict:
    from app.storage import load_db, save_db
    from app.search_orchestrator import marketplace_scan
    from app.query_intelligence import learn_from_products

    all_queries = _all_queries()
    if not all_queries:
        return {"processed": 0}

    db = load_db()
    state = db.setdefault("catalog_crawler_state", {"cursor": 0})
    n = _queries_per_invocation()
    cursor = state.get("cursor", 0) % len(all_queries)

    batch = [all_queries[(cursor + i) % len(all_queries)] for i in range(n)]
    state["cursor"] = (cursor + n) % len(all_queries)
    db["catalog_crawler_state"] = state
    save_db(db)

    total_words = 0
    total_products = 0
    per_query_counts: dict[str, int] = {}

    for category, query in batch:
        try:
            products = await marketplace_scan(query, forced_category=category)
        except Exception:
            products = []
        if products:
            total_words += learn_from_products(products, category)
            total_products += len(products)
        per_query_counts[query] = len(products) if products else 0
        # Mağazalara nazik davranmak için sorgular arasında bekleme
        await asyncio.sleep(_PER_QUERY_DELAY_SECONDS)

    return {
        "day_index": _days_since_launch(),
        "daily_budget": _daily_query_budget(),
        "queries_this_run": len(batch),
        "total_products_seen": total_products,
        "total_words_updated": total_words,
        "cursor": state["cursor"],
    }
