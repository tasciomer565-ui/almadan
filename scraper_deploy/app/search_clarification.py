"""Belirsiz/genel arama terimleri için daraltma (facet) katmanı.

"tişört", "klavye" gibi tek başına çok geniş kapsamlı sorgular için,
ham sonuç dökmek yerine kullanıcıya birkaç hızlı seçenek (chip) sunup
sorguyu otomatik daraltır. Sadece TAM OLARAK bu listedeki çıplak
terimlerde devreye girer -- "mavi tişört", "nike tişört 42" gibi zaten
ek bilgi taşıyan sorgular ASLA tetiklenmez, ham arama akışı bozulmaz.
"""
from __future__ import annotations

from app.text_utils import normalize_turkish


def _norm(text: str) -> str:
    return normalize_turkish(text).strip()


# terim(ler) (normalize edilmiş) -> facet seçenekleri
# Her seçenek: {"label": kullanıcıya gösterilen, "append": sorguya eklenecek kelime(ler)}
_CLARIFICATIONS: dict[str, dict] = {
    # MODA
    "tisort": {
        "question": "Kimin için tişört arıyorsun?",
        "facets": [
            {"label": "Erkek", "append": "erkek"},
            {"label": "Kadın", "append": "kadın"},
            {"label": "Çocuk", "append": "çocuk"},
        ],
    },
    "pantolon": {
        "question": "Ne tür pantolon arıyorsun?",
        "facets": [
            {"label": "Erkek", "append": "erkek"},
            {"label": "Kadın", "append": "kadın"},
            {"label": "Jean", "append": "jean"},
        ],
    },
    "ayakkabi": {
        "question": "Nasıl bir ayakkabı arıyorsun?",
        "facets": [
            {"label": "Spor Ayakkabı", "append": "spor"},
            {"label": "Erkek", "append": "erkek"},
            {"label": "Kadın", "append": "kadın"},
            {"label": "Çocuk", "append": "çocuk"},
        ],
    },
    "elbise": {
        "question": "Ne tarz bir elbise arıyorsun?",
        "facets": [
            {"label": "Günlük", "append": "günlük"},
            {"label": "Abiye", "append": "abiye"},
            {"label": "Çocuk", "append": "çocuk"},
        ],
    },
    "ceket": {
        "question": "Kimin için ceket arıyorsun?",
        "facets": [
            {"label": "Erkek", "append": "erkek"},
            {"label": "Kadın", "append": "kadın"},
        ],
    },
    "canta": {
        "question": "Ne tür çanta arıyorsun?",
        "facets": [
            {"label": "Sırt Çantası", "append": "sırt"},
            {"label": "Kadın El Çantası", "append": "kadın el"},
            {"label": "Laptop Çantası", "append": "laptop"},
        ],
    },
    # TEKNOLOJİ
    "klavye": {
        "question": "Nasıl bir klavye arıyorsun?",
        "facets": [
            {"label": "Kablosuz", "append": "kablosuz"},
            {"label": "Mekanik", "append": "mekanik"},
            {"label": "Oyuncu", "append": "oyuncu"},
        ],
    },
    "kulaklik": {
        "question": "Nasıl bir kulaklık arıyorsun?",
        "facets": [
            {"label": "Kablosuz", "append": "kablosuz bluetooth"},
            {"label": "Kulak İçi", "append": "kulak içi"},
            {"label": "Kulak Üstü", "append": "kulak üstü"},
        ],
    },
    "telefon": {
        "question": "Hangi marka telefon arıyorsun?",
        "facets": [
            {"label": "iPhone", "append": "iphone"},
            {"label": "Samsung", "append": "samsung"},
            {"label": "Xiaomi", "append": "xiaomi"},
        ],
    },
    "laptop": {
        "question": "Ne için laptop arıyorsun?",
        "facets": [
            {"label": "Oyun", "append": "oyuncu"},
            {"label": "Ofis / Günlük Kullanım", "append": "ofis"},
            {"label": "Öğrenci", "append": "ekonomik"},
        ],
    },
    "kamera": {
        "question": "Nasıl bir kamera arıyorsun?",
        "facets": [
            {"label": "Aksiyon Kamerası", "append": "aksiyon"},
            {"label": "DSLR", "append": "dslr"},
            {"label": "Güvenlik Kamerası", "append": "güvenlik"},
        ],
    },
    # EV
    "tencere": {
        "question": "Nasıl bir tencere arıyorsun?",
        "facets": [
            {"label": "Tencere Seti", "append": "seti"},
            {"label": "Düdüklü", "append": "düdüklü"},
            {"label": "Granit", "append": "granit"},
        ],
    },
    "hali": {
        "question": "Ne tür halı arıyorsun?",
        "facets": [
            {"label": "Salon Halısı", "append": "salon"},
            {"label": "Çocuk Odası Halısı", "append": "çocuk odası"},
            {"label": "Yolluk", "append": "yolluk"},
        ],
    },
    # KOZMETİK
    "sampuan": {
        "question": "Ne için şampuan arıyorsun?",
        "facets": [
            {"label": "Saç Dökülmesine Karşı", "append": "dökülme karşıtı"},
            {"label": "Kepeğe Karşı", "append": "kepek karşıtı"},
            {"label": "Bebek", "append": "bebek"},
        ],
    },
    "parfum": {
        "question": "Kimin için parfüm arıyorsun?",
        "facets": [
            {"label": "Kadın", "append": "kadın"},
            {"label": "Erkek", "append": "erkek"},
            {"label": "Unisex", "append": "unisex"},
        ],
    },
}


def get_clarification(raw_query: str) -> dict | None:
    """Sorgu, listedeki bir terimle TAM olarak eşleşiyorsa (ekstra kelime
    yoksa) facet seçeneklerini döner; aksi halde None (normal akış devam eder)."""
    normalized = _norm(raw_query)
    entry = _CLARIFICATIONS.get(normalized)
    if not entry:
        return None
    return {
        "term": raw_query.strip(),
        "question": entry["question"],
        "options": [
            {"label": f["label"], "query": f"{f['append']} {raw_query.strip()}".strip()}
            for f in entry["facets"]
        ],
    }
