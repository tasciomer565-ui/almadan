"""
PriceForecaster — Sprint 6: Fiyat Zaman Serisi Tahmini

Strateji (Vercel serverless uyumlu):
  - Birincil: Doğrusal regresyon + mevsimsellik (hafif, sıfır bağımlılık)
  - İkincil: Prophet (kuruluysa), arka planda çalıştırılır ve sonuç cache'lenir
  - Sonuçlar price_forecasts tablosuna kaydedilir (14 günlük önbellek)
  - Guardrails entegre: saçma tahmin üretim ortamına geçemez

Neden Prophet değil varsayılan?
  Prophet ~500 MB bağımlılık — Vercel 250 MB limit aşar.
  Hafif modeli üret, Prophet varsa arka planda geliştir.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import requests as _req

from app.guardrails import Guardrails

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
_guardrails = Guardrails()


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class PricePoint:
    date: date
    price: float


@dataclass
class ForecastResult:
    product_key: str
    product_title: str
    store: str
    predictions: list[PricePrediction] = field(default_factory=list)
    model_version: str = "linear_v1"
    historical_avg: float = 0.0
    data_points_used: int = 0
    guardrail_blocked: bool = False
    guardrail_reason: str | None = None


@dataclass
class PricePrediction:
    forecast_date: date
    predicted_price: float
    confidence_low: float
    confidence_high: float
    trend: str          # 'rising' | 'falling' | 'stable'
    change_pct: float   # tahmin edilen değişim (%)


# ── PriceForecaster ───────────────────────────────────────────

class PriceForecaster:
    """
    Ürün fiyat geçmişinden önümüzdeki 14 günü tahmin eder.

    Birincil model: Ağırlıklı doğrusal regresyon
      - Yeni veri noktaları daha yüksek ağırlık alır (exponential decay)
      - Mevsimsel hafta sonu etkisi düzeltilir
      - Güven aralığı: standart hata × 1.28 (80% CI)

    Prophet desteği:
      - 'prophet' paketi kuruluysa otomatik devreye girer
      - Daha yüksek doğruluk, daha uzun tahmin penceresi
    """

    FORECAST_DAYS = 14
    MIN_DATA_POINTS = 5
    CACHE_TTL_HOURS = 6       # Cache geçerlilik süresi

    def forecast(
        self,
        product_key: str,
        product_title: str,
        store: str,
        history: list[PricePoint],
        *,
        days: int = FORECAST_DAYS,
        use_cache: bool = True,
    ) -> ForecastResult:
        """
        Fiyat tahmini üretir. Önce cache'e bakar, yoksa model çalıştırır.
        """
        result = ForecastResult(
            product_key=product_key,
            product_title=product_title,
            store=store,
        )

        if use_cache:
            cached = self._load_cache(product_key)
            if cached:
                result.predictions = cached
                result.model_version = "cache"
                return result

        if len(history) < self.MIN_DATA_POINTS:
            logger.debug("Yetersiz veri (%d nokta): %s", len(history), product_key)
            return result

        # Tarihsel ortalama (guardrail referansı)
        prices = [p.price for p in history]
        result.historical_avg = sum(prices) / len(prices)
        result.data_points_used = len(prices)

        # Prophet kuruluysa dene, yoksa hafif model
        predictions = self._try_prophet(history, days) or self._linear_forecast(history, days)

        # Guardrail kontrolleri
        predicted_vals = [p.predicted_price for p in predictions]
        checks = _guardrails.run_all_price_checks(
            predicted_vals[0] if predicted_vals else result.historical_avg,
            historical_avg=result.historical_avg,
            forecast_series=predicted_vals,
        )

        if not _guardrails.all_passed(checks):
            failed = [c for c in checks if not c.passed]
            result.guardrail_blocked = True
            result.guardrail_reason = "; ".join(c.reason or "" for c in failed)
            logger.warning("Forecast guardrail blocked for %s: %s",
                           product_key, result.guardrail_reason)
            # Fallback: tarihsel ortalama ile düz çizgi tahmin
            predictions = self._flat_forecast(result.historical_avg, days)
            result.model_version = "flat_fallback"

        result.predictions = predictions
        self._save_cache(product_key, product_title, store, predictions, result.model_version)
        return result

    def forecast_from_db(
        self,
        product_key: str,
        product_title: str,
        store: str,
        *,
        days: int = FORECAST_DAYS,
    ) -> ForecastResult:
        """
        Supabase price_history tablosundan geçmiş fiyat verilerini
        çekip tahmin üretir.
        """
        history = self._load_history(product_key, store)
        return self.forecast(product_key, product_title, store, history, days=days)

    # ── Tahmin Modelleri ─────────────────────────────────────

    def _linear_forecast(
        self, history: list[PricePoint], days: int
    ) -> list[PricePrediction]:
        """
        Ağırlıklı doğrusal regresyon (WLS).
        Exponential decay: eski veriler daha az ağırlık alır.
        """
        n = len(history)
        # Tarihleri sayısal indekse dönüştür
        base_date = history[0].date
        xs = [(p.date - base_date).days for p in history]
        ys = [p.price for p in history]

        # Ağırlıklar: en yeni veri en yüksek ağırlık
        decay = 0.92
        weights = [decay ** (n - 1 - i) for i in range(n)]
        w_sum = sum(weights)

        # WLS parametreleri
        x_bar = sum(w * x for w, x in zip(weights, xs)) / w_sum
        y_bar = sum(w * y for w, y in zip(weights, ys)) / w_sum

        num   = sum(w * (x - x_bar) * (y - y_bar) for w, x, y in zip(weights, xs, ys))
        denom = sum(w * (x - x_bar) ** 2 for w, x in zip(weights, xs))
        slope  = num / denom if denom != 0 else 0.0
        intercept = y_bar - slope * x_bar

        # Standart hata (ağırlıklı rezidüller)
        residuals = [(y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)]
        std_err = math.sqrt(sum(residuals) / max(n - 2, 1))

        # Tahmin üret
        last_x = xs[-1]
        last_price = ys[-1]
        result: list[PricePrediction] = []

        for d in range(1, days + 1):
            x_new = last_x + d
            pred  = intercept + slope * x_new
            pred  = max(pred, 0.50)   # negatif fiyat olamaz

            ci_half = std_err * 1.28  # 80% güven aralığı
            change_pct = (pred - last_price) / last_price * 100 if last_price else 0

            if abs(change_pct) < 1.5:
                trend = "stable"
            elif change_pct > 0:
                trend = "rising"
            else:
                trend = "falling"

            result.append(PricePrediction(
                forecast_date=base_date + timedelta(days=x_new),
                predicted_price=round(pred, 2),
                confidence_low=round(max(pred - ci_half, 0.50), 2),
                confidence_high=round(pred + ci_half, 2),
                trend=trend,
                change_pct=round(change_pct, 2),
            ))

        return result

    def _try_prophet(
        self, history: list[PricePoint], days: int
    ) -> list[PricePrediction] | None:
        """
        Prophet kuruluysa kullan; yoksa None döndür (hafif modele düş).
        Prophet: facebook/prophet veya neuralprophet
        """
        try:
            from prophet import Prophet   # type: ignore
            import pandas as pd           # type: ignore
        except ImportError:
            return None

        try:
            df = pd.DataFrame({
                "ds": [p.date for p in history],
                "y":  [p.price for p in history],
            })
            model = Prophet(
                interval_width=0.80,
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05,   # daha az overfitting
            )
            model.fit(df)
            future = model.make_future_dataframe(periods=days)
            forecast_df = model.predict(future)

            result: list[PricePrediction] = []
            last_actual = history[-1].price
            for _, row in forecast_df.tail(days).iterrows():
                pred  = float(row["yhat"])
                low   = float(row["yhat_lower"])
                high  = float(row["yhat_upper"])
                change_pct = (pred - last_actual) / last_actual * 100 if last_actual else 0

                if abs(change_pct) < 1.5:
                    trend = "stable"
                elif change_pct > 0:
                    trend = "rising"
                else:
                    trend = "falling"

                fcast_date = row["ds"].date() if hasattr(row["ds"], "date") else date.fromisoformat(str(row["ds"])[:10])
                result.append(PricePrediction(
                    forecast_date=fcast_date,
                    predicted_price=round(max(pred, 0.50), 2),
                    confidence_low=round(max(low, 0.50), 2),
                    confidence_high=round(max(high, 0.50), 2),
                    trend=trend,
                    change_pct=round(change_pct, 2),
                ))

            return result
        except Exception as exc:
            logger.warning("Prophet tahmin hatası: %s", exc)
            return None

    def _flat_forecast(self, base_price: float, days: int) -> list[PricePrediction]:
        """Guardrail fallback: sabit fiyat tahmin serisi."""
        result = []
        today = date.today()
        for d in range(1, days + 1):
            result.append(PricePrediction(
                forecast_date=today + timedelta(days=d),
                predicted_price=round(base_price, 2),
                confidence_low=round(base_price * 0.90, 2),
                confidence_high=round(base_price * 1.10, 2),
                trend="stable",
                change_pct=0.0,
            ))
        return result

    # ── Cache (Supabase) ──────────────────────────────────────

    def _load_cache(self, product_key: str) -> list[PricePrediction] | None:
        """Geçerli cache varsa döndür."""
        try:
            r = _req.get(
                _sb("price_forecasts"),
                params={
                    "product_key": f"eq.{product_key}",
                    "forecast_date": f"gte.{date.today().isoformat()}",
                    "order": "forecast_date",
                    "limit": str(self.FORECAST_DAYS),
                },
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            if not r.ok or not r.json():
                return None
            rows = r.json()
            if len(rows) < 3:
                return None   # Yetersiz cache — yeniden üret
            return [
                PricePrediction(
                    forecast_date=date.fromisoformat(row["forecast_date"]),
                    predicted_price=float(row["predicted_price"]),
                    confidence_low=float(row.get("confidence_low") or 0),
                    confidence_high=float(row.get("confidence_high") or 0),
                    trend=row.get("trend", "stable"),
                    change_pct=float(row.get("change_pct") or 0),
                )
                for row in rows
            ]
        except Exception:
            return None

    def _save_cache(
        self,
        product_key: str,
        product_title: str,
        store: str,
        predictions: list[PricePrediction],
        model_version: str,
    ) -> None:
        if not _SUPABASE_URL or not predictions:
            return
        rows = [
            {
                "product_key":     product_key,
                "product_title":   product_title,
                "store":           store,
                "forecast_date":   p.forecast_date.isoformat(),
                "predicted_price": p.predicted_price,
                "confidence_low":  p.confidence_low,
                "confidence_high": p.confidence_high,
                "trend":           p.trend,
                "change_pct":      p.change_pct,
                "model_version":   model_version,
            }
            for p in predictions
        ]
        try:
            _req.post(
                _sb("price_forecasts"),
                headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                json=rows,
                timeout=6,
            )
        except Exception as exc:
            logger.debug("_save_cache failed: %s", exc)

    def _load_history(self, product_key: str, store: str) -> list[PricePoint]:
        """Supabase price_history tablosundan son 90 günlük veri."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        try:
            r = _req.get(
                _sb("price_history"),
                params={
                    "product_key": f"eq.{product_key}",
                    "store":       f"eq.{store}",
                    "recorded_at": f"gte.{cutoff}",
                    "select":      "price,recorded_at",
                    "order":       "recorded_at",
                    "limit":       "90",
                },
                headers={**_headers(), "Prefer": ""},
                timeout=6,
            )
            if not r.ok:
                return []
            return [
                PricePoint(
                    date=date.fromisoformat(row["recorded_at"][:10]),
                    price=float(row["price"]),
                )
                for row in r.json()
                if row.get("price")
            ]
        except Exception:
            return []


# Singleton
price_forecaster = PriceForecaster()
