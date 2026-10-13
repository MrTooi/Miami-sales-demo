from decimal import Decimal
import unittest

from agent_workbench_finance import canonical_net_revenue


class SyntheticFinanceTaskTests(unittest.TestCase):
    def test_returns_exact_decimal_net_sales_only(self):
        events = [
            {"kind": "sale", "amount": "100.00"},
            {"kind": "refund", "amount": "20.00"},
            {"kind": "fee", "amount": "3.00"},
            {"kind": "payout", "amount": "77.00"},
            {"kind": "bank_deposit", "amount": "77.00"},
        ]
        result = canonical_net_revenue(events)
        self.assertIsInstance(result, Decimal)
        self.assertEqual(Decimal("80.00"), result)

    def test_fractional_cents_are_not_silently_rounded_by_float(self):
        events = [
            {"kind": "sale", "amount": "0.10"},
            {"kind": "sale", "amount": "0.20"},
        ]
        self.assertEqual(Decimal("0.30"), canonical_net_revenue(events))


if __name__ == "__main__":
    unittest.main()
