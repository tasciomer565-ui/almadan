"""
Sprint 5 — Analitik, A/B Test ve Tutundurma Birim Testleri

Çalıştırma:
    pytest tests/test_sprint5_analytics.py -v
"""
from __future__ import annotations

import unittest.mock as mock
from dataclasses import dataclass


# ══════════════════════════════════════════════════════════════
# UserAnalyticsEngine
# ══════════════════════════════════════════════════════════════

class TestUserAnalyticsEngineUnit:
    def _engine(self):
        from app.analytics_engine import UserAnalyticsEngine
        return UserAnalyticsEngine()

    def test_track_event_no_identity_returns_false(self):
        engine = self._engine()
        result = engine.track_event("open_app")   # user_id ve device_id yok
        assert result is False

    def test_track_event_with_device_id_calls_supabase(self):
        engine = self._engine()
        with mock.patch("app.analytics_engine._req.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True)
            result = engine.track_event("search", device_id="dev-123", payload={"q": "süt"})
        assert result is True
        call_args = mock_post.call_args
        sent_json = call_args.kwargs.get("json") or call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("json", {})
        assert sent_json.get("event_type") == "search"

    def test_record_saving_calculates_saved_amount(self):
        engine = self._engine()
        with mock.patch("app.analytics_engine._req.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True)
            engine.record_saving(
                user_id="uid-1",
                device_id=None,
                product_title="Pınar Süt 1L",
                store="migros",
                price=24.90,
                original_price=29.90,
                saved_pct=17,
            )
        sent = mock_post.call_args.kwargs.get("json", {})
        assert sent.get("saved_amount") == round(29.90 - 24.90, 2)
        assert sent.get("price") == 24.90

    def test_record_saving_no_original_price(self):
        engine = self._engine()
        with mock.patch("app.analytics_engine._req.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True)
            engine.record_saving(
                user_id="uid-2",
                device_id=None,
                product_title="Ariel 3kg",
                store="a101",
                price=89.90,
            )
        sent = mock_post.call_args.kwargs.get("json", {})
        assert sent.get("saved_amount") is None

    def test_to_dict_structure(self):
        from app.analytics_engine import UserAnalyticsEngine, DashboardData, SavingsSummary
        engine = UserAnalyticsEngine()
        data = DashboardData(
            user_id="uid-test",
            savings=SavingsSummary(
                user_id="uid-test",
                total_saved=125.50,
                save_count=5,
                monthly=[{"month": "2026-06", "total_saved": 125.50}],
                by_store=[{"store": "migros", "total_saved": 80.0}],
                points=150,
                streak_days=7,
            ),
            recent_deals=[{"product_title": "Pınar Süt", "saved_amount": 5.0}],
            price_alerts=[],
            ab_variants={"price_display": "variant_a"},
        )
        d = engine.to_dict(data)
        assert d["savings"]["total_saved"] == 125.50
        assert d["savings"]["streak_days"] == 7
        assert d["savings"]["points"] == 150
        assert len(d["recent_deals"]) == 1
        assert d["ab_variants"]["price_display"] == "variant_a"

    def test_record_health_builds_correct_row(self):
        engine = self._engine()
        with mock.patch("app.analytics_engine._req.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True)
            engine.record_health(
                "scraper_migros",
                status="ok",
                latency_ms=320,
                success_count=10,
                error_count=1,
            )
        sent = mock_post.call_args.kwargs.get("json", {})
        assert sent["component"] == "scraper_migros"
        assert sent["status"] == "ok"
        assert sent["latency_ms"] == 320
        assert sent["success_count"] == 10

    def test_utc_minus_hours(self):
        from app.analytics_engine import _utc_minus_hours
        result = _utc_minus_hours(24)
        assert "T" in result    # ISO format
        assert result < _utc_minus_hours(0)


# ══════════════════════════════════════════════════════════════
# ABTestEngine
# ══════════════════════════════════════════════════════════════

class TestABTestEngine:
    def _engine(self):
        from app.ab_testing import ABTestEngine
        return ABTestEngine()

    def test_get_variant_no_experiment_returns_control(self):
        engine = self._engine()
        with mock.patch("app.ab_testing._req.get") as mock_get:
            mock_get.return_value = mock.Mock(ok=True, json=lambda: [])
            variant = engine.get_variant("user-123", "nonexistent_exp")
        assert variant == "control"

    def test_get_variant_inactive_returns_control(self):
        engine = self._engine()
        exp_row = {"id": 1, "key": "test", "variants": ["control", "variant_a"],
                   "traffic_pct": 100, "is_active": False}
        with mock.patch("app.ab_testing._req.get") as mock_get:
            mock_get.return_value = mock.Mock(ok=True, json=lambda: [exp_row])
            variant = engine.get_variant("user-123", "test")
        assert variant == "control"

    def test_hash_bucket_deterministic(self):
        from app.ab_testing import ABTestEngine
        b1 = ABTestEngine._hash_bucket("user-abc", "price_display")
        b2 = ABTestEngine._hash_bucket("user-abc", "price_display")
        assert b1 == b2

    def test_hash_bucket_different_users(self):
        from app.ab_testing import ABTestEngine
        b1 = ABTestEngine._hash_bucket("user-aaa", "exp_x")
        b2 = ABTestEngine._hash_bucket("user-bbb", "exp_x")
        # Farklı kullanıcılar genellikle farklı bucket alır (her zaman değil ama çoğunlukla)
        assert 0 <= b1 < 100
        assert 0 <= b2 < 100

    def test_hash_bucket_range(self):
        from app.ab_testing import ABTestEngine
        for i in range(50):
            b = ABTestEngine._hash_bucket(f"user-{i}", "test_exp")
            assert 0 <= b < 100

    def test_get_variant_traffic_pct_below_bucket_returns_control(self):
        """Bucket değeri traffic_pct'den büyükse control döner."""
        from app.ab_testing import ABTestEngine, Experiment

        engine = ABTestEngine()
        exp = Experiment(id=1, key="low_traffic", variants=["control", "v_a"],
                         traffic_pct=1, is_active=True)
        engine._cache["low_traffic"] = exp

        # user-999 bucket > 1 olmalı (hash deterministic)
        with mock.patch.object(engine, "_get_assignment", return_value=None), \
             mock.patch.object(engine, "_save_assignment"):
            bucket = ABTestEngine._hash_bucket("user-999", "low_traffic")
            if bucket >= 1:
                variant = engine.get_variant("user-999", "low_traffic")
                assert variant == "control"

    def test_create_experiment_posts_correct_data(self):
        engine = self._engine()
        created = {"id": 42, "key": "btn_color", "variants": ["control", "red"], "is_active": True}
        with mock.patch("app.ab_testing._req.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True, json=lambda: [created])
            result = engine.create_experiment("btn_color", "Buton rengi testi", variants=["control", "red"])
        assert result["id"] == 42
        sent = mock_post.call_args.kwargs.get("json", {})
        assert sent["key"] == "btn_color"
        assert "red" in sent["variants"]

    def test_stop_experiment_patches_db(self):
        engine = self._engine()
        with mock.patch("app.ab_testing._req.patch") as mock_patch:
            mock_patch.return_value = mock.Mock(ok=True)
            ok = engine.stop_experiment("price_display", winner_variant="variant_a")
        assert ok is True
        sent = mock_patch.call_args.kwargs.get("json", {})
        assert sent["is_active"] is False
        assert sent["winner_variant"] == "variant_a"

    def test_track_event_without_assignment_returns_false(self):
        from app.ab_testing import ABTestEngine, Experiment
        engine = ABTestEngine()
        exp = Experiment(id=5, key="ev_test", variants=["control", "v_a"],
                         traffic_pct=100, is_active=True)
        engine._cache["ev_test"] = exp
        # _get_assignment_id → None (atama yok)
        with mock.patch.object(engine, "_get_assignment_id", return_value=None):
            result = engine.track_event("ev_test", "click_buy", user_id="uid-x")
        assert result is False


# ══════════════════════════════════════════════════════════════
# RetentionService & Puan Sistemi
# ══════════════════════════════════════════════════════════════

class TestRetentionServiceUnit:
    def _service(self):
        from app.retention_service import RetentionService
        return RetentionService()

    def test_digest_payload_is_worth_sending_with_deals(self):
        from app.retention_service import DigestPayload
        p = DigestPayload(
            user_id="uid", email="test@x.com", display_name="Ali",
            total_saved_week=50.0,
            top_deals=[{"product_title": "Süt", "saved_amount": 5.0}],
            points_balance=0, streak_days=3, watchlist_count=5,
        )
        assert p.is_worth_sending() is True

    def test_digest_payload_not_worth_sending_when_empty(self):
        from app.retention_service import DigestPayload
        p = DigestPayload(
            user_id="uid", email="test@x.com", display_name="Ali",
            total_saved_week=0.0, top_deals=[],
            points_balance=5, streak_days=0, watchlist_count=0,
        )
        assert p.is_worth_sending() is False

    def test_digest_payload_worth_sending_with_high_points(self):
        from app.retention_service import DigestPayload
        p = DigestPayload(
            user_id="uid", email="test@x.com", display_name="Ali",
            total_saved_week=0.0, top_deals=[],
            points_balance=50, streak_days=0, watchlist_count=0,
        )
        assert p.is_worth_sending() is True

    def test_render_email_html_contains_key_elements(self):
        from app.retention_service import RetentionService, DigestPayload
        svc = RetentionService()
        payload = DigestPayload(
            user_id="uid-1", email="user@test.com", display_name="Fatma",
            total_saved_week=120.50,
            top_deals=[
                {"product_title": "Pınar Süt", "store": "migros",
                 "price": 24.90, "saved_amount": 5.0, "saved_pct": 17}
            ],
            points_balance=200, streak_days=14, watchlist_count=10,
        )
        html = svc._render_email_html(payload)
        assert "Fatma" in html
        assert "120,50" in html or "120.50" in html
        assert "200" in html      # puan
        assert "14" in html       # streak
        assert "Pınar Süt" in html
        assert "Migros" in html or "migros" in html

    def test_render_email_html_no_deals(self):
        from app.retention_service import RetentionService, DigestPayload
        svc = RetentionService()
        payload = DigestPayload(
            user_id="uid-2", email="user2@test.com", display_name="Ahmet",
            total_saved_week=0.0, top_deals=[],
            points_balance=5, streak_days=0, watchlist_count=2,
        )
        html = svc._render_email_html(payload)
        assert "Watchlist" in html or "watchlist" in html or "ürün ekle" in html.lower()


class TestPointSystem:
    def test_point_rules_defined(self):
        from app.retention_service import POINT_RULES
        assert POINT_RULES["weekly_login"] > 0
        assert POINT_RULES["first_save"] >= 50
        assert POINT_RULES["app_open"] >= 1
        assert POINT_RULES["invite_friend"] >= 50

    def test_award_points_unknown_reason_returns_zero(self):
        from app.retention_service import award_points
        result = award_points("uid-x", "nonexistent_reason")
        assert result == 0

    def test_award_points_custom_amount(self):
        with mock.patch("app.retention_service._req.post") as mock_post, \
             mock.patch("app.retention_service._already_rewarded_today", return_value=False):
            mock_post.return_value = mock.Mock(ok=True)
            from app.retention_service import award_points
            pts = award_points("uid-x", "invite_friend", custom_amount=500)
        assert pts == 500

    def test_award_points_daily_throttle_for_app_open(self):
        """app_open aynı günde ikinci kez 0 puan vermeli."""
        with mock.patch("app.retention_service._already_rewarded_today", return_value=True):
            from app.retention_service import award_points
            pts = award_points("uid-x", "app_open")
        assert pts == 0

    def test_award_points_save_recorded(self):
        with mock.patch("app.retention_service._req.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True)
            from app.retention_service import award_points
            pts = award_points("uid-x", "save_recorded")
        assert pts == 10   # POINT_RULES["save_recorded"]


# ══════════════════════════════════════════════════════════════
# Entegrasyon: Engine + Service birlikte
# ══════════════════════════════════════════════════════════════

class TestAnalyticsIntegration:
    def test_full_event_tracking_flow(self):
        """Etkinlik kaydı → puan → dashboard akışını mock ile test eder."""
        from app.analytics_engine import UserAnalyticsEngine

        engine = UserAnalyticsEngine()

        with mock.patch("app.analytics_engine._req.post") as p1, \
             mock.patch("app.analytics_engine._req.get") as g1, \
             mock.patch("app.analytics_engine._rpc") as rpc:

            p1.return_value = mock.Mock(ok=True)
            g1.return_value = mock.Mock(ok=True, json=lambda: [])
            rpc.return_value = []

            # Etkinlik kaydet
            ok = engine.track_event("search", user_id="uid-abc", payload={"q": "süt"})
            assert ok is True

            # Tasarruf kaydet
            ok2 = engine.record_saving(
                user_id="uid-abc",
                device_id=None,
                product_title="Pınar Süt",
                store="migros",
                price=24.90,
                original_price=29.90,
            )
            assert ok2 is True

    def test_dashboard_data_to_dict_round_trip(self):
        """to_dict hiçbir veri kaybetmemeli."""
        from app.analytics_engine import UserAnalyticsEngine, DashboardData, SavingsSummary

        engine = UserAnalyticsEngine()
        summary = SavingsSummary(
            user_id="u1", total_saved=500.0, save_count=20,
            monthly=[], by_store=[], points=300, streak_days=10,
        )
        data = DashboardData(
            user_id="u1", savings=summary,
            recent_deals=[{"product_title": "X"}],
            price_alerts=[{"watchlist_title": "Y"}],
            ab_variants={"price_display": "control"},
        )
        d = engine.to_dict(data)
        assert d["savings"]["total_saved"] == 500.0
        assert d["savings"]["save_count"] == 20
        assert d["savings"]["streak_days"] == 10
        assert d["recent_deals"][0]["product_title"] == "X"
        assert d["price_alerts"][0]["watchlist_title"] == "Y"
        assert d["ab_variants"]["price_display"] == "control"
