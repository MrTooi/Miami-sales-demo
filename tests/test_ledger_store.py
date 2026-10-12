import os
import tempfile
import unittest
from decimal import Decimal

from ledger_store import LedgerStore


def record(source, external_id, kind, amount, tenant_id="shop-1"):
    return {
        "tenant_id": tenant_id,
        "source": source,
        "external_id": external_id,
        "kind": kind,
        "amount": amount,
        "currency": "USD",
    }


class LedgerStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tempdir.name, "ledger.db")
        self.store = LedgerStore(self.path)

    def tearDown(self):
        try:
            self.store.close()
        except sqlite3.ProgrammingError:
            pass
        self.tempdir.cleanup()

    def test_transactions_persist_after_reopen(self):
        self.store.ingest([record("square", "p-1", "sale", "10.25")], batch_id="b1")
        self.store.close()
        self.store = LedgerStore(self.path)
        rows = self.store.list_transactions("shop-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], Decimal("10.25"))

    def test_duplicate_across_later_batches_is_idempotent(self):
        payment = record("square", "p-1", "sale", "10.00")
        first = self.store.ingest([payment], batch_id="b1")
        second = self.store.ingest([payment], batch_id="b2")
        self.assertEqual(first["inserted_count"], 1)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(len(self.store.list_transactions("shop-1")), 1)

    def test_same_batch_replay_can_arrive_in_different_order(self):
        rows = [record("square", "p-1", "sale", "10"),
                record("square", "p-2", "sale", "20")]
        original = self.store.ingest(rows, batch_id="provider-page-1")
        replay = self.store.ingest(list(reversed(rows)), batch_id="provider-page-1")
        self.assertFalse(original["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(self.store.list_transactions("shop-1")), 2)

    def test_batch_id_reuse_with_different_content_is_rejected(self):
        self.store.ingest([record("square", "p-1", "sale", "10")], batch_id="same")
        with self.assertRaisesRegex(ValueError, "different contents"):
            self.store.ingest([record("square", "p-2", "sale", "10")], batch_id="same")

    def test_conflicting_revision_is_audited_and_does_not_overwrite(self):
        self.store.ingest([record("square", "p-1", "sale", "10")], batch_id="b1")
        result = self.store.ingest([record("square", "p-1", "sale", "12")], batch_id="b2")
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["conflict_count"], 1)
        self.assertEqual(self.store.list_transactions("shop-1")[0]["amount"], Decimal("10"))
        conflicts = self.store.list_conflicts("shop-1")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["incoming_amount"], Decimal("12"))

    def test_invalid_batch_is_atomic_and_writes_nothing(self):
        rows = [record("square", "p-1", "sale", "10"),
                record("square", "p-2", "sale", "1.001")]
        with self.assertRaises(ValueError):
            self.store.ingest(rows, batch_id="bad")
        self.assertEqual(self.store.list_transactions("shop-1"), [])
        self.assertIsNone(self.store._batch_summary("bad"))

    def test_batch_must_be_single_tenant_and_source(self):
        with self.assertRaisesRegex(ValueError, "one tenant"):
            self.store.ingest([
                record("square", "p-1", "sale", "10", tenant_id="shop-1"),
                record("square", "p-2", "sale", "10", tenant_id="shop-2"),
            ])
        with self.assertRaisesRegex(ValueError, "one source"):
            self.store.ingest([
                record("square", "p-1", "sale", "10"),
                record("stripe", "p-2", "sale", "10"),
            ])

    def test_tenant_and_source_keys_remain_isolated(self):
        self.store.ingest([record("square", "same-id", "sale", "10")], batch_id="b1")
        self.store.ingest([record("stripe", "same-id", "sale", "20")], batch_id="b2")
        self.store.ingest([record("square", "same-id", "sale", "30", tenant_id="shop-2")], batch_id="b3")
        self.assertEqual(len(self.store.list_transactions("shop-1")), 2)
        self.assertEqual(self.store.list_transactions("shop-2")[0]["amount"], Decimal("30"))

    def test_keep_existing_conflict_resolution_is_idempotent(self):
        self.store.ingest([record("square", "p-1", "sale", "10")], batch_id="b1")
        self.store.ingest([record("square", "p-1", "sale", "12")], batch_id="b2")
        conflict_id = self.store.list_conflicts("shop-1")[0]["id"]
        first = self.store.resolve_conflict(conflict_id, "keep_existing", note="provider export verified")
        replay = self.store.resolve_conflict(conflict_id, "keep_existing")
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.store.list_transactions("shop-1")[0]["amount"], Decimal("10"))
        self.assertEqual(self.store.list_conflicts("shop-1"), [])

    def test_accept_incoming_conflict_resolution_updates_canonical_record(self):
        self.store.ingest([record("square", "p-1", "sale", "10")], batch_id="b1")
        self.store.ingest([record("square", "p-1", "sale", "12")], batch_id="b2")
        conflict_id = self.store.list_conflicts("shop-1")[0]["id"]
        self.store.resolve_conflict(conflict_id, "accept_incoming")
        self.assertEqual(self.store.list_transactions("shop-1")[0]["amount"], Decimal("12"))

    def test_exact_reconciliation_is_suggested_but_not_auto_confirmed(self):
        self.store.ingest([record("square", "po-1", "payout", "970")], batch_id="sq1")
        self.store.ingest([record("bank", "d-1", "bank_deposit", "970")], batch_id="bank1")
        found = self.store.find_reconciliation_candidates("shop-1")
        self.assertEqual(len(found["candidates"]), 1)
        self.assertEqual(found["candidates"][0]["amount"], Decimal("970"))
        self.assertFalse(self.store.reconciliation_status("shop-1")["recorded_transfers_reconciled"])

    def test_ambiguous_equal_amounts_require_manual_review(self):
        self.store.ingest([
            record("square", "po-1", "payout", "100"),
            record("square", "po-2", "payout", "100"),
        ], batch_id="sq")
        self.store.ingest([
            record("bank", "d-1", "bank_deposit", "100"),
            record("bank", "d-2", "bank_deposit", "100"),
        ], batch_id="bank")
        found = self.store.find_reconciliation_candidates("shop-1")
        self.assertEqual(found["candidates"], [])
        self.assertEqual(len(found["ambiguous_groups"]), 1)
        self.assertEqual(found["ambiguous_groups"][0]["payout_count"], 2)

    def test_confirmed_reconciliation_is_persistent_and_idempotent(self):
        self.store.ingest([record("square", "po-1", "payout", "970")], batch_id="sq")
        self.store.ingest([record("bank", "d-1", "bank_deposit", "970")], batch_id="bank")
        first = self.store.confirm_reconciliation(
            "shop-1", payout_source="square", payout_external_id="po-1",
            deposit_source="bank", deposit_external_id="d-1")
        replay = self.store.confirm_reconciliation(
            "shop-1", payout_source="square", payout_external_id="po-1",
            deposit_source="bank", deposit_external_id="d-1")
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertTrue(self.store.reconciliation_status("shop-1")["recorded_transfers_reconciled"])

        self.store.close()
        self.store = LedgerStore(self.path)
        self.assertTrue(self.store.reconciliation_status("shop-1")["recorded_transfers_reconciled"])

    def test_reconciliation_rejects_amount_mismatch_and_reuse(self):
        self.store.ingest([record("square", "po-1", "payout", "970")], batch_id="sq")
        self.store.ingest([
            record("bank", "d-1", "bank_deposit", "970"),
            record("bank", "d-2", "bank_deposit", "960"),
        ], batch_id="bank")
        with self.assertRaisesRegex(ValueError, "same amount"):
            self.store.confirm_reconciliation(
                "shop-1", payout_source="square", payout_external_id="po-1",
                deposit_source="bank", deposit_external_id="d-2")
        self.store.confirm_reconciliation(
            "shop-1", payout_source="square", payout_external_id="po-1",
            deposit_source="bank", deposit_external_id="d-1")
        with self.assertRaisesRegex(ValueError, "already reconciled"):
            self.store.confirm_reconciliation(
                "shop-1", payout_source="square", payout_external_id="po-1",
                deposit_source="bank", deposit_external_id="d-2")

    def test_reconciliation_never_crosses_tenants(self):
        self.store.ingest([record("square", "po-1", "payout", "100", tenant_id="shop-1")], batch_id="sq")
        self.store.ingest([record("bank", "d-1", "bank_deposit", "100", tenant_id="shop-2")], batch_id="bank")
        self.assertEqual(self.store.find_reconciliation_candidates("shop-1")["candidates"], [])
        with self.assertRaisesRegex(ValueError, "Bank deposit transaction not found"):
            self.store.confirm_reconciliation(
                "shop-1", payout_source="square", payout_external_id="po-1",
                deposit_source="bank", deposit_external_id="d-1")

    def test_reconciled_transaction_cannot_be_replaced_by_conflict_resolution(self):
        self.store.ingest([record("square", "po-1", "payout", "100")], batch_id="sq1")
        self.store.ingest([record("bank", "d-1", "bank_deposit", "100")], batch_id="bank1")
        self.store.confirm_reconciliation(
            "shop-1", payout_source="square", payout_external_id="po-1",
            deposit_source="bank", deposit_external_id="d-1")
        self.store.ingest([record("square", "po-1", "payout", "101")], batch_id="sq2")
        conflict_id = self.store.list_conflicts("shop-1")[0]["id"]
        with self.assertRaisesRegex(ValueError, "reconciled transaction"):
            self.store.resolve_conflict(conflict_id, "accept_incoming")

    def test_kind_filter_and_status_warning_scope(self):
        self.store.ingest([
            record("square", "sale-1", "sale", "25"),
            record("square", "po-1", "payout", "24"),
        ], batch_id="sq")
        payouts = self.store.list_transactions("shop-1", kinds=["payout"])
        self.assertEqual([row["kind"] for row in payouts], ["payout"])
        status = self.store.reconciliation_status("shop-1")
        self.assertFalse(status["recorded_transfers_reconciled"])
        self.assertIn("does not prove", status["note"])


if __name__ == "__main__":
    unittest.main()
