import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.main import claim_device_data, request_owner_id


class AuthOwnershipTests(unittest.TestCase):
    def test_request_owner_prefers_authenticated_user(self):
        request = SimpleNamespace(
            state=SimpleNamespace(user_id="user-123")
        )

        self.assertEqual(
            request_owner_id(request, "device-12345678"),
            "user:user-123",
        )

    def test_request_owner_uses_device_for_guests(self):
        request = SimpleNamespace(
            state=SimpleNamespace(user_id=None)
        )

        self.assertEqual(
            request_owner_id(request, "device-12345678"),
            "device-12345678",
        )

    def test_claim_device_data_moves_products_and_notifications(self):
        db = {
            "products": [
                {"id": "p1", "owner_id": "device-12345678"},
                {"id": "p2", "owner_id": "other-device"},
            ],
            "notifications": [
                {"id": "n1", "owner_id": "device-12345678"},
            ],
        }
        saved = []

        with (
            patch("app.main.load_db", return_value=db),
            patch("app.main.save_db", side_effect=saved.append),
        ):
            claim_device_data("device-12345678", "user-123")

        self.assertEqual(db["products"][0]["owner_id"], "user:user-123")
        self.assertEqual(db["products"][1]["owner_id"], "other-device")
        self.assertEqual(
            db["notifications"][0]["owner_id"],
            "user:user-123",
        )
        self.assertEqual(saved, [db])


if __name__ == "__main__":
    unittest.main()
