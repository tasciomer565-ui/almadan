from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.main import (
    PushSubscriptionKeys,
    PushSubscriptionRequest,
    claim_device_data,
    save_push_subscription,
)
from app.push import send_push_to_owner
from app.storage import normalize_db
from app.tracker import notification_payload


class PushNotificationTests(unittest.TestCase):
    def test_storage_normalizes_push_subscriptions(self) -> None:
        db = normalize_db({"products": [], "notifications": []})
        self.assertEqual(db["push_subscriptions"], [])

    def test_claim_device_data_moves_push_subscription(self) -> None:
        db = {
            "products": [],
            "notifications": [],
            "push_subscriptions": [
                {"endpoint": "https://push.example/1", "owner_id": "device-12345678"}
            ],
            "password_reset_attempts": {},
        }

        import app.main as main

        original_load_db = main.load_db
        original_save_db = main.save_db
        saved = []
        main.load_db = lambda: db
        main.save_db = lambda value: saved.append(value)
        try:
            claim_device_data("device-12345678", "user-1")
        finally:
            main.load_db = original_load_db
            main.save_db = original_save_db

        self.assertEqual(
            db["push_subscriptions"][0]["owner_id"],
            "user:user-1",
        )
        self.assertEqual(len(saved), 1)

    def test_notification_payload_opens_product(self) -> None:
        payload = notification_payload(
            {"id": "product-1"},
            {
                "id": "notification-1",
                "title": "Fiyat düştü",
                "message": "Yeni fiyat 100 TL",
            },
        )
        self.assertEqual(payload["url"], "/?product=product-1")
        self.assertEqual(payload["tag"], "notification-1")

    @patch("app.main.public_image_url", return_value=True)
    @patch("app.main.push_enabled", return_value=True)
    @patch("app.main.save_db")
    @patch("app.main.load_db")
    def test_subscription_is_saved_for_owner(
        self,
        load_db_mock,
        save_db_mock,
        _push_enabled_mock,
        _public_url_mock,
    ) -> None:
        db = {
            "products": [],
            "notifications": [],
            "push_subscriptions": [],
            "password_reset_attempts": {},
        }
        load_db_mock.return_value = db
        request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))
        payload = PushSubscriptionRequest(
            endpoint="https://push.example.com/subscription/1",
            keys=PushSubscriptionKeys(
                p256dh="p" * 32,
                auth="a" * 16,
            ),
        )

        result = save_push_subscription(payload, request, None)

        self.assertEqual(result["status"], "subscribed")
        self.assertEqual(
            db["push_subscriptions"][0]["owner_id"],
            "user:user-1",
        )
        save_db_mock.assert_called_once_with(db)

    @patch("app.storage.save_db")
    @patch("app.storage.load_db")
    @patch("app.push.send_push")
    @patch("app.push.push_enabled", return_value=True)
    def test_push_is_sent_to_each_owner_device(
        self,
        _enabled_mock,
        send_mock,
        load_db_mock,
        save_db_mock,
    ) -> None:
        load_db_mock.return_value = {
            "push_subscriptions": [
                {
                    "owner_id": "user:user-1",
                    "endpoint": "https://push.example/1",
                    "keys": {"p256dh": "p", "auth": "a"},
                },
                {
                    "owner_id": "user:user-2",
                    "endpoint": "https://push.example/2",
                    "keys": {"p256dh": "p", "auth": "a"},
                },
            ]
        }

        result = send_push_to_owner(
            "user:user-1",
            {"title": "Fiyat düştü", "body": "100 TL"},
        )

        self.assertEqual(result, {"sent": 1, "removed": 0})
        send_mock.assert_called_once()
        save_db_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
