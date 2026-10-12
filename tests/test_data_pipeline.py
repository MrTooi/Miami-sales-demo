import unittest
import pandas as pd
from decimal import Decimal
from data_pipeline import normalize, analyze, findings

class PipelineTests(unittest.TestCase):
    def sales(self):
        return pd.DataFrame([{"id":"S1","date":"2026-09-01","service":"Banners","amount":"100.00"},
                             {"id":"S2","date":"2026-09-02","service":"Banners","amount":"-20.00"}])
    def expenses(self):
        return pd.DataFrame([{"id":"E1","date":"2026-09-01","category":"direct","amount":"30"},
                             {"id":"E2","date":"2026-09-02","category":"operating","amount":"10"}])
    def test_reconciliation(self):
        r=analyze(normalize(self.sales(),"sales"),normalize(self.expenses(),"expenses"),expenses_complete=True)
        self.assertEqual(r["net_revenue"],Decimal("80"))
        self.assertEqual(r["operating_profit"],Decimal("40"))
    def test_sales_only_profit_unavailable(self):
        self.assertFalse(analyze(normalize(self.sales(),"sales"))["profit_available"])
    def test_duplicate_rejected(self):
        x=self.sales();x.loc[1,"id"]="S1"
        with self.assertRaisesRegex(ValueError,"duplicate"):normalize(x,"sales")
    def test_missing_amount_rejected(self):
        x=self.sales();x.loc[0,"amount"]=None
        with self.assertRaises(ValueError):normalize(x,"sales")
    def test_bad_date_rejected(self):
        x=self.sales();x.loc[0,"date"]="2026-02-30"
        with self.assertRaises(ValueError):normalize(x,"sales")
    def test_negative_expense_rejected(self):
        x=self.expenses();x.loc[0,"amount"]="-3"
        with self.assertRaises(ValueError):normalize(x,"expenses")
    def test_bad_category_rejected(self):
        x=self.expenses();x.loc[0,"category"]="unknown"
        with self.assertRaises(ValueError):normalize(x,"expenses")
    def test_duplicate_headers_rejected(self):
        x=self.sales();x.columns=["id","id","service","amount"]
        with self.assertRaises(ValueError):normalize(x,"sales")
    def test_findings_are_observed_not_estimated(self):
        x=findings(normalize(self.sales(),"sales"),normalize(self.expenses(),"expenses"))
        self.assertEqual(x[0]["amount"],Decimal("20"))
        self.assertNotIn("savings",x[0])
    def test_order_id_alias(self):
        x=self.sales().rename(columns={"id":"order_id"})
        self.assertEqual(normalize(x,"sales").iloc[0]["id"],"S1")
if __name__=="__main__":unittest.main()
