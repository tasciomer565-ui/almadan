"""
Upstash Redis cache katmanı — Supabase cache'in önünde çalışır.
GET/SET: REST API üzerinden (serverless uyumlu, pip paketi gerekmez).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import requests as _req

logger = logging.getLogger(__name__)

_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
_TTL   = int(os.getenv("CACHE_TTL_HOURS", "6")) * 3600  # saniye


def _enabled() -> bool:
    return bool(_URL and _TOKEN)


def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _safe_key(key: str) -> str:
    """Redis key'de boşluk/özel karakter olmaması için temizle."""
    import re
    return re.sub(r'[^\w\-|.]', '_', key)[:200]


def rget(key: str) -> list[dict] | None:
    if not _enabled():
        return None
    try:
        k = _safe_key(key)
        r = _req.get(f"{_URL}/get/{urllib.parse.quote(k, safe='')}", headers=_headers(), timeout=2)
        if r.ok:
            val = r.json().get("result")
            if val:
                return json.loads(val)
    except Exception as exc:
        logger.warning("Redis GET hata: %s", exc)
    return None


def rset(key: str, data: list[dict]) -> None:
    if not _enabled() or not data:
        return
    try:
        k = _safe_key(key)
        payload = json.dumps(data, ensure_ascii=False)
        # Upstash REST: POST /set/<key>/<value>?EX=<ttl>
        _req.post(
            f"{_URL}/set/{urllib.parse.quote(k, safe='')}",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
            params={"EX": _TTL},
            timeout=2
        )
    except Exception as exc:
        logger.warning("Redis SET hata: %s", exc)


def rdel(key: str) -> None:
    if not _enabled():
        return
    try:
        _req.get(f"{_URL}/del/{key}", headers=_headers(), timeout=2)
    except Exception:
        pass
