import unittest
from decimal import Decimal
from finance_engine import MAX_MONEY, AmountTooLarge, money, summarize

class FinanceTests(unittest.TestCase):
    def test_money_precision(self):
        self.assertEqual(money("$1,200.50"),Decimal("1200.50"))
        for bad in ("NaN","Infinity","1.234",None,True,"abc"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                money(bad)

    def test_sales_only_never_claims_profit(self):
        result=summarize([{"id":"a","amount":"100"}])
        self.assertFalse(result["profit_available"])
        self.assertNotIn("operating_profit",result)

    def test_profit_and_refunds(self):
        sales=[{"id":"1","amount":"100.00"},{"id":"2","amount":"-20.00"}]
        expenses=[{"id":"e1","amount":"30","category":"direct"},{"id":"e2","amount":"10","category":"operating"}]
        r=summarize(sales,expenses,expenses_complete=True)
        self.assertEqual(r["net_revenue"],Decimal("80"))
        self.assertEqual(r["refund_total"],Decimal("20"))
        self.assertEqual(r["gross_profit"],Decimal("50"))
        self.assertEqual(r["operating_profit"],Decimal("40"))
        self.assertEqual(r["operating_margin_pct"],Decimal("50"))

    def test_negative_profit(self):
        r=summarize([{"id":"1","amount":"20"}],[{"id":"x","amount":"25","category":"direct"}],expenses_complete=True)
        self.assertEqual(r["operating_profit"],Decimal("-5"))

    def test_zero_revenue_margin_undefined(self):
        r=summarize([{"id":"1","amount":"0"}],[],expenses_complete=True)
        self.assertIsNone(r["gross_margin_pct"])

    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate sale"):
            summarize([{"id":"1","amount":"2"},{"id":"1","amount":"2"}])
        with self.assertRaisesRegex(ValueError,"Duplicate expense"):
            summarize([], [{"id":"x","amount":"1","category":"direct"},{"id":"x","amount":"2","category":"operating"}])

    def test_missing_id_rejected(self):
        with self.assertRaises(ValueError):
            summarize([{"amount":"20"}])
        with self.assertRaises(ValueError):
            summarize([{"id":None,"amount":"20"}])

    def test_invalid_expenses_rejected(self):
        with self.assertRaises(ValueError):
            summarize([], [{"id":"1","amount":"-10","category":"direct"}])
        with self.assertRaises(ValueError):
            summarize([], [{"id":"1","amount":"10","category":"unknown"}])

    def test_expense_records_without_confirmation_never_show_profit(self):
        r=summarize(
            [{"id":"s1","amount":"100.00"}],
            [
                {"id":"e1","amount":"25.00","category":"direct"},
                {"id":"e2","amount":"5.00","category":"operating"},
            ],
        )
        self.assertFalse(r["profit_available"])
        self.assertNotIn("operating_profit",r)
        self.assertEqual(r["direct_costs"],Decimal("25.00"))
        self.assertEqual(r["operating_expenses"],Decimal("5.00"))
        self.assertEqual(r["profit_unavailable_reason"],"Expense coverage not confirmed")

    def test_exact_cents(self):
        r=summarize([{"id":"a","amount":"0.10"},{"id":"b","amount":"0.20"}])
        self.assertEqual(r["net_revenue"],Decimal("0.30"))

    def test_empty_expenses_is_explicit_zero_not_missing(self):
        self.assertTrue(summarize([],[],expenses_complete=True)["profit_available"])
        self.assertFalse(summarize([])["profit_available"])



class MoneySizeTests(unittest.TestCase):
    """Amounts are capped just under one trillion dollars so every sum stays exact (no rounding)."""

    def test_amounts_up_to_the_cap_are_read_exactly(self):
        for text, value in (("999,999,999,999.99", "999999999999.99"), ("-$999,999,999,999.99", "-999999999999.99"),
                            ("999999999999", "999999999999"), ("12.50", "12.50")):
            self.assertEqual(Decimal(value), money(text), text)
        self.assertEqual(MAX_MONEY, money(MAX_MONEY))
        self.assertEqual(Decimal(-999999999999), money(-999999999999))

    def test_larger_amounts_are_refused_never_rounded(self):
        too_large = ["1,000,000,000,000.00", "-1000000000000", "$1000000000000.01", "1" * 30, "9" * 30 + ".99",
                     "1" * 5000, 10 ** 30, -(10 ** 12), Decimal("1E+12"), Decimal("1000000000000.00")]
        # Checked by the too_large flag, as callers do: data_pipeline.analyze reloads finance_engine,
        # which replaces the AmountTooLarge class, but the flag survives.
        for value in too_large:
            with self.assertRaises(ValueError, msg=repr(value)[:40]) as caught:
                money(value)
            self.assertTrue(getattr(caught.exception, "too_large", False), repr(value)[:40])
        # AmountTooLarge is a ValueError, so every existing caller already refuses it.
        self.assertTrue(issubclass(AmountTooLarge, ValueError))
        # Long text that isn't an amount at all is still "not an amount", not "too large".
        with self.assertRaises(ValueError) as caught:
            money("this is not an amount, it is just a long line of text")
        self.assertFalse(getattr(caught.exception, "too_large", False))

    def test_the_too_large_reason_survives_the_engine_being_reloaded(self):
        import importlib
        import finance_engine
        import job_intake as ji
        importlib.reload(finance_engine)  # what data_pipeline.analyze does on every analysis
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        records = [ji.Record(2, ("INV-1", "10/02/2026", "A (fictional)", "J-1", "1" * 30))]
        result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertIn("more than MargenX can add up exactly", result.rejected[0]["reasons"][0])

    def test_sums_of_capped_amounts_stay_exact(self):
        # With Python's default 28 digits, adding a billion amounts at the cap (far more rows than any
        # file can hold) is still exact: the Inexact trap would raise if anything were rounded.
        from decimal import Inexact, localcontext
        with localcontext() as ctx:
            ctx.traps[Inexact] = True
            for amount in (MAX_MONEY, -MAX_MONEY, Decimal("0.01")):
                self.assertEqual(amount * 10 ** 9, sum([amount] * 1000, Decimal(0)) * 10 ** 6)
            total = Decimal(0)
            for _ in range(100_000):
                total += MAX_MONEY
            self.assertEqual(MAX_MONEY * 100_000, total)
            # The same trap does fire past 28 digits, so the test above would catch rounding.
            with self.assertRaises(Inexact):
                Decimal("9" * 30) + Decimal("0.01")


if __name__ == "__main__":
    unittest.main()
