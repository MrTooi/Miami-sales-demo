import unittest
from decimal import Decimal
from transaction_integrity import deduplicate, normalize_record, sales_summary

def record(source, external_id, kind, amount, tenant_id="shop-1"):
    return {"tenant_id": tenant_id, "source": source, "external_id": external_id,
            "kind": kind, "amount": amount, "currency": "USD"}

class TransactionIntegrityTests(unittest.TestCase):
    def test_square_fee_payout_and_bank_deposit_not_double_counted(self):
        records = [record("square", "payment-1", "sale", "1000.00"),
                   record("square", "fee-1", "fee", "30.00"),
                   record("square", "payout-1", "payout", "970.00"),
                   record("bank", "deposit-1", "bank_deposit", "970.00")]
        result = sales_summary(records, "shop-1")
        self.assertEqual(result["gross_sales"], Decimal("1000.00"))
        self.assertEqual(result["net_sales"], Decimal("1000.00"))
        self.assertEqual(result["recorded_fees"], Decimal("30.00"))
        self.assertFalse(result["reconciled"])

    def test_repeated_event_is_idempotent(self):
        payment = record("square", "p-1", "sale", "10.00")
        unique, count = deduplicate([payment, payment])
        self.assertEqual((len(unique), count), (1, 1))
        self.assertEqual(sales_summary([payment, payment], "shop-1")["net_sales"], Decimal("10.00"))

    def test_conflicting_revision_requires_review(self):
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            deduplicate([record("square", "p-1", "sale", "10.00"),
                         record("square", "p-1", "sale", "12.00")])

    def test_same_external_id_across_tenants_is_distinct(self):
        records = [record("square", "p-1", "sale", "10.00"),
                   record("square", "p-1", "sale", "50.00", tenant_id="shop-2")]
        self.assertEqual(sales_summary(records, "shop-1")["net_sales"], Decimal("10.00"))
        self.assertEqual(sales_summary(records, "shop-2")["net_sales"], Decimal("50.00"))

    def test_same_external_id_across_sources_not_assumed_same(self):
        unique, count = deduplicate([record("square", "p-1", "sale", "10"),
                                     record("stripe", "p-1", "sale", "10")])
        self.assertEqual((len(unique), count), (2, 0))

    def test_refunds_subtract_from_sales(self):
        result = sales_summary([record("square", "p-1", "sale", "100"),
                                record("square", "r-1", "refund", "20")], "shop-1")
        self.assertEqual(result["net_sales"], Decimal("80"))

    def test_precision(self):
        result = sales_summary([record("square", "p-1", "sale", "0.10"),
                                record("square", "p-2", "sale", "0.20")], "shop-1")
        self.assertEqual(result["net_sales"], Decimal("0.30"))

    def test_invalid_data_rejected(self):
        for bad in [record("square", "p", "sale", "-10"),
                    record("square", "p", "sale", "1.001"),
                    record("square", "p", "sale", "NaN"),
                    {**record("square", "p", "sale", "1"), "currency": "EUR"},
                    {**record("square", "p", "sale", "1"), "tenant_id": ""}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_record(bad)

if __name__ == "__main__":
    unittest.main()
