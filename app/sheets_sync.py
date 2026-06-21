"""
Google Sheets Senkronizasyonu — Almadan
gspread yerine doğrudan Google Sheets REST API kullanır (Vercel uyumlu).

Gerekli Vercel env değişkenleri:
  GOOGLE_SERVICE_ACCOUNT_JSON  — servis hesabı JSON içeriği
  GOOGLE_SHEET_ID              — sheet URL'sindeki uzun ID
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import requests as _req

logger = logging.getLogger(__name__)

_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_TOKEN_URL    = "https://oauth2.googleapis.com/token"


def _get_access_token() -> str:
    """Service Account JSON'dan OAuth2 access token alır."""
    import base64, hashlib, hmac
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON env değişkeni ayarlanmamış.")
    creds = json.loads(raw)

    # JWT oluştur
    now = int(time.time())
    header  = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss":   creds["client_email"],
        "scope": _SHEETS_SCOPE,
        "aud":   _TOKEN_URL,
        "iat":   now,
        "exp":   now + 3600,
    }

    def _b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    signing_input = f"{_b64(header)}.{_b64(payload)}".encode()

    # RSA-SHA256 imzası — cryptography kütüphanesi ile
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = serialization.load_pem_private_key(
        creds["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    jwt_token = signing_input.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    resp = _req.post(_TOKEN_URL, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt_token,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _sheets_request(method: str, url: str, token: str, **kwargs):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return _req.request(method, url, headers=headers, timeout=20, **kwargs)


def _ensure_sheet(token: str, sheet_id: str, title: str) -> int:
    """Sekme yoksa oluştur, sheet_id (gid) döner."""
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    meta = _sheets_request("GET", base, token).json()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    # Yoksa oluştur
    body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
    resp = _sheets_request("POST", f"{base}:batchUpdate", token, json=body).json()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def _clear_and_write(token: str, sheet_id: str, tab: str, rows: list[list]):
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    # Temizle
    _sheets_request("POST", f"{base}/values/{tab}!A1:Z10000:clear", token, json={})
    if not rows:
        return
    # Yaz
    body = {"values": [[str(c) for c in row] for row in rows]}
    _sheets_request("PUT", f"{base}/values/{tab}!A1",
                    token, json=body,
                    params={"valueInputOption": "USER_ENTERED"})


def _sb_url() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def _sb_hdrs() -> dict:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def sync_to_sheets(local_db: dict) -> dict:
    """3 sekmeye veri yaz. Döner: {links, products, stores, sheet_url, synced_at}"""
    token    = _get_access_token()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID env değişkeni ayarlanmamış.")

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── 1. Yapıştırılan Linkler ───────────────────────────────────────────────
    _ensure_sheet(token, sheet_id, "Yapıştırılan Linkler")
    link_resp = _req.get(f"{_sb_url()}/rest/v1/user_events",
                         headers=_sb_hdrs(),
                         params={"event_type": "eq.url_search", "order": "created_at.desc",
                                 "limit": "2000", "select": "user_id,payload,created_at"},
                         timeout=15)
    link_rows = [["Kullanıcı ID", "Arama Sorgusu", "Kategori", "Sonuç Sayısı", "Tarih"]]
    for ev in (link_resp.json() if link_resp.ok else []):
        p = ev.get("payload") or {}
        link_rows.append([ev.get("user_id") or "anonim", p.get("query", ""),
                          p.get("category", ""), p.get("result_count", ""),
                          (ev.get("created_at") or "")[:19].replace("T", " ")])
    _clear_and_write(token, sheet_id, "Yapıştırılan Linkler", link_rows)

    # ── 2. Takip Edilen Ürünler ───────────────────────────────────────────────
    _ensure_sheet(token, sheet_id, "Takip Edilen Ürünler")
    prod_resp = _req.get(f"{_sb_url()}/rest/v1/user_events",
                         headers=_sb_hdrs(),
                         params={"event_type": "eq.product_track", "order": "created_at.desc",
                                 "limit": "2000", "select": "user_id,payload,created_at"},
                         timeout=15)
    prod_rows = [["Kullanıcı ID", "Ürün Adı", "URL", "Fiyat", "Mağaza", "Eklenme Tarihi"]]
    for ev in (prod_resp.json() if prod_resp.ok else []):
        p = ev.get("payload") or {}
        prod_rows.append([ev.get("user_id") or "anonim", p.get("title", ""), p.get("url", ""),
                          p.get("price", ""), p.get("source", ""),
                          (ev.get("created_at") or "")[:19].replace("T", " ")])
    # Dosya tabanlı DB ürünleri
    for pr in (local_db.get("products") or []):
        prod_rows.append([pr.get("owner_id", ""), pr.get("title", ""), pr.get("url", ""),
                          pr.get("price", ""), pr.get("source", ""),
                          (pr.get("added_at") or "")[:19].replace("T", " ")])
    _clear_and_write(token, sheet_id, "Takip Edilen Ürünler", prod_rows)

    # ── 3. Takip Edilen Mağazalar ─────────────────────────────────────────────
    _ensure_sheet(token, sheet_id, "Takip Edilen Mağazalar")
    follow_resp = _req.get(f"{_sb_url()}/rest/v1/followed_stores",
                           headers=_sb_hdrs(),
                           params={"order": "created_at.desc", "limit": "5000",
                                   "select": "user_id,email,store_slug,created_at"},
                           timeout=15)
    store_rows = [["Kullanıcı ID", "Email", "Mağaza", "Takip Tarihi"]]
    for row in (follow_resp.json() if follow_resp.ok else []):
        store_rows.append([row.get("user_id", ""), row.get("email", ""),
                           row.get("store_slug", ""),
                           (row.get("created_at") or "")[:19].replace("T", " ")])
    _clear_and_write(token, sheet_id, "Takip Edilen Mağazalar", store_rows)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    logger.info("Sheets sync OK: %d link, %d ürün, %d mağaza",
                len(link_rows) - 1, len(prod_rows) - 1, len(store_rows) - 1)
    return {
        "links":     len(link_rows) - 1,
        "products":  len(prod_rows) - 1,
        "stores":    len(store_rows) - 1,
        "sheet_url": sheet_url,
        "synced_at": now_ts,
    }
