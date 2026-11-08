"""Gerçek kullanıcı aramalarından önbellek ısıtma terimleri.

Önbellekte olmayan bir sorgu canlıda (Render IP'si engelli) yalnızca tek
mağaza döndürür. `/api/search` her aramayı `user_events` tablosuna
`url_search` olayı olarak yazıyor; ısıtma betiği bu olaylardaki en çok aranan
sorguları da tarayarak "uzun kuyruğu" önbelleğe alır -- yani bir sorgu bir kez
aranınca bir sonraki ısıtma turunda çok mağazalı veriyle hazır olur.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

_URL_RE = re.compile(r"https?://|www\.|\.com|\.net", re.I)


def count_search_terms(
    events: Iterable[dict[str, Any]],
    min_len: int = 3,
    max_len: int = 60,
) -> Counter[str]:
    """`user_events` satırlarından (payload.query) normalize sorgu sayımı.

    URL yapıştırmalar, çok kısa/uzun metinler ve yalnızca rakam/sembolden oluşan
    sorgular atılır. Büyük/küçük harf ve fazla boşluk birleştirilir.
    """
    counts: Counter[str] = Counter()
    for event in events:
        payload = event.get("payload") if isinstance(event, dict) else None
        query = payload.get("query") if isinstance(payload, dict) else None
        if not isinstance(query, str):
            continue
        term = " ".join(query.lower().split())
        if not (min_len <= len(term) <= max_len) or _URL_RE.search(term):
            continue
        if not re.search(r"[a-zçğıöşü]", term):
            continue
        counts[term] += 1
    return counts
