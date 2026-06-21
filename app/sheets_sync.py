"""
Google Sheets Senkronizasyonu — Almadan (hızlı versiyon, <8s)
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
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE     = "https://www.googleapis.com/auth/spreadsheets"


def _token() -> str:
    creds = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    def _b64(d): return base64.urlsafe_b64encode(json.dumps(d, separators=(",",":")).encode()).rstrip(b"=").decode()
    inp  = f"{_b64({'alg':'RS256','typ':'JWT'})}.{_b64({'iss':creds['client_email'],'scope':_SCOPE,'aud':_TOKEN_URL,'iat':now,'exp':now+3600})}".encode()
    key  = serialization.load_pem_private_key(creds["private_key"].encode(), password=None)
    sig  = key.sign(inp, padding.PKCS1v15(), hashes.SHA256())
    jwt  = inp.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    r    = _req.post(_TOKEN_URL, data={"grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer","assertion":jwt}, timeout=8)
    r.raise_for_status()
    return r.json()["access_token"]


def _sheets(method, path, tok, **kw):
    sid = os.environ["GOOGLE_SHEET_ID"]
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}{path}"
    return _req.request(method, url, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, timeout=8, **kw)


def _sb():
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return os.environ["SUPABASE_URL"].rstrip("/"), {"apikey": key, "Authorization": f"Bearer {key}"}


def sync_to_sheets(local_db: dict) -> dict:
    sb_url, sb_hdrs = _sb()
    tok = _token()

    # Veri çek
    ev_r = _req.get(f"{sb_url}/rest/v1/user_events",    headers=sb_hdrs, params={"order":"created_at.desc","limit":"3000","select":"user_id,event_type,payload,created_at"}, timeout=6)
    fs_r = _req.get(f"{sb_url}/rest/v1/followed_stores", headers=sb_hdrs, params={"order":"created_at.desc","limit":"3000","select":"user_id,email,store_slug,created_at"}, timeout=6)
    # Auth kullanıcıları — email mapping için
    au_r = _req.get(f"{sb_url}/auth/v1/admin/users", headers=sb_hdrs, params={"per_page":"1000"}, timeout=6)

    events  = ev_r.json() if ev_r.ok else []
    follows = fs_r.json() if fs_r.ok else []

    # Email map: user_id → email (auth tablosundan)
    emails: dict[str, str] = {}
    if au_r.ok:
        for u in (au_r.json().get("users") or []):
            if u.get("id") and u.get("email"):
                emails[u["id"]] = u["email"]

    # Kullanıcı bazlı grupla
    links:    dict[str, list[str]] = defaultdict(list)
    products: dict[str, list[str]] = defaultdict(list)
    stores:   dict[str, list[str]] = defaultdict(list)
    last_act: dict[str, str]       = {}

    for ev in events:
        uid  = ev.get("user_id") or "anonim"
        p    = ev.get("payload") or {}
        date = (ev.get("created_at") or "")[:10]
        if not last_act.get(uid) or date > last_act[uid]: last_act[uid] = date
        if ev["event_type"] == "url_search" and p.get("query"):
            e = f'{p["query"]} ({date})'
            if len(links[uid]) < 30 and e not in links[uid]: links[uid].append(e)
        elif ev["event_type"] == "product_track" and p.get("title"):
            price = f' ₺{p["price"]}' if p.get("price") else ""
            e = f'{p["title"]}{price} ({date})'
            if len(products[uid]) < 30 and e not in products[uid]: products[uid].append(e)

    for f in follows:
        uid = f.get("user_id") or "anonim"
        if f.get("email") and uid not in emails: emails[uid] = f["email"]
        slug = f.get("store_slug", "")
        if slug and slug not in stores[uid]: stores[uid].append(slug)
        date = (f.get("created_at") or "")[:10]
        if not last_act.get(uid) or date > last_act[uid]: last_act[uid] = date

    for pr in (local_db.get("products") or []):
        uid = pr.get("owner_id", "anonim")
        price = f' ₺{pr["price"]}' if pr.get("price") else ""
        e = f'{pr.get("title","")}{price}'
        if len(products[uid]) < 30 and e not in products[uid]: products[uid].append(e)

    all_users = set(links) | set(products) | set(stores)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Satırları oluştur
    rows = [["Kullanıcı ID", "Email", "Yapıştırılan Linkler", "Takip Edilen Ürünler", "Takip Edilen Mağazalar", "Son Aktivite", "Güncelleme"]]
    for uid in sorted(all_users):
        rows.append([
            uid,
            emails.get(uid, ""),
            "\n".join(links[uid]),
            "\n".join(products[uid]),
            ", ".join(stores[uid]),
            last_act.get(uid, ""),
            now_ts,
        ])

    # Sekme adı
    tab = "Kullanıcı Aktiviteleri"

    # Var mı kontrol et, yoksa oluştur
    meta = _sheets("GET", "", tok).json()
    if not any(s["properties"]["title"] == tab for s in meta.get("sheets", [])):
        _sheets("POST", ":batchUpdate", tok, json={"requests":[{"addSheet":{"properties":{"title":tab}}}]})

    # Temizle + yaz
    _sheets("POST", f"/values/{tab}!A1:Z50000:clear", tok, json={})
    _sheets("PUT",  f"/values/{tab}!A1", tok,
            json={"values": [[str(c) for c in r] for r in rows]},
            params={"valueInputOption": "USER_ENTERED"})

    sheet_url = f"https://docs.google.com/spreadsheets/d/{os.environ['GOOGLE_SHEET_ID']}"
    return {"users": len(all_users), "links": sum(len(v) for v in links.values()),
            "products": sum(len(v) for v in products.values()),
            "stores": sum(len(v) for v in stores.values()),
            "sheet_url": sheet_url, "synced_at": now_ts}
