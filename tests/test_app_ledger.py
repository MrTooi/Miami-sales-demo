import unittest
from decimal import Decimal

import pandas as pd

from app_ledger import deterministic_batch_id, normalize_transfer_frame, sales_to_integrity_records
from ledger_store import LedgerStore


class AppLedgerTests(unittest.TestCase):
    def sales(self):
        return pd.DataFrame(
            {
                "id": ["s-1", "r-1"],
                "date": pd.to_datetime(["2026-10-01", "2026-10-02"]),
                "service": ["Signs", "Refund"],
                "amount": [Decimal("100.10"), Decimal("-20.05")],
            }
        )

    def test_sales_mapping_uses_explicit_refund_kind(self):
        records = sales_to_integrity_records(self.sales(), "tenant-a", "square_export")
        self.assertEqual(records[0]["kind"], "sale")
        self.assertEqual(records[0]["amount"], "100.10")
        self.assertEqual(records[1]["kind"], "refund")
        self.assertEqual(records[1]["amount"], "20.05")

    def test_stable_batch_id_is_order_independent(self):
        records = sales_to_integrity_records(self.sales(), "tenant-a", "square_export")
        self.assertEqual(
            deterministic_batch_id(records, "sales"),
            deterministic_batch_id(list(reversed(records)), "sales"),
        )

    def test_same_dashboard_upload_is_idempotent_in_store(self):
        records = sales_to_integrity_records(self.sales(), "tenant-a", "square_export")
        batch_id = deterministic_batch_id(records, "sales")
        with LedgerStore(":memory:") as store:
            first = store.ingest(records, batch_id=batch_id)
            second = store.ingest(records, batch_id=batch_id)
            self.assertEqual(first["inserted_count"], 2)
            self.assertTrue(second["replayed"])
            self.assertEqual(len(store.list_transactions("tenant-a")), 2)

    def test_changed_file_adds_new_rows_without_recounting_old_rows(self):
        original = sales_to_integrity_records(self.sales(), "tenant-a", "square_export")
        expanded = original + [{
            "tenant_id": "tenant-a",
            "source": "square_export",
            "external_id": "s-2",
            "kind": "sale",
            "amount": "50.00",
            "currency": "USD",
        }]
        with LedgerStore(":memory:") as store:
            store.ingest(original, batch_id=deterministic_batch_id(original, "sales"))
            result = store.ingest(expanded, batch_id=deterministic_batch_id(expanded, "sales"))
            self.assertEqual(result["inserted_count"], 1)
            self.assertEqual(result["duplicate_count"], 2)
            self.assertEqual(len(store.list_transactions("tenant-a")), 3)

    def test_transfer_import_defaults_to_usd(self):
        frame = pd.DataFrame({
            "external_id": ["p-1"],
            "kind": ["payout"],
            "amount": ["970.00"],
        })
        records = normalize_transfer_frame(frame, "tenant-a", "square")
        self.assertEqual(records[0]["currency"], "USD")
        self.assertEqual(records[0]["amount"], "970.00")

    def test_transfer_import_rejects_unsupported_kind(self):
        frame = pd.DataFrame({
            "external_id": ["x-1"],
            "kind": ["sale"],
            "amount": ["10.00"],
        })
        with self.assertRaisesRegex(ValueError, "payout or bank_deposit"):
            normalize_transfer_frame(frame, "tenant-a", "square")

    def test_transfer_import_rejects_duplicate_ids(self):
        frame = pd.DataFrame({
            "external_id": ["p-1", "p-1"],
            "kind": ["payout", "payout"],
            "amount": ["10.00", "10.00"],
        })
        with self.assertRaisesRegex(ValueError, "Duplicate external_id"):
            normalize_transfer_frame(frame, "tenant-a", "square")


if __name__ == "__main__":
    unittest.main()
