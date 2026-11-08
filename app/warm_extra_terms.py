"""Önbellek ısıtmaya eklenen, SEO whitelist'inden bağımsız ek arama terimleri.

`get_seo_price_terms()` rakam içeren terimleri bilerek eler (ör. "iphone 15"),
çünkü o liste /fiyat sayfalarını ve sitemap'i besler. Oysa canlı aramada en çok
sorulan şeyler tam olarak model düzeyinde sorgulardır ve önbellekte karşılığı
yoksa Render IP'sinden yalnızca Amazon döner. Bu liste ısıtma betiğinin
(scripts/warm_price_cache.py) yanında bu terimleri de taramasını sağlar; SEO
sayfalarını/sitemap'i etkilemez.

İki kaynak: (1) elle seçilmiş popüler model sorguları, (2) marka rehberindeki
(app/brands.py) her markanın kendi adı -- /marka/{slug} sayfalarını besleyen
price_history kayıtları da buradan dolar.
"""
from __future__ import annotations

from app.brands import BRANDS

POPULAR_MODEL_TERMS: tuple[str, ...] = (
    # Telefon
    "iphone 15", "iphone 15 pro", "iphone 16", "iphone 14", "iphone 13",
    "samsung galaxy s24", "samsung galaxy s25", "samsung galaxy a55",
    "samsung galaxy a35", "samsung galaxy a15", "xiaomi redmi note 13",
    "xiaomi redmi 13c", "poco x6 pro", "xiaomi 14t",
    # Bilgisayar / tablet
    "macbook air m2", "macbook air m3", "macbook pro m3", "ipad 10 nesil",
    "ipad air", "lenovo ideapad 3", "asus vivobook 15", "hp 250 g9",
    "monster abra a5", "casper nirvana",
    # Ses / giyilebilir / oyun
    "airpods pro 2", "airpods 4", "apple watch se", "apple watch series 9",
    "samsung galaxy buds", "jbl flip 6", "sony wh-1000xm5",
    "playstation 5", "ps5 dualsense", "nintendo switch",
    # TV / beyaz eşya / küçük ev aletleri
    "samsung 55 inç tv", "lg 55 inç oled", "vestel 50 inç tv",
    "philips airfryer", "dyson v15", "roborock s8", "xiaomi robot süpürge",
    "arçelik 9 kg çamaşır makinesi", "beko buzdolabı", "bosch bulaşık makinesi",
    # Market
    "pınar süt 1 lt", "ülker çikolata", "eti browni", "nescafe 3ü1 arada",
    "ariel 5 kg", "persil jel", "omo sıvı deterjan", "sana tuvalet kağıdı",
    # Moda
    "nike air max", "nike air force 1", "adidas samba", "adidas superstar",
    "puma suede", "new balance 574",
    # Kozmetik
    "loreal şampuan", "nivea krem", "garnier saç boyası", "eucerin güneş kremi",
)


def extra_warm_terms() -> list[str]:
    """Tekrarsız, sıralı ek ısıtma terimleri: önce model sorguları, sonra marka adları."""
    seen: set[str] = set()
    out: list[str] = []
    for term in (*POPULAR_MODEL_TERMS, *(m["name"].lower() for m in BRANDS.values())):
        key = " ".join(term.split())
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out
