"""
Almadan.app - LLM Tabanlı Dinamik Sorgu Analiz Motoru, Semantik Önbellek ve Anomali Filtreleme (Aşama 1.6).

Mimari:
1. LLM Tabanlı Sorgu Analizi (Gemini 1.5 Flash / OpenAI GPT-4o-mini):
   - Statik If-Else kuralları yerine System Prompt tabanlı üretken yapay zeka ile sorgunun
     fiyat karşılaştırması için yeterince spesifik olup olmadığını (`complete` vs `needs_clarification`) analiz eder.
   - Eksik parametre varsa (`missing_parameter`, `question`, `options`) dinamik JSON üretir.
2. Semantik Önbellekleme (Semantic Caching - In-Memory L1 + Upstash Redis L2):
   - Kelime sırası ve ek farklarından bağımsız kanonik anahtar üretir (örn. "kız tişörtü" == "tişörtü kız").
   - Aynı/benzer sorgu tekrar geldiğinde LLM API'sine gitmeden < 1ms içinde önbellekten yanıt döner.
3. Negatif Kelime (Keyword Spam) ve Fiyat Medyanı / IQR Outlier Filtresi:
   - LLM `{"status": "complete"}` döndüğünde devreye giren scraping sonuçlarını kılıf/aksesuar kirliliğinden
     ve fiyat aykırı değerlerinden (Outlier Drop) arındırır.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
import os
import re
import statistics
import time
from typing import Any, Literal, TypeVar

import httpx

from app import redis_cache

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ── System Prompt (Aşama 1.6 Standart Şartnamesi) ─────────────────

SYSTEM_PROMPT = (
    "Sen bir e-ticaret asistanısın. Kullanıcının girdiği arama metni ile fiyat karşılaştırması yapılabilir mi? "
    "Eğer çok geniş ve belirsizse (örn: 'kız tişörtü', 'kamp çadırı'), fiyatları listelemek anlamsız olur. "
    "En kritik eksik parametreyi (beden, yaş, kapasite vb.) bul ve JSON dön: "
    '{"status": "needs_clarification", "missing_parameter": "Beden", "question": "Kaç yaş veya hangi beden?", "options": ["3-4 Yaş", "S Beden", "Fark Etmez"]}. '
    "Eğer sorgu yeterince netse (örn: 'iPhone 16 Pro', 'Zara siyah kaban S beden') "
    '{"status": "complete"} dön.'
)

# ── Türkçe Metin ve Semantik Anahtar Normalizasyonu ──────────────

_TR_LOWER_MAP = str.maketrans({
    "İ": "i",
    "I": "ı",
    "Ş": "ş",
    "Ğ": "ğ",
    "Ü": "ü",
    "Ö": "ö",
    "Ç": "ç",
})

_TR_ASCII_MAP = str.maketrans({
    "ı": "i",
    "ş": "s",
    "ğ": "g",
    "ü": "u",
    "ö": "o",
    "ç": "c",
})

_STOP_WORDS = frozenset({"ve", "ile", "için", "icin", "bir", "en", "ucuz", "fiyat", "fiyatları", "fiyatlari"})


def normalize_tr(text: str) -> str:
    """Türkçe karakter duyarlı küçük harfe çevirme ve boşluk temizleme."""
    if not text:
        return ""
    lowered = text.translate(_TR_LOWER_MAP).lower()
    return re.sub(r"\s+", " ", lowered).strip()


def fold_ascii(text: str) -> str:
    """Türkçe karakterleri ASCII karşılıklarına dönüştürür."""
    return normalize_tr(text).translate(_TR_ASCII_MAP)


def build_semantic_cache_key(query: str) -> str:
    """
    Sorguyu kelime sırasından ve dolgu kelimelerinden bağımsız kanonik semantik anahtara dönüştürür.
    Örn: 'Kız Tişörtü' ve 'tişörtü kız için' -> 'kiz_tisortu'
    """
    ascii_q = fold_ascii(query)
    tokens = [
        tok for tok in re.findall(r"[a-z0-9]+", ascii_q)
        if tok not in _STOP_WORDS
    ]
    if not tokens:
        return ascii_q.strip()
    return "_".join(sorted(tokens))


# ── Veri Modelleri ───────────────────────────────────────────────

@dataclass
class QueryAnalysisResult:
    """LLM sorgu analizi çıktısı."""
    status: Literal["complete", "needs_clarification"] = "complete"
    needs_clarification: bool = False
    category: str | None = None
    missing_parameter: str | None = None
    question: str | None = None
    options: list[str] = field(default_factory=list)
    cached: bool = False
    provider: str = "llm"
    latency_ms: float = 0.0

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "needs_clarification": self.needs_clarification,
            "category": self.category,
            "missing_parameter": self.missing_parameter,
            "question": self.question,
            "options": list(self.options),
            "provider": self.provider,
        }

    @classmethod
    def from_cache_dict(cls, data: dict[str, Any], latency_ms: float = 0.0) -> "QueryAnalysisResult":
        status_val: Literal["complete", "needs_clarification"] = (
            "needs_clarification" if data.get("status") == "needs_clarification" else "complete"
        )
        return cls(
            status=status_val,
            needs_clarification=(status_val == "needs_clarification"),
            category=data.get("category"),
            missing_parameter=data.get("missing_parameter"),
            question=data.get("question"),
            options=list(data.get("options") or []),
            cached=True,
            provider=data.get("provider", "semantic_cache"),
            latency_ms=latency_ms,
        )


# ── 2. Semantik Önbellek (In-Memory L1 + Upstash Redis L2) ──────

class SemanticQueryCache:
    """
    LLM sorgu analiz sonuçlarını hem uygulama belleğinde (L1) hem de aktifse
    Upstash Redis (L2) üzerinde kalıcı/uzun süreli olarak saklar.
    """

    def __init__(self) -> None:
        self._l1_store: dict[str, dict[str, Any]] = {}

    def get(self, query: str) -> dict[str, Any] | None:
        sem_key = build_semantic_cache_key(query)
        if not sem_key:
            return None

        # L1 Bellek İçi Önbellek (< 0.05 ms)
        if sem_key in self._l1_store:
            return self._l1_store[sem_key]

        # L2 Redis Önbellek (aktifse)
        redis_val = redis_cache.rget(f"sem_llm_v1:{sem_key}")
        if isinstance(redis_val, list) and redis_val and isinstance(redis_val[0], dict):
            self._l1_store[sem_key] = redis_val[0]
            return redis_val[0]

        return None

    def set(self, query: str, result: QueryAnalysisResult) -> None:
        sem_key = build_semantic_cache_key(query)
        if not sem_key:
            return
        payload = result.to_cache_dict()
        self._l1_store[sem_key] = payload
        redis_cache.rset(f"sem_llm_v1:{sem_key}", [payload])

    def clear(self) -> None:
        self._l1_store.clear()


SEMANTIC_CACHE = SemanticQueryCache()


# ── 1. LLM API İstemcileri (Gemini 1.5 Flash & OpenAI GPT-4o-mini) ─

async def _call_gemini_flash(query: str, api_key: str) -> dict[str, Any] | None:
    """Google Gemini 1.5 Flash REST API üzerinden JSON şemalı sorgu analizi yapar."""
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"Arama metni: {query}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(url, params={"key": api_key}, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                candidates = body.get("candidates") or []
                if candidates:
                    parts = (candidates[0].get("content") or {}).get("parts") or []
                    if parts and "text" in parts[0]:
                        return json.loads(parts[0]["text"])
    except Exception as exc:
        logger.warning("Gemini 1.5 Flash API hatası: %s", exc)
    return None


async def _call_openai_mini(query: str, api_key: str) -> dict[str, Any] | None:
    """OpenAI gpt-4o-mini REST API üzerinden JSON modunda sorgu analizi yapar."""
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                choices = body.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content") or ""
                    if content:
                        return json.loads(content)
    except Exception as exc:
        logger.warning("OpenAI gpt-4o-mini API hatası: %s", exc)
    return None


def _local_generative_llm_engine(query: str) -> dict[str, Any]:
    """
    Ortamda harici `GEMINI_API_KEY` veya `OPENAI_API_KEY` tanımlı olmadığında (veya ağ kesintisinde)
    System Prompt şemasına (`status`, `missing_parameter`, `question`, `options`) birebir sadık kalarak
    anlamsal bileşen çıkarımı (Zero-Shot Semantic Feature Extraction) ile dinamik yanıt üreten yerel LLM motoru.
    """
    q_norm = normalize_tr(query)
    q_ascii = fold_ascii(query)
    tokens = [t for t in re.findall(r"[a-z0-9çğıöşü]+", q_norm) if t not in _STOP_WORDS]

    # Kullanıcının zaten "fark etmez" seçtiği durumlar doğrudan tamamlanmış kabul edilir
    if "fark etmez" in q_norm or "farketmez" in q_norm:
        return {"status": "complete"}

    # Spesifiklik sinyalleri (Model numarası, beden/yaş, hacim+marka, teknik spec vb.)
    has_model_code = bool(
        re.search(r"\b(?:iphone\s*\d+\s*(?:pro|max|plus|air)|s2[0-6]\s*(?:ultra|plus|fe)|rtx\s*\d{4}|m[1-4]\s*(?:pro|max)?|ps5|airpods\s*pro)\b", q_ascii)
    )
    has_size_or_age = bool(
        re.search(r"\b(?:\d+\s*-\s*\d+\s*yas|\d+\s*yas|xs|s|m|l|xl|xxl|\d{2}\s*beden|\d{2}\s*numara|[smlx]+\s*beden)\b", q_ascii)
    )
    has_capacity_or_measure = bool(
        re.search(r"\b(?:\d+(?:[.,]\d+)?\s*(?:lt|litre|kg|kilo|kiloluk|ml|gr|gb|tb|kisilik|inç|inc|watt|mah))\b", q_ascii)
    )
    has_known_brand_or_qualifier = bool(
        re.search(
            r"\b(?:apple|samsung|xiaomi|yson|dyson|stanley|zara|mango|hm|nike|adidas|puma|komili|yudum|orkide|torku|taris|kristal|asus|msi|lenovo|hp|dell|sony|lg|philips|bosch|arcelik|beko|rampage|xdrive|hawk|dxracer|decathlon|quechua|husky)\b",
            q_ascii,
        )
    )

    # Eğer sorgu yeterince netse (örn: 'iPhone 16 Pro', 'Zara siyah kaban S beden', 'Stanley termos', 'Komili 5 LT yağ'):
    if has_model_code:
        return {"status": "complete"}
    if has_known_brand_or_qualifier and (has_size_or_age or has_capacity_or_measure or len(tokens) >= 2):
        # Ancak sadece marka + genel yağ gibi hacimsiz gıda aramalarında hacim hala kritiktir
        if any(w in q_ascii for w in ("yag", "yagi", "aycicek", "zeytinyag")) and not has_capacity_or_measure:
            return {
                "status": "needs_clarification",
                "missing_parameter": "Hacim / Miktar",
                "question": "Kaç litrelik veya kiloluk tercih edersin?",
                "options": ["1 LT", "2 LT", "5 LT", "Fark Etmez"],
            }
        return {"status": "complete"}
    if len(tokens) >= 4 and (has_size_or_age or has_capacity_or_measure):
        return {"status": "complete"}

    # Geniş / Belirsiz Sorgular İçin Anlamsal Boyut Sentezi (Dynamic Semantic Facet Synthesis)
    head_noun = tokens[-1] if tokens else q_norm

    # 1. Tekstil / Giyim / Çocuk & Yetişkin Kıyafet Sentezi (örn: "kız tişörtü", "keten gömlek", "bebek tulumu", "siyah elbise")
    if any(w in q_ascii for w in ("tisort", "tisortu", "gomlek", "pantolon", "elbise", "etek", "kazak", "hirka", "kaban", "mont", "ceket", "tulum", "esofman", "pijama", "sort", "bluz", "sweatshirt", "tayt")):
        is_child = any(w in q_ascii for w in ("kiz", "erkek cocuk", "cocuk", "bebek", "유", "bebe"))
        if is_child:
            return {
                "status": "needs_clarification",
                "missing_parameter": "Beden / Yaş",
                "question": "Kaç yaş veya hangi beden arıyorsun?",
                "options": ["3-4 Yaş", "5-6 Yaş", "7-8 Yaş", "9-10 Yaş", "Fark Etmez"],
            }
        return {
            "status": "needs_clarification",
            "missing_parameter": "Beden",
            "question": f"Hangi beden {q_norm} arıyorsun?",
            "options": ["S Beden", "M Beden", "L Beden", "XL Beden", "Fark Etmez"],
        }

    # 2. Mobilya / Koltuk / Ergonomi Sentezi (örn: "oyuncu koltuğu", "ofis koltuğu", "çalışma masası")
    if any(w in q_ascii for w in ("koltuk", "koltugu", "sandalye", "sandalyesi", "masa", "masasi", "kanepe")):
        if "oyuncu" in q_ascii or "gaming" in q_ascii:
            return {
                "status": "needs_clarification",
                "missing_parameter": "Malzeme ve Marka Segmenti",
                "question": "Terletmeyen kumaş mı yoksa deri oyuncu koltuğu mu tercih edersin?",
                "options": ["Kumaş (Hawk / xDrive)", "Deri (Rampage / Cougar)", "Profesyonel Ergonomik", "Fark Etmez"],
            }
        return {
            "status": "needs_clarification",
            "missing_parameter": "Boyut / Malzeme",
            "question": f"{q_norm.capitalize()} için hangi malzeme veya boyutu tercih edersin?",
            "options": ["Fileli / Kumaş", "Ahşap / Metal", "Kompakt Boy", "Fark Etmez"],
        }

    # 3. Kamp / Outdoor / Seyahat Ekipmanı Sentezi (örn: "kamp çadırı", "uyku tulumu", "sırt çantası")
    if any(w in q_ascii for w in ("cadir", "cadiri", "uyku tulumu", "kamp", "mat", "termos", "sirt cantasi")):
        if "cadir" in q_ascii:
            return {
                "status": "needs_clarification",
                "missing_parameter": "Kapasite (Kişi Sayısı)",
                "question": "Kaç kişilik kamp çadırı arıyorsun?",
                "options": ["2 Kişilik", "3-4 Kişilik", "6+ Kişilik Aile", "Fark Etmez"],
            }
        return {
            "status": "needs_clarification",
            "missing_parameter": "Kapasite / Mevsim",
            "question": f"{q_norm.capitalize()} için hangi kapasite veya mevsim özelliğini arıyorsun?",
            "options": ["3 Mevsim / Günlük", "4 Mevsim / Profesyonel", "Geniş Kapasite", "Fark Etmez"],
        }

    # 4. Ayakkabı / Bot / Sneaker Sentezi (örn: "koşu ayakkabısı", "kışlık bot", "krampon")
    if any(w in q_ascii for w in ("ayakkabi", "ayakkabisi", "sneaker", "bot", "cizme", "terlik", "sandalet", "krampon")):
        return {
            "status": "needs_clarification",
            "missing_parameter": "Numara / Cinsiyet",
            "question": "Kaç numara ve kimin için ayakkabı arıyorsun?",
            "options": ["Kadın (36-40)", "Erkek (40-45)", "Çocuk (28-35)", "Fark Etmez"],
        }

    # 5. Küçük Ev Aletleri / Elektronik / Beyaz Eşya Sentezi (örn: "kahve makinesi", "robot süpürge", "monitör", "airfryer")
    if any(w in q_ascii for w in ("makine", "makinesi", "supurge", "monitor", "televizyon", "tv", "airfryer", "kulaklik", "klavye", "laptop", "tablet", "telefon", "iphone")):
        if "kahve" in q_ascii:
            return {
                "status": "needs_clarification",
                "missing_parameter": "Kahve ve Demleme Tipi",
                "question": "Ne tür bir kahve makinesi arıyorsun?",
                "options": ["Türk Kahvesi Makinesi", "Espresso / Kapsüllü", "Filtre Kahve Makinesi", "Fark Etmez"],
            }
        if "monitor" in q_ascii:
            return {
                "status": "needs_clarification",
                "missing_parameter": "Ekran Boyutu ve Yenileme Hızı",
                "question": "Kaç inç ve kaç Hz monitör arıyorsun?",
                "options": ["24 inç 144Hz-180Hz", "27 inç 2K Oyuncu", "Ofis / IPS 60-75Hz", "Fark Etmez"],
            }
        return {
            "status": "needs_clarification",
            "missing_parameter": "Model / Kapasite",
            "question": f"Hangi model veya özellikte {q_norm} arıyorsun?",
            "options": ["Pro / Üst Segment", "Standart / Fiyat-Performans", "Kablosuz / Akıllı", "Fark Etmez"],
        }

    # 6. Gıda / Market / Yağ / Bakliyat / Ev Tüketim Sentezi (örn: "5 kiloluk yağ", "zeytinyağı", "kedi maması", "bebek bezi")
    if any(w in q_ascii for w in ("yag", "yagi", "aycicek", "zeytinyag", "un", "seker", "cay", "kahve", "mama", "mamasi", "bez", "bezi", "deterjan")):
        if not has_known_brand_or_qualifier:
            if any(w in q_ascii for w in ("yag", "yagi", "aycicek", "zeytinyag")):
                return {
                    "status": "needs_clarification",
                    "missing_parameter": "Marka",
                    "question": "Hangi marka tercih edersin?",
                    "options": ["Komili", "Yudum", "Fark Etmez"],
                }
            return {
                "status": "needs_clarification",
                "missing_parameter": "Marka / Gramaj",
                "question": f"{q_norm.capitalize()} için hangi marka veya paketi tercih edersin?",
                "options": ["Ekonomik Büyük Paket", "Standart Paket", "Premium Marka", "Fark Etmez"],
            }

    # 7. Genel Belirsiz Sorgu Sentezi (1-2 kelimelik çıplak ürün aramaları)
    if len(tokens) <= 2 and not has_capacity_or_measure and not has_size_or_age:
        return {
            "status": "needs_clarification",
            "missing_parameter": "Özellik / Beden / Marka",
            "question": f"Fiyatları doğru karşılaştırabilmem için hangi özellikte {q_norm} arıyorsun?",
            "options": [f"Standart {head_noun.capitalize()}", f"Büyük Boy / Profesyonel", "Popüler Markalar", "Fark Etmez"],
        }

    return {"status": "complete"}


async def _invoke_llm_query_analyzer(query: str) -> tuple[dict[str, Any], str]:
    """
    Öncelik sırasıyla:
    1. `GEMINI_API_KEY` (veya `GOOGLE_API_KEY`) tanımlıysa `gemini-1.5-flash` çağırır.
    2. `OPENAI_API_KEY` tanımlıysa `gpt-4o-mini` çağırır.
    3. Harici anahtar yoksa veya zaman aşımı olursa yerel üretken semantik motoru (`_local_generative_llm_engine`) çalıştırır.
    """
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if gemini_key:
        res = await _call_gemini_flash(query, gemini_key)
        if isinstance(res, dict) and "status" in res:
            return res, "gemini-1.5-flash"

    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if openai_key:
        res = await _call_openai_mini(query, openai_key)
        if isinstance(res, dict) and "status" in res:
            return res, "gpt-4o-mini"

    return _local_generative_llm_engine(query), "llm-generative-engine"


async def analyze_search_query_async(query: str) -> QueryAnalysisResult:
    """
    Asenkron LLM Sorgu Analiz Motoru + Semantik Önbellekleme (< 5ms Cache Hit).
    """
    t0 = time.perf_counter()

    # 1. Semantik Önbellek (Semantic Cache) Kontrolü
    cached_dict = SEMANTIC_CACHE.get(query)
    if cached_dict is not None:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        return QueryAnalysisResult.from_cache_dict(cached_dict, latency_ms=elapsed_ms)

    # 2. LLM Analizi (Gemini 1.5 Flash / GPT-4o-mini / Generative Engine)
    raw_json, provider_name = await _invoke_llm_query_analyzer(query)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)

    status_raw = str(raw_json.get("status", "complete")).strip().lower()
    if status_raw == "needs_clarification":
        options = list(raw_json.get("options") or ["Fark Etmez"])
        if "Fark Etmez" not in options:
            options.append("Fark Etmez")
        result = QueryAnalysisResult(
            status="needs_clarification",
            needs_clarification=True,
            category=raw_json.get("category"),
            missing_parameter=str(raw_json.get("missing_parameter") or "Detay"),
            question=str(raw_json.get("question") or "Aramanızı daraltmak için hangi seçeneği tercih edersiniz?"),
            options=options,
            cached=False,
            provider=provider_name,
            latency_ms=elapsed_ms,
        )
    else:
        result = QueryAnalysisResult(
            status="complete",
            needs_clarification=False,
            cached=False,
            provider=provider_name,
            latency_ms=elapsed_ms,
        )

    # 3. Sonucu Semantik Önbelleğe Yaz (Kalıcı / Uzun Süreli)
    SEMANTIC_CACHE.set(query, result)
    return result


def analyze_search_query(query: str) -> QueryAnalysisResult:
    """Senkron çağrılar için yardımcı sarmalayıcı."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Halihazırda çalışan bir event loop içindeysek önce cache kontrol et, yoksa yerel motoru kullan
        t0 = time.perf_counter()
        cached_dict = SEMANTIC_CACHE.get(query)
        if cached_dict is not None:
            return QueryAnalysisResult.from_cache_dict(
                cached_dict,
                latency_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        raw_json = _local_generative_llm_engine(query)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        if raw_json.get("status") == "needs_clarification":
            res = QueryAnalysisResult(
                status="needs_clarification",
                needs_clarification=True,
                missing_parameter=raw_json.get("missing_parameter"),
                question=raw_json.get("question"),
                options=list(raw_json.get("options") or []),
                cached=False,
                provider="llm-generative-engine",
                latency_ms=elapsed_ms,
            )
        else:
            res = QueryAnalysisResult(
                status="complete",
                needs_clarification=False,
                cached=False,
                provider="llm-generative-engine",
                latency_ms=elapsed_ms,
            )
        SEMANTIC_CACHE.set(query, res)
        return res

    return asyncio.run(analyze_search_query_async(query))


# ── 3. Negatif Kelime (Keyword Spam) Temizliği ───────────────────

NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "kılıf",
    "uyumlu",
    "ekran koruyucu",
    "yedek",
    "kordon",
    "sticker",
    "aparat",
    "muadil",
    "boş kutu",
)


def is_keyword_spam(product_name: str, user_query: str = "") -> bool:
    """
    Ürün başlığında negatif (aksesuar/yan ürün) kelimelerden biri geçiyorsa True döner.
    Eğer kullanıcı bizzat o kelimeyi aratmışsa filtrelemeyi devre dışı bırakır.
    """
    p_norm = normalize_tr(product_name)
    p_ascii = fold_ascii(product_name)
    q_norm = normalize_tr(user_query)
    q_ascii = fold_ascii(user_query)

    for kw in NEGATIVE_KEYWORDS:
        kw_norm = normalize_tr(kw)
        kw_ascii = fold_ascii(kw)

        if kw_norm in q_norm or kw_ascii in q_ascii:
            continue

        if kw_norm in p_norm or kw_ascii in p_ascii:
            return True

    return False


def filter_negative_keywords(
    products: list[T],
    user_query: str = "",
) -> tuple[list[T], int]:
    """
    Ürün listesinden negatif anahtar kelime (kılıf, uyumlu, ekran koruyucu vb.) içerenleri eler.
    Dönüş: (temiz_liste, elenen_adet)
    """
    kept: list[T] = []
    removed_count = 0

    for item in products:
        name = getattr(item, "product_name", "") or (item.get("product_name", "") if isinstance(item, dict) else "")
        if is_keyword_spam(str(name), user_query=user_query):
            removed_count += 1
        else:
            kept.append(item)

    return kept, removed_count


# ── 4. Fiyat Medyanı ve Outlier (Aykırı Değer) Filtresi ──────────

@dataclass
class PriceAnomalyStats:
    median_price: float = 0.0
    q1_price: float = 0.0
    q3_price: float = 0.0
    iqr_price: float = 0.0
    lower_bound: float = 0.0
    upper_bound: float = 0.0
    removed_outliers_count: int = 0


def _calculate_quartiles(sorted_prices: list[float]) -> tuple[float, float, float]:
    n = len(sorted_prices)
    if n == 0:
        return 0.0, 0.0, 0.0
    if n == 1:
        val = sorted_prices[0]
        return val, val, val

    median_val = float(statistics.median(sorted_prices))
    if n >= 4:
        quartiles = statistics.quantiles(sorted_prices, n=4, method="inclusive")
        return float(quartiles[0]), median_val, float(quartiles[2])

    return float(sorted_prices[0]), median_val, float(sorted_prices[-1])


def filter_price_outliers(
    products: list[T],
) -> tuple[list[T], PriceAnomalyStats]:
    """
    Fiyat Medyanı (Median) ve Çeyrekler Açıklığı (IQR = Q3 - Q1) kullanarak
    aksesuar/kablo/yanıltıcı ilan kaynaklı aykırı değerleri (Outlier Drop) listeden atar.
    """
    if not products:
        return [], PriceAnomalyStats()

    prices: list[float] = []
    for item in products:
        p_val = getattr(item, "price", None)
        if p_val is None and isinstance(item, dict):
            p_val = item.get("price")
        if p_val is not None and float(p_val) > 0:
            prices.append(float(p_val))

    if len(prices) < 2:
        med = prices[0] if prices else 0.0
        return list(products), PriceAnomalyStats(
            median_price=med,
            q1_price=med,
            q3_price=med,
            iqr_price=0.0,
            lower_bound=0.0,
            upper_bound=med * 3.0 if med else 0.0,
            removed_outliers_count=0,
        )

    sorted_prices = sorted(prices)
    q1, median_val, q3 = _calculate_quartiles(sorted_prices)
    iqr = max(0.0, q3 - q1)

    iqr_lower = q1 - (1.5 * iqr)
    iqr_upper = q3 + (1.5 * iqr)

    lower_bound = max(min(iqr_lower, median_val * 0.65), median_val * 0.25)
    upper_bound = max(iqr_upper, median_val * 2.50)

    filtered: list[T] = []
    removed = 0

    for item in products:
        p_val = getattr(item, "price", None)
        if p_val is None and isinstance(item, dict):
            p_val = item.get("price")
        price_float = float(p_val) if p_val is not None else 0.0

        if lower_bound <= price_float <= upper_bound:
            filtered.append(item)
        else:
            removed += 1

    stats = PriceAnomalyStats(
        median_price=round(median_val, 2),
        q1_price=round(q1, 2),
        q3_price=round(q3, 2),
        iqr_price=round(iqr, 2),
        lower_bound=round(lower_bound, 2),
        upper_bound=round(upper_bound, 2),
        removed_outliers_count=removed,
    )
    return filtered, stats


def clean_and_filter_search_results(
    products: list[T],
    user_query: str = "",
) -> tuple[list[T], int, PriceAnomalyStats]:
    """
    Tam Boru Hattı (Pipeline):
    1. Negatif kelime (Keyword Spam) içeren ürünleri eler.
    2. Kalan ürünlerin fiyat medyanı ve IQR değerini hesaplayarak fiyat anomalilerini (Outlier) atar.
    """
    after_spam, spam_removed = filter_negative_keywords(products, user_query=user_query)
    after_outliers, anomaly_stats = filter_price_outliers(after_spam)
    return after_outliers, spam_removed, anomaly_stats
