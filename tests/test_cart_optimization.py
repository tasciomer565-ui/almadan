from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException

from app.comparator import extract_volume_info, lookup_barcode
from app.main import (
    api_barcode_lookup,
    ocr_receipt,
    create_shared_list,
    get_shared_list,
    update_shared_list,
    SharedListPayload,
    SharedListItem,
    ReceiptOcrRequest,
    parse_receipt_text,
    parse_receipt_details,
    receipt_store_from_text,
)

class CartOptimizationTests(unittest.TestCase):
    def test_extract_volume_info(self) -> None:
        # Test Litres
        self.assertEqual(extract_volume_info("Yudum Ayçiçek Yağı 5 L"), (5.0, "L"))
        self.assertEqual(extract_volume_info("Sırma Su 1.5 lt"), (1.5, "L"))
        self.assertEqual(extract_volume_info("Coca Cola 250 ml"), (0.25, "L"))
        
        # Test Kilograms
        self.assertEqual(extract_volume_info("Eriş Un 5 kg"), (5.0, "kg"))
        self.assertEqual(extract_volume_info("Sütaş Süzme Peynir 500 gr"), (0.5, "kg"))
        self.assertEqual(extract_volume_info("Hardline Whey 908 Gram"), (0.908, "kg"))

        # Test Electronics (GB/TB)
        self.assertEqual(extract_volume_info("Samsung T7 Portable SSD 1 TB"), (1000.0, "GB"))
        self.assertEqual(extract_volume_info("Kingston SSD 500 GB"), (500.0, "GB"))
        self.assertEqual(extract_volume_info("Sandisk USB 128 Gigabayt"), (128.0, "GB"))

        # Test Supplements (Servings)
        self.assertEqual(extract_volume_info("Bigjoy Creatine 120 Servis"), (120.0, "servis"))
        self.assertEqual(extract_volume_info("Whey Protein 60 porsiyon"), (60.0, "servis"))

        # Test Fashion / Packages (Pieces)
        self.assertEqual(extract_volume_info("Defacto Erkek Çorap 3'lü Paket"), (3.0, "adet"))
        self.assertEqual(extract_volume_info("Koton Kadın TişörT 2'li set"), (2.0, "adet"))

    @patch("app.comparator.search_n11_direct")
    @patch("app.comparator._fetch_aol_urls")
    def test_best_unit_price_supports_electronics(
        self,
        mock_fetch_urls,
        mock_n11,
    ) -> None:
        from app.comparator import search_products_by_name

        mock_fetch_urls.return_value = []
        mock_n11.return_value = (
            [
                {
                    "title": "Disk A 500 GB",
                    "price": 1500.0,
                    "original_price": None,
                    "image_url": None,
                    "source": "n11",
                    "url": "https://www.n11.com/urun/disk-a",
                    "labels": ["Önerilen"],
                    "extra_info": {"out_of_stock": False},
                },
                {
                    "title": "Disk B 1 TB",
                    "price": 2000.0,
                    "original_price": None,
                    "image_url": None,
                    "source": "n11",
                    "url": "https://www.n11.com/urun/disk-b",
                    "labels": ["Önerilen"],
                    "extra_info": {"out_of_stock": False},
                },
            ],
            "disk",
        )

        results = search_products_by_name("disk")
        best = next(item for item in results if item["extra_info"].get("best_unit_price"))
        self.assertEqual(best["title"], "Disk B 1 TB")
        self.assertIn("Birim Fiyat Avantajı", best["labels"])

    def test_optimize_basket_with_distance_filtering(self) -> None:
        from app.shopping import optimize_market_basket
        
        items = [
            {
                "name": "Süt 1 L",
                "quantity": 1,
                "offers": {
                    "bim": 5.0,
                    "metro": 2.0,
                    "migros": 99.0,
                    "a101": 99.0,
                    "sok": 99.0,
                    "file": 99.0,
                    "carrefoursa": 99.0,
                }
            }
        ]
        
        res_no_filter = optimize_market_basket(items, location_name="besiktas")
        self.assertEqual(res_no_filter["single_store"]["store"], "metro")
        self.assertEqual(res_no_filter["store_distances"]["metro"], 3.80)
        self.assertEqual(res_no_filter["store_distances"]["bim"], 0.10)
        
        res_filtered = optimize_market_basket(items, location_name="besiktas", max_distance=1.0)
        self.assertEqual(res_filtered["single_store"]["store"], "bim")

    def test_barcode_lookup_utility(self) -> None:
        # Valid Barcode
        match = lookup_barcode("8690506390074")
        self.assertIsNotNone(match)
        self.assertEqual(match["title"], "Yudum Ayçiçek Yağı 5 L")

        # Invalid Barcode
        self.assertIsNone(lookup_barcode("0000000000000"))



    def test_ocr_receipt_simulation(self) -> None:
        response = ocr_receipt(ReceiptOcrRequest(image_base64="mock_data"))
        self.assertEqual(response["store"], "migros")
        self.assertTrue(len(response["detected_items"]) > 0)
        self.assertEqual(response["detected_items"][0]["title"], "Yudum Ayçiçek Yağı 5 L")
        self.assertTrue(all(item["category"] for item in response["detected_items"]))

    def test_ocr_receipt_multi_category(self) -> None:
        # Cosmetics receipt
        response_cos = ocr_receipt(ReceiptOcrRequest(image_base64="data:image/png;base64,cosmetics_receipt"))
        self.assertEqual(response_cos["store"], "gratis")
        self.assertTrue(any("İpana" in x["title"] for x in response_cos["detected_items"]))

        # Electronics receipt
        response_elec = ocr_receipt(ReceiptOcrRequest(image_base64="data:image/png;base64,electronics_receipt"))
        self.assertEqual(response_elec["store"], "vatanbilgisayar")
        self.assertTrue(any("SSD" in x["title"] for x in response_elec["detected_items"]))

    @patch("app.main.requests.post")
    def test_real_ocr_failure_does_not_return_fake_products(self, post_mock) -> None:
        post_mock.side_effect = RuntimeError("ocr unavailable")
        with self.assertRaises(HTTPException) as raised:
            ocr_receipt(
                ReceiptOcrRequest(
                    image_base64="data:image/jpeg;base64,real-photo",
                    category_hint="grocery",
                )
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_receipt_parser_ignores_totals_and_detects_store(self) -> None:
        items = parse_receipt_text(
            "A101\nDOMATES 24,90\nSUT 1L 39,50\nTOPLAM 64,40\nKDV 5,85"
        )
        self.assertEqual([item["title"] for item in items], ["DOMATES", "SUT 1L"])
        self.assertEqual(receipt_store_from_text("A101 MARKET"), "a101")

    def test_receipt_parser_separates_meta_noise_from_items(self) -> None:
        parsed = parse_receipt_details(
            "\n".join([
                "A101 MARKET",
                "Tarih: 12/06/2026",
                "Saat: 14:21",
                "Mahmudiye Mah. Cuma Cami Caddesi 1078,00",
                "DOMATES 24,90",
                "10,00 SUT 1L",
                "URUN ADI",
                "TOPLAM 34,90",
            ]),
            category_hint="grocery",
        )

        self.assertEqual(
            [item["title"] for item in parsed["items"]],
            ["DOMATES", "SUT 1L"],
        )
        self.assertEqual([item["price"] for item in parsed["items"]], [24.9, 10.0])
        self.assertTrue(all(item["category"] == "grocery" for item in parsed["items"]))
        self.assertTrue(
            any("Cuma Cami" in line for line in parsed["receipt_info"])
        )

    def test_universal_receipt_parser_accepts_any_product_price_line(self) -> None:
        parsed = parse_receipt_details(
            "\n".join([
                "MIS KASAP",
                "KUZU ET 1.600,00",
                "DANA KIYMA 500.00",
                "KALEM 12,50",
                "TOPLAM 2.112,50",
            ])
        )

        self.assertEqual(
            [item["title"] for item in parsed["items"]],
            ["KUZU ET", "DANA KIYMA", "KALEM"],
        )
        self.assertEqual([item["price"] for item in parsed["items"]], [1600.0, 500.0, 12.5])
        self.assertTrue(all(item["category"] == "grocery" for item in parsed["items"]))

    def test_universal_receipt_parser_accepts_price_before_unit_noise(self) -> None:
        parsed = parse_receipt_details("KUZU ET 1.600,00 KG")

        self.assertEqual(parsed["items"][0]["title"], "KUZU ET")
        self.assertEqual(parsed["items"][0]["price"], 1600.0)

    @patch("app.tracker.load_db")
    @patch("app.tracker.save_db")
    @patch("app.tracker.send_push_to_owner")
    def test_cosmetics_expiration_alert(self, mock_send_push, mock_save_db, mock_load_db) -> None:
        from app.tracker import check_cosmetics_expiration
        from datetime import datetime, timezone, timedelta

        now_str = (datetime.now(timezone.utc) - timedelta(days=350)).isoformat()
        db = {
            "products": [
                {
                    "id": "prod-cos-1",
                    "title": "İpana Diş Macunu",
                    "owner_id": "user:test",
                    "extra_info": {
                        "opening_date": now_str,
                        "shelf_life_months": 12
                    }
                }
            ],
            "notifications": [],
            "users": {
                "user:test": {
                    "email": "test@test.com",
                    "phone": "05555555555",
                    "notification_pref": "both"
                }
            }
        }
        mock_load_db.return_value = db

        check_cosmetics_expiration()

        self.assertTrue(len(db["notifications"]) > 0)
        self.assertEqual(db["notifications"][0]["type"], "cosmetic_expiration_alert")

    @patch("app.main.save_db")
    @patch("app.main.load_db")
    def test_shared_lists_crud(self, mock_load_db, mock_save_db) -> None:
        db = {"shared_lists": {}}
        mock_load_db.return_value = db

        # Create List
        payload = SharedListPayload(
            items=[
                SharedListItem(id="1", name="Süt", checked=False),
                SharedListItem(id="2", name="Ekmek", checked=True)
            ]
        )
        res_create = create_shared_list(payload)
        list_id = res_create["id"]
        self.assertIsNotNone(list_id)
        self.assertEqual(len(res_create["items"]), 2)
        self.assertEqual(res_create["version"], 1)

        # Get List
        res_get = get_shared_list(list_id)
        self.assertEqual(res_get["id"], list_id)
        self.assertEqual(res_get["items"][0]["name"], "Süt")
        self.assertFalse(res_get["items"][0]["checked"])

        # Update List
        update_payload = SharedListPayload(
            items=[
                SharedListItem(id="1", name="Süt", checked=True),
                SharedListItem(id="2", name="Ekmek", checked=True)
            ]
        )
        res_update = update_shared_list(list_id, update_payload)
        self.assertTrue(res_update["items"][0]["checked"])
        self.assertEqual(res_update["version"], 2)
