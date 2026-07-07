"""Veriden öğrenen sorgu tanıma katmanı.

Elle terim ekleme yerine iki mekanizma:

  1. correct_query() — rapidfuzz ile yazım hatası toleranslı düzeltme.
     Sorgudaki her kelime, statik kategori kelime setleri + öğrenilmiş
     kelime dağarcığından oluşan havuzdaki en yakın terimle (yeterince
     yüksek benzerlik skorunda) değiştirilir. Zayıf eşleşmelerde kelime
     olduğu gibi bırakılır (yanlış "düzeltme" riskini önlemek için).

  2. refresh_learned_vocabulary() — günlük cron'da çağrılır; Supabase
     product_cache tablosundaki son taranan GERÇEK ürün başlıklarından
     kelime çıkarıp db["vocabulary"] içine kategori bazlı frekans olarak
     kaydeder. Böylece kapsam elle değil, siteye gelen gerçek envanterle
     birlikte otomatik büyür.

  3. classify_from_learned_vocabulary() — classify_intent() statik
     setlerde eşleşme bulamazsa, öğrenilmiş kelime dağarcığına bakar.
"""
from __future__ import annotations

import re
from collections import Counter

try:
    from rapidfuzz import process, fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

_STOPWORDS = {
    "ve", "ile", "icin", "için", "bir", "bu", "su", "şu", "o", "de", "da",
    "ki", "mi", "mı", "mu", "mü", "en", "cok", "çok", "adet", "set", "takim",
    "takım", "yeni", "orijinal", "marka", "ucuz", "indirimli", "kampanya",
    "fiyat", "fiyatı", "fiyati", "satın", "satin", "al", "alma",
}

_MIN_WORD_LEN = 3
_FUZZY_SCORE_CUTOFF = 84
# Bir kelimenin "öğrenilmiş" sayılıp kullanılması için gereken min. gözlem sayısı
_MIN_LEARNED_COUNT = 3
_MAX_LEARNED_VOCAB_SIZE = 5000


def _normalize_tr(text: str) -> str:
    tr_map = str.maketrans("şğıöüçŞĞİÖÜÇ", "sgioucSGIOUC")
    return text.lower().translate(tr_map)


def _static_vocabulary() -> set[str]:
    """Kategori anahtar kelime setlerinden tek-kelimelik terimler."""
    from app.search_orchestrator import CATEGORY_KEYWORD_SETS
    vocab = set()
    for kw_set in CATEGORY_KEYWORD_SETS.values():
        for term in kw_set:
            if " " not in term and "-" not in term:
                vocab.add(_normalize_tr(term))
    return vocab


def _learned_vocabulary() -> dict[str, str]:
    """db['vocabulary'] içinden {kelime: kategori} — sadece yeterince
    gözlemlenmiş kelimeler."""
    try:
        from app.storage import load_db
        db = load_db()
        vocab = db.get("vocabulary", {})
        return {
            word: info.get("category", "GENEL")
            for word, info in vocab.items()
            if isinstance(info, dict) and info.get("count", 0) >= _MIN_LEARNED_COUNT
        }
    except Exception:
        return {}


def classify_from_learned_vocabulary(q_lower: str, q_normalized: str) -> str | None:
    """classify_intent() statik setlerde eşleşme bulamazsa çağrılır."""
    learned = _learned_vocabulary()
    if not learned:
        return None
    words = set(re.findall(r"\w+", q_normalized))
    votes = Counter()
    for w in words:
        cat = learned.get(w)
        if cat and cat != "GENEL":
            votes[cat] += 1
    if votes:
        return votes.most_common(1)[0][0]
    return None


def correct_query(query: str) -> str:
    """Sorgudaki kelimeleri bilinen kelime dağarcığına göre yazım-hatası
    toleranslı biçimde düzeltir. Zaten bilinen ya da kısa kelimelere
    dokunmaz; sadece iyi bir eşleşme bulunursa değiştirir."""
    if not _RAPIDFUZZ_AVAILABLE or not query or not query.strip():
        return query

    static_vocab = _static_vocabulary()
    learned_vocab = set(_learned_vocabulary().keys())
    full_vocab = static_vocab | learned_vocab
    if not full_vocab:
        return query

    vocab_list = list(full_vocab)
    words = query.split()
    changed = False
    corrected_words = []

    for raw_word in words:
        word_norm = _normalize_tr(raw_word.strip(".,!?;:()[]\"'"))
        if len(word_norm) < _MIN_WORD_LEN or word_norm in _STOPWORDS:
            corrected_words.append(raw_word)
            continue
        if word_norm in full_vocab:
            # zaten bilinen kelime, dokunma
            corrected_words.append(raw_word)
            continue
        match = process.extractOne(
            word_norm, vocab_list, scorer=fuzz.ratio, score_cutoff=_FUZZY_SCORE_CUTOFF
        )
        if match:
            corrected_words.append(match[0])
            changed = True
        else:
            corrected_words.append(raw_word)

    return " ".join(corrected_words) if changed else query


def learn_from_products(products: list[dict], category: str) -> int:
    """Gerçek ürün başlıklarından kelime dağarcığını büyüt. Cache'e her
    yeni sonuç yazıldığında ya da günlük cron'da çağrılabilir.
    Döner: yeni/güncellenen kelime sayısı.
    """
    if not products or not category or category == "GENEL":
        return 0
    try:
        from app.storage import load_db, save_db
    except Exception:
        return 0

    word_counts = Counter()
    for p in products:
        title = p.get("title", "") if isinstance(p, dict) else ""
        if not title:
            continue
        for raw in re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", title.lower()):
            w = _normalize_tr(raw)
            if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS and not w.isdigit():
                word_counts[w] += 1

    if not word_counts:
        return 0

    db = load_db()
    vocab = db.setdefault("vocabulary", {})
    updated = 0
    for word, cnt in word_counts.items():
        entry = vocab.get(word)
        if entry and isinstance(entry, dict):
            entry["count"] = entry.get("count", 0) + cnt
            # Kategori kararsızsa en çok görülen kategoriyi tut
            if entry.get("category") != category and cnt > entry.get("count", 0) / 2:
                entry["category"] = category
        else:
            vocab[word] = {"category": category, "count": cnt}
        updated += 1

    # Kelime dağarcığı sınırsız büyümesin — en düşük frekanslıları buda
    if len(vocab) > _MAX_LEARNED_VOCAB_SIZE:
        sorted_words = sorted(vocab.items(), key=lambda kv: kv[1].get("count", 0), reverse=True)
        db["vocabulary"] = dict(sorted_words[:_MAX_LEARNED_VOCAB_SIZE])
    else:
        db["vocabulary"] = vocab

    save_db(db)
    return updated


async def refresh_learned_vocabulary(sample_size: int = 200) -> dict:
    """Günlük cron: Supabase product_cache'teki en son taranan gerçek
    sonuçlardan kelime dağarcığını büyütür (elle terim eklemeye alternatif,
    envanterle birlikte kendiliğinden ölçeklenir)."""
    from app.cache import SUPABASE_URL, SUPABASE_KEY, CACHE_TABLE, _enabled, _headers
    import requests

    if not _enabled():
        return {"learned_words": 0, "rows_scanned": 0, "reason": "supabase_disabled"}

    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{CACHE_TABLE}"
            f"?select=products,category"
            f"&order=created_at.desc"
            f"&limit={sample_size}"
        )
        resp = requests.get(url, headers=_headers(), timeout=8)
        rows = resp.json() if resp.ok else []
    except Exception as exc:
        return {"learned_words": 0, "rows_scanned": 0, "error": str(exc)}

    total_updated = 0
    for row in rows:
        products = row.get("products") or []
        category = row.get("category") or "GENEL"
        total_updated += learn_from_products(products, category)

    return {"learned_words": total_updated, "rows_scanned": len(rows)}
