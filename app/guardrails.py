"""
Guardrails — Sprint 6: AI Çıktı Denetimi

AI modellerinin döndürdüğü sonuçları üretim ortamına girmeden önce
istatistiksel ve kural tabanlı filtrelerden geçirir.

Denetlenen senaryolar:
  1. Fiyat sınır kontrolü    — tahmin edilen fiyat makul aralıkta mı?
  2. Fiyat tutarsızlığı      — tarihsel ortalamadan sapma çok yüksek mi?
  3. Ürün ismi halüsinasyonu — vision/embedding çıktısı gerçekçi mi?
  4. Liste temizliği         — alışveriş listesinde yasaklı/anlamsız öğe var mı?
  5. Güven eşiği             — model confidence skoru yeterince yüksek mi?
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# Alışveriş listesine girmemesi gereken kategoriler
_BLOCKLIST_PATTERNS = re.compile(
    r"\b(sigara|alkol|bira|votka|rakı|whisky|şarap|kumar|silah|ilaç|reçete)\b",
    re.IGNORECASE,
)

# Geçerli Türkçe market ürünü için minimum karakter ve anlam eşiği
_MIN_PRODUCT_LEN = 3
_MAX_PRODUCT_LEN = 200

# Fiyat makul sınırları (TL)
_PRICE_MIN = 0.50
_PRICE_MAX = 100_000.0

# Tarihsel ortalamadan maksimum sapma
_MAX_PRICE_DEVIATION_PCT = 300.0   # %300 sapma → guardrail devreye girer


@dataclass
class GuardrailResult:
    passed: bool
    check_type: str
    reason: str | None = None
    original_value: Any = None
    sanitized_value: Any = None


class Guardrails:
    """
    Zincirleme guardrail denetimleri.

    Kullanım:
        g = Guardrails()
        result = g.check_price(predicted=15.0, historical_avg=24.90)
        if not result.passed:
            logger.warning("Guardrail blocked: %s", result.reason)
    """

    # ── Fiyat Denetimleri ────────────────────────────────────

    def check_price_bounds(self, price: float) -> GuardrailResult:
        """Tahmin edilen fiyat mantıklı aralıkta mı?"""
        if price < _PRICE_MIN:
            return GuardrailResult(
                passed=False,
                check_type="price_bounds",
                reason=f"Fiyat çok düşük: ₺{price} < ₺{_PRICE_MIN}",
                original_value=price,
            )
        if price > _PRICE_MAX:
            return GuardrailResult(
                passed=False,
                check_type="price_bounds",
                reason=f"Fiyat çok yüksek: ₺{price} > ₺{_PRICE_MAX}",
                original_value=price,
            )
        return GuardrailResult(passed=True, check_type="price_bounds", original_value=price)

    def check_price_deviation(
        self,
        predicted: float,
        historical_avg: float,
        *,
        max_deviation_pct: float = _MAX_PRICE_DEVIATION_PCT,
    ) -> GuardrailResult:
        """Tahminin tarihsel ortalamadan sapması makul mı?"""
        if historical_avg <= 0:
            return GuardrailResult(passed=True, check_type="price_deviation",
                                   reason="Tarihsel veri yok, atlandi")
        deviation_pct = abs(predicted - historical_avg) / historical_avg * 100
        if deviation_pct > max_deviation_pct:
            return GuardrailResult(
                passed=False,
                check_type="price_deviation",
                reason=(
                    f"Tahmin tarihsel ortalamadan %{deviation_pct:.1f} sapıyor "
                    f"(maks %{max_deviation_pct}). "
                    f"Tahmin: ₺{predicted}, Ort: ₺{historical_avg:.2f}"
                ),
                original_value=predicted,
                sanitized_value=historical_avg,   # fallback: ortalamayı kullan
            )
        return GuardrailResult(
            passed=True,
            check_type="price_deviation",
            original_value=predicted,
        )

    def check_forecast_trend(
        self,
        prices: list[float],
        *,
        max_weekly_jump_pct: float = 50.0,
    ) -> GuardrailResult:
        """
        Tahmin serisi içinde tek bir adımda %50'den fazla fiyat atlayışı var mı?
        Prophet bazen overfitting ile saçma değerler üretir.
        """
        if len(prices) < 2:
            return GuardrailResult(passed=True, check_type="forecast_trend")
        for i in range(1, len(prices)):
            prev, curr = prices[i - 1], prices[i]
            if prev > 0:
                jump = abs(curr - prev) / prev * 100
                if jump > max_weekly_jump_pct:
                    return GuardrailResult(
                        passed=False,
                        check_type="forecast_trend",
                        reason=(
                            f"Adım {i}: ₺{prev:.2f} → ₺{curr:.2f} "
                            f"(%{jump:.1f} atlayış, maks %{max_weekly_jump_pct})"
                        ),
                        original_value=prices,
                    )
        return GuardrailResult(passed=True, check_type="forecast_trend", original_value=prices)

    # ── Ürün İsmi Denetimleri ────────────────────────────────

    def check_product_name(self, name: str) -> GuardrailResult:
        """Vision/embedding çıktısındaki ürün adı geçerli mi?"""
        name = name.strip() if name else ""

        if len(name) < _MIN_PRODUCT_LEN:
            return GuardrailResult(
                passed=False,
                check_type="product_name",
                reason=f"Ürün adı çok kısa: '{name}'",
                original_value=name,
            )
        if len(name) > _MAX_PRODUCT_LEN:
            sanitized = name[:_MAX_PRODUCT_LEN].strip()
            return GuardrailResult(
                passed=True,   # Kırp ama engelleme
                check_type="product_name",
                reason=f"Ürün adı kısaltıldı ({len(name)} → {_MAX_PRODUCT_LEN} karakter)",
                original_value=name,
                sanitized_value=sanitized,
            )
        if _BLOCKLIST_PATTERNS.search(name):
            return GuardrailResult(
                passed=False,
                check_type="product_name",
                reason=f"Engellenen kategori içeriyor: '{name}'",
                original_value=name,
            )
        return GuardrailResult(passed=True, check_type="product_name", original_value=name)

    def sanitize_product_name(self, name: str) -> str:
        """check_product_name başarılıysa temizlenmiş adı döndür."""
        result = self.check_product_name(name)
        if not result.passed:
            return ""
        return str(result.sanitized_value or result.original_value)

    # ── Alışveriş Listesi Denetimi ────────────────────────────

    def filter_shopping_list(self, items: list[dict]) -> tuple[list[dict], list[str]]:
        """
        Vision modelinin ürettiği alışveriş listesini filtreler.

        Döndürür:
            (geçen_öğeler, engellenen_öğe_listesi)
        """
        passed: list[dict] = []
        blocked: list[str] = []

        for item in items:
            title = str(item.get("title") or item.get("name") or "")
            result = self.check_product_name(title)
            if result.passed:
                # Kısaltılmışsa güncelle
                if result.sanitized_value:
                    item = {**item, "title": result.sanitized_value}
                passed.append(item)
            else:
                blocked.append(f"{title}: {result.reason}")

        return passed, blocked

    # ── Güven Skoru Denetimi ─────────────────────────────────

    def check_confidence(
        self,
        score: float,
        *,
        threshold: float = 0.60,
        check_type: str = "confidence",
    ) -> GuardrailResult:
        """Model confidence skoru yeterince yüksek mi?"""
        if score < threshold:
            return GuardrailResult(
                passed=False,
                check_type=check_type,
                reason=f"Güven skoru çok düşük: {score:.3f} < {threshold}",
                original_value=score,
            )
        return GuardrailResult(passed=True, check_type=check_type, original_value=score)

    # ── Zincir Denetim ────────────────────────────────────────

    def run_all_price_checks(
        self,
        price: float,
        *,
        historical_avg: float = 0,
        forecast_series: list[float] | None = None,
    ) -> list[GuardrailResult]:
        """Fiyat için tüm denetimleri sırayla çalıştırır."""
        results = [self.check_price_bounds(price)]
        if historical_avg:
            results.append(self.check_price_deviation(price, historical_avg))
        if forecast_series:
            results.append(self.check_forecast_trend(forecast_series))
        self._log_results(results)
        return results

    def all_passed(self, results: list[GuardrailResult]) -> bool:
        return all(r.passed for r in results)

    # ── Loglama ───────────────────────────────────────────────

    def _log_results(self, results: list[GuardrailResult]) -> None:
        """Başarısız guardrail'leri Supabase'e ve lokale loglar."""
        for r in results:
            if not r.passed:
                logger.warning("Guardrail BLOCKED [%s]: %s", r.check_type, r.reason)
            self._persist(r)

    def _persist(self, result: GuardrailResult) -> None:
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            return
        row = {
            "check_type":   result.check_type,
            "input_value":  str(result.original_value)[:200] if result.original_value is not None else None,
            "reason":       result.reason,
            "passed":       result.passed,
        }
        try:
            _req.post(
                f"{_SUPABASE_URL}/rest/v1/guardrail_logs",
                headers={
                    "apikey": _SUPABASE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=row,
                timeout=3,
            )
        except Exception:
            pass


# Singleton
guardrails = Guardrails()
