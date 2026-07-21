"""public/sitemap.xml'i app/main.py'deki gercek veri kaynaklarindan
(ALL_STORES_MAP, get_seo_price_terms) yeniden uretir.

Neden ayri script (dinamik /sitemap.xml route yerine): Vercel'de public/
altindaki statik dosyalar bazen Python fonksiyonunu hic calistirmadan
CDN'den dogrudan sunuluyor (bkz. "/" -> public/index.html davranisi) --
bu proje icin route eklemenin gercekten devreye girecegi garanti degil.
Bunun yerine mevcut GitHub Actions + statik-dosya-commit deseniyle
(catalog-crawl.yml, scraper-healthcheck.yml) tutarli sekilde, dosyayi
periyodik olarak yeniden uretip commitliyoruz.

app/main.py'yi dogrudan import ediyoruz (FastAPI app olusturma ve modul
seviyesi veri yapilari agir yan etki yapmiyor -- Supabase/ScrapingBee gibi
dis servislere sadece istek aninda, supabase_enabled() gibi kontrollerin
ardindan baglaniliyor) boylece veri iki yerde ayri ayri tutulup
senkronizasyon hatasina yol acmiyor.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import ALL_STORES_MAP, get_seo_price_terms, _seo_price_slug_map  # noqa: E402
from app.comparator import normalize_turkish_search_query  # noqa: E402
from app.cache import make_cache_key, cache_get_stale  # noqa: E402

STATIC_PAGES = [
    ("index.html", "daily", "1.0"),
    ("hakkinda", "monthly", "0.6"),
    ("gizlilik", "monthly", "0.3"),
    ("iletisim", "monthly", "0.4"),
    ("fiyat-rehberi", "weekly", "0.5"),
    ("oneri", "monthly", "0.3"),
]


def _term_has_live_inventory(term: str) -> bool:
    """app/main.py:price_landing_page'in dondurecegi sonucu ONBELLEKTEN
    (product_cache) kontrol eder -- CANLI TARAMA YAPMAZ.

    2026-07-20'de whitelist 795'ten 3994 terime cikinca (bkz.
    _seo_extract_keyword_sets duzeltmesi), eski surum (her terim icin
    gercek search_products_by_name cagirip canli tarama yapan) GitHub
    Actions'in sabit 6 saatlik is limitine takilip yarida kesildi (hicbir
    terim sitemap'e eklenemeden calisma iptal oldu).

    Artik app/price_term_cache_warmer.py'nin (30 dk'da bir calisan ayri
    cron) doldurdugu product_cache'e (Supabase REST, ~100-300ms/terim)
    bakiyoruz -- canli scraping'in kendisi degil. Bir terim henuz hic
    isitilmamissa (cache'de hic kaydi yoksa) bu turda sitemap'e girmez,
    warmer onu isittiginde bir sonraki haftalik/manuel calistirmada
    otomatik eklenir. Boylece script dakikalar icinde biter."""
    try:
        query = normalize_turkish_search_query(term)
        cache_key = make_cache_key(query, "GENEL")
        products = cache_get_stale(cache_key)
        if not products:
            return False
        real = [p for p in products if isinstance(p, dict) and p.get("title") and p.get("url")]
        return len(real) >= 2
    except Exception as exc:  # noqa: BLE001
        print(f"  envanter kontrolu basarisiz ({term!r}): {exc}", file=sys.stderr)
        return False


def build_sitemap() -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    def add(path: str, changefreq: str, priority: str) -> None:
        lines.append("  <url>")
        lines.append(f"    <loc>https://www.almadan.app/{path}</loc>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")

    for path, freq, prio in STATIC_PAGES:
        add(path, freq, prio)

    for category in ALL_STORES_MAP:
        add(f"kategori/{category}", "weekly", "0.6")

    seen_slugs: set[str] = set()
    for slugs in ALL_STORES_MAP.values():
        for slug in slugs:
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            add(f"magaza/{slug}", "weekly", "0.5")

    try:
        slug_map = _seo_price_slug_map()
        included, skipped = 0, 0
        for slug, term in sorted(slug_map.items()):
            if not _term_has_live_inventory(term):
                skipped += 1
                continue
            add(f"fiyat/{slug}", "monthly", "0.4")
            included += 1
        print(
            f"fiyat/{{terim}}: {included} sayfa envanterli (sitemap'e eklendi), "
            f"{skipped} sayfa envantersiz (atlandi, 404 donerdi).",
            file=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"UYARI: fiyat/{{terim}} sayfalari uretilemedi: {exc}", file=sys.stderr)

    lines.append("</urlset>")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    out_path = ROOT / "public" / "sitemap.xml"
    new_content = build_sitemap()
    old_content = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
    url_count = new_content.count("<loc>")
    if new_content.strip() == old_content.strip():
        print(f"sitemap.xml zaten guncel, degisiklik yok ({url_count} URL).")
        return
    out_path.write_text(new_content, encoding="utf-8")
    print(f"sitemap.xml yeniden uretildi: {url_count} URL ({date.today().isoformat()})")


if __name__ == "__main__":
    main()
