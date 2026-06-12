from __future__ import annotations

import unittest

from app.forecast import calculate_discount_forecast


def product_with_prices(prices: list[float]) -> dict:
    return {
        "price_history": [
            {
                "price": price,
                "seen_at": f"2026-06-{index + 1:02d}T10:00:00+00:00",
            }
            for index, price in enumerate(prices)
        ]
    }


class DiscountForecastTests(unittest.TestCase):
    def test_requires_at_least_three_prices(self) -> None:
        forecast = calculate_discount_forecast(product_with_prices([100, 98]))
        self.assertEqual(forecast["status"], "insufficient")
        self.assertEqual(forecast["probability"], None)

    def test_new_historic_low_recommends_buying(self) -> None:
        forecast = calculate_discount_forecast(
            product_with_prices([1200, 1180, 1140, 1090, 1050])
        )
        self.assertEqual(forecast["status"], "ready")
        self.assertGreaterEqual(forecast["probability"], 50)
        self.assertEqual(forecast["recommendation"], "şimdi al")

    def test_high_current_price_can_signal_future_discount(self) -> None:
        forecast = calculate_discount_forecast(
            product_with_prices([100, 110, 108, 115, 120])
        )
        self.assertEqual(forecast["status"], "ready")
        self.assertGreaterEqual(forecast["probability"], 40)

    def test_near_historic_low_recommends_buying(self) -> None:
        forecast = calculate_discount_forecast(
            product_with_prices([100, 95, 98, 94])
        )
        self.assertEqual(forecast["recommendation"], "şimdi al")
        self.assertLess(forecast["probability"], 65)


if __name__ == "__main__":
    unittest.main()
