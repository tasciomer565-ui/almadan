"""
MatchingEngine — Sprint 4: Katalog-Watchlist Fuzzy Eşleştirme

Algoritma:
  Her watchlist ürünü için katalog item'larını şu metriklerle skorlar:
  1. Token overlap (Jaccard) — kelime seti örtüşmesi
  2. Sequence similarity   — difflib.SequenceMatcher
  3. Substring bonus       — ürün adı diğerinin içinde geçiyor mu
  4. Türkçe normalizer     — ş→s, ğ→g, ı→i, ö→o, ü→u

  Minimum skor eşiği: 0.55 (deneysel olarak belirlendi)

  Örnek eşleşmeler:
    "Pınar Tam Yağlı Süt 1L"  ↔ "PINAR SÜT 1LT"       → 0.82 ✅
    "Ülker Çikolata"           ↔ "ULKER CIKOLATA 100G"  → 0.78 ✅
    "Samsung Galaxy S24"       ↔ "Galaxy S24 256GB"     → 0.71 ✅
    "Ariel Toz Deterjan"       ↔ "Persil Sıvı"          → 0.12 ❌
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from app.text_utils import normalize_turkish

def _norm(text: str) -> str:
    """Küçük harf + Türkçe karakter → Latin ASCII."""
    return normalize_turkish(text).strip()


# Stop words — eşleştirmede anlam taşımayan kelimeler
_STOP_WORDS = frozenset({
    "ve", "ile", "bir", "bu", "o", "da", "de", "ki", "mi", "mu",
    "adet", "paket", "pk", "kutu", "lt", "kg", "gr", "ml", "cl",
    "the", "a", "an", "of", "and", "for",
})

_TOKEN_RE = re.compile(r"[a-z0-9çğışöü]{2,}", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    """Metni anlamlı token setine dönüştür."""
    return {t for t in _TOKEN_RE.findall(_norm(text)) if t not in _STOP_WORDS}


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class MatchResult:
    watchlist_title: str         # Kullanıcının aranan ürünü
    catalog_product: str         # Katalogda bulunan ürün
    store: str
    score: float                 # 0.0 – 1.0
    price: float | None
    original_price: float | None
    discount_pct: int | None
    unit: str | None
    catalog_item_id: int | None = None
    is_deal: bool = False        # İndirimli mi?
    debug: dict = field(default_factory=dict)


@dataclass
class MatchSummary:
    user_id: str | None
    device_id: str | None
    total_watchlist: int
    total_catalog: int
    matches: list[MatchResult] = field(default_factory=list)

    @property
    def match_count(self) -> int:
        return len(self.matches)

    @property
    def deal_count(self) -> int:
        return sum(1 for m in self.matches if m.is_deal)


# ── FuzzyMatcher ─────────────────────────────────────────────

class FuzzyMatcher:
    """
    İki metin arasındaki benzerliği hesaplar.

    Skor = ağırlıklı ortalama:
      - Token Jaccard  (ağırlık 0.50)
      - Sequence match (ağırlık 0.35)
      - Substring bonus(ağırlık 0.15)
    """

    THRESHOLD: float = 0.55

    def score(self, query: str, candidate: str) -> float:
        """İki metin arasındaki benzerlik skoru (0.0–1.0)."""
        q_norm = _norm(query)
        c_norm = _norm(candidate)

        if not q_norm or not c_norm:
            return 0.0

        # Tam eşleşme kısa devre
        if q_norm == c_norm:
            return 1.0

        jaccard  = self._jaccard(q_norm, c_norm)
        seq      = self._seq(q_norm, c_norm)
        substr   = self._substr_bonus(q_norm, c_norm)

        # Token Jaccard ağırlıklı: kısa sorgular için daha anlamlı
        score = jaccard * 0.60 + seq * 0.25 + substr * 0.15

        # Bonus: kısa sorgunun tüm tokenleri uzun metinde geçiyorsa
        q_tokens = _tokenize(q_norm)
        c_tokens = _tokenize(c_norm)
        if q_tokens and q_tokens.issubset(c_tokens):
            score = min(score + 0.20, 1.0)

        return round(min(score, 1.0), 4)

    def is_match(self, query: str, candidate: str) -> bool:
        return self.score(query, candidate) >= self.THRESHOLD

    def best_match(
        self, query: str, candidates: list[str], top_n: int = 1
    ) -> list[tuple[str, float]]:
        """En iyi N eşleşmeyi (kandidat, skor) tuple listesi olarak döner."""
        scored = [(c, self.score(query, c)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(c, s) for c, s in scored[:top_n] if s >= self.THRESHOLD]

    # ── Metrikler ────────────────────────────────────────────

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        """Token Jaccard benzerliği."""
        t_a = _tokenize(a)
        t_b = _tokenize(b)
        if not t_a or not t_b:
            return 0.0
        intersection = len(t_a & t_b)
        union        = len(t_a | t_b)
        return intersection / union if union else 0.0

    @staticmethod
    def _seq(a: str, b: str) -> float:
        """Sıralı karakter eşleşmesi (difflib)."""
        return difflib.SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _substr_bonus(a: str, b: str) -> float:
        """Kısa olan uzunun içinde tam geçiyorsa bonus."""
        short, long_ = (a, b) if len(a) <= len(b) else (b, a)
        if short in long_:
            return 1.0
        # En uzun ortak alt dizi oranı
        lcs_len = len(difflib.get_close_matches(short, [long_[:i] for i in range(3, len(long_)+1)]))
        return min(lcs_len / max(len(short), 1), 1.0) * 0.5


# ── MatchingEngine ────────────────────────────────────────────

class MatchingEngine:
    """
    Kullanıcı watchlist'ini katalog öğeleri ile karşılaştırır.

    Kullanım:
        engine = MatchingEngine()
        summary = engine.match(
            watchlist=["Pınar Süt 1L", "Ariel 3kg"],
            catalog_items=[CatalogItem(...)],
            store="migros",
            user_id="uuid",
        )
        for m in summary.matches:
            print(f"{m.watchlist_title} → {m.catalog_product} ({m.score:.2f}) ₺{m.price}")
    """

    def __init__(self, threshold: float = 0.55):
        self.matcher   = FuzzyMatcher()
        self.threshold = threshold

    def match(
        self,
        watchlist: list[str],
        catalog_items: list[Any],         # CatalogItem veya dict
        store: str = "",
        user_id: str | None = None,
        device_id: str | None = None,
    ) -> MatchSummary:
        """
        Watchlist × katalog çapraz eşleştirme.
        Her watchlist ürünü için en iyi katalog eşleşmesini döner.
        """
        summary = MatchSummary(
            user_id=user_id,
            device_id=device_id,
            total_watchlist=len(watchlist),
            total_catalog=len(catalog_items),
        )

        for wl_title in watchlist:
            best_score  = 0.0
            best_item   = None
            best_result = None

            for item in catalog_items:
                catalog_name = (
                    item.product_name if hasattr(item, "product_name")
                    else item.get("product_name", "")
                )
                if not catalog_name:
                    continue

                score = self.matcher.score(wl_title, catalog_name)
                if score > best_score:
                    best_score = score
                    best_item  = item

            if best_score >= self.threshold and best_item is not None:
                price  = getattr(best_item, "price", None) or (
                    best_item.get("price") if isinstance(best_item, dict) else None
                )
                orig   = getattr(best_item, "original_price", None) or (
                    best_item.get("original_price") if isinstance(best_item, dict) else None
                )
                disc   = getattr(best_item, "discount_pct", None) or (
                    best_item.get("discount_pct") if isinstance(best_item, dict) else None
                )
                unit   = getattr(best_item, "unit", None) or (
                    best_item.get("unit") if isinstance(best_item, dict) else None
                )
                item_id = getattr(best_item, "id", None) or (
                    best_item.get("id") if isinstance(best_item, dict) else None
                )
                catalog_name_final = (
                    best_item.product_name if hasattr(best_item, "product_name")
                    else best_item.get("product_name", "")
                )

                summary.matches.append(MatchResult(
                    watchlist_title=wl_title,
                    catalog_product=catalog_name_final,
                    store=store,
                    score=best_score,
                    price=price,
                    original_price=orig,
                    discount_pct=disc,
                    unit=unit,
                    catalog_item_id=item_id,
                    is_deal=bool(disc and disc >= 5),
                    debug={"score": best_score},
                ))

        return summary

    def match_from_db(
        self,
        watchlist: list[str],
        store: str,
        user_id: str | None = None,
        device_id: str | None = None,
    ) -> MatchSummary:
        """
        Supabase'deki catalog_items tablosundan eşleştirme yap.
        Tam text search + Python-side fuzzy refinement.
        """
        import requests as _req
        import os

        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        supabase_key = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

        if not supabase_url or not supabase_key:
            return MatchSummary(user_id, device_id, len(watchlist), 0)

        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }

        # Supabase full-text search (Türkçe) ile ön eleme
        catalog_items_raw = []
        for wl_title in watchlist[:20]:   # Max 20 ürün/çalıştırma
            # İlk 3 anlamlı kelimeyi arama terimine çevir
            tokens = list(_tokenize(wl_title))[:3]
            if not tokens:
                continue
            fts_query = " | ".join(tokens)  # OR operatörü
            try:
                resp = _req.get(
                    f"{supabase_url}/rest/v1/catalog_items",
                    params={
                        "store":   f"eq.{store}" if store else None,
                        "select":  "id,product_name,price,original_price,discount_pct,unit,store",
                        "fts":     f"product_name.phfts(turkish).{fts_query}",
                        "limit":   "30",
                        "order":   "discount_pct.desc.nullslast",
                    },
                    headers=headers,
                    timeout=5,
                )
                if resp.ok:
                    catalog_items_raw.extend(resp.json())
            except Exception:
                pass

        # Tekrar eden öğeleri kaldır
        seen_ids: set = set()
        unique_items = []
        for item in catalog_items_raw:
            item_id = item.get("id")
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_items.append(item)

        return self.match(watchlist, unique_items, store, user_id, device_id)


# ── Modül seviyesi örnekler ──────────────────────────────────
fuzzy_matcher  = FuzzyMatcher()
matching_engine = MatchingEngine()
