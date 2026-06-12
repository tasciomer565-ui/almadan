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
        "bim",
        "a101",
        "sok",
        "file",
        "metro",
        "carrefoursa",
        "migros",
    ))
    def test_single_and_split_basket_apply_coupons(self) -> None:
        items = [
            {
                "id": "milk",
                "name": "Sut 1 L",
                "offers": {
                    "bim": 35,
                    "a101": 30,
                    "sok": 33,
                    "file": 36,
                    "metro": 37,
                    "carrefoursa": 38,
                    "migros": 40,
                },
            },
            {
                "id": "flour",
                "name": "Un 5 kg",
                "offers": {
                    "bim": 80,
                    "a101": 90,
                    "sok": 84,
                    "file": 82,
                    "metro": 75,
                    "carrefoursa": 92,
                    "migros": 95,
                },
            },
        ]
        coupons = [
            {
                "id": "a101-5",
                "store": "a101",
                "code": "A1015",
                "min_amount": 100,
                "discount": 5,
                "active": True,
            }
        ]

        result = optimize_market_basket(items, coupons)

        self.assertEqual(result["single_store"]["store"], "metro")
        self.assertEqual(result["single_store"]["total"], 112.0)
        self.assertEqual(result["split_basket"]["total"], 105.0)
        self.assertEqual(result["split_basket"]["savings"], 7.0)
        stores = {group["store"] for group in result["split_basket"]["stores"]}
        self.assertEqual(stores, {"a101", "metro"})

    def test_empty_basket(self) -> None:
        result = optimize_market_basket([])
        self.assertIsNone(result["single_store"])
        self.assertEqual(result["baseline_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
