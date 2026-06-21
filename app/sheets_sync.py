"""
Google Sheets Senkronizasyonu — Almadan
Kullanıcı bazlı 3 ayrı sekme:
  1. Yapıştırılan Linkler    (user_events.url_search)
  2. Takip Edilen Ürünler    (product_reminders + user_events.product_track)
  3. Takip Edilen Mağazalar  (followed_stores)

Gerekli Vercel env değişkenleri:
  GOOGLE_SERVICE_ACCOUNT_JSON  — servis hesabı JSON içeriği (tek satır string)
  GOOGLE_SHEET_ID              — sheet URL'sindeki uzun ID
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import requests as _req

logger = logging.getLogger(__name__)


def _sb_url() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def _sb_hdrs() -> dict:
    return {
        "apikey":        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
        "Content-Type":  "application/json",
    }


def _get_sheet():
    """Kimlik doğrulama + Google Sheet nesnesini döner."""
    import gspread
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON env değişkeni ayarlanmamış.")
    creds_dict = json.loads(raw)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID env değişkeni ayarlanmamış.")
    return gc.open_by_key(sheet_id)


def _ensure_worksheet(spreadsheet, title: str, header: list[str]):
    """Sekme yoksa oluştur, header satırını yaz."""
    try:
        ws = spreadsheet.worksheet(title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=5000, cols=len(header))
    ws.clear()
    ws.append_row(header, value_input_option="USER_ENTERED")
    return ws


def sync_to_sheets(local_db: dict) -> dict:
    """
    3 sekmeye veri yaz.
    local_db: load_db() çıktısı (takip edilen ürünler için).
    Dönen dict: {"links": int, "products": int, "stores": int, "sheet_url": str}
    """
    spreadsheet = _get_sheet()
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── 1. Yapıştırılan Linkler ───────────────────────────────────────────────
    ws_links = _ensure_worksheet(
        spreadsheet,
        "Yapıştırılan Linkler",
        ["Kullanıcı ID", "Arama Sorgusu", "Kategori", "Sonuç Sayısı", "Tarih"],
    )
    link_events = _req.get(
        f"{_sb_url()}/rest/v1/user_events",
        headers=_sb_hdrs(),
        params={
            "event_type": "eq.url_search",
            "order":      "created_at.desc",
            "limit":      "2000",
            "select":     "user_id,payload,created_at",
        },
        timeout=15,
    )
    link_rows = []
    for ev in (link_events.json() if link_events.ok else []):
        p = ev.get("payload") or {}
        link_rows.append([
            ev.get("user_id") or "anonim",
            p.get("query", ""),
            p.get("category", ""),
            p.get("result_count", ""),
            ev.get("created_at", "")[:19].replace("T", " "),
        ])
    if link_rows:
        ws_links.append_rows(link_rows, value_input_option="USER_ENTERED")

    # ── 2. Takip Edilen Ürünler ───────────────────────────────────────────────
    ws_prods = _ensure_worksheet(
        spreadsheet,
        "Takip Edilen Ürünler",
        ["Kullanıcı ID", "Ürün Adı", "URL", "Fiyat", "Mağaza", "Eklenme Tarihi"],
    )
    prod_events = _req.get(
        f"{_sb_url()}/rest/v1/user_events",
        headers=_sb_hdrs(),
        params={
            "event_type": "eq.product_track",
            "order":      "created_at.desc",
            "limit":      "2000",
            "select":     "user_id,payload,created_at",
        },
        timeout=15,
    )
    prod_rows = []
    for ev in (prod_events.json() if prod_events.ok else []):
        p = ev.get("payload") or {}
        prod_rows.append([
            ev.get("user_id") or "anonim",
            p.get("title", ""),
            p.get("url", ""),
            p.get("price", ""),
            p.get("source", ""),
            ev.get("created_at", "")[:19].replace("T", " "),
        ])
    # Dosya tabanlı DB ürünlerini de ekle
    for product in (local_db.get("products") or []):
        prod_rows.append([
            product.get("owner_id", ""),
            product.get("title", ""),
            product.get("url", ""),
            product.get("price", ""),
            product.get("source", ""),
            product.get("added_at", "")[:19].replace("T", " ") if product.get("added_at") else "",
        ])
    if prod_rows:
        ws_prods.append_rows(prod_rows, value_input_option="USER_ENTERED")

    # ── 3. Takip Edilen Mağazalar ─────────────────────────────────────────────
    ws_stores = _ensure_worksheet(
        spreadsheet,
        "Takip Edilen Mağazalar",
        ["Kullanıcı ID", "Email", "Mağaza", "Takip Tarihi"],
    )
    follows = _req.get(
        f"{_sb_url()}/rest/v1/followed_stores",
        headers=_sb_hdrs(),
        params={
            "order":  "created_at.desc",
            "limit":  "5000",
            "select": "user_id,email,store_slug,created_at",
        },
        timeout=15,
    )
    store_rows = []
    for row in (follows.json() if follows.ok else []):
        store_rows.append([
            row.get("user_id", ""),
            row.get("email", ""),
            row.get("store_slug", ""),
            (row.get("created_at") or "")[:19].replace("T", " "),
        ])
    if store_rows:
        ws_stores.append_rows(store_rows, value_input_option="USER_ENTERED")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
    logger.info("Google Sheets sync: %d link, %d ürün, %d mağaza → %s",
                len(link_rows), len(prod_rows), len(store_rows), sheet_url)

    return {
        "links":     len(link_rows),
        "products":  len(prod_rows),
        "stores":    len(store_rows),
        "sheet_url": sheet_url,
        "synced_at": now_ts,
    }
