"""
NotificationOrchestrator — Sprint 4: Katalog Eşleşme Bildirimleri

Akış:
  1. CatalogParser → [CatalogItem, ...]
  2. MatchingEngine → [MatchResult, ...]
  3. NotificationOrchestrator → Push Notification (WebPush + DB log)

Bildirim formatı:
  📢 "Pınar Süt 1L Migros'ta ₺24,90'a indi! (Normalde ₺29,90)"

Duplikasyon koruması:
  - catalog_matches tablosunda UNIQUE (catalog_item_id, user_id, watchlist_title)
  - 24 saatte bir kez bildirim gönderilebilir
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

import requests

from app.matching_engine import MatchResult, MatchSummary

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())


def _db_ok() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


# ── Bildirim Mesaj Fabrikası ─────────────────────────────────

def _build_push_payload(match: MatchResult, store_display: str) -> dict:
    """Push notification payload oluştur."""
    title = f"🛒 {store_display}'de İndirim!"

    if match.price and match.original_price and match.discount_pct:
        body = (
            f"{match.catalog_product} şimdi ₺{match.price:.2f}! "
            f"(Normalde ₺{match.original_price:.2f}, %{match.discount_pct} indirim)"
        )
    elif match.price:
        body = f"{match.catalog_product} → ₺{match.price:.2f}"
    else:
        body = f"{match.catalog_product} şu an {store_display} katalogunda!"

    # "Takip ettiğin Pınar Süt" gibi kişiselleştirilmiş başlık
    if match.watchlist_title.lower() not in match.catalog_product.lower():
        body = f"Takip ettiğin '{match.watchlist_title}' bulundu! " + body

    return {
        "title": title,
        "body":  body,
        "tag":   f"catalog-{match.store}-{match.catalog_item_id}",
        "data": {
            "url":              f"/?q={requests.utils.quote(match.catalog_product)}&category=GIDA",
            "store":            match.store,
            "price":            match.price,
            "discount_pct":     match.discount_pct,
            "catalog_item_id":  match.catalog_item_id,
            "watchlist_title":  match.watchlist_title,
        },
        "icon":  "/static/icon-192.png",
        "badge": "/static/icon-192.png",
    }


_STORE_DISPLAY = {
    "migros":    "Migros",
    "carrefoursa": "CarrefourSA",
    "a101":      "A101",
    "bim":       "BİM",
    "sok":       "ŞOK",
    "file":      "File Market",
    "metro":     "Metro",
    "gratis":    "Gratis",
}


# ── NotificationOrchestrator ─────────────────────────────────

class NotificationOrchestrator:
    """
    Katalog eşleşmelerini kullanıcılara bildirir.

    Kullanım:
        orch = NotificationOrchestrator()
        sent = orch.notify_matches(match_summary)
        # → {"sent": 3, "skipped": 1, "errors": 0}
    """

    def notify_matches(self, summary: MatchSummary) -> dict[str, int]:
        """
        Eşleşen her ürün için kullanıcıya push bildirim gönder.
        Daha önce gönderilmiş (24h içinde) olanları atla.
        """
        stats = {"sent": 0, "skipped": 0, "errors": 0}
        if not summary.matches:
            return stats

        for match in summary.matches:
            try:
                sent = self._notify_single_match(match, summary.user_id, summary.device_id)
                if sent:
                    stats["sent"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.warning("notify_matches error match=%s: %s", match.catalog_product, e)
                stats["errors"] += 1

        return stats

    def _notify_single_match(
        self,
        match: MatchResult,
        user_id: str | None,
        device_id: str | None,
    ) -> bool:
        """Tek bir eşleşme için bildirim gönder. True → gönderildi."""
        if not user_id and not device_id:
            return False

        # Duplikasyon kontrolü — 24h içinde aynı eşleşme gönderilmişse atla
        if self._already_notified(match, user_id):
            return False

        # catalog_matches'e kayıt (UNIQUE constraint ile duplicate koruması)
        match_record = self._save_match(match, user_id, device_id)
        if match_record is None:
            return False  # UNIQUE conflict → zaten kaydedilmiş

        # Push notification gönder
        payload = _build_push_payload(match, _STORE_DISPLAY.get(match.store, match.store.title()))
        sent = self._send_push_to_user(user_id or f"device:{device_id}", payload)

        # Bildirim gönderildi olarak işaretle
        if sent and match_record.get("id"):
            self._mark_notified(match_record["id"])

        # Ayrıca DB notification tablosuna da ekle (in-app bildirim için)
        self._save_in_app_notification(match, user_id, device_id, payload)

        return sent

    def _already_notified(self, match: MatchResult, user_id: str | None) -> bool:
        """Son 24 saatte bu eşleşme için bildirim gönderildi mi?"""
        if not _db_ok() or not user_id or not match.catalog_item_id:
            return False
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/catalog_matches",
                params={
                    "user_id":         f"eq.{user_id}",
                    "catalog_item_id": f"eq.{match.catalog_item_id}",
                    "watchlist_title": f"eq.{match.watchlist_title}",
                    "notified":        "eq.true",
                    "notified_at":     "gte.now()-interval '24 hours'",
                    "limit":           "1",
                },
                headers=_headers(),
                timeout=4,
            )
            return bool(resp.ok and resp.json())
        except Exception:
            return False

    def _save_match(
        self,
        match: MatchResult,
        user_id: str | None,
        device_id: str | None,
    ) -> dict | None:
        """catalog_matches tablosuna kayıt yaz (duplikat → None döner)."""
        if not _db_ok():
            # DB yoksa direkt bildirim gönder
            return {"id": None}
        record = {
            "catalog_item_id": match.catalog_item_id,
            "user_id":         user_id,
            "device_id":       device_id,
            "watchlist_title": match.watchlist_title,
            "match_score":     match.score,
        }
        try:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/catalog_matches",
                headers={**_headers(), "Prefer": "return=representation,resolution=ignore-duplicates"},
                json=record,
                timeout=4,
            )
            rows = resp.json() if resp.ok else []
            return rows[0] if rows else None   # None → duplicate
        except Exception as e:
            logger.warning("save_match error: %s", e)
            return {"id": None}

    def _mark_notified(self, match_db_id: int) -> None:
        if not _db_ok():
            return
        try:
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/catalog_matches?id=eq.{match_db_id}",
                headers=_headers(),
                json={"notified": True, "notified_at": "now()"},
                timeout=4,
            )
        except Exception:
            pass

    def _send_push_to_user(self, owner_id: str, payload: dict) -> bool:
        """push.py'deki mevcut WebPush altyapısını kullan."""
        try:
            from app.push import send_push_to_owner
            result = send_push_to_owner(owner_id, payload)
            return result.get("sent", 0) > 0
        except Exception as e:
            logger.warning("Push send failed owner=%s: %s", owner_id, e)
            return False

    def _save_in_app_notification(
        self,
        match: MatchResult,
        user_id: str | None,
        device_id: str | None,
        payload: dict,
    ) -> None:
        """In-app bildirim tablosuna (notifications) ekle."""
        from app.storage import load_db, save_db
        owner_id = f"user:{user_id}" if user_id else f"device:{device_id}"
        try:
            db = load_db()
            notifications = db.setdefault("notifications", [])
            notifications.insert(0, {
                "id":      f"cat-{match.store}-{match.catalog_item_id}-{match.watchlist_title[:20]}",
                "owner_id": owner_id,
                "title":   payload["title"],
                "body":    payload["body"],
                "type":    "catalog_match",
                "data":    payload.get("data", {}),
                "read":    False,
                "created_at": __import__("app.storage", fromlist=["utc_now"]).utc_now(),
            })
            # Max 100 bildirim tut
            db["notifications"] = notifications[:100]
            save_db(db)
        except Exception as e:
            logger.warning("In-app notification save error: %s", e)


# ── Otomasyon: Tam Katalog Tarama Döngüsü ───────────────────

class CatalogAutomation:
    """
    Pazartesi/Perşembe katalog günlerinde otomatik çalışır.
    /api/cron/catalog-scan endpoint'inden tetiklenir.

    Akış:
      1. Tüm market kataloglarını çek (catalogs.py)
      2. Her katalog HTML'ini CatalogParser ile işle
      3. Tüm kullanıcıların watchlist'ini al
      4. MatchingEngine ile eşleştir
      5. NotificationOrchestrator ile bildir
      6. catalog_runs tablosuna özet kaydet
    """

    def __init__(self):
        from app.catalog_parser import catalog_parser
        from app.matching_engine import matching_engine
        self.parser  = catalog_parser
        self.matcher = matching_engine
        self.notifier = NotificationOrchestrator()

    def run(self, store_filter: str | None = None) -> dict:
        """
        Tam katalog tarama ve eşleştirme döngüsü.
        store_filter=None → tüm marketler.
        """
        from app.catalogs import fetch_all_catalogs, CATALOG_SOURCES

        logger.info("Katalog otomasyon başladı. store_filter=%s", store_filter)
        stats = {
            "stores_scanned": 0,
            "items_parsed":   0,
            "matches_found":  0,
            "notifications":  0,
        }

        # 1. Katalogları çek
        snapshots = fetch_all_catalogs()

        for snapshot in snapshots:
            store = snapshot.get("store", "")
            if store_filter and store != store_filter:
                continue
            if not snapshot.get("ok") or not snapshot.get("items"):
                continue

            # 2. HTML snapshot'ı parse et
            html_text = "\n".join(snapshot.get("items", []))
            catalog_items = self.parser.parse_text(html_text, store=store)
            stats["stores_scanned"] += 1
            stats["items_parsed"]   += len(catalog_items)

            if not catalog_items:
                continue

            # 3. catalog_items DB'ye kaydet
            self._save_catalog_items(store, catalog_items, snapshot)

            # 4. Tüm kullanıcıların watchlist'ini al
            user_watchlists = self._load_all_watchlists()

            # 5. Her kullanıcı için eşleştir + bildir
            for user_id, wl_items in user_watchlists.items():
                if not wl_items:
                    continue
                wl_titles = [item.get("title", "") for item in wl_items if item.get("title")]
                summary = self.matcher.match(
                    watchlist=wl_titles,
                    catalog_items=catalog_items,
                    store=store,
                    user_id=user_id,
                )
                if summary.matches:
                    stats["matches_found"] += summary.match_count
                    notif_stats = self.notifier.notify_matches(summary)
                    stats["notifications"] += notif_stats.get("sent", 0)

        logger.info("Katalog otomasyon tamamlandı: %s", stats)
        return stats

    def _save_catalog_items(
        self, store: str, items: list, snapshot: dict
    ) -> str | None:
        """catalog_runs + catalog_items DB'ye kaydet."""
        if not _db_ok():
            return None
        try:
            # catalog_runs kaydı
            run_resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/catalog_runs",
                headers=_headers(),
                json={
                    "store":       store,
                    "source_url":  snapshot.get("url", ""),
                    "source_type": "html",
                    "status":      "done",
                    "item_count":  len(items),
                    "fingerprint": snapshot.get("fingerprint"),
                },
                timeout=5,
            )
            run_id = None
            if run_resp.ok and run_resp.json():
                run_id = run_resp.json()[0].get("run_id")

            # catalog_items toplu insert (max 50'lik batch)
            batch = []
            for item in items[:200]:
                d = item.to_dict() if hasattr(item, "to_dict") else item
                batch.append({
                    "run_id":       run_id,
                    "store":        store,
                    "raw_text":     d.get("raw_text", "")[:500],
                    "product_name": d.get("product_name", "")[:200],
                    "price":        d.get("price"),
                    "original_price": d.get("original_price"),
                    "discount_pct": d.get("discount_pct"),
                    "unit":         d.get("unit"),
                    "confidence":   d.get("confidence", 1.0),
                })
                if len(batch) == 50:
                    self._batch_insert("catalog_items", batch)
                    batch = []
            if batch:
                self._batch_insert("catalog_items", batch)
            return run_id
        except Exception as e:
            logger.warning("save_catalog_items error: %s", e)
            return None

    @staticmethod
    def _batch_insert(table: str, records: list) -> None:
        try:
            requests.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers={**_headers(), "Prefer": "resolution=ignore-duplicates"},
                json=records,
                timeout=10,
            )
        except Exception as e:
            logger.warning("batch_insert %s error: %s", table, e)

    @staticmethod
    def _load_all_watchlists() -> dict[str, list]:
        """Supabase'den tüm kullanıcıların ürün listesini çek."""
        if not _db_ok():
            return {}
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/products",
                params={"select": "owner_id,title,name", "limit": "5000"},
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                timeout=8,
            )
            if not resp.ok:
                return {}
            user_map: dict[str, list] = {}
            for row in resp.json():
                owner = row.get("owner_id", "")
                if not owner or not owner.startswith("user:"):
                    continue
                user_id = owner.replace("user:", "")
                user_map.setdefault(user_id, []).append({
                    "title": row.get("title") or row.get("name", ""),
                })
            return user_map
        except Exception as e:
            logger.warning("load_all_watchlists error: %s", e)
            return {}


# ── Modül seviyesi örnekler ──────────────────────────────────
notification_orchestrator = NotificationOrchestrator()
catalog_automation        = CatalogAutomation()
