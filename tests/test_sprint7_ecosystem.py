"""
Sprint 7 — Ekosistem & İş Ortaklığı Birim Testleri

Çalıştırma:
    pytest tests/test_sprint7_ecosystem.py -v
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest.mock as mock
from datetime import datetime, timedelta, timezone


# ══════════════════════════════════════════════════════════════
# Partner Gateway
# ══════════════════════════════════════════════════════════════

class TestPartnerKeyGeneration:
    def test_generate_key_format(self):
        from app.partner_gateway import generate_api_key
        raw, key_hash = generate_api_key()
        assert raw.startswith("pk_live_")
        assert len(raw) > 20
        assert len(key_hash) == 64   # SHA-256 hex

    def test_generate_key_unique(self):
        from app.partner_gateway import generate_api_key
        k1, _ = generate_api_key()
        k2, _ = generate_api_key()
        assert k1 != k2

    def test_hash_key_deterministic(self):
        from app.partner_gateway import hash_key
        assert hash_key("pk_live_abc") == hash_key("pk_live_abc")

    def test_hash_key_sha256(self):
        from app.partner_gateway import hash_key
        raw = "pk_live_test"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert hash_key(raw) == expected

    def test_valid_scopes_defined(self):
        from app.partner_gateway import VALID_SCOPES
        assert "read:prices" in VALID_SCOPES
        assert "write:orders" in VALID_SCOPES
        assert "read:coupons" in VALID_SCOPES
        assert "write:group_buy" in VALID_SCOPES

    def test_create_partner_validates_scope(self):
        from app.partner_gateway import create_partner
        with mock.patch("app.partner_gateway._req.post"):
            try:
                create_partner("test", "Test", ["invalid:scope"])
                assert False, "Hata bekleniyor"
            except ValueError as exc:
                assert "invalid:scope" in str(exc)


class TestWebhookSender:
    def _sender(self):
        from app.partner_gateway import WebhookSender
        return WebhookSender()

    def test_sign_is_hmac_sha256(self):
        from app.partner_gateway import WebhookSender
        ts = "1700000000"
        payload = '{"event":"test"}'
        secret = "my_secret"
        sig = WebhookSender._sign(ts, payload, secret)
        expected = hmac.new(
            secret.encode(),
            f"{ts}.{payload}".encode(),
            hashlib.sha256,
        ).hexdigest()
        assert sig == expected

    def test_verify_signature_valid(self):
        from app.partner_gateway import WebhookSender
        secret = "test_secret_123"
        ts = str(int(time.time()))
        payload = b'{"event":"price_alert","product":"Sut"}'
        sig = WebhookSender._sign(ts, payload.decode(), secret)

        valid = WebhookSender.verify_signature(
            payload, f"sha256={sig}", ts, secret
        )
        assert valid is True

    def test_verify_signature_wrong_secret(self):
        from app.partner_gateway import WebhookSender
        ts = str(int(time.time()))
        payload = b'{"data":"test"}'
        sig = WebhookSender._sign(ts, payload.decode(), "correct_secret")
        valid = WebhookSender.verify_signature(
            payload, f"sha256={sig}", ts, "wrong_secret"
        )
        assert valid is False

    def test_verify_signature_expired_timestamp(self):
        from app.partner_gateway import WebhookSender
        secret = "s"
        old_ts = str(int(time.time()) - 400)   # 400 saniye önce (max 300)
        payload = b"body"
        sig = WebhookSender._sign(old_ts, payload.decode(), secret)
        valid = WebhookSender.verify_signature(
            payload, f"sha256={sig}", old_ts, secret, max_age_seconds=300
        )
        assert valid is False

    def test_send_webhook_success(self):
        sender = self._sender()
        with mock.patch("app.partner_gateway._req.post") as mock_post, \
             mock.patch.object(sender, "_log"):
            mock_post.return_value = mock.Mock(status_code=200)
            ok = sender.send(
                "partner_x", "price_alert",
                {"product": "Süt", "price": 24.90},
                webhook_url="https://example.com/hook",
                webhook_secret="secret123",
            )
        assert ok is True
        headers = mock_post.call_args.kwargs.get("headers", {})
        assert "X-Almadan-Signature" in headers
        assert headers["X-Almadan-Signature"].startswith("sha256=")

    def test_send_webhook_retries_on_failure(self):
        sender = self._sender()
        with mock.patch("app.partner_gateway._req.post") as mock_post, \
             mock.patch.object(sender, "_log"), \
             mock.patch("app.partner_gateway.time.sleep"):
            mock_post.return_value = mock.Mock(status_code=500, text="Server Error")
            ok = sender.send(
                "p", "ev", {},
                webhook_url="https://bad.example.com/hook",
                webhook_secret="s",
            )
        assert ok is False
        assert mock_post.call_count == sender.MAX_ATTEMPTS


# ══════════════════════════════════════════════════════════════
# CouponEngine
# ══════════════════════════════════════════════════════════════

class TestCouponEngine:
    def _engine(self):
        from app.coupon_engine import CouponEngine
        return CouponEngine()

    def test_gen_code_format(self):
        from app.coupon_engine import _gen_code
        code = _gen_code("aura_studio")
        assert code.startswith("ALMADAN-")
        assert len(code) > 10

    def test_gen_code_unique(self):
        from app.coupon_engine import _gen_code
        codes = {_gen_code("partner") for _ in range(20)}
        assert len(codes) == 20

    def test_exchange_below_minimum_fails(self):
        engine = self._engine()
        with mock.patch("app.coupon_engine._get_user_points", return_value=500):
            result = engine.exchange_points_for_coupon("uid", 50)   # < 100 minimum
        assert result.success is False
        assert "Minimum" in (result.error or "")

    def test_exchange_insufficient_points_fails(self):
        engine = self._engine()
        with mock.patch("app.coupon_engine._get_user_points", return_value=50):
            result = engine.exchange_points_for_coupon("uid", 200)
        assert result.success is False
        assert "Yetersiz" in (result.error or "")

    def test_exchange_creates_coupon(self):
        engine = self._engine()
        created_coupon = {"id": 42, "code": "ALMADAN-TEST-XY1234"}
        with mock.patch("app.coupon_engine._get_user_points", return_value=500), \
             mock.patch("app.coupon_engine._req.post") as mock_post, \
             mock.patch("app.coupon_engine._deduct_points", return_value=True):
            mock_post.return_value = mock.Mock(ok=True, json=lambda: [created_coupon])
            result = engine.exchange_points_for_coupon("uid-1", 200)
        assert result.success is True
        assert result.discount_amount == round(200 * 0.05, 2)   # ₺10

    def test_calc_discount_percentage(self):
        from app.coupon_engine import CouponEngine
        coupon = {"coupon_type": "percentage", "discount_pct": 20, "discount_amount": None}
        disc = CouponEngine._calc_discount(coupon, 100.0)
        assert disc == 20.0

    def test_calc_discount_fixed(self):
        from app.coupon_engine import CouponEngine
        coupon = {"coupon_type": "fixed", "discount_pct": None, "discount_amount": 15.0}
        disc = CouponEngine._calc_discount(coupon, 100.0)
        assert disc == 15.0

    def test_check_coupon_expired(self):
        engine = self._engine()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        coupon = {
            "id": 1, "is_active": True, "expires_at": past,
            "uses_count": 0, "max_uses": 10, "min_spend": 0,
        }
        error = engine._check_coupon_usability(coupon, "uid", 50.0)
        assert error is not None
        assert "süre" in error.lower()

    def test_check_coupon_limit_reached(self):
        engine = self._engine()
        coupon = {
            "id": 1, "is_active": True, "expires_at": None,
            "uses_count": 5, "max_uses": 5, "min_spend": 0,
        }
        error = engine._check_coupon_usability(coupon, "uid", 50.0)
        assert error is not None
        assert "limit" in error.lower()

    def test_check_coupon_min_spend_not_met(self):
        engine = self._engine()
        coupon = {
            "id": 1, "is_active": True, "expires_at": None,
            "uses_count": 0, "max_uses": 10, "min_spend": 100.0,
        }
        with mock.patch("app.coupon_engine._req.get") as mock_get:
            mock_get.return_value = mock.Mock(ok=True, json=lambda: [])
            error = engine._check_coupon_usability(coupon, "uid", 50.0)
        assert error is not None
        assert "Minimum" in error

    def test_points_to_tl_rate(self):
        from app.coupon_engine import POINTS_TO_TL, MIN_EXCHANGE_POINTS
        assert POINTS_TO_TL == 0.05
        assert MIN_EXCHANGE_POINTS == 100
        # 100 puan = ₺5
        assert round(MIN_EXCHANGE_POINTS * POINTS_TO_TL, 2) == 5.0


# ══════════════════════════════════════════════════════════════
# GroupBuyEngine
# ══════════════════════════════════════════════════════════════

class TestGroupBuyEngine:
    def _engine(self):
        from app.group_buy import GroupBuyEngine
        return GroupBuyEngine()

    def test_hash_location_deterministic(self):
        from app.group_buy import hash_location
        assert hash_location("Beşiktaş") == hash_location("Beşiktaş")

    def test_hash_location_different_districts(self):
        from app.group_buy import hash_location
        assert hash_location("Kadıköy") != hash_location("Beşiktaş")

    def test_hash_location_length(self):
        from app.group_buy import hash_location
        assert len(hash_location("Üsküdar")) == 8

    def test_create_group_buy_target_price_must_be_lower(self):
        engine = self._engine()
        result = engine.create_group_buy(
            "Pınar Süt", "migros",
            current_price=24.90,
            target_price=30.0,     # Mevcut fiyattan yüksek → hata
            target_quantity=10,
            organizer_id="uid-1",
        )
        assert result.success is False
        assert "düşük" in (result.error or "").lower()

    def test_create_group_buy_invalid_quantity(self):
        engine = self._engine()
        result = engine.create_group_buy(
            "Test", "a101",
            current_price=50.0,
            target_price=40.0,
            target_quantity=1,     # < MIN (2)
            organizer_id="uid-1",
        )
        assert result.success is False

    def test_create_group_buy_success(self):
        engine = self._engine()
        with mock.patch("app.group_buy._req.post") as mock_post, \
             mock.patch.object(engine, "join_group_buy") as mock_join:
            mock_post.return_value = mock.Mock(ok=True, json=lambda: [{"id": 99}])
            mock_join.return_value = mock.Mock(success=True)
            result = engine.create_group_buy(
                "Ariel Toz 3kg", "migros",
                current_price=89.90,
                target_price=70.0,
                target_quantity=20,
                organizer_id="uid-org",
                district="Beşiktaş",
            )
        assert result.success is True
        assert result.group_id == 99

    def test_join_group_buy_group_not_found(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_group", return_value=None):
            result = engine.join_group_buy(999, "uid-x")
        assert result.success is False
        assert "bulunamadı" in (result.error or "").lower()

    def test_join_group_buy_completed_status(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_group", return_value={
            "id": 1, "status": "completed", "expires_at": None
        }):
            result = engine.join_group_buy(1, "uid-x")
        assert result.success is False

    def test_leave_group_buy_organizer_blocked(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_group", return_value={
            "id": 1, "status": "recruiting",
            "organizer_id": "uid-org", "expires_at": None
        }):
            result = engine.leave_group_buy(1, "uid-org")
        assert result.success is False
        assert "Organizatör" in (result.error or "")

    def test_progress_pct_calculation(self):
        """10 hedef, 5 mevcut → %50"""
        engine = self._engine()
        with mock.patch.object(engine, "_load_group", return_value={
            "id": 1, "product_title": "Süt", "store": "migros",
            "current_price": 24.90, "target_price": 20.0,
            "target_quantity": 10, "current_quantity": 5,
            "status": "recruiting", "expires_at": None,
            "organizer_id": "uid-org",
        }), mock.patch("app.group_buy._req.get") as mock_get:
            mock_get.return_value = mock.Mock(ok=True, json=lambda: [
                {"quantity_wanted": 1},
                {"quantity_wanted": 1},
            ])
            detail = engine.get_group_details(1)
        assert detail["progress_pct"] == 50.0


# ══════════════════════════════════════════════════════════════
# EcoScoreEngine
# ══════════════════════════════════════════════════════════════

class TestEcoScoreEngine:
    def _engine(self):
        from app.eco_score import EcoScoreEngine
        return EcoScoreEngine()

    def test_score_range(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_cache", return_value=None), \
             mock.patch.object(engine, "_save_cache"):
            result = engine.score("k1", "Pınar Süt 1L", use_cache=False)
        assert 0 <= result.eco_score <= 100

    def test_glass_packaging_scores_higher(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_cache", return_value=None), \
             mock.patch.object(engine, "_save_cache"):
            glass   = engine.score("k1", "Reçel", packaging_hint="glass", use_cache=False)
            plastic = engine.score("k2", "Reçel", packaging_hint="plastic", use_cache=False)
        assert glass.eco_score > plastic.eco_score

    def test_local_brand_detected(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_cache", return_value=None), \
             mock.patch.object(engine, "_save_cache"):
            result = engine.score("k1", "Ülker Çikolata", use_cache=False)
        assert result.breakdown["origin"] >= 30   # local

    def test_organic_keyword_detected(self):
        engine = self._engine()
        with mock.patch.object(engine, "_load_cache", return_value=None), \
             mock.patch.object(engine, "_save_cache"):
            result = engine.score("k1", "Organik Yumurta Köy", use_cache=False)
        assert "organic" in result.certifications
        assert result.breakdown["cert"] >= 20

    def test_detect_packaging_glass(self):
        engine = self._engine()
        assert engine._detect_packaging("Doğanay Vişne Suyu cam şişe") == "glass"

    def test_detect_packaging_cardboard(self):
        engine = self._engine()
        assert engine._detect_packaging("Pınar Süt 1L karton") == "cardboard"

    def test_detect_packaging_plastic(self):
        engine = self._engine()
        assert engine._detect_packaging("Plastik poşet") == "plastic"

    def test_detect_origin_local_brand(self):
        engine = self._engine()
        assert engine._detect_origin("Ülker Kremalı Bisküvi") == "local"

    def test_detect_origin_europe(self):
        engine = self._engine()
        assert engine._detect_origin("İtalyan Pesto Sos") == "europe"

    def test_grade_boundaries(self):
        engine = self._engine()
        assert engine._grade(95) == "A+"
        assert engine._grade(80) == "A"
        assert engine._grade(65) == "B"
        assert engine._grade(50) == "C"
        assert engine._grade(30) == "D"

    def test_eco_friendly_property(self):
        from app.eco_score import EcoScoreResult
        good = EcoScoreResult("k", "T", 75, "A", "glass")
        bad  = EcoScoreResult("k", "T", 45, "C", "plastic")
        assert good.is_eco_friendly is True
        assert bad.is_eco_friendly is False

    def test_color_property(self):
        from app.eco_score import EcoScoreResult
        r = EcoScoreResult("k", "T", 90, "A+", "glass")
        assert r.color.startswith("#")

    def test_get_eco_summary_empty(self):
        engine = self._engine()
        summary = engine.get_eco_summary([])
        assert summary["avg_score"] == 0

    def test_bulk_score(self):
        engine = self._engine()
        products = [
            {"product_key": "k1", "product_title": "Cam Kavanoz Reçel", "packaging_type": "glass"},
            {"product_key": "k2", "product_title": "Plastik Şişe Yağ", "packaging_type": "plastic"},
        ]
        with mock.patch.object(engine, "_load_cache", return_value=None), \
             mock.patch.object(engine, "_save_cache"):
            results = engine.bulk_score(products)
        assert len(results) == 2
        assert results[0].eco_score > results[1].eco_score   # cam > plastik
