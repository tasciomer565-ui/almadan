from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from app.comparator import extract_volume_info, lookup_barcode
from app.main import (
    list_coupons,
    api_barcode_lookup,
    ocr_receipt,
    create_shared_list,
    get_shared_list,
    update_shared_list,
    SharedListPayload,
    SharedListItem,
    ReceiptOcrRequest,
    CouponPayload,
    create_coupon,
    delete_coupon,
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

    def test_barcode_lookup_utility(self) -> None:
        # Valid Barcode
        match = lookup_barcode("8690506390074")
        self.assertIsNotNone(match)
        self.assertEqual(match["title"], "Yudum Ayçiçek Yağı 5 L")

        # Invalid Barcode
        self.assertIsNone(lookup_barcode("0000000000000"))

    @patch("app.main.load_db")
    def test_coupons_endpoint(self, mock_load_db) -> None:
        db = {"coupons": [{"id": "c1", "store": "migros", "code": "MIGR50"}]}
        mock_load_db.return_value = db
        coupons = list_coupons()
        self.assertEqual(len(coupons), 1)
        self.assertEqual(coupons[0]["code"], "MIGR50")

    @patch("app.main.save_db")
    @patch("app.main.load_db")
    def test_coupon_create_and_delete(self, mock_load_db, mock_save_db) -> None:
        db = {"coupons": []}
        mock_load_db.return_value = db
        coupon = create_coupon(
            CouponPayload(
                store="migros",
                code="TEST50",
                min_amount=500,
                discount=50,
            )
        )
        self.assertEqual(coupon["store"], "migros")
        self.assertEqual(len(db["coupons"]), 1)

        result = delete_coupon(coupon["id"])
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(db["coupons"], [])

    def test_ocr_receipt_simulation(self) -> None:
        response = ocr_receipt(ReceiptOcrRequest(image_base64="mock_data"))
        self.assertEqual(response["store"], "migros")
        self.assertTrue(len(response["detected_items"]) > 0)
        self.assertEqual(response["detected_items"][0]["title"], "Yudum Ayçiçek Yağı 5 L")

    def test_ocr_receipt_multi_category(self) -> None:
        # Cosmetics receipt
        response_cos = ocr_receipt(ReceiptOcrRequest(image_base64="data:image/png;base64,cosmetics_receipt"))
        self.assertEqual(response_cos["store"], "gratis")
        self.assertTrue(any("İpana" in x["title"] for x in response_cos["detected_items"]))

        # Electronics receipt
        response_elec = ocr_receipt(ReceiptOcrRequest(image_base64="data:image/png;base64,electronics_receipt"))
        self.assertEqual(response_elec["store"], "vatanbilgisayar")
        self.assertTrue(any("SSD" in x["title"] for x in response_elec["detected_items"]))

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
