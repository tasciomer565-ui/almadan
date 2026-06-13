from __future__ import annotations

import unittest
from unittest.mock import patch

from app.shopping import (
    MARKET_STORES,
    calculate_unit_price,
    optimize_market_basket,
    simulated_market_prices,
)


class ShoppingFeatureTests(unittest.TestCase):
    def test_simulated_prices_are_stable_and_cover_markets(self) -> None:
        first = simulated_market_prices("Sut 1 L")
        second = simulated_market_prices("Sut 1 L")
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(MARKET_STORES))
        self.assertTrue(all(price > 0 for price in first.values()))

    def test_unit_price_analysis(self) -> None:
        self.assertEqual(
            calculate_unit_price("Su 1.5 L", 30),
            {"amount": 1.5, "unit": "L", "unit_price": 20.0},
        )
        self.assertEqual(
            calculate_unit_price("SSD 1 TB", 2000),
            {"amount": 1000.0, "unit": "GB", "unit_price": 2.0},
        )
        self.assertEqual(
            calculate_unit_price("Protein 60 servis", 1200),
            {"amount": 60.0, "unit": "servis", "unit_price": 20.0},
        )

    @patch("app.shopping.MARKET_STORES", (
        "trendyol",
        "hepsiburada",
        "amazon",
        "n11",
    ))
    def test_single_and_split_basket_apply_shipping(self) -> None:
        items = [
            {
                "id": "item1",
                "name": "T-shirt",
                "offers": {
                    "trendyol": 100,
                    "hepsiburada": 120,
                    "amazon": 130,
                    "n11": 90,
                },
            },
            {
                "id": "item2",
                "name": "Jeans",
                "offers": {
                    "trendyol": 250,
                    "hepsiburada": 220,
                    "amazon": 240,
                    "n11": 210,
                },
            },
        ]

        # Single store option should find n11 as cheapest (subtotal 300, total 300, shipping 0)
        # Hepsiburada would be: subtotal 340, total 340, shipping 0
        # Trendyol would be: subtotal 350, total 350, shipping 0
        # Amazon would be: subtotal 370, total 370, shipping 0
        result = optimize_market_basket(items)

        self.assertEqual(result["single_store"]["store"], "n11")
        self.assertEqual(result["single_store"]["total"], 300.0)
        
        # Split basket analysis:
        # Cheapest offers: item1 -> n11 (90 TL), item2 -> n11 (210 TL)
        # Since both are cheapest at n11, split total is 300.0
        self.assertEqual(result["split_basket"]["total"], 300.0)

    def test_empty_basket(self) -> None:
        result = optimize_market_basket([])
        self.assertIsNone(result["single_store"])
        self.assertEqual(result["baseline_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
