"""Marka veri modeli ve "aynı ürün farklı isimle" eşleştirme.

İki bağımsız parça:

1. Marka rehberi (`BRANDS`, `extract_brand`): ürün başlığından marka çıkarır,
   /marka/{slug} SEO sayfalarının veri kaynağıdır.
2. Ürün eşleştirme (`product_signature`, `same_product_score`,
   `group_same_products`): farklı mağazalarda farklı yazılmış başlıkların
   (örn. "Samsung Galaxy S24 256 GB" / "GALAXY S24 256GB Samsung") aynı ürün
   olup olmadığına karar verir. Marka, model kodu ve ölçü (GB, ml, kg ...)
   uyuşmazlığı kesin red sebebidir; bunlar uyuştuktan sonra metin benzerliği
   (FuzzyMatcher) bakılır. Bu sayede "S24" ile "S24 Ultra" veya 128 GB ile
   256 GB yanlışlıkla birleştirilmez.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.matching_engine import FuzzyMatcher
from app.text_utils import normalize_turkish

# ── Marka rehberi ────────────────────────────────────────────
# slug -> (görünen ad, iç kategori anahtarı [ALL_STORES_MAP], takma adlar, açıklama)
# Takma adlar normalize (küçük harf, ASCII) yazılır.
_BRAND_DEFS: list[tuple[str, str, str, tuple[str, ...], str]] = [
    ("apple", "Apple", "tech", ("apple", "iphone", "ipad", "macbook", "airpods"),
     "iPhone, iPad, MacBook ve AirPods fiyatlarını mağazalar arasında karşılaştır."),
    ("samsung", "Samsung", "tech", ("samsung", "galaxy"),
     "Samsung Galaxy telefon, televizyon ve beyaz eşya fiyatlarını karşılaştır."),
    ("xiaomi", "Xiaomi", "tech", ("xiaomi", "redmi", "poco"),
     "Xiaomi, Redmi ve POCO ürünlerinde en uygun fiyatı bul."),
    ("lenovo", "Lenovo", "tech", ("lenovo", "thinkpad", "ideapad", "legion"),
     "Lenovo dizüstü bilgisayar ve aksesuar fiyatlarını karşılaştır."),
    ("asus", "ASUS", "tech", ("asus", "rog", "zenbook", "vivobook"),
     "ASUS dizüstü, ekran kartı ve anakart fiyatlarını karşılaştır."),
    ("hp", "HP", "tech", ("hp", "hewlett packard", "pavilion", "omen"),
     "HP bilgisayar ve yazıcı fiyatlarını karşılaştır."),
    ("sony", "Sony", "tech", ("sony", "playstation", "bravia"),
     "Sony televizyon, kulaklık ve PlayStation fiyatlarını karşılaştır."),
    ("lg", "LG", "tech", ("lg",),
     "LG televizyon, monitör ve beyaz eşya fiyatlarını karşılaştır."),
    ("philips", "Philips", "home", ("philips",),
     "Philips küçük ev aletleri ve kişisel bakım ürünlerini karşılaştır."),
    ("arcelik", "Arçelik", "home", ("arcelik",),
     "Arçelik beyaz eşya ve küçük ev aletleri fiyatlarını karşılaştır."),
    ("beko", "Beko", "home", ("beko",),
     "Beko buzdolabı, çamaşır makinesi ve ankastre fiyatlarını karşılaştır."),
    ("vestel", "Vestel", "home", ("vestel",),
     "Vestel televizyon ve beyaz eşya fiyatlarını karşılaştır."),
    ("bosch", "Bosch", "home", ("bosch",),
     "Bosch beyaz eşya ve el aletleri fiyatlarını karşılaştır."),
    ("nike", "Nike", "fashion", ("nike",),
     "Nike ayakkabı ve spor giyim fiyatlarını karşılaştır."),
    ("adidas", "Adidas", "fashion", ("adidas",),
     "Adidas ayakkabı ve spor giyim fiyatlarını karşılaştır."),
    ("puma", "Puma", "fashion", ("puma",),
     "Puma ayakkabı ve spor giyim fiyatlarını karşılaştır."),
    ("loreal", "L'Oréal", "beauty", ("loreal", "l'oreal"),
     "L'Oréal saç ve cilt bakım ürünlerini karşılaştır."),
    ("nivea", "Nivea", "beauty", ("nivea",),
     "Nivea cilt bakımı ürünlerinde en uygun fiyatı bul."),
    ("garnier", "Garnier", "beauty", ("garnier",),
     "Garnier saç ve cilt bakım ürünlerini karşılaştır."),
    ("pinar", "Pınar", "market", ("pinar",),
     "Pınar süt, yoğurt ve şarküteri ürünlerinin market fiyatlarını karşılaştır."),
    ("ulker", "Ülker", "market", ("ulker",),
     "Ülker çikolata ve bisküvi ürünlerinin market fiyatlarını karşılaştır."),
    ("eti", "Eti", "market", ("eti",),
     "Eti bisküvi ve atıştırmalık ürünlerinin market fiyatlarını karşılaştır."),
    ("ariel", "Ariel", "market", ("ariel",),
     "Ariel deterjan fiyatlarını marketler arasında karşılaştır."),
    ("persil", "Persil", "market", ("persil",),
     "Persil deterjan fiyatlarını marketler arasında karşılaştır."),
    ("nescafe", "Nescafé", "market", ("nescafe",),
     "Nescafé kahve ürünlerinin market fiyatlarını karşılaştır."),
]

BRANDS: dict[str, dict[str, Any]] = {
    slug: {"name": name, "category": category, "aliases": aliases, "description": desc}
    for slug, name, category, aliases, desc in _BRAND_DEFS
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_turkish(text or "")).strip()


# Takma ad -> slug; uzun takma adlar önce denensin diye uzunluğa göre sıralı.
_ALIAS_INDEX: list[tuple[re.Pattern[str], str]] = sorted(
    (
        (re.compile(rf"(?<![a-z0-9]){re.escape(_norm(alias))}(?![a-z0-9])"), slug)
        for slug, meta in BRANDS.items()
        for alias in meta["aliases"]
    ),
    key=lambda item: -len(item[0].pattern),
)

# Marka rehberinde "iphone" gibi alt-marka takma adı, başlıkta marka adı
# yazmasa da markayı belirler. Başlıkta iki farklı marka geçerse (aksesuar
# ürünleri: "iPhone 15 Samsung şarj aleti") ilk geçen kazanır.


def extract_brand(title: str) -> str | None:
    """Başlıktaki markanın slug'ını döner; tanınmıyorsa None."""
    text = _norm(title)
    if not text:
        return None
    best: tuple[int, str] | None = None
    for pattern, slug in _ALIAS_INDEX:
        m = pattern.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), slug)
    return best[1] if best else None


def get_brand(slug: str) -> dict[str, Any] | None:
    meta = BRANDS.get((slug or "").lower())
    return {"slug": slug.lower(), **meta} if meta else None


def brands_for_category(category: str) -> list[dict[str, Any]]:
    return [
        {"slug": slug, **meta}
        for slug, meta in BRANDS.items()
        if meta["category"] == category
    ]


# ── Ürün imzası ──────────────────────────────────────────────

# Ölçü birimi -> (kanonik birim, çarpan). Hacim ml'e, ağırlık g'a, bellek GB'a.
_UNIT_CANON = {
    "gb": ("gb", 1.0), "tb": ("gb", 1024.0), "mb": ("gb", 1 / 1024),
    "ml": ("ml", 1.0), "cl": ("ml", 10.0), "l": ("ml", 1000.0), "lt": ("ml", 1000.0),
    "g": ("g", 1.0), "gr": ("g", 1.0), "kg": ("g", 1000.0),
    "mah": ("mah", 1.0), "w": ("w", 1.0),
    "inc": ("inch", 1.0), "inch": ("inch", 1.0), "cm": ("cm", 1.0),
}
_SPEC_RE = re.compile(
    r"(?<![a-z0-9])(\d{1,5}(?:[.,]\d{1,2})?)\s*(gb|tb|mb|ml|cl|lt|l|kg|gr|g|mah|w|inch|inc|cm)(?![a-z])"
)
# Marka dışı model kodu: hem harf hem rakam içeren belirteç (s24, a15, 65uq8000).
_MODEL_RE = re.compile(r"(?<![a-z0-9])(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)*(?![a-z0-9])")
# Model kodu sayılmayacak belirteçler (ölçü: 256gb, 5g, 4k, 1lt ...).
_NOT_MODEL_RE = re.compile(r"^\d+(?:gb|tb|mb|ml|cl|lt|l|kg|gr|g|mah|w|inch|inc|cm|k|x|li|lu)$")
# Anlam ayıran varyant kelimeleri: biri diğerinde yoksa farklı üründür.
_VARIANT_WORDS = frozenset({
    "pro", "max", "ultra", "plus", "mini", "lite", "fe", "air", "se",
    "zero", "diet", "light", "laktozsuz", "sekersiz", "yagsiz",
})


@dataclass(frozen=True)
class ProductSignature:
    brand: str | None
    models: frozenset[str] = field(default_factory=frozenset)
    specs: frozenset[tuple[str, float]] = field(default_factory=frozenset)
    variants: frozenset[str] = field(default_factory=frozenset)


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", "."))


def product_signature(title: str) -> ProductSignature:
    text = _norm(title)
    specs: set[tuple[str, float]] = set()
    for num, unit in _SPEC_RE.findall(text):
        canon, factor = _UNIT_CANON[unit]
        specs.add((canon, round(_parse_number(num) * factor, 3)))
    stripped = _SPEC_RE.sub(" ", text)
    models = {
        m for m in _MODEL_RE.findall(stripped) if not _NOT_MODEL_RE.match(m)
    }
    words = set(re.findall(r"[a-z]+", stripped))
    return ProductSignature(
        brand=extract_brand(title),
        models=frozenset(models),
        specs=frozenset(specs),
        variants=frozenset(words & _VARIANT_WORDS),
    )


# ── Eşleştirme ───────────────────────────────────────────────

_matcher = FuzzyMatcher()
SAME_PRODUCT_THRESHOLD = 0.6


def _specs_conflict(a: ProductSignature, b: ProductSignature) -> bool:
    """Aynı ölçü türü iki tarafta da varsa değerleri birebir uymalı."""
    kinds_a = {kind: set() for kind, _ in a.specs}
    kinds_b = {kind: set() for kind, _ in b.specs}
    for kind, val in a.specs:
        kinds_a[kind].add(val)
    for kind, val in b.specs:
        kinds_b[kind].add(val)
    return any(kinds_a[k] != kinds_b[k] for k in kinds_a.keys() & kinds_b.keys())


def same_product_score(title_a: str, title_b: str) -> float:
    """İki başlığın aynı ürün olma skoru (0–1). Kesin uyuşmazlıkta 0.0."""
    sig_a, sig_b = product_signature(title_a), product_signature(title_b)

    if sig_a.brand and sig_b.brand and sig_a.brand != sig_b.brand:
        return 0.0
    if _specs_conflict(sig_a, sig_b):
        return 0.0
    # Model kodları iki tarafta da varsa en az biri ortak olmalı ve kümeler
    # birbirini kapsamalı ("s24" vs "s24" tamam; "s24" vs "s23" red).
    if sig_a.models and sig_b.models:
        if not (sig_a.models <= sig_b.models or sig_b.models <= sig_a.models):
            return 0.0
    if sig_a.variants != sig_b.variants:
        return 0.0

    # Ölçüler yukarıda birebir doğrulandı; metin benzerliğini ölçüsüz
    # çekirdek başlık üzerinden hesapla ("256 GB" / "256GB" yazım farkı skoru bozmasın).
    core_a = _SPEC_RE.sub(" ", _norm(title_a))
    core_b = _SPEC_RE.sub(" ", _norm(title_b))
    score = _matcher.score(core_a, core_b)
    # Aynı model kodu güçlü kanıt: sırası/yazımı farklı başlıklarda skoru yükselt.
    if sig_a.models and sig_b.models and sig_a.models & sig_b.models:
        score = min(1.0, score + 0.15)
    # Aynı marka + aynı ölçü küçük bir güven artışıdır.
    if sig_a.brand and sig_a.brand == sig_b.brand:
        score = min(1.0, score + 0.05)
    return round(score, 4)


def are_same_product(title_a: str, title_b: str, threshold: float = SAME_PRODUCT_THRESHOLD) -> bool:
    return same_product_score(title_a, title_b) >= threshold


def group_same_products(
    items: Iterable[dict[str, Any]],
    title_key: str = "title",
    threshold: float = SAME_PRODUCT_THRESHOLD,
) -> list[list[dict[str, Any]]]:
    """Ürün sözlüklerini aynı ürün kümelerine ayırır (açgözlü, ilk-uyan küme).

    Küme temsilcisi ilk eleman başlığıdır; girdi sırası korunur. Aynı mağazanın
    iki ürünü de aynı kümeye girebilir -- mağaza ayrımı çağıran tarafın işi.
    """
    groups: list[list[dict[str, Any]]] = []
    for item in items:
        title = str(item.get(title_key) or "")
        placed = False
        for group in groups:
            if are_same_product(str(group[0].get(title_key) or ""), title, threshold):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    return groups


# ── Marka sayfası ürün özeti ─────────────────────────────────

def summarize_brand_products(
    rows: Iterable[dict[str, Any]],
    slug: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """price_history satırlarından (yeniden eskiye sıralı) marka ürün özeti çıkarır.

    Her ürün anahtarının en güncel fiyatı alınır, markaya ait olanlar süzülür,
    farklı mağazalardaki aynı ürünler `group_same_products` ile tek satırda
    toplanır. Dönen her öğe: title, min_price, min_source, store_count, offers
    (mağaza başına en ucuz teklif). Çok mağazada bulunan ürünler önce gelir.
    """
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key, price, title = row.get("product_key"), row.get("price"), row.get("title")
        if not key or not title or price is None or key in latest:
            continue
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        if price_f <= 0 or extract_brand(title) != slug:
            continue
        latest[key] = {"title": title, "price": price_f, "source": row.get("source") or "", "url": row.get("url") or ""}

    result = []
    for group in group_same_products(latest.values()):
        by_source: dict[str, dict[str, Any]] = {}
        for item in group:
            cur = by_source.get(item["source"])
            if cur is None or item["price"] < cur["price"]:
                by_source[item["source"]] = item
        offers = sorted(by_source.values(), key=lambda o: o["price"])
        best = offers[0]
        result.append({
            "title": best["title"],
            "min_price": best["price"],
            "min_source": best["source"],
            "store_count": len(offers),
            "offers": offers,
        })
    result.sort(key=lambda g: (-g["store_count"], g["min_price"]))
    return result[:limit]
