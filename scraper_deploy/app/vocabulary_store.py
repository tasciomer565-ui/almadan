"""Sorgu tanıma kelime dağarcığı için ayrı Supabase tablosu erişimi.

app_state (db.json/app_state tablosu) blob'undan bilinçli olarak ayrı
tutulur: günde onbinlerce güncelleme burada olacağı için, diğer site
verisiyle (kullanıcılar, ürünler) aynı satırı okuyup-yazmak yarış
durumu ve performans sorunu yaratır. Bkz. supabase_vocabulary_migration.sql
(tablo + increment_vocabulary_batch RPC fonksiyonu).
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from app.cache import SUPABASE_URL, SUPABASE_KEY, _enabled, _headers

logger = logging.getLogger(__name__)

VOCAB_TABLE = "vocabulary"


def increment_words(word_counts: dict[str, int], category: str) -> int:
    """Kelime sayaçlarını tek bir toplu (batch) RPC isteğiyle arttırır.
    Döner: gönderilen kelime sayısı (başarı garantisi değil, best-effort)."""
    if not _enabled() or not word_counts:
        return 0
    items = [
        {"word": word, "category": category, "count": count}
        for word, count in word_counts.items()
    ]
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/increment_vocabulary_batch"
        resp = requests.post(
            url,
            headers=_headers(),
            json={"p_items": items},
            timeout=6,
        )
        if not resp.ok:
            logger.warning("increment_vocabulary_batch failed: %s %s", resp.status_code, resp.text[:200])
            return 0
        return len(items)
    except Exception as exc:
        logger.warning("increment_vocabulary_batch error: %s", exc)
        return 0


def fetch_learned_vocabulary(min_count: int = 3, limit: int = 5000) -> dict[str, str]:
    """{kelime: kategori} — sadece yeterince gözlemlenmiş kelimeler.
    Sonuç bir süre (process ömrü boyunca) çağıran taraf tarafından
    önbelleğe alınmalı; her sorguda çağırmak gereksiz round-trip yaratır."""
    if not _enabled():
        return {}
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{VOCAB_TABLE}"
            f"?select=word,category"
            f"&count=gte.{min_count}"
            f"&order=count.desc"
            f"&limit={limit}"
        )
        resp = requests.get(url, headers=_headers(), timeout=6)
        rows = resp.json() if resp.ok else []
        return {row["word"]: row.get("category", "GENEL") for row in rows}
    except Exception as exc:
        logger.warning("fetch_learned_vocabulary error: %s", exc)
        return {}


def vocabulary_stats() -> dict:
    """Admin/izleme için özet: toplam kelime sayısı, kategori dağılımı."""
    if not _enabled():
        return {"enabled": False}
    try:
        url = f"{SUPABASE_URL}/rest/v1/{VOCAB_TABLE}?select=category"
        resp = requests.get(
            url,
            headers={**_headers(), "Prefer": "count=exact"},
            timeout=6,
        )
        total = resp.headers.get("content-range", "").split("/")[-1] if resp.ok else "?"
        return {"enabled": True, "total_words": total}
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}
