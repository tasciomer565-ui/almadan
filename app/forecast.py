from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from statistics import mean, pstdev
from typing import Any


MIN_OBSERVATIONS = 3
FORECAST_HORIZON_DAYS = 7


def parse_seen_at(value: Any, fallback_index: int) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_index * 86400, tz=timezone.utc)


def clean_history(history: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    observations = []
    for index, item in enumerate(history):
        try:
            price = float(item.get("price", 0))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        observations.append((parse_seen_at(item.get("seen_at"), index), price))
    observations.sort(key=lambda item: item[0])
    return observations


def linear_slope(xs: list[float], ys: list[float]) -> float:
    x_mean = mean(xs)
    y_mean = mean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        return 0.0
    return sum(
        (x - x_mean) * (y - y_mean)
        for x, y in zip(xs, ys, strict=True)
    ) / denominator


def confidence_level(observation_count: int, span_days: float) -> tuple[str, int]:
    sample_score = min(55, observation_count * 5)
    span_score = min(45, int(span_days * 1.5))
    score = min(100, sample_score + span_score)

    if score >= 75:
        return "yüksek", score
    if score >= 45:
        return "orta", score
    return "düşük", score


def calculate_discount_forecast(product: dict[str, Any]) -> dict[str, Any]:
    observations = clean_history(product.get("price_history", []))
    missing = max(0, MIN_OBSERVATIONS - len(observations))

    if missing:
        return {
            "status": "insufficient",
            "horizon_days": FORECAST_HORIZON_DAYS,
            "probability": None,
            "confidence": "düşük",
            "confidence_score": 0,
            "expected_drop_percent": None,
            "recommendation": "takip et",
            "message": (
                f"Tahmin için {missing} fiyat kaydı daha gerekiyor. "
                "Fiyat kontrolleri arttıkça tahmin güçlenecek."
            ),
            "observation_count": len(observations),
        }

    first_time = observations[0][0]
    times = [
        max(0.0, (seen_at - first_time).total_seconds() / 86400)
        for seen_at, _ in observations
    ]
    prices = [price for _, price in observations]
    current = prices[-1]
    average = mean(prices)
    lowest = min(prices)
    span_days = max(times[-1], float(len(prices) - 1))
    slope_per_day = linear_slope(times, prices)
    slope_percent = slope_per_day / average if average else 0
    volatility = pstdev(prices) / average if average and len(prices) > 1 else 0

    recent_prices = prices[-min(4, len(prices)) :]
    recent_change = (
        (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        if recent_prices[0]
        else 0
    )
    price_position = (current - lowest) / lowest if lowest else 0

    probability = 35.0
    probability += max(-22, min(22, -slope_percent * 900))
    probability += max(-18, min(18, -recent_change * 140))
    probability += min(12, volatility * 160)

    if current <= lowest * 1.02:
        probability -= 24
    elif current > average * 1.05:
        probability += 30
    elif current < average * 0.97:
        probability -= 8

    probability = int(round(max(8, min(88, probability))))

    projected_trend_drop = max(
        0.0,
        (-slope_per_day * FORECAST_HORIZON_DAYS) / current,
    )
    expected_drop = min(
        0.25,
        projected_trend_drop + volatility * sqrt(FORECAST_HORIZON_DAYS) * 0.45,
    )
    expected_drop_percent = round(expected_drop * 100, 1)
    confidence, confidence_score = confidence_level(len(prices), span_days)

    if current <= lowest * 1.02:
        recommendation = "şimdi al"
        message = (
            "Fiyat geçmişteki en düşük seviyeye çok yakın. "
            "Daha büyük bir düşüş bekleme ihtimali şu an sınırlı."
        )
    elif probability >= 65:
        recommendation = "bekle"
        message = (
            "Son fiyat yönü ve dalgalanma, önümüzdeki 7 günde "
            "yeni bir indirim olasılığını yükseltiyor."
        )
    elif probability >= 45:
        recommendation = "takip et"
        message = (
            "Fiyat hareketi kararsız. Kısa süre daha izlemek daha güvenli."
        )
    else:
        recommendation = "alınabilir"
        message = (
            "Yakın vadede belirgin bir fiyat düşüşü sinyali görünmüyor."
        )

    return {
        "status": "ready",
        "horizon_days": FORECAST_HORIZON_DAYS,
        "probability": probability,
        "confidence": confidence,
        "confidence_score": confidence_score,
        "expected_drop_percent": expected_drop_percent,
        "recommendation": recommendation,
        "message": message,
        "observation_count": len(prices),
        "price_position_percent": round(price_position * 100, 1),
    }
