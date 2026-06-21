"""
Google Sheets Senkronizasyonu — Almadan
Kullanıcı bazlı özet görünüm: bir satır = bir kullanıcı, 3 veri sütunu.

Gerekli Vercel env değişkenleri:
  GOOGLE_SERVICE_ACCOUNT_JSON  — servis hesabı JSON içeriği
  GOOGLE_SHEET_ID              — sheet URL'sindeki uzun ID
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests as _req

logger = logging.getLogger(__name__)

_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_TOKEN_URL    = "https://oauth2.googleapis.com/token"


def _get_access_token() -> str:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON env değişkeni ayarlanmamış.")
    creds = json.loads(raw)

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())

    def _b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()

    signing_input = f"{_b64({'alg':'RS256','typ':'JWT'})}.{_b64({'iss':creds['client_email'],'scope':_SHEETS_SCOPE,'aud':_TOKEN_URL,'iat':now,'exp':now+3600})}".encode()
    private_key   = serialization.load_pem_private_key(creds["private_key"].encode(), password=None)
    sig           = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    jwt_token     = signing_input.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    resp = _req.post(_TOKEN_URL, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt_token}, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _api(method: str, url: str, token: str, **kwargs):
    return _req.request(method, url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=20, **kwargs)


def _sb_url() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def _sb_hdrs() -> dict:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _fmt_date(iso: str) -> str:
    return (iso or "")[:10]


def sync_to_sheets(local_db: dict) -> dict:
    """
    Tek sekme 'Kullanıcı Aktiviteleri':
      Kullanıcı | Email | Yapıştırılan Linkler | Takip Edilen Ürünler | Takip Edilen Mağazalar | Son Aktivite
    """
    token    = _get_access_token()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID env değişkeni ayarlanmamış.")

    base_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    now_ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Veri topla ────────────────────────────────────────────────────────────

    # user_events: url_search + product_track
    events_resp = _req.get(f"{_sb_url()}/rest/v1/user_events",
                           headers=_sb_hdrs(),
                           params={"order": "created_at.desc", "limit": "5000",
                                   "select": "user_id,event_type,payload,created_at"},
                           timeout=15)
    events = events_resp.json() if events_resp.ok else []

    # followed_stores
    follows_resp = _req.get(f"{_sb_url()}/rest/v1/followed_stores",
                            headers=_sb_hdrs(),
                            params={"order": "created_at.desc", "limit": "5000",
                                    "select": "user_id,email,store_slug,created_at"},
                            timeout=15)
    follows = follows_resp.json() if follows_resp.ok else []

    # auth.users emaillerini al (user_id → email mapping)
    users_resp = _req.get(f"{_sb_url()}/auth/v1/admin/users",
                          headers=_sb_hdrs(),
                          params={"per_page": "1000"},
                          timeout=15)
    email_map: dict[str, str] = {}
    if users_resp.ok:
        for u in (users_resp.json().get("users") or []):
            email_map[u["id"]] = u.get("email", "")

    # followed_stores'dan da email al
    for f in follows:
        if f.get("user_id") and f.get("email"):
            email_map.setdefault(f["user_id"], f["email"])

    # ── Kullanıcı bazlı grupla ────────────────────────────────────────────────
    links:    dict[str, list[str]] = defaultdict(list)
    products: dict[str, list[str]] = defaultdict(list)
    stores:   dict[str, list[str]] = defaultdict(list)
    last_act: dict[str, str]       = {}

    for ev in events:
        uid  = ev.get("user_id") or "anonim"
        p    = ev.get("payload") or {}
        date = _fmt_date(ev.get("created_at", ""))
        if not last_act.get(uid) or date > last_act[uid]:
            last_act[uid] = date

        if ev["event_type"] == "url_search" and p.get("query"):
            entry = f'{p["query"]} ({date})'
            if entry not in links[uid]:
                links[uid].append(entry)

        elif ev["event_type"] == "product_track" and p.get("title"):
            price = f' ₺{p["price"]}' if p.get("price") else ""
            entry = f'{p["title"]}{price} ({date})'
            if entry not in products[uid]:
                products[uid].append(entry)

    for f in follows:
        uid  = f.get("user_id") or "anonim"
        slug = f.get("store_slug", "")
        if slug and slug not in stores[uid]:
            stores[uid].append(slug)
        date = _fmt_date(f.get("created_at", ""))
        if not last_act.get(uid) or date > last_act[uid]:
            last_act[uid] = date

    # Dosya tabanlı DB ürünleri
    for pr in (local_db.get("products") or []):
        uid  = pr.get("owner_id", "anonim")
        price = f' ₺{pr["price"]}' if pr.get("price") else ""
        entry = f'{pr.get("title","")}{price}'
        if entry not in products[uid]:
            products[uid].append(entry)

    # ── Tüm user_id'leri birleştir ────────────────────────────────────────────
    all_users = set(links) | set(products) | set(stores)

    # ── Satırları oluştur ─────────────────────────────────────────────────────
    header = ["Kullanıcı ID", "Email", "Yapıştırılan Linkler", "Takip Edilen Ürünler",
              "Takip Edilen Mağazalar", "Son Aktivite"]
    rows = [header]
    for uid in sorted(all_users):
        rows.append([
            uid,
            email_map.get(uid, ""),
            "\n".join(links[uid][:50]),
            "\n".join(products[uid][:50]),
            ", ".join(stores[uid]),
            last_act.get(uid, ""),
        ])

    # ── Google Sheets'e yaz ───────────────────────────────────────────────────
    # Sekme var mı kontrol et / oluştur
    tab = "Kullanıcı Aktiviteleri"
    meta = _api("GET", base_url, token).json()
    tab_exists = any(s["properties"]["title"] == tab for s in meta.get("sheets", []))
    if not tab_exists:
        _api("POST", f"{base_url}:batchUpdate", token,
             json={"requests": [{"addSheet": {"properties": {"title": tab}}}]})

    # Temizle
    _api("POST", f"{base_url}/values/{tab}!A1:Z50000:clear", token, json={})

    # Yaz
    _api("PUT", f"{base_url}/values/{tab}!A1", token,
         json={"values": [[str(c) for c in row] for row in rows]},
         params={"valueInputOption": "USER_ENTERED"})

    # Header satırını bold + freeze yap
    sheet_gid = next((s["properties"]["sheetId"] for s in
                      _api("GET", base_url, token).json().get("sheets", [])
                      if s["properties"]["title"] == tab), 0)
    _api("POST", f"{base_url}:batchUpdate", token, json={"requests": [
        {"repeatCell": {
            "range": {"sheetId": sheet_gid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                           "backgroundColor": {"red": 0.16, "green": 0.24, "blue": 0.16}}},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }},
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_gid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},
    ]})

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    logger.info("Sheets sync OK: %d kullanıcı, sync: %s", len(all_users), now_ts)
    return {
        "users":     len(all_users),
        "links":     sum(len(v) for v in links.values()),
        "products":  sum(len(v) for v in products.values()),
        "stores":    sum(len(v) for v in stores.values()),
        "sheet_url": sheet_url,
        "synced_at": now_ts,
    }
