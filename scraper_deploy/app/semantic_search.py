"""
SemanticSearch — Sprint 6: pgvector Tabanlı Anlamsal Ürün Arama

Mimari:
  - Supabase pgvector eklentisi: product_embeddings tablosu
  - Embedding: OpenAI text-embedding-3-small (1536 boyut, $0.02/1M token)
  - Fallback: TF-IDF benzeri basit n-gram vektörü (OpenAI yoksa)
  - Cache: aynı sorgu 1 saat içinde tekrar gelirse DB'den döndür

'Semantik Arama' ne kazandırır:
  - "Kışlık kahvaltılık" → peynir + zeytin + reçel birlikte gelir
  - "Bebek için" → mama, bez, biberon bir arada
  - Yazım hatası toleransı: "yoğurt" = "yogurt"
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import requests as _req

from app.ai_monitor import AIMonitor

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
_OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "").strip()

_EMBED_MODEL   = "text-embedding-3-small"
_EMBED_DIMS    = 1536
_EMBED_COST_1K = 0.00002   # USD / 1K token


def _sb_headers() -> dict[str, str]:
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
class SemanticResult:
    product_key: str
    product_title: str
    store: str
    category: str
    price: float | None
    similarity: float
    metadata: dict


# ── Embedding ────────────────────────────────────────────────

def embed_text(text: str, *, user_id: str | None = None) -> list[float] | None:
    """
    OpenAI text-embedding-3-small ile metin vektörü üretir.
    OpenAI yoksa TF-IDF benzeri fallback kullanır.
    """
    if _OPENAI_KEY:
        return _embed_openai(text, user_id=user_id)
    return _embed_fallback(text)


def _embed_openai(text: str, *, user_id: str | None = None) -> list[float] | None:
    """OpenAI Embeddings API."""
    with AIMonitor.trace("embedding", "embed_text",
                         model_id=_EMBED_MODEL, user_id=user_id) as span:
        try:
            r = _req.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {_OPENAI_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": _EMBED_MODEL, "input": text[:8000]},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", len(text) // 4)
            span.set_tokens(input=tokens)
            span.set_cost(tokens / 1000 * _EMBED_COST_1K)
            return data["data"][0]["embedding"]
        except Exception as exc:
            span.set_error(str(exc))
            logger.warning("OpenAI embed failed: %s", exc)
            return None


def _embed_fallback(text: str) -> list[float]:
    """
    OpenAI yokken kullanılan deterministik vektör.
    TF-IDF'e benzer: karakter n-gram tabanlı sparse encoding.
    Cosine similarity ile çalışır ama OpenAI kadar iyi değildir.
    Not: Boyut 1536'ya pad'lenir (pgvector uyumu için).
    """
    import math

    # 3-gram frekans vektörü
    ngrams: dict[str, int] = {}
    norm_text = text.lower().strip()
    for i in range(len(norm_text) - 2):
        ng = norm_text[i:i+3]
        ngrams[ng] = ngrams.get(ng, 0) + 1

    # Deterministik hash tabanlı projeksiyon
    vec = [0.0] * _EMBED_DIMS
    for ng, count in ngrams.items():
        h = int(hashlib.md5(ng.encode(), usedforsecurity=False).hexdigest()[:4], 16)
        idx = h % _EMBED_DIMS
        vec[idx] += count

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


# ── Toplu Embedding (Ürün Katalog İndekslemesi) ───────────────

def embed_products_batch(
    products: list[dict],
    *,
    batch_size: int = 50,
) -> int:
    """
    Ürün listesini vektörize edip product_embeddings tablosuna yazar.
    products: [{"product_key", "product_title", "store", "category", "price", "metadata"}]
    Döndürür: başarıyla embed edilen ürün sayısı
    """
    indexed = 0
    for i in range(0, len(products), batch_size):
        batch = products[i: i + batch_size]
        texts = [p["product_title"] for p in batch]

        # Toplu embed (OpenAI batch endpoint daha ekonomik)
        if _OPENAI_KEY:
            vectors = _embed_batch_openai(texts)
        else:
            vectors = [_embed_fallback(t) for t in texts]

        if not vectors:
            continue

        rows = []
        for product, vec in zip(batch, vectors):
            if vec:
                rows.append({
                    "product_key":   product["product_key"],
                    "product_title": product["product_title"],
                    "store":         product.get("store", ""),
                    "category":      product.get("category", ""),
                    "price":         product.get("price"),
                    "embedding":     vec,
                    "metadata":      product.get("metadata") or {},
                })

        if rows:
            try:
                r = _req.post(
                    _sb("product_embeddings"),
                    headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
                    json=rows,
                    timeout=15,
                )
                if r.ok:
                    indexed += len(rows)
            except Exception as exc:
                logger.warning("embed_products_batch save failed: %s", exc)

    return indexed


def _embed_batch_openai(texts: list[str]) -> list[list[float] | None]:
    """OpenAI batch embedding (tek API çağrısı, daha ekonomik)."""
    with AIMonitor.trace("embedding", "embed_batch", model_id=_EMBED_MODEL) as span:
        try:
            r = _req.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {_OPENAI_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": _EMBED_MODEL, "input": [t[:8000] for t in texts]},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            span.set_tokens(input=usage.get("prompt_tokens", 0))
            span.set_cost(usage.get("total_tokens", 0) / 1000 * _EMBED_COST_1K)
            # Sıralama garantili: OpenAI "index" alanıyla döndürür
            result_map = {item["index"]: item["embedding"] for item in data["data"]}
            return [result_map.get(i) for i in range(len(texts))]
        except Exception as exc:
            span.set_error(str(exc))
            return [None] * len(texts)


# ── Semantik Arama ────────────────────────────────────────────

class SemanticSearch:
    """
    pgvector cosine similarity ile anlamsal ürün araması.

    Kullanım:
        ss = SemanticSearch()
        results = ss.search("Kışlık kahvaltılık", limit=10)
    """

    def search(
        self,
        query: str,
        *,
        store: str | None = None,
        category: str | None = None,
        limit: int = 10,
        threshold: float = 0.70,
        user_id: str | None = None,
    ) -> list[SemanticResult]:
        """
        Sorguyu vektörize et → pgvector cosine similarity ile ara.
        OpenAI yoksa fallback vektör kullanır.
        """
        query_vec = embed_text(query, user_id=user_id)
        if query_vec is None:
            logger.warning("Embedding üretilemedi, keyword aramaya düşülüyor")
            return self._keyword_fallback(query, store=store, limit=limit)

        return self._vector_search(
            query_vec,
            store=store,
            category=category,
            limit=limit,
            threshold=threshold,
        )

    def _vector_search(
        self,
        query_vec: list[float],
        *,
        store: str | None,
        category: str | None,
        limit: int,
        threshold: float,
    ) -> list[SemanticResult]:
        """Supabase RPC: search_products_semantic fonksiyonu."""
        try:
            params: dict[str, Any] = {
                "query_embedding": query_vec,
                "p_limit": limit,
                "p_threshold": threshold,
            }
            if store:
                params["p_store"] = store
            if category:
                params["p_category"] = category

            r = _req.post(
                f"{_SUPABASE_URL}/rest/v1/rpc/search_products_semantic",
                headers={**_sb_headers(), "Prefer": ""},
                json=params,
                timeout=8,
            )
            if not r.ok:
                logger.warning("Vector search RPC failed: %s", r.text[:200])
                return []
            return [
                SemanticResult(
                    product_key=row["product_key"],
                    product_title=row["product_title"],
                    store=row["store"],
                    category=row.get("category", ""),
                    price=float(row["price"]) if row.get("price") else None,
                    similarity=float(row.get("similarity", 0)),
                    metadata=row.get("metadata") or {},
                )
                for row in r.json()
            ]
        except Exception as exc:
            logger.warning("_vector_search failed: %s", exc)
            return []

    def _keyword_fallback(
        self, query: str, *, store: str | None, limit: int
    ) -> list[SemanticResult]:
        """pgvector çalışmazsa Supabase full-text search'e düş."""
        try:
            params: dict[str, Any] = {
                "select": "product_key,product_title,store,category,price,metadata",
                "product_title": f"ilike.*{query[:50]}*",
                "limit": str(limit),
            }
            if store:
                params["store"] = f"eq.{store}"
            r = _req.get(
                _sb("product_embeddings"),
                params=params,
                headers={**_sb_headers(), "Prefer": ""},
                timeout=5,
            )
            return [
                SemanticResult(
                    product_key=row["product_key"],
                    product_title=row["product_title"],
                    store=row["store"],
                    category=row.get("category", ""),
                    price=float(row["price"]) if row.get("price") else None,
                    similarity=0.5,   # keyword match için sabit skor
                    metadata=row.get("metadata") or {},
                )
                for row in (r.json() if r.ok else [])
            ]
        except Exception:
            return []

    def index_catalog_items(self, store_filter: str | None = None) -> dict[str, int]:
        """
        catalog_items tablosundaki tüm ürünleri product_embeddings'e yazar.
        Cron veya manuel admin endpoint'inden çağrılır.
        """
        params: dict[str, Any] = {
            "select": "id,product_name,store,price",
            "limit":  "500",
        }
        if store_filter:
            params["store"] = f"eq.{store_filter}"
        try:
            r = _req.get(_sb("catalog_items"), params=params,
                         headers={**_sb_headers(), "Prefer": ""}, timeout=8)
            if not r.ok:
                return {"error": 1}
            items = r.json()
        except Exception:
            return {"error": 1}

        products = [
            {
                "product_key":   f"{row.get('store','?')}::{_slugify(row.get('product_name',''))}",
                "product_title": row.get("product_name", ""),
                "store":         row.get("store", ""),
                "category":      "",
                "price":         row.get("price"),
                "metadata":      {"catalog_item_id": row.get("id")},
            }
            for row in items
            if row.get("product_name")
        ]

        indexed = embed_products_batch(products)
        return {"total_input": len(products), "indexed": indexed}


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip())[:80]


# Singleton
semantic_search = SemanticSearch()
