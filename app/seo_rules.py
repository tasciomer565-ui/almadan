"""/fiyat/{terim} SEO sayfalari icin ortak index esigi.

app/main.py:price_landing_page (robots meta) ve scripts/generate_sitemap.py
(sitemap'e girme) AYNI kurali kullanmali -- noindex bir sayfayi sitemap'e
koymak Search Console'da tutarsizlik uyarisi verir. Esik tek yerde durur.

Gecmis: 2026-08-13'te AdSense "dusuk degerli icerik" reddi sonrasi esik
3 magaza / 5 urun yapilmisti; GSC verisinde en cok gosterim alan sayfalarin
~%90'i (nohut, kefir, tefal-kettle...) noindex'e dusup haftalik gosterim
~2.300'den ~1.300'e indi. 2026-09-29'da 2 magaza / 4 urune cekildi: tek
magazali sayfalar (gercek karsilastirma sunmayan) yine noindex kalir.
"""
from __future__ import annotations

MIN_INDEX_STORES = 2
MIN_INDEX_PRODUCTS = 4


def price_page_store_count(products: list[dict]) -> int:
    return len({p.get("source") for p in products if isinstance(p, dict) and p.get("source")})


def is_price_page_indexable(products: list[dict]) -> bool:
    return (
        len(products) >= MIN_INDEX_PRODUCTS
        and price_page_store_count(products) >= MIN_INDEX_STORES
    )
