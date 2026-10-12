import unittest
from decimal import Decimal
from finance_engine import money, summarize

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

    def test_empty_expenses_is_explicit_zero_not_missing(self):
        self.assertTrue(summarize([],[],expenses_complete=True)["profit_available"])
        self.assertFalse(summarize([])["profit_available"])

if __name__=="__main__":
    unittest.main()
