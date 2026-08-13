"""Veriden öğrenen sorgu tanıma katmanı.

Elle terim ekleme yerine üç mekanizma:

  1. correct_query() — rapidfuzz ile yazım hatası toleranslı düzeltme.
     Sorgudaki her kelime, statik kategori kelime setleri + öğrenilmiş
     kelime dağarcığından oluşan havuzdaki en yakın terimle (yeterince
     yüksek benzerlik skorunda) değiştirilir. Zayıf eşleşmelerde kelime
     olduğu gibi bırakılır (yanlış "düzeltme" riskini önlemek için).

  2. learn_from_products() / refresh_learned_vocabulary() — günlük cron
     ve katalog crawler'ında çağrılır; gerçek ürün başlıklarından kelime
     çıkarıp app/vocabulary_store.py üzerinden AYRI bir Supabase tablosuna
     (app_state blob'undan bağımsız, atomik sayaç artırma ile) kaydeder.
     Böylece kapsam elle değil, siteye gelen gerçek envanterle birlikte
     otomatik büyür.

  3. classify_from_learned_vocabulary() — classify_intent() statik
     setlerde eşleşme bulamazsa, öğrenilmiş kelime dağarcığına bakar.

Öğrenilmiş kelime dağarcığı, arama başına Supabase'e gitmemek için
process içi kısa süreli önbelleğe alınır (bkz. _VOCAB_CACHE_TTL).
"""
from __future__ import annotations

import re
import time
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
# Process içi önbellek — her arama isteğinde Supabase'e gitmemek için
_VOCAB_CACHE_TTL = 600  # saniye
_vocab_cache: dict[str, str] = {}
_vocab_cache_ts: float = 0.0


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
    """{kelime: kategori} — ayrı vocabulary tablosundan, process içi
    önbellekle (10 dk TTL) okunur."""
    global _vocab_cache, _vocab_cache_ts
    now = time.monotonic()
    if _vocab_cache and (now - _vocab_cache_ts) < _VOCAB_CACHE_TTL:
        return _vocab_cache
    try:
        from app.vocabulary_store import fetch_learned_vocabulary
        _vocab_cache = fetch_learned_vocabulary(min_count=_MIN_LEARNED_COUNT)
        _vocab_cache_ts = now
    except Exception:
        pass
    return _vocab_cache


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
    """Gerçek ürün başlıklarından kelime dağarcığını büyüt. Tek bir toplu
    (batch) istekle app/vocabulary_store.py üzerinden ayrı tabloya yazılır.
    Döner: gönderilen benzersiz kelime sayısı.
    """
    if not products or not category or category == "GENEL":
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

    try:
        from app.vocabulary_store import increment_words
        return increment_words(dict(word_counts), category)
    except Exception:
        return 0


async def refresh_learned_vocabulary(sample_size: int = 200) -> dict:
    """Günlük cron: Supabase product_cache'teki en son taranan gerçek
    sonuçlardan kelime dağarcığını büyütür (elle terim eklemeye alternatif,
    envanterle birlikte kendiliğinden ölçeklenir)."""
    from app.cache import SUPABASE_URL, CACHE_TABLE, _enabled, _headers
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
