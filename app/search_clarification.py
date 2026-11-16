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
    "ruj": {
        "question": "Hangi marka veya tür ruj arıyorsun?",
        "facets": [
            {"label": "Maybelline", "append": "maybelline"},
            {"label": "MAC", "append": "mac"},
            {"label": "L'Oréal Paris", "append": "loreal"},
            {"label": "Flormar", "append": "flormar"},
            {"label": "Golden Rose", "append": "golden rose"},
            {"label": "Likit Mat Ruj", "append": "likit mat"},
        ],
    },
    "maskara": {
        "question": "Hangi marka maskara arıyorsun?",
        "facets": [
            {"label": "Maybelline Sky High", "append": "maybelline sky high"},
            {"label": "L'Oréal Telescopic", "append": "loreal telescopic"},
            {"label": "Essence", "append": "essence"},
        ],
    },
    "fondoten": {
        "question": "Hangi marka veya formda fondöten arıyorsun?",
        "facets": [
            {"label": "L'Oréal True Match", "append": "loreal true match"},
            {"label": "Maybelline Fit Me", "append": "maybelline fit me"},
            {"label": "Estée Lauder", "append": "estee lauder"},
            {"label": "BB / CC Krem", "append": "bb krem"},
        ],
    },
    "gunes kremi": {
        "question": "Hangi marka güneş kremi arıyorsun?",
        "facets": [
            {"label": "La Roche-Posay", "append": "la roche posay"},
            {"label": "Bioderma", "append": "bioderma"},
            {"label": "Garnier", "append": "garnier"},
            {"label": "Bebek / Çocuk", "append": "bebek"},
        ],
    },
    # MARKET & GIDA
    "aycicek yagi": {
        "question": "Hangi ebatta veya markada ayçiçek yağı arıyorsun?",
        "facets": [
            {"label": "5 Litre", "append": "5 L"},
            {"label": "2 Litre", "append": "2 L"},
            {"label": "1 Litre", "append": "1 L"},
            {"label": "Yudum 5 L", "append": "yudum 5 L"},
            {"label": "Komili 5 L", "append": "komili 5 L"},
        ],
    },
    "yag": {
        "question": "Ne tür ve kaç litre yağ arıyorsun?",
        "facets": [
            {"label": "Ayçiçek Yağı 5 L", "append": "ayçiçek 5 L"},
            {"label": "Ayçiçek Yağı 2 L", "append": "ayçiçek 2 L"},
            {"label": "Sızma Zeytinyağı 2 L", "append": "zeytinyağı 2 L"},
        ],
    },
    "zeytinyagi": {
        "question": "Hangi tür ve ebatta zeytinyağı arıyorsun?",
        "facets": [
            {"label": "Sızma 2 L", "append": "sızma 2 L"},
            {"label": "Riviera 2 L", "append": "riviera 2 L"},
            {"label": "5 Litre Teneke", "append": "5 L"},
        ],
    },
    "sut": {
        "question": "Nasıl bir süt arıyorsun?",
        "facets": [
            {"label": "Tam Yağlı 1 L", "append": "tam yağlı 1 L"},
            {"label": "Yarım Yağlı 1 L", "append": "yarım yağlı 1 L"},
            {"label": "Laktozsuz 1 L", "append": "laktozsuz 1 L"},
            {"label": "Pınar / Sütaş", "append": "sütaş 1 L"},
        ],
    },
    "kahve": {
        "question": "Ne tür kahve arıyorsun?",
        "facets": [
            {"label": "Türk Kahvesi", "append": "türk kahvesi"},
            {"label": "Filtre Kahve", "append": "filtre"},
            {"label": "Granül / Nescafe", "append": "nescafe"},
            {"label": "Çekirdek Kahve", "append": "çekirdek"},
        ],
    },
    "cay": {
        "question": "Hangi gramaj veya markada çay arıyorsun?",
        "facets": [
            {"label": "Çaykur Rize 1 Kg", "append": "çaykur rize 1 kg"},
            {"label": "Çaykur Tiryaki 1 Kg", "append": "çaykur tiryaki 1 kg"},
            {"label": "Demlik Poşet", "append": "demlik poşet"},
        ],
    },
    "deterjan": {
        "question": "Ne tür deterjan arıyorsun?",
        "facets": [
            {"label": "Toz Çamaşır Deterjanı", "append": "toz çamaşır"},
            {"label": "Sıvı Çamaşır Deterjanı", "append": "sıvı çamaşır"},
            {"label": "Bulaşık Makinesi Tableti", "append": "bulaşık tableti"},
        ],
    },
    "bebek bezi": {
        "question": "Hangi marka veya beden bebek bezi arıyorsun?",
        "facets": [
            {"label": "Prima 4 Beden", "append": "prima 4"},
            {"label": "Prima 5 Beden", "append": "prima 5"},
            {"label": "Sleepy 4 Beden", "append": "sleepy 4"},
            {"label": "Molfix", "append": "molfix"},
        ],
    },
    # EV & TEKNOLOJİ EK
    "supurge": {
        "question": "Nasıl bir süpürge arıyorsun?",
        "facets": [
            {"label": "Dikey Şarjlı Süpürge", "append": "dikey şarjlı"},
            {"label": "Robot Süpürge", "append": "robot"},
            {"label": "Toz Torbasız Süpürge", "append": "toz torbasız"},
        ],
    },
    "televizyon": {
        "question": "Hangi ekran boyutunda televizyon arıyorsun?",
        "facets": [
            {"label": "55 İnç 4K", "append": "55 inç 4k"},
            {"label": "65 İnç 4K", "append": "65 inç 4k"},
            {"label": "50 İnç 4K", "append": "50 inç 4k"},
        ],
    },
    "mont": {
        "question": "Kimin için mont arıyorsun?",
        "facets": [
            {"label": "Erkek", "append": "erkek"},
            {"label": "Kadın", "append": "kadın"},
            {"label": "Şişme Mont", "append": "şişme"},
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
