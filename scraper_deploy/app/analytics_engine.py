"""
UserAnalyticsEngine — Sprint 5: Kullanıcı Tasarruf Paneli

Sorumluluklar:
  - Kullanıcı etkinliklerini kaydet (arama, görüntüleme, watchlist, satın alma)
  - Tasarruf özetleri üret: toplam, aylık, market karşılaştırma
  - Dashboard için tek API çağrısıyla tüm veriyi döndür
  - Admin sistem sağlığı metriklerini kaydet/oku
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


def _rpc(fn: str, params: dict) -> Any:
    r = _req.post(
        f"{_SUPABASE_URL}/rest/v1/rpc/{fn}",
        headers={**_headers(), "Prefer": ""},
        json=params,
        timeout=8,
    )
    if r.ok:
        return r.json()
    logger.warning("RPC %s failed: %s", fn, r.text[:200])
    return None


# ── Veri sınıfları ────────────────────────────────────────────

@dataclass
class SavingsSummary:
    user_id: str
    total_saved: float = 0.0
    save_count: int = 0
    monthly: list[dict] = field(default_factory=list)
    by_store: list[dict] = field(default_factory=list)
    points: int = 0
    streak_days: int = 0


@dataclass
class DashboardData:
    user_id: str
    savings: SavingsSummary
    recent_deals: list[dict] = field(default_factory=list)
    price_alerts: list[dict] = field(default_factory=list)
    ab_variants: dict[str, str] = field(default_factory=dict)


# ── UserAnalyticsEngine ───────────────────────────────────────

class UserAnalyticsEngine:
    """
    Kullanıcı davranışını izler, tasarruf metriklerini hesaplar ve
    dashboard için veri üretir.
    """

    # ── Etkinlik Takibi ──────────────────────────────────────

    def track_event(
        self,
        event_type: str,
        *,
        user_id: str | None = None,
        device_id: str | None = None,
        session_id: str | None = None,
        payload: dict | None = None,
        platform: str = "web",
    ) -> bool:
        """
        Kullanıcı etkinliğini user_analytics_events tablosuna kaydeder.

        event_type örnekleri:
          search, view_product, add_watchlist, remove_watchlist,
          click_buy, share, open_app, catalog_viewed
        """
        if not user_id and not device_id:
            return False

        row = {
            "user_id": user_id,
            "device_id": device_id,
            "event_type": event_type,
            "payload": payload or {},
            "session_id": session_id,
            "platform": platform,
        }
        try:
            r = _req.post(_sb("user_analytics_events"), headers=_headers(), json=row, timeout=4)
            return r.ok
        except Exception as exc:
            logger.debug("track_event failed: %s", exc)
            return False

    def record_saving(
        self,
        *,
        user_id: str | None,
        device_id: str | None,
        product_title: str,
        store: str,
        price: float,
        original_price: float | None = None,
        saved_pct: int | None = None,
        catalog_match_id: int | None = None,
    ) -> bool:
        """
        Bir katalog eşleşmesinden tasarruf kaydeder.
        NotificationOrchestrator, eşleşme bildirimi gönderdikten sonra çağırır.
        """
        saved_amount: float | None = None
        if original_price and original_price > price:
            saved_amount = round(original_price - price, 2)

        row = {
            "user_id": user_id,
            "device_id": device_id,
            "product_title": product_title,
            "store": store,
            "price": price,
            "original_price": original_price,
            "saved_amount": saved_amount,
            "saved_pct": saved_pct,
            "catalog_match_id": catalog_match_id,
        }
        try:
            r = _req.post(_sb("user_savings"), headers=_headers(), json=row, timeout=4)
            return r.ok
        except Exception as exc:
            logger.debug("record_saving failed: %s", exc)
            return False

    # ── Tasarruf Özetleri ────────────────────────────────────

    def get_savings_summary(self, user_id: str) -> SavingsSummary:
        """
        Kullanıcının tüm tasarruf verilerini döndürür.
        Supabase RPC fonksiyonlarını kullanır.
        """
        summary = SavingsSummary(user_id=user_id)

        # Aylık tasarruf (son 12 ay)
        monthly = _rpc("get_monthly_savings", {"p_user_id": user_id})
        if monthly:
            summary.monthly = monthly
            summary.total_saved = sum(float(m.get("total_saved", 0)) for m in monthly)
            summary.save_count = sum(int(m.get("save_count", 0)) for m in monthly)

        # Market karşılaştırma
        by_store = _rpc("get_store_comparison", {"p_user_id": user_id})
        if by_store:
            summary.by_store = by_store

        # Toplam puan
        try:
            r = _req.get(
                _sb("user_points_summary"),
                params={"user_id": f"eq.{user_id}", "select": "total_points"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if r.ok and r.json():
                summary.points = int(r.json()[0].get("total_points", 0))
        except Exception:
            pass

        # Giriş serisi (streak): son kaç gün arka arkaya open_app eventi var
        summary.streak_days = self._calc_streak(user_id)

        return summary

    def get_price_history(self, user_id: str, product_title: str) -> list[dict]:
        """
        Kullanıcının watchlist'indeki bir ürün için fiyat geçmişi.
        catalog_matches tablosundan zaman serisi döndürür.
        """
        try:
            r = _req.get(
                _sb("catalog_matches"),
                params={
                    "user_id": f"eq.{user_id}",
                    "watchlist_title": f"ilike.*{product_title[:30]}*",
                    "select": "price,original_price,store,matched_at",
                    "order": "matched_at.asc",
                    "limit": "90",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    def get_dashboard_data(
        self,
        user_id: str,
        *,
        device_id: str | None = None,
        ab_engine: "ABTestEngine | None" = None,
    ) -> DashboardData:
        """
        Frontend dashboard için tek API çağrısıyla tam veri seti.
        """
        savings = self.get_savings_summary(user_id)

        # Son 10 indirimi bul
        recent_deals: list[dict] = []
        try:
            r = _req.get(
                _sb("user_savings"),
                params={
                    "user_id": f"eq.{user_id}",
                    "saved_amount": "gt.0",
                    "select": "product_title,store,price,original_price,saved_amount,saved_pct,recorded_at",
                    "order": "recorded_at.desc",
                    "limit": "10",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            recent_deals = r.json() if r.ok else []
        except Exception:
            pass

        # Bekleyen fiyat düşüşleri (watchlist ürünlerinin son eşleşmeleri)
        price_alerts: list[dict] = []
        try:
            r = _req.get(
                _sb("catalog_matches"),
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "watchlist_title,store,price,discount_pct,matched_at",
                    "order": "matched_at.desc",
                    "limit": "5",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            price_alerts = r.json() if r.ok else []
        except Exception:
            pass

        # Aktif A/B varyantları
        ab_variants: dict[str, str] = {}
        if ab_engine and user_id:
            for key in ["price_display", "buy_btn_color", "deal_badge"]:
                ab_variants[key] = ab_engine.get_variant(user_id, key)

        return DashboardData(
            user_id=user_id,
            savings=savings,
            recent_deals=recent_deals,
            price_alerts=price_alerts,
            ab_variants=ab_variants,
        )

    def to_dict(self, data: DashboardData) -> dict:
        """DashboardData → JSON-serializable dict."""
        s = data.savings
        return {
            "user_id": data.user_id,
            "savings": {
                "total_saved": s.total_saved,
                "save_count": s.save_count,
                "points": s.points,
                "streak_days": s.streak_days,
                "monthly": s.monthly,
                "by_store": s.by_store,
            },
            "recent_deals": data.recent_deals,
            "price_alerts": data.price_alerts,
            "ab_variants": data.ab_variants,
        }

    # ── Admin Sistem Sağlığı ──────────────────────────────────

    def record_health(
        self,
        component: str,
        *,
        status: str = "ok",
        latency_ms: int | None = None,
        error_count: int = 0,
        success_count: int = 0,
        metadata: dict | None = None,
    ) -> bool:
        """
        Bir scraper / cron / AI worker çalışması sonrası sağlık kaydı oluşturur.
        BaseScraper, AiOrchestrator ve CatalogAutomation tarafından çağrılır.
        """
        row = {
            "component": component,
            "status": status,
            "latency_ms": latency_ms,
            "error_count": error_count,
            "success_count": success_count,
            "metadata": metadata or {},
        }
        try:
            r = _req.post(_sb("system_health_log"), headers=_headers(), json=row, timeout=4)
            return r.ok
        except Exception as exc:
            logger.debug("record_health failed: %s", exc)
            return False

    def get_system_health(self) -> list[dict]:
        """Admin dashboard için scraper sağlık özeti (son 24 saat)."""
        result = _rpc("get_scraper_health_summary", {})
        return result or []

    def get_admin_dashboard(self) -> dict:
        """
        Admin kontrol paneli için tam veri seti:
          - Scraper sağlığı
          - AI job istatistikleri
          - Kullanıcı metrikleri (DAU/WAU)
          - API maliyet tahmini
        """
        health = self.get_system_health()

        # AI job istatistikleri (son 24 saat)
        ai_stats: dict = {}
        try:
            r = _req.get(
                _sb("ai_jobs"),
                params={
                    "created_at": f"gte.{_utc_minus_hours(24)}",
                    "select": "status,actual_cost_usd,model_key",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if r.ok:
                jobs = r.json()
                total_cost = sum(float(j.get("actual_cost_usd") or 0) for j in jobs)
                status_counts: dict[str, int] = {}
                for j in jobs:
                    s = j.get("status", "unknown")
                    status_counts[s] = status_counts.get(s, 0) + 1
                ai_stats = {
                    "total_jobs_24h": len(jobs),
                    "total_cost_usd": round(total_cost, 4),
                    "by_status": status_counts,
                }
        except Exception:
            pass

        # DAU (son 24 saat benzersiz kullanıcı)
        dau_count = 0
        try:
            r = _req.get(
                _sb("user_analytics_events"),
                params={
                    "created_at": f"gte.{_utc_minus_hours(24)}",
                    "event_type": "eq.open_app",
                    "select": "user_id",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if r.ok:
                dau_count = len({row["user_id"] for row in r.json() if row.get("user_id")})
        except Exception:
            pass

        # Son catalog_run istatistikleri
        catalog_stats: dict = {}
        try:
            r = _req.get(
                _sb("catalog_runs"),
                params={"select": "store,status,item_count,started_at", "order": "started_at.desc", "limit": "20"},
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if r.ok:
                runs = r.json()
                catalog_stats = {
                    "recent_runs": runs[:10],
                    "total_items_scanned": sum(int(r.get("item_count") or 0) for r in runs),
                }
        except Exception:
            pass

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "system_health": health,
            "ai_jobs": ai_stats,
            "users": {"dau_24h": dau_count},
            "catalog": catalog_stats,
        }

    # ── Yardımcılar ──────────────────────────────────────────

    def _calc_streak(self, user_id: str) -> int:
        """Kullanıcının arka arkaya uygulama açma serisi (gün)."""
        try:
            r = _req.get(
                _sb("user_analytics_events"),
                params={
                    "user_id": f"eq.{user_id}",
                    "event_type": "eq.open_app",
                    "select": "created_at",
                    "order": "created_at.desc",
                    "limit": "30",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if not r.ok:
                return 0
            rows = r.json()
            if not rows:
                return 0
            # Günlere dönüştür ve ardışık kontrol
            seen_dates: set[str] = set()
            for row in rows:
                ts = row.get("created_at", "")[:10]
                if ts:
                    seen_dates.add(ts)
            from datetime import date, timedelta
            streak = 0
            check = date.today()
            while check.isoformat() in seen_dates:
                streak += 1
                check -= timedelta(days=1)
            return streak
        except Exception:
            return 0


def _utc_minus_hours(hours: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# Modül düzeyinde singleton
analytics_engine = UserAnalyticsEngine()
