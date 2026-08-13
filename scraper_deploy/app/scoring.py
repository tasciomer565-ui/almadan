from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass
class DealDecision:
    score: int
    verdict: str
    reason: str


def calculate_deal_score(current_price: float, price_history: list[float]) -> DealDecision:
    clean_history = [price for price in price_history if price > 0]

    if current_price <= 0:
        return DealDecision(
            score=0,
            verdict="bekle",
            reason="Geçerli fiyat bilgisi yok.",
        )

    if not clean_history:
        return DealDecision(
            score=50,
            verdict="takip et",
            reason="Karar vermek için henüz fiyat geçmişi oluşmadı.",
        )

    lowest = min(clean_history)
    average = mean(clean_history)

    discount_vs_average = (average - current_price) / average
    near_lowest = current_price <= lowest * 1.03

    score = 50
    score += int(discount_vs_average * 180)

    if near_lowest:
        score += 20

    if current_price <= lowest:
        score += 10

    score = max(0, min(100, score))

    if score >= 80:
        verdict = "al"
        reason = "Fiyat geçmişine göre güçlü fırsat görünüyor."
    elif score >= 60:
        verdict = "düşünülebilir"
        reason = "Fiyat ortalamadan iyi, ama mükemmel fırsat değil."
    elif score >= 40:
        verdict = "takip et"
        reason = "Fiyat normal seviyede, biraz daha beklenebilir."
    else:
        verdict = "bekle"
        reason = "Fiyat geçmişe göre pahalı görünüyor."

    return DealDecision(score=score, verdict=verdict, reason=reason)
