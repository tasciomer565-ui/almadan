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

STATIC_PAGES = [
    ("index.html", "daily", "1.0"),
    ("hakkinda", "monthly", "0.6"),
    ("gizlilik", "monthly", "0.3"),
    ("iletisim", "monthly", "0.4"),
    ("fiyat-rehberi", "weekly", "0.5"),
    ("oneri", "monthly", "0.3"),
]


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
        price_slugs = sorted(_seo_price_slug_map().keys())
        for slug in price_slugs:
            add(f"fiyat/{slug}", "monthly", "0.4")
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
