"""
EcoScore — Sprint 7: Sürdürülebilirlik Puanı

Ürünleri ambalaj türü, üretim yeri ve sertifikasyon bazında
0–100 arası bir Eko-Skor ile derecelendirir.

Skor bileşenleri:
  1. Ambalaj (40 puan max):
       Plastik tek kullanım → 5
       Karton                → 30
       Cam                   → 35
       Metal/Teneke          → 25
       Biyobozunur           → 40
       Bilinmeyen            → 10

  2. Üretim mesafesi (30 puan max):
       Yerel (Türk ürünü)    → 30
       Komşu ülke            → 20
       Avrupa                → 15
       Uzak (Asya/Amerika)   → 5
       Bilinmeyen            → 10

  3. Organik/Sertifika (20 puan max):
       Organik sertifika     → 20
       Doğal (etiket)        → 10
       Sertifikasız          → 0

  4. Yeniden kullanılabilirlik (10 puan max):
       Doldurulabilir/iade  → 10
       Standart             → 5
       Tek kullanım         → 0

Skor → Harf notu:
  90–100: A+ (Süper Yeşil)
  75–89 : A  (Çevre Dostu)
  60–74 : B  (Makul)
  40–59 : C  (Ortalama)
  0–39  : D  (İyileştirilebilir)
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# ── Puanlama Tabloları ────────────────────────────────────────

PACKAGING_SCORES: dict[str, int] = {
    "biodegradable": 40,
    "glass":         35,
    "cardboard":     30,
    "paper":         28,
    "metal":         25,
    "plastic_recycle": 15,
    "plastic":       5,
    "unknown":       10,
}

ORIGIN_SCORES: dict[str, int] = {
    "local":     30,   # Türkiye
    "neighbor":  20,   # Yunanistan, Bulgaristan, İran, Irak
    "europe":    15,
    "far":       5,    # Asya, Amerika, Afrika
    "unknown":   10,
}

CERT_SCORES: dict[str, int] = {
    "organic":     20,
    "natural":     10,
    "fair_trade":  10,
    "none":        0,
}

REUSE_SCORES: dict[str, int] = {
    "refillable":  10,
    "standard":    5,
    "disposable":  0,
}

# Anahtar kelime → ambalaj türü eşlemesi
_PACKAGING_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(cam|şişe|glass)\b", re.I),                   "glass"),
    (re.compile(r"\b(karton|kağıt|kutu|cardboard)\b", re.I),      "cardboard"),
    (re.compile(r"\b(teneke|konserve|metal|can)\b", re.I),         "metal"),
    (re.compile(r"\b(biyobozunur|bio|kompost)\b", re.I),           "biodegradable"),
    (re.compile(r"\b(geri dönüşüm|recycle|pet|hdpe)\b", re.I),    "plastic_recycle"),
    (re.compile(r"\b(plastik|poşet|naylon|plastic)\b", re.I),      "plastic"),
]

_LOCAL_BRANDS = frozenset({
    "pınar", "sek", "içim", "ülker", "eti", "aytaç", "besler", "koska",
    "torku", "söke", "cargill", "saray", "sutas", "mis", "sütaş",
    "banvit", "keyif", "çamlı", "kayısı", "doğanay", "uludağ",
})

_ORGANIC_KEYWORDS = re.compile(r"\b(organik|organic|ekolojik|bio|doğal)\b", re.I)
_CERT_KEYWORDS    = re.compile(r"\b(sertifikalı|certified|fair.trade)\b", re.I)


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class EcoScoreResult:
    product_key: str
    product_title: str
    eco_score: int
    grade: str
    packaging_type: str
    breakdown: dict = field(default_factory=dict)
    certifications: list[str] = field(default_factory=list)

    @property
    def is_eco_friendly(self) -> bool:
        return self.eco_score >= 60

    @property
    def color(self) -> str:
        if self.eco_score >= 90:
            return "#2d6a4f"   # Koyu yeşil
        if self.eco_score >= 75:
            return "#52b788"   # Açık yeşil
        if self.eco_score >= 60:
            return "#95d5b2"   # Sarı-yeşil
        if self.eco_score >= 40:
            return "#f4a261"   # Turuncu
        return "#e76f51"       # Kırmızı


# ── EcoScoreEngine ────────────────────────────────────────────

class EcoScoreEngine:
    """
    Ürün adı ve meta veriden Eko-Skor hesaplar.
    Sonucu Supabase'e cache'ler.
    """

    def score(
        self,
        product_key: str,
        product_title: str,
        *,
        packaging_hint: str = "unknown",
        origin_hint: str = "unknown",
        certifications: list[str] | None = None,
        reuse_type: str = "standard",
        use_cache: bool = True,
    ) -> EcoScoreResult:
        """
        Eko-skor hesaplar.

        Parametreler:
          packaging_hint: Bilinenler için ('glass', 'plastic', ...);
                          Bilinmiyorsa ürün adından çıkarılmaya çalışılır.
          origin_hint:    'local', 'europe', 'far', 'unknown'
          certifications: ['organic', 'fair_trade']
          reuse_type:     'refillable', 'standard', 'disposable'
        """
        if use_cache:
            cached = self._load_cache(product_key)
            if cached:
                return cached

        certs = certifications or self._detect_certifications(product_title)

        # Ambalaj tür tespiti
        pkg_type = packaging_hint
        if pkg_type == "unknown":
            pkg_type = self._detect_packaging(product_title)

        # Köken tespiti
        origin = origin_hint
        if origin == "unknown":
            origin = self._detect_origin(product_title)

        # Puanlama
        pkg_score   = PACKAGING_SCORES.get(pkg_type, PACKAGING_SCORES["unknown"])
        origin_score = ORIGIN_SCORES.get(origin, ORIGIN_SCORES["unknown"])
        cert_score  = max((CERT_SCORES.get(c, 0) for c in certs), default=0)
        reuse_score = REUSE_SCORES.get(reuse_type, REUSE_SCORES["standard"])

        total = min(pkg_score + origin_score + cert_score + reuse_score, 100)

        result = EcoScoreResult(
            product_key=product_key,
            product_title=product_title,
            eco_score=total,
            grade=self._grade(total),
            packaging_type=pkg_type,
            breakdown={
                "packaging":  pkg_score,
                "origin":     origin_score,
                "cert":       cert_score,
                "reuse":      reuse_score,
            },
            certifications=certs,
        )
        self._save_cache(result)
        return result

    def bulk_score(self, products: list[dict]) -> list[EcoScoreResult]:
        """
        Birden fazla ürün için toplu skor.
        products: [{"product_key", "product_title", ...}]
        """
        return [
            self.score(
                p["product_key"],
                p["product_title"],
                packaging_hint=p.get("packaging_type", "unknown"),
                origin_hint=p.get("origin", "unknown"),
                certifications=p.get("certifications"),
                reuse_type=p.get("reuse_type", "standard"),
            )
            for p in products
        ]

    def get_eco_summary(self, product_keys: list[str]) -> dict:
        """
        Birden fazla ürünün ortalama eko-skoru ve dağılımı.
        Alışveriş sepeti analizi için kullanılır.
        """
        if not product_keys:
            return {"avg_score": 0, "grade": "N/A", "breakdown": {}}

        scores = []
        for key in product_keys:
            cached = self._load_cache(key)
            if cached:
                scores.append(cached.eco_score)

        if not scores:
            return {"avg_score": 0, "grade": "N/A", "item_count": 0}

        avg = round(sum(scores) / len(scores), 1)
        return {
            "avg_score": avg,
            "grade": self._grade(int(avg)),
            "item_count": len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
        }

    # ── Tespit Metodları ─────────────────────────────────────

    def _detect_packaging(self, title: str) -> str:
        for pattern, pkg_type in _PACKAGING_KEYWORDS:
            if pattern.search(title):
                return pkg_type
        # Yaygın cam ürünler
        if re.search(r"\b(reçel|bal|sos|turşu|zeytin|zeytinyağı)\b", title, re.I):
            return "glass"
        # Süt ürünleri genellikle karton
        if re.search(r"\b(süt|ayran|meyve suyu|juice)\b", title, re.I):
            return "cardboard"
        return "unknown"

    def _detect_origin(self, title: str) -> str:
        title_lower = title.lower()
        for brand in _LOCAL_BRANDS:
            if brand in title_lower:
                return "local"
        if re.search(r"\b(türk|turkey|yerli|anadolu)\b", title, re.I):
            return "local"
        if re.search(r"\b(italyan|alman|fransız|yunan|İspanyol)\b", title, re.I):
            return "europe"
        if re.search(r"\b(japon|çin|hindistan|amerikan|brezilyalı)\b", title, re.I):
            return "far"
        return "unknown"

    def _detect_certifications(self, title: str) -> list[str]:
        certs = []
        if _ORGANIC_KEYWORDS.search(title):
            certs.append("organic")
        if _CERT_KEYWORDS.search(title):
            certs.append("fair_trade")
        return certs

    # ── Cache ────────────────────────────────────────────────

    def _load_cache(self, product_key: str) -> EcoScoreResult | None:
        try:
            r = _req.get(
                _sb("eco_scores"),
                params={"product_key": f"eq.{product_key}", "select": "*"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if not r.ok or not r.json():
                return None
            row = r.json()[0]
            return EcoScoreResult(
                product_key=row["product_key"],
                product_title=row["product_title"],
                eco_score=int(row["eco_score"]),
                grade=self._grade(int(row["eco_score"])),
                packaging_type=row.get("packaging_type", "unknown"),
                breakdown=row.get("breakdown") or {},
                certifications=row.get("certifications") or [],
            )
        except Exception:
            return None

    def _save_cache(self, result: EcoScoreResult) -> None:
        if not _SUPABASE_URL:
            return
        row = {
            "product_key":   result.product_key,
            "product_title": result.product_title,
            "packaging_type": result.packaging_type,
            "eco_score":     result.eco_score,
            "breakdown":     result.breakdown,
            "certifications": result.certifications,
        }
        try:
            _req.post(
                _sb("eco_scores"),
                headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                json=row,
                timeout=4,
            )
        except Exception:
            pass

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 90: return "A+"
        if score >= 75: return "A"
        if score >= 60: return "B"
        if score >= 40: return "C"
        return "D"


# Singleton
eco_score_engine = EcoScoreEngine()
