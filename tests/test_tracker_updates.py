import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import os

from app.tracker import log_sms_notification, log_email_notification, trigger_weekly_catalogs, refresh_product
from app.storage import DATA_DIR

class TestTrackerUpdates(unittest.TestCase):
    def setUp(self):
        self.sms_file = DATA_DIR / "sms_logs.json"
        self.email_file = DATA_DIR / "email_logs.json"
        self.clean_files()

    def tearDown(self):
        self.clean_files()

    def clean_files(self):
        for f in (self.sms_file, self.email_file):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    @patch("app.tracker.load_db")
    def test_log_notifications_routing(self, mock_load):
        # Setup mock db with users
        db = {
            "users": {
                "user:both": {
                    "email": "both@test.com",
                    "phone": "05551111111",
                    "notification_pref": "both"
                },
                "user:sms_only": {
                    "email": "sms@test.com",
                    "phone": "05552222222",
                    "notification_pref": "sms"
                },
                "user:email_only": {
                    "email": "email@test.com",
                    "phone": "05553333333",
                    "notification_pref": "email"
                }
            }
        }
        mock_load.return_value = db

        # 1. Routing for user:both -> should write both logs
        log_sms_notification("user:both", "Title SMS both", "Msg")
        log_email_notification("user:both", "Title Email both", "Msg")
        self.assertTrue(self.sms_file.exists())
        self.assertTrue(self.email_file.exists())

        # Check SMS
        with open(self.sms_file, "r", encoding="utf-8") as f:
            sms_logs = json.load(f)
        self.assertEqual(len(sms_logs), 1)
        self.assertEqual(sms_logs[0]["phone"], "05551111111")
        self.assertEqual(sms_logs[0]["title"], "Title SMS both")

        # Check Email
        with open(self.email_file, "r", encoding="utf-8") as f:
            email_logs = json.load(f)
        self.assertEqual(len(email_logs), 1)
        self.assertEqual(email_logs[0]["email"], "both@test.com")
        self.assertEqual(email_logs[0]["title"], "Title Email both")

        self.clean_files()

        # 2. Routing for user:sms_only -> should write only SMS
        log_sms_notification("user:sms_only", "Title SMS", "Msg")
        log_email_notification("user:sms_only", "Title Email", "Msg")
        self.assertTrue(self.sms_file.exists())
        self.assertFalse(self.email_file.exists())

        self.clean_files()

        # 3. Routing for user:email_only -> should write only Email
        log_sms_notification("user:email_only", "Title SMS", "Msg")
        log_email_notification("user:email_only", "Title Email", "Msg")
        self.assertFalse(self.sms_file.exists())
        self.assertTrue(self.email_file.exists())

    @patch("app.tracker.load_db")
    @patch("app.tracker.save_db")
    @patch("app.tracker.parse_product_url")
    def test_refresh_product_stock_back(self, mock_parse, mock_save_db, mock_load_db):
        product = {
            "id": "prod-1",
            "title": "Out of stock item",
            "url": "https://www.n11.com/urun/123",
            "source": "n11",
            "owner_id": "user:123",
            "extra_info": {
                "out_of_stock": True
            },
            "price_history": [
                {"price": 0, "seen_at": "2026-06-12T12:00:00"}
            ]
        }
        db = {
            "products": [product],
            "notifications": [],
            "push_subscriptions": [],
            "users": {
                "user:123": {
                    "email": "user@test.com",
                    "phone": "05554444444",
                    "notification_pref": "both"
                }
            }
        }
        mock_load_db.return_value = db

        mock_parsed_result = MagicMock()
        mock_parsed_result.price = 150.0
        mock_parsed_result.title = "Out of stock item"
        mock_parsed_result.image_url = "https://img.com/1"
        mock_parsed_result.warnings = []
        mock_parsed_result.source = "n11"
        mock_parsed_result.canonical_url = "https://www.n11.com/urun/123"
        mock_parse.return_value = mock_parsed_result

        res = refresh_product("prod-1")

        self.assertEqual(res["status"], "success")
        self.assertFalse(product["extra_info"]["out_of_stock"])
        self.assertEqual(len(db["notifications"]), 1)
        self.assertEqual(db["notifications"][0]["type"], "stock_back")

        # Verify SMS & Email logged
        self.assertTrue(self.sms_file.exists())
        self.assertTrue(self.email_file.exists())

    @patch("app.catalogs.fetch_all_catalogs")
    @patch("app.tracker.load_db")
    @patch("app.tracker.save_db")
    @patch("app.tracker.send_push_to_owner")
    def test_trigger_weekly_catalogs(
        self,
        mock_send_push,
        mock_save,
        mock_load,
        mock_fetch_catalogs,
    ):
        db = {
            "products": [
                {
                    "id": "p-1",
                    "owner_id": "user:user-A",
                    "title": "Yudum Ayçiçek Yağı 5 L",
                }
            ],
            "notifications": [],
            "push_subscriptions": [],
            "catalog_snapshots": {},
            "users": {
                "user:user-A": {
                    "email": "usera@test.com",
                    "phone": "05555555555",
                    "notification_pref": "both"
                }
            }
        }
        mock_load.return_value = db
        mock_fetch_catalogs.return_value = [
            {
                "store": "bim",
                "title": "BİM Aktüel Ürünler",
                "url": "https://www.bim.com.tr/aktuel",
                "items": ["Yudum Ayçiçek Yağı 5 L"],
                "keywords": ["yağ"],
                "fingerprint": "new-catalog",
                "checked_at": "2026-06-12T10:00:00+00:00",
                "ok": True,
            }
        ]

        trigger_weekly_catalogs()

        self.assertEqual(len(db["notifications"]), 2)
        self.assertEqual(db["notifications"][0]["title"], "Kataloğa Düştü!")
        self.assertEqual(
            db["catalog_snapshots"]["bim"]["fingerprint"],
            "new-catalog",
        )
        self.assertTrue(self.sms_file.exists())
        self.assertTrue(self.email_file.exists())

if __name__ == "__main__":
    unittest.main()
