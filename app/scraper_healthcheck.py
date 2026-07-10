"""Proaktif scraper sağlık izleme.

Her gün /cron/refresh-all çalışırken haftanın gününe göre TEK bir
kategorinin mağazaları bilinen bir test sorgusuyla taranır. Bir mağaza
daha önce düzenli sonuç buluyorken art arda birkaç gün 0 sonuç/hata
vermeye başlarsa (site yapısı değişmiş, scraper kırılmış olabilir),
app.notifier üzerinden admin'e (Telegram/e-posta) proaktif uyarı
gönderilir -- kullanıcılar fark etmeden önce.

Vercel Hobby'nin 10s fonksiyon limiti nedeniyle her çalıştırmada TÜM
122+ scraper değil, günde bir kategori test edilir; bu yüzden her
mağaza yaklaşık haftada bir kez kontrol edilmiş olur.
"""
from __future__ import annotations

import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor

_HC_EXECUTOR = ThreadPoolExecutor(max_workers=16)

# Art arda kaç gün 0 sonuç gelirse alarm verilsin (tek seferlik ağ
# hatalarından kaynaklı yanlış alarmları önlemek için >= 2)
_MIN_CONSECUTIVE_ZERO_TO_ALERT = 2
# Bir mağazanın "geçmişte gerçekten çalışıyordu" sayılması için gereken
# en düşük en-iyi sonuç sayısı
_MIN_HISTORY_TO_CARE = 3

_DAILY_PLAN: dict[int, tuple[str, str, list[str]]] = {
    0: ("TEKNOLOJİ", "telefon", [
        "search_mediamarkt", "search_teknosa", "search_vatanbilgisayar",
        "search_itopya", "search_casper", "search_huawei", "search_xiaomi",
        "search_lenovo", "search_asusrog", "search_lg", "search_sony",
        "search_hp", "search_canon", "search_epson", "search_turkcell",
        "search_dsmart",
    ]),
    1: ("MODA", "tişört", [
        "search_yargici", "search_kinetix", "search_flo", "search_lcwaikiki",
        "search_mavi", "search_boyner", "search_zara", "search_hm", "search_bershka",
        "search_colins", "search_ltb", "search_vakko", "search_beymen", "search_sarar",
        "search_twist", "search_penti", "search_pierrecardin", "search_altinyildiz",
        "search_derimod", "search_damattween", "search_shein", "search_modanisa",
        "search_bigjoy", "search_decathlon", "search_nike", "search_adidas",
        "search_puma", "search_reebok", "search_newbalance", "search_sportive",
        "search_lescon", "search_pandora",
    ]),
    2: ("KOZMETİK", "şampuan", [
        "search_gratis", "search_rossmann", "search_watsons", "search_sephora",
        "search_flormar", "search_goldenrose", "search_farmasi",
    ]),
    3: ("EV", "tencere", [
        "search_vivense", "search_evidea", "search_karaca", "search_englishhome",
        "search_madamecoco", "search_koctas", "search_bauhaus", "search_istikbal",
        "search_bellona", "search_dogtas", "search_kelebek", "search_schafer",
        "search_korkmaz", "search_bosch", "search_tefal", "search_arzum",
        "search_fakir", "search_philips",
    ]),
    4: ("GIDA", "süt", [
        "search_bim", "search_sokmarket", "search_tarimkredi",
        "search_metro", "search_bizimtoptan", "search_tazedirekt",
        "search_migros_proxy", "search_carrefoursa",
    ]),
    5: ("BEBEK", "bebek bezi", [
        "search_ebebek", "search_toyzz", "search_bebek", "search_lego", "search_frigg",
    ]),
    6: ("GENEL", "roman", [
        "search_kitapyurdu", "search_dr", "search_remzi", "search_idefix",
        "search_muzikdunyasi", "search_ufukkirtasiye", "search_ofissepeti",
        "search_evpet", "search_petbis", "search_petlebi", "search_zopet",
        "search_proteinocean", "search_supplementler", "search_runnutrition",
        "search_n11_direct", "search_amazon_tr", "search_trendyol_direct",
        "search_hepsiburada_direct", "search_pazarama", "search_aliexpress", "search_temu",
    ]),
}


async def run_daily_healthcheck(weekday: int | None = None, slot: int = 0) -> dict:
    """slot=0: günün normal kategorisi (Vercel'in tek günlük cron'u).
    slot=1: GitHub Actions'tan günde ikinci kez tetiklenen çalıştırma --
    aynı kategoriyi tekrar test etmek yerine BİR SONRAKİ günün kategorisini
    test eder, böylece haftalık tam tur süresi 7 günden ~3.5 güne iner."""
    from app import comparator
    from app import search_orchestrator
    from app.storage import load_db, save_db
    from app.notifier import notify_failure, notify_recovery

    if weekday is None:
        weekday = datetime.datetime.utcnow().weekday()

    plan_day = (weekday + slot) % 7
    category, test_query, fn_names = _DAILY_PLAN[plan_day]

    loop = asyncio.get_running_loop()
    valid_names = []
    tasks = []
    for name in fn_names:
        fn = getattr(comparator, name, None) or getattr(search_orchestrator, name, None)
        if fn is None:
            continue
        valid_names.append(name)
        tasks.append(loop.run_in_executor(_HC_EXECUTOR, fn, test_query))

    try:
        results_raw = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=8.0
        )
    except asyncio.TimeoutError:
        results_raw = []
        for t in tasks:
            if t.done() and not t.cancelled():
                exc = t.exception()
                results_raw.append(exc if exc else t.result())
            else:
                results_raw.append(None)
                t.cancel()

    db = load_db()
    health = db.setdefault("scraper_health", {})

    alerts: list[tuple[str, int, int]] = []
    recoveries: list[str] = []
    report: dict[str, int] = {}

    for name, res in zip(valid_names, results_raw):
        if isinstance(res, tuple):
            res = res[0] if res else []
        if isinstance(res, Exception) or res is None or not isinstance(res, list):
            count = 0
        else:
            count = len(res)
        report[name] = count

        entry = health.setdefault(name, {"consecutive_zero": 0, "best_count": 0, "alerted": False})

        if count > 0:
            entry["best_count"] = max(entry.get("best_count", 0), count)
            if entry.get("alerted"):
                recoveries.append(name)
            entry["consecutive_zero"] = 0
            entry["alerted"] = False
        else:
            entry["consecutive_zero"] = entry.get("consecutive_zero", 0) + 1
            had_history = entry.get("best_count", 0) >= _MIN_HISTORY_TO_CARE
            if (
                had_history
                and entry["consecutive_zero"] >= _MIN_CONSECUTIVE_ZERO_TO_ALERT
                and not entry.get("alerted")
            ):
                alerts.append((name, entry["best_count"], entry["consecutive_zero"]))
                entry["alerted"] = True

    db["scraper_health"] = health
    save_db(db)

    for name, best, streak in alerts:
        notify_failure(
            f"⚠️ {name} scraper'ı {streak} gündür 0 sonuç veriyor "
            f"(önceden ~{best} ürün buluyordu, test sorgusu: '{test_query}', "
            f"kategori: {category}). Site yapısı değişmiş olabilir, kontrol edin.",
            test_name=f"scraper_{name}",
        )
    for name in recoveries:
        notify_recovery(test_name=f"scraper_{name}")

    return {
        "category": category,
        "query": test_query,
        "tested": len(valid_names),
        "alerts_sent": len(alerts),
        "recoveries_sent": len(recoveries),
        "counts": report,
    }
