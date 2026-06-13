from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.main import (
    ReceiptCreateRequest,
    ReceiptItemPayload,
    create_receipt,
    delete_receipt,
    list_receipts,
    receipt_summary,
)


class ReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = SimpleNamespace(
            state=SimpleNamespace(user_id="receipt-user")
        )

    def test_create_list_and_delete_receipt(self) -> None:
        db = {"receipts": []}
        payload = ReceiptCreateRequest(
            store="Migros",
            purchased_at="2026-06-13",
            payment_method="card",
            items=[
                ReceiptItemPayload(
                    title="Süt 1 L",
                    price=40,
                    quantity=2,
                    category="grocery",
                ),
                ReceiptItemPayload(
                    title="Şampuan",
                    price=120,
                    category="cosmetics",
                ),
            ],
        )

        with (
            patch("app.main.load_db", return_value=db),
            patch("app.main.save_db") as save_db,
        ):
            created = create_receipt(payload, self.request)
            result = list_receipts(self.request, month="2026-06")
            deleted = delete_receipt(created["id"], self.request)

        self.assertEqual(created["total"], 200)
        self.assertEqual(result["summary"]["total"], 200)
        self.assertEqual(result["summary"]["store_totals"]["Migros"], 200)
        self.assertEqual(result["summary"]["category_totals"]["grocery"], 80)
        self.assertEqual(deleted["status"], "deleted")
        self.assertEqual(db["receipts"], [])
        self.assertEqual(save_db.call_count, 2)

    def test_summary_compares_previous_month(self) -> None:
        receipts = [
            {
                "purchased_at": "2026-05-10T10:00:00+00:00",
                "store": "A101",
                "total": 100,
                "items": [],
            },
            {
                "purchased_at": "2026-06-10T10:00:00+00:00",
                "store": "BİM",
                "total": 125,
                "items": [],
            },
        ]

        summary = receipt_summary(receipts, "2026-06")

        self.assertEqual(summary["total"], 125)
        self.assertEqual(summary["previous_total"], 100)
        self.assertEqual(summary["change_percent"], 25)


if __name__ == "__main__":
    unittest.main()
