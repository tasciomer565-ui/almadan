"""
Sprint 8 — Resilience, Cache Strategy, Observability, Chaos

Test kapsamı:
  - CircuitBreaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - retry dekoratörü (backoff, max_attempts, jitter)
  - with_fallback dekoratörü
  - LRUCache (get/set/TTL/eviction)
  - lru_cached dekoratörü
  - cache_headers (preset'ler)
  - StructuredLogger (_persist sadece Supabase varken)
  - record_request_metric (fire-and-forget)
  - ChaosRunner (inject_fault, senaryo başlatma/durdurma)
  - FaultType tüm dalları
"""
from __future__ import annotations

import time
import unittest
import unittest.mock as mock

# ── resilience ─────────────────────────────────────────────────

from app.resilience import (
    CBState,
    CircuitBreaker,
    retry,
    with_fallback,
    with_timeout,
    check_timeout,
    get_all_circuit_states,
    reset_circuit_breaker,
)


class TestCircuitBreaker(unittest.TestCase):
    def _fresh(self, **kwargs) -> CircuitBreaker:
        cb = CircuitBreaker("test_svc_" + str(id(self)), **kwargs)
        return cb

    def test_initial_state_is_closed(self):
        cb = self._fresh()
        self.assertEqual(cb.state, CBState.CLOSED)
        self.assertFalse(cb.is_open)

    def test_success_does_not_open(self):
        cb = self._fresh(failure_threshold=3)
        for _ in range(10):
            with cb.call():
                pass
        self.assertEqual(cb.state, CBState.CLOSED)

    def test_failures_open_circuit(self):
        cb = self._fresh(failure_threshold=3)
        for _ in range(3):
            with self.assertRaises(ValueError):
                with cb.call():
                    raise ValueError("boom")
        self.assertEqual(cb.state, CBState.OPEN)
        self.assertTrue(cb.is_open)

    def test_open_circuit_rejects_immediately(self):
        cb = self._fresh(failure_threshold=1)
        with self.assertRaises(ValueError):
            with cb.call():
                raise ValueError("first")
        self.assertEqual(cb.state, CBState.OPEN)
        with self.assertRaises(PermissionError):
            with cb.call():
                pass   # should not reach here

    def test_recovery_to_half_open(self):
        cb = self._fresh(failure_threshold=1, recovery_timeout=0.01)
        with self.assertRaises(ValueError):
            with cb.call():
                raise ValueError("fail")
        self.assertEqual(cb.state, CBState.OPEN)
        time.sleep(0.05)
        # Bir başarılı çağrı → HALF_OPEN
        with cb.call():
            pass
        self.assertEqual(cb.state, CBState.HALF_OPEN)

    def test_half_open_to_closed_after_success_threshold(self):
        cb = self._fresh(failure_threshold=1, recovery_timeout=0.01, success_threshold=2)
        with self.assertRaises(ValueError):
            with cb.call():
                raise ValueError("fail")
        time.sleep(0.05)
        with cb.call():
            pass
        self.assertEqual(cb.state, CBState.HALF_OPEN)
        with cb.call():
            pass
        self.assertEqual(cb.state, CBState.CLOSED)

    def test_half_open_failure_reopens(self):
        cb = self._fresh(failure_threshold=1, recovery_timeout=0.01, success_threshold=2)
        with self.assertRaises(ValueError):
            with cb.call():
                raise ValueError("fail")
        time.sleep(0.05)
        # HALF_OPEN'da hata → tekrar OPEN
        with self.assertRaises(RuntimeError):
            with cb.call():
                raise RuntimeError("half_open_fail")
        self.assertEqual(cb.state, CBState.OPEN)

    def test_manual_reset(self):
        cb = self._fresh(failure_threshold=1)
        with self.assertRaises(ValueError):
            with cb.call():
                raise ValueError("fail")
        self.assertEqual(cb.state, CBState.OPEN)
        cb.reset()
        self.assertEqual(cb.state, CBState.CLOSED)
        self.assertEqual(cb.status()["failure_count"], 0)

    def test_status_dict(self):
        cb = self._fresh()
        s = cb.status()
        self.assertIn("service", s)
        self.assertIn("state", s)
        self.assertIn("failure_count", s)

    def test_persist_skipped_without_supabase(self):
        cb = self._fresh(failure_threshold=1)
        with self.assertRaises(ValueError):
            with cb.call():
                raise ValueError("x")
        # persist() is called but silently skipped — no exception should escape

    def test_get_all_circuit_states_returns_list(self):
        states = get_all_circuit_states()
        self.assertIsInstance(states, list)
        self.assertGreater(len(states), 0)

    def test_reset_circuit_breaker_helper(self):
        reset_circuit_breaker("supabase")  # should not raise


class TestRetryDecorator(unittest.TestCase):
    def test_succeeds_on_first_try(self):
        calls = []

        @retry(max_attempts=3)
        def fn():
            calls.append(1)
            return "ok"

        result = fn()
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_and_succeeds(self):
        calls = []

        @retry(max_attempts=3, backoff_base=0.001, jitter=False)
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("not yet")
            return "ok"

        result = fn()
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_raises_after_max_attempts(self):
        calls = []

        @retry(max_attempts=2, backoff_base=0.001, jitter=False)
        def fn():
            calls.append(1)
            raise ConnectionError("always fails")

        with self.assertRaises(ConnectionError):
            fn()
        self.assertEqual(len(calls), 2)

    def test_on_retry_callback(self):
        retries = []

        @retry(max_attempts=3, backoff_base=0.001, jitter=False, on_retry=lambda a, e: retries.append(a))
        def fn():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            fn()
        self.assertEqual(retries, [1, 2])

    def test_exception_filter(self):
        calls = []

        @retry(max_attempts=3, backoff_base=0.001, jitter=False, exceptions=(ValueError,))
        def fn():
            calls.append(1)
            raise TypeError("not retried")

        with self.assertRaises(TypeError):
            fn()
        self.assertEqual(len(calls), 1)


class TestWithFallback(unittest.TestCase):
    def test_returns_value_on_success(self):
        @with_fallback(fallback_value=[], log_error=False)
        def fn():
            return [1, 2, 3]

        self.assertEqual(fn(), [1, 2, 3])

    def test_returns_fallback_on_error(self):
        @with_fallback(fallback_value=[], log_error=False)
        def fn():
            raise RuntimeError("boom")

        self.assertEqual(fn(), [])

    def test_fallback_none(self):
        @with_fallback(log_error=False)
        def fn():
            raise ValueError("x")

        self.assertIsNone(fn())


class TestWithTimeout(unittest.TestCase):
    def test_no_warning_when_fast(self):
        with with_timeout(10, "fast_op"):
            pass   # completes instantly

    def test_warning_logged_when_slow(self):
        import logging
        with self.assertLogs("app.resilience", level="WARNING") as cm:
            with with_timeout(0.0, "slow_op"):
                time.sleep(0.01)
        self.assertTrue(any("slow_op" in m for m in cm.output))

    def test_check_timeout_raises(self):
        start = time.monotonic() - 5
        with self.assertRaises(TimeoutError):
            check_timeout(start, 1.0, "op")

    def test_check_timeout_ok(self):
        start = time.monotonic()
        check_timeout(start, 10.0, "op")   # should not raise


# ── cache_strategy ─────────────────────────────────────────────

from app.cache_strategy import (
    LRUCache,
    lru_cached,
    cache_headers,
    cache_key,
    get_cache_stats,
    CACHE_NO_STORE,
    CACHE_PRICES,
)


class TestLRUCache(unittest.TestCase):
    def test_set_and_get(self):
        c = LRUCache(max_size=10, default_ttl=60)
        c.set("k", "v")
        hit, val = c.get("k")
        self.assertTrue(hit)
        self.assertEqual(val, "v")

    def test_miss(self):
        c = LRUCache()
        hit, val = c.get("nonexistent")
        self.assertFalse(hit)
        self.assertIsNone(val)

    def test_ttl_expiry(self):
        c = LRUCache(default_ttl=0.01)
        c.set("k", "v")
        time.sleep(0.05)
        hit, _ = c.get("k")
        self.assertFalse(hit)

    def test_eviction_at_max_size(self):
        c = LRUCache(max_size=3, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.set("d", 4)   # should evict "a" (LRU)
        hit_a, _ = c.get("a")
        hit_d, _ = c.get("d")
        self.assertFalse(hit_a)
        self.assertTrue(hit_d)

    def test_delete(self):
        c = LRUCache()
        c.set("x", 42)
        deleted = c.delete("x")
        self.assertTrue(deleted)
        hit, _ = c.get("x")
        self.assertFalse(hit)

    def test_clear(self):
        c = LRUCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        self.assertEqual(c.stats()["size"], 0)

    def test_stats(self):
        c = LRUCache(max_size=100, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        s = c.stats()
        self.assertEqual(s["size"], 2)
        self.assertEqual(s["max_size"], 100)


class TestLruCachedDecorator(unittest.TestCase):
    def test_caches_result(self):
        cache = LRUCache(default_ttl=60)
        calls = []

        @lru_cached(cache, ttl=60)
        def expensive(x: int) -> int:
            calls.append(x)
            return x * 2

        self.assertEqual(expensive(5), 10)
        self.assertEqual(expensive(5), 10)
        self.assertEqual(len(calls), 1)   # second call served from cache

    def test_different_args_not_shared(self):
        cache = LRUCache(default_ttl=60)

        @lru_cached(cache)
        def fn(x):
            return x + 1

        self.assertEqual(fn(1), 2)
        self.assertEqual(fn(2), 3)


class TestCacheHeaders(unittest.TestCase):
    def test_no_store_headers(self):
        h = CACHE_NO_STORE()
        self.assertIn("no-store", h["Cache-Control"])

    def test_prices_headers(self):
        h = CACHE_PRICES()
        self.assertIn("public", h["Cache-Control"])
        self.assertIn("max-age=300", h["Cache-Control"])

    def test_private_headers(self):
        h = cache_headers(private=True, max_age=30)
        self.assertIn("private", h["Cache-Control"])
        self.assertNotIn("CDN-Cache-Control", h)

    def test_cache_key_deterministic(self):
        k1 = cache_key("prices", "ürün-123", "migros")
        k2 = cache_key("prices", "ürün-123", "migros")
        self.assertEqual(k1, k2)

    def test_cache_key_different_args(self):
        k1 = cache_key("a", "b")
        k2 = cache_key("a", "c")
        self.assertNotEqual(k1, k2)

    def test_get_cache_stats_returns_dict(self):
        stats = get_cache_stats()
        self.assertIn("price_cache", stats)
        self.assertIn("search_cache", stats)
        self.assertIn("product_cache", stats)


# ── observability ──────────────────────────────────────────────

from app.observability import (
    StructuredLogger,
    get_logger,
    record_request_metric,
    sentry_init,
)

import app.observability as obs_mod


class TestStructuredLogger(unittest.TestCase):
    def test_get_logger_returns_instance(self):
        lg = get_logger("test.module")
        self.assertIsInstance(lg, StructuredLogger)

    def test_info_does_not_persist(self):
        lg = get_logger("test")
        with mock.patch.object(lg, "_persist") as m:
            lg.info("hello")
            m.assert_not_called()

    def test_error_calls_persist_with_level(self):
        lg = get_logger("test")
        captured = {}

        def fake_persist(level, msg, **kw):
            captured["level"] = level
            captured["msg"] = msg

        with mock.patch.object(lg, "_persist", side_effect=fake_persist):
            lg.error("something broke")

        self.assertEqual(captured["level"], "error")

    def test_persist_skipped_without_supabase(self):
        lg = get_logger("test")
        with mock.patch.object(obs_mod, "_SUPABASE_URL", ""):
            # Should not raise
            lg._persist("error", "test message")

    def test_sentry_init_returns_false_without_dsn(self):
        with mock.patch.object(obs_mod, "_SENTRY_DSN", ""):
            result = sentry_init()
        self.assertFalse(result)

    def test_record_request_metric_skipped_without_supabase(self):
        with mock.patch.object(obs_mod, "_SUPABASE_URL", ""):
            record_request_metric(
                endpoint="/api/test",
                method="GET",
                status_code=200,
                latency_ms=42,
            )   # should not raise


# ── chaos ──────────────────────────────────────────────────────

import app.chaos as chaos_mod
from app.chaos import (
    ChaosRunner,
    FaultType,
    SCENARIOS,
    run_scenario,
    get_chaos_runner,
)


class TestChaosRunner(unittest.TestCase):
    def setUp(self):
        self.runner = ChaosRunner()

    def _start(self, fault_type: FaultType, **kwargs) -> None:
        with mock.patch.object(chaos_mod, "_CHAOS_ENABLED", True):
            with mock.patch.object(self.runner, "_persist_start", return_value=1):
                self.runner.start(
                    "test_exp",
                    "openai",
                    fault_type,
                    triggered_by="test",
                    **kwargs,
                )

    def test_start_disabled_returns_none(self):
        with mock.patch.object(chaos_mod, "_CHAOS_ENABLED", False):
            result = self.runner.start("x", "openai", FaultType.ERROR)
        self.assertIsNone(result)
        self.assertFalse(self.runner.is_active("openai"))

    def test_start_and_is_active(self):
        self._start(FaultType.LATENCY, latency_ms=0)
        self.assertTrue(self.runner.is_active("openai"))

    def test_stop(self):
        self._start(FaultType.ERROR, error_rate=1.0)
        with mock.patch.object(self.runner, "_persist_complete"):
            stopped = self.runner.stop("test_exp")
        self.assertTrue(stopped)
        self.assertFalse(self.runner.is_active("openai"))

    def test_stop_unknown_name(self):
        result = self.runner.stop("nonexistent")
        self.assertFalse(result)

    def test_inject_latency(self):
        self._start(FaultType.LATENCY, latency_ms=1)
        with mock.patch("time.sleep") as m:
            self.runner.inject_fault("openai")
        m.assert_called_once()

    def test_inject_error_raises(self):
        self._start(FaultType.ERROR, error_rate=1.0)
        with self.assertRaises(ConnectionError):
            self.runner.inject_fault("openai")

    def test_inject_error_rate_zero_no_raise(self):
        self._start(FaultType.ERROR, error_rate=0.0)
        # Should never raise with rate=0
        self.runner.inject_fault("openai")

    def test_inject_data_corruption_raises(self):
        self._start(FaultType.DATA_CORRUPTION)
        with self.assertRaises(ValueError):
            self.runner.inject_fault("openai")

    def test_inject_no_active_experiment(self):
        self.runner.inject_fault("supabase")   # nothing active, should not raise

    def test_experiment_auto_expires(self):
        with mock.patch.object(chaos_mod, "_CHAOS_ENABLED", True):
            with mock.patch.object(self.runner, "_persist_start", return_value=1):
                self.runner.start("auto_exp", "replicate", FaultType.ERROR, duration_sec=0)
        # duration_sec=0 → already expired
        time.sleep(0.01)
        exp = self.runner.get_active_experiment("replicate")
        self.assertIsNone(exp)

    def test_scenarios_dict_not_empty(self):
        self.assertGreater(len(SCENARIOS), 0)

    def test_run_scenario_unknown(self):
        result = run_scenario("nonexistent_scenario")
        self.assertIn("error", result)

    def test_run_scenario_known(self):
        with mock.patch.object(get_chaos_runner(), "start", return_value=42) as m:
            result = run_scenario("supabase-latency", triggered_by="test")
        self.assertIn("scenario", result)

    def test_get_chaos_runner_singleton(self):
        r1 = get_chaos_runner()
        r2 = get_chaos_runner()
        self.assertIs(r1, r2)


if __name__ == "__main__":
    unittest.main()
