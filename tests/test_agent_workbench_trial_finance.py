"""Synthetic-only acceptance and validation cases for Agent OS trial A."""

import unittest
from copy import deepcopy
from decimal import Decimal, Overflow, localcontext

from agent_workbench.trial_finance import summarize_transactions


class TrialFinanceTests(unittest.TestCase):
    def test_sales_are_exact_decimal_totals(self):
        result = summarize_transactions([
            {"kind": "sale", "amount": "0.10"},
            {"kind": "sale", "amount": Decimal("0.20")},
            {"kind": "sale", "amount": 1},
        ])
        self.assertEqual(result, {
            "revenue": Decimal("1.30"), "costs": Decimal("0.00"),
            "profit": Decimal("1.30"),
        })
        self.assertTrue(all(isinstance(value, Decimal) for value in result.values()))

    def test_costs_refund_and_movements_together(self):
        result = summarize_transactions([
            {"kind": "sale", "amount": "1000.00"},
            {"kind": "expense", "amount": "120.15"},
            {"kind": "provider_fee", "amount": "30.10"},
            {"kind": "refund", "amount": "20.25"},
            {"kind": "payout", "amount": "969.90"},
            {"kind": "bank_deposit", "amount": "969.90"},
        ])
        self.assertEqual(result, {
            "revenue": Decimal("979.75"), "costs": Decimal("150.25"),
            "profit": Decimal("829.50"),
        })

    def test_empty_zero_and_movement_only_inputs(self):
        zero = dict.fromkeys(("revenue", "costs", "profit"), Decimal("0.00"))
        self.assertEqual(summarize_transactions([]), zero)
        for kind in ("sale", "expense", "provider_fee", "refund", "payout", "bank_deposit"):
            with self.subTest(kind=kind):
                self.assertEqual(summarize_transactions([{"kind": kind, "amount": "0.00"}]), zero)
        for kind in ("payout", "bank_deposit"):
            with self.subTest(kind=kind):
                self.assertEqual(summarize_transactions([{"kind": kind, "amount": "500"}]), zero)

    def test_refund_and_costs_can_produce_negative_totals(self):
        result = summarize_transactions([
            {"kind": "sale", "amount": "0.10"},
            {"kind": "refund", "amount": "0.30"},
            {"kind": "expense", "amount": "0.15"},
        ])
        self.assertEqual(result, {
            "revenue": Decimal("-0.20"), "costs": Decimal("0.15"),
            "profit": Decimal("-0.35"),
        })

    def test_unknown_and_missing_kinds_fail_explicitly(self):
        for kind in ("unknown", "fee", "SALE", "", None, [], {}):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "Unknown transaction kind"):
                summarize_transactions([{"kind": kind, "amount": "1.00"}])
        with self.assertRaises(ValueError):
            summarize_transactions([{"amount": "1.00"}])

    def test_invalid_amounts_rejected_for_every_kind(self):
        invalid = (None, True, False, 0.1, "abc", "", "NaN", "sNaN",
                   "Infinity", "-Infinity", "-0.01", "1.001", Decimal("NaN"), [])
        for kind in ("sale", "expense", "provider_fee", "refund", "payout", "bank_deposit"):
            for amount in invalid:
                with self.subTest(kind=kind, amount=amount), self.assertRaises(ValueError):
                    summarize_transactions([{"kind": kind, "amount": amount}])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                summarize_transactions([{"kind": kind}])

    def test_non_mapping_records_fail(self):
        for record in (None, [], "sale", 1):
            with self.subTest(record=record), self.assertRaises(ValueError):
                summarize_transactions([record])

    def test_large_totals_preserve_cents_and_caller_context(self):
        with localcontext() as context:
            context.prec = 3
            result = summarize_transactions([
                {"kind": "sale", "amount": "123456789012345678901234567890.12"},
                {"kind": "sale", "amount": "0.01"},
                {"kind": "expense", "amount": "0.02"},
            ])
            self.assertEqual(result["revenue"], Decimal("123456789012345678901234567890.13"))
            self.assertEqual(result["profit"], Decimal("123456789012345678901234567890.11"))
            self.assertEqual(context.prec, 3)
            self.assertFalse(any(context.flags.values()))

    def test_input_is_unchanged_and_iterables_are_supported(self):
        records = [{"kind": "sale", "amount": "12.34"}]
        original = deepcopy(records)
        self.assertEqual(summarize_transactions(iter(records))["revenue"], Decimal("12.34"))
        self.assertEqual(records, original)

    def test_narrow_caller_exponent_bounds_cannot_overflow_or_round(self):
        for trap_overflow in (True, False):
            with self.subTest(trap_overflow=trap_overflow), localcontext() as context:
                context.Emax = 2
                context.Emin = 0
                context.prec = 1
                context.clamp = 1
                context.traps[Overflow] = trap_overflow
                context.clear_flags()
                result = summarize_transactions([
                    {"kind": "sale", "amount": "1000.00"},
                    {"kind": "expense", "amount": "0.01"},
                ])
                self.assertEqual(result, {
                    "revenue": Decimal("1000.00"), "costs": Decimal("0.01"),
                    "profit": Decimal("999.99"),
                })
                self.assertEqual((context.Emax, context.Emin, context.prec, context.clamp), (2, 0, 1, 1))
                self.assertEqual(context.traps[Overflow], trap_overflow)
                self.assertFalse(any(context.flags.values()))


if __name__ == "__main__":
    unittest.main()
