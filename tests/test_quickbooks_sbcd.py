"""Issue #128, step 5a: recognising and reading QuickBooks Online's Sales by Customer Detail.

End to end on made-up files in the layout seen (tests/quickbooks_fixtures.py): Excel bytes -> rows ->
recognised layout -> customer and sub-customer groups, lines and totals -> checks -> one ledger outcome
per line -> each customer's status. Uploads still refuse every QuickBooks report.
"""
from decimal import Decimal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_fixtures as fx  # noqa: E402
import job_intake as ji  # noqa: E402
import quickbooks_layouts as qlayouts  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_rules as qr  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

D = Decimal
S = fx.sale
CORAL, PALM, BAY = "Coral Cafe (fictional)", "Palm Gym (fictional)", "Bay Clinic (fictional)"


def customers(coral_total=None, palm=None, bay_lines=None):
    """Coral Cafe: $900 + $300. Palm Gym, with no own lines: Lobby $600; Pool $100 and a -$50 credit memo.
    Bay Clinic: $120 and a -$20 refund. Grand total $1,950; quantities 2 + 1 + 3 + 4 - 1 + 1 - 1 = 9."""
    return [(CORAL, [S(2, "Invoice", "1001", "Design:Patio", 2, 450), S(3, "Sales Receipt", "1002", "Plants", 1, 300)], []),
            (PALM, [], palm if palm is not None else [
                ("Lobby", [S(4, "Invoice", "1003", "Plants", 3, 200)]),
                ("Pool", [S(5, "Invoice", "1004", "Pots", 4, 25), S(6, "Credit Memo", "1005", "Pots", -1, 50)])]),
            (BAY, bay_lines or [S(7, "Invoice", "1006", "Planters", 1, 120), S(8, "Refund", "1007", "Planters", -1, 20)],
             [])]


def read(rows=None) -> qs.SalesByCustomerDetail:
    return qs.read_sales_by_customer_detail("sales.xlsx", fx.xlsx(rows or fx.sbcd_rows(customers())))


def replaced(rows, label, amount=None, quantity=None):
    """The rows with the total row `label` changed."""
    out = []
    for row in rows:
        if row[:1] == [label]:
            row = list(row)
            if amount is not None:
                row[8] = amount
            if quantity is not None:
                row[6] = quantity
        out.append(row)
    return out


class RecognitionTests(unittest.TestCase):
    def test_the_layout_seen_is_recognised_and_still_refused_on_upload(self):
        table = ji._xlsx_rows(fx.xlsx(fx.sbcd_rows(customers(), period="All Dates")))
        found = qlayouts.recognise_sales_by_customer_detail(table, is_xlsx=True)
        self.assertEqual((), found.problems)
        self.assertEqual((qr.SALES_BY_CUSTOMER_DETAIL, None, None), (found.layout.report, found.layout.period_start,
                                                                     found.layout.period_end))
        self.assertTrue(found.layout.in_period(qp._date("01/01/1999")))  # "All Dates" holds every date
        with self.assertRaisesRegex(ji.IntakeError, "This is QuickBooks' Sales by Customer Detail report for Biscayne "
                                                    r"Landscaping \(fictional\) \(All Dates, accrual basis\)"):
            ji.read_file("sales.xlsx", fx.xlsx(fx.sbcd_rows(customers(), period="All Dates")))

    def test_all_dates_is_still_refused_for_profit_and_loss_detail(self):
        found = qlayouts.recognise_profit_and_loss_detail(ji._xlsx_rows(fx.xlsx(fx.pnl_rows(period="All Dates"))),
                                                          is_xlsx=True)
        self.assertIsNone(found.layout)

    def test_variants_are_refused_with_their_reason(self):
        with self.assertRaisesRegex(ji.IntakeError, "it's a CSV file"):  # the upload page's reason
            ji.read_file("sales.csv", fx.csv_bytes(fx.sbcd_rows(customers())))
        cases = {
            "only as an Excel (.xlsx) file": ("sales.csv", fx.csv_bytes(fx.sbcd_rows(customers()))),
            "a column MargenX doesn't know: 'Customer full name'": ("sales.xlsx", fx.xlsx(fx.sbcd_rows(
                customers(), columns=[*fx.SBCD_COLUMNS, "Customer full name"]))),
            "missing the column 'Amount'": ("sales.xlsx", fx.xlsx(fx.sbcd_rows(
                customers(), columns=[c if c != "Amount" else "Total" for c in fx.SBCD_COLUMNS]))),
            "cash-basis": ("sales.xlsx", fx.xlsx(fx.sbcd_rows(
                customers(), footer="Cash Basis Monday, October 26, 2026 07:04 PM GMTZ"))),
            "row 4 should be empty": ("sales.xlsx", fx.xlsx(fx.sbcd_rows(customers(), row4=["Customer: Coral Cafe"]))),
        }
        for says, (name, data) in cases.items():
            with self.subTest(says), self.assertRaises(ji.IntakeError) as caught:
                qs.read_sales_by_customer_detail(name, data)
            self.assertIn(says, str(caught.exception))


class GoodReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = read()

    def test_every_total_matches_amounts_and_quantities(self):
        self.assertEqual((), self.report.problems)
        self.assertEqual({("Total for Coral Cafe (fictional)", D("1200")), ("Total for Lobby", D("600")),
                          ("Total for Pool", D("50")), ("Total for Palm Gym (fictional) with sub-customers", D("650")),
                          ("Total for Bay Clinic (fictional)", D("100")), ("TOTAL", D("1950"))},
                         {(c.label, c.expected) for c in self.report.checks})
        self.assertTrue(all(c.matches for c in self.report.checks))
        self.assertEqual(D("1950.00"), self.report.grand_total)

    def test_every_line_is_in_the_ledger_with_its_customer_and_sub_customer(self):
        lines = {l.num: l for l in self.report.lines}
        self.assertEqual(7, len(self.report.lines))
        self.assertEqual(((CORAL,), CORAL, None, qp.INCLUDED, qr.SALE),
                         (lines["1001"].customer_path, lines["1001"].customer, lines["1001"].sub_customer,
                          lines["1001"].outcome, lines["1001"].counts_as))
        self.assertEqual(((PALM, "Lobby"), "Lobby"), (lines["1003"].customer_path, lines["1003"].sub_customer))
        for held in ("1005", "1007"):  # a credit memo and a refund: not tested yet, held, never dropped
            self.assertEqual(qp.NOT_RESOLVED, lines[held].outcome)
        self.assertEqual(("sales.xlsx", "Sheet", "10/02/2026", "Design:Patio", "2", "450"),
                         (lines["1001"].source, lines["1001"].sheet, lines["1001"].date, lines["1001"].product,
                          lines["1001"].quantity_text, lines["1001"].price_text))

    def test_each_customer_adds_up_and_has_its_status(self):
        expected = {CORAL: (2, D("1200"), D("0"), True), PALM: (3, D("700"), D("-50"), False),
                    BAY: (2, D("120"), D("-20"), False)}
        for name, (count, included, held, status) in expected.items():
            with self.subTest(name):
                coverage = self.report.customers[name]
                self.assertEqual((count, included, held, status), (coverage.lines, coverage.included,
                                                                   coverage.not_resolved, coverage.all_counted))
                self.assertTrue(coverage.adds_up)
        self.assertFalse(self.report.ownership_proven)


class HeldTests(unittest.TestCase):
    """A total that doesn't match, an odd row or an odd line never makes a line disappear (S6)."""

    def assert_held(self, report, customer, says):
        self.assertTrue(any(says in p.text for p in report.problems), report.problems)
        coverage = report.customers[customer]
        self.assertEqual((False, False, 0), (coverage.totals_match, coverage.all_counted, coverage.included_lines))
        for line in report.lines:
            if line.customer == customer:
                self.assertEqual(qp.NOT_RESOLVED, line.outcome)

    def test_a_customer_total_a_cent_off_holds_that_customer_only(self):
        report = read(replaced(fx.sbcd_rows(customers()), "Total for Coral Cafe (fictional)", amount=D("1199.99")))
        self.assert_held(report, CORAL, "it says 1,199.99, but its lines add up to 1,200.00")
        self.assertTrue(report.customers[PALM].totals_match)

    def test_a_grand_total_that_doesnt_match_holds_every_customer(self):
        report = read(replaced(fx.sbcd_rows(customers()), "TOTAL", amount=D("1950.10")))
        for name in (CORAL, PALM, BAY):
            self.assert_held(report, name, "'TOTAL'")

    def test_a_quantity_total_that_doesnt_match_holds_its_customer(self):
        report = read(replaced(fx.sbcd_rows(customers()), "Total for Lobby", quantity=D("4")))
        self.assert_held(report, PALM, "its Quantity says 4")

    def test_the_float_rule_reads_a_noisy_stored_total(self):
        rows = replaced(fx.sbcd_rows(customers()), "Total for Coral Cafe (fictional)", amount=D("1199.9999999999998"))
        self.assertTrue(read(rows).customers[CORAL].all_counted)

    def test_a_line_whose_quantity_times_price_isnt_its_amount_is_held(self):
        bay = [S(7, "Invoice", "1006", "Planters", 1, 120, amount="125"), S(8, "Refund", "1007", "Planters", -1, 20)]
        report = read(fx.sbcd_rows(customers(bay_lines=bay)))
        line = next(l for l in report.lines if l.num == "1006")
        self.assertEqual(qp.NOT_RESOLVED, line.outcome)
        self.assertIn("Quantity × Sales price (1 × 120) doesn't give its Amount (125)", line.reason)
        # The automated review of 5f45bbd: it holds its whole customer, not just itself.
        self.assert_held(report, BAY, "doesn't give its Amount")
        self.assertTrue(report.customers[CORAL].totals_match)

    def test_a_good_line_beside_a_bad_one_is_held_too(self):
        good = S(7, "Invoice", "1006", "Planters", 1, 120)
        for bad, says in ((S(8, "Invoice", "1008", "Pots", 2, 30, amount="65"), "doesn't give its Amount"),
                          (S(8, "Invoice", "1008", "Pots", 2, 30), "outside the report's period"),
                          (S(8, "Invoice", "1008", "Pots", 2, 30), "isn't written the way QuickBooks writes dates")):
            with self.subTest(says):
                if "outside" in says:
                    bad[1] = "11/02/2026"
                elif "isn't written" in says:
                    bad[1] = "2026-10-08"
                report = read(fx.sbcd_rows(customers(bay_lines=[good, bad])))
                self.assert_held(report, BAY, says)
                self.assertEqual(qp.NOT_RESOLVED, next(l for l in report.lines if l.num == "1006").outcome)

    def test_huge_quantities_and_prices_are_held_never_a_crash(self):
        # The automated review of 5f45bbd: 100,000,000,000,000 × 100,000,000,000,000 can't be quantized to cents.
        huge = S(7, "Invoice", "1006", "Planters", 1, 120)
        huge[6], huge[7] = Decimal("100000000000000"), Decimal("100000000000000")
        report = read(fx.sbcd_rows(customers(bay_lines=[huge])))
        line = next(l for l in report.lines if l.num == "1006")
        self.assertEqual(qp.NOT_RESOLVED, line.outcome)
        self.assert_held(report, BAY, "doesn't give its Amount")

    def test_lines_with_uneven_cents_or_dates_outside_the_period_are_held(self):
        uneven = S(7, "Invoice", "1006", "Planters", 1, "120.005", amount="120.005")
        late = S(7, "Invoice", "1008", "Planters", 1, 120)
        late[1] = "11/02/2026"
        report = read(fx.sbcd_rows(customers(bay_lines=[uneven, late])))
        reasons = {l.num: l.reason for l in report.lines}
        self.assertIn("isn't an exact number of cents", reasons["1006"])
        self.assertIn("outside the report's period", reasons["1008"])
        self.assert_held(report, BAY, "outside the report's period")

    def test_structure_problems_hold(self):
        rows = fx.sbcd_rows(customers())
        cases = {
            "has no closing total": [r for r in rows if r[:1] != ["Total for Coral Cafe (fictional)"]],
            "the report has no grand TOTAL row": [r for r in rows if r[:1] != ["TOTAL"]],
            "appears twice": rows[:-5] + [[CORAL], S(9, "Invoice", "1099", "Plants", 1, 10),
                                          ["Total for Coral Cafe (fictional)", None, None, None, None, None, D("1"), None,
                                           D("10")]] + rows[-5:],
            "comes after the grand TOTAL": rows[:-4] + [[None, "10/09/2026", "Invoice", "2001", "", "", 1, 5, 5]] + rows[-4:],
            "isn't a heading, a line or a total": rows[:6] + [["Memo", None, None, None, None, "note", None, None, 5]]
                                                  + rows[6:],
        }
        for says, variant in cases.items():
            with self.subTest(says):
                report = read(variant)
                self.assertTrue(any(says in p.text for p in report.problems), report.problems)
                self.assertFalse(any(c.all_counted for c in report.customers.values()))

    def test_nesting_deeper_than_one_sub_customer_is_held(self):
        rows = fx.sbcd_rows(customers())
        index = rows.index(["Lobby"])
        deep = rows[:index + 1] + [["North wing"]] + rows[index + 1:index + 2] + [
            ["Total for North wing", None, None, None, None, None, D("3"), None, D("600")]] + rows[index + 2:]
        report = read(deep)
        self.assertTrue(any("nested 3 levels deep" in p.text for p in report.problems), report.problems)
        self.assertFalse(report.customers[PALM].all_counted)
        self.assertTrue(report.customers[CORAL].totals_match)

    def test_a_parent_with_its_own_lines_and_sub_customers(self):
        rows = fx.sbcd_rows([(PALM, [S(3, "Invoice", "1010", "Design", 1, 80)],
                              [("Lobby", [S(4, "Invoice", "1003", "Plants", 3, 200)])])])
        report = read(rows)
        self.assertEqual((), report.problems)
        self.assertEqual({"1010": (PALM,), "1003": (PALM, "Lobby")}, {l.num: l.customer_path for l in report.lines})
        self.assertEqual((D("680"), True), (report.customers[PALM].included, report.customers[PALM].all_counted))

    def test_a_missing_with_sub_customers_total_is_why_ownership_is_never_proven(self):
        # The automated review of 4ef0f9d: "A, invoice, Total for A, B, invoice, Total for B, TOTAL" reads as two
        # customers, whether or not B was A's sub-customer with A's combined total deleted. Both readings match every
        # remaining total, so this report never proves ownership; step 5b takes it from Profit and Loss Detail.
        rows = fx.sbcd_rows([(PALM, [S(3, "Invoice", "1010", "Design", 1, 80)],
                              [("Lobby", [S(4, "Invoice", "1003", "Plants", 3, 200)])])])
        deleted = [r for r in rows if r[:1] != [f"Total for {PALM} with sub-customers"]]
        report = read(deleted)
        self.assertEqual({PALM, "Lobby"}, set(report.customers))
        self.assertFalse(report.ownership_proven)
        self.assertEqual({PALM: (PALM,), "Lobby": ("Lobby",)}, {l.customer: l.customer_path for l in report.lines})

    def test_a_total_that_closes_nothing_above_it_holds_the_whole_report(self):
        rows = fx.sbcd_rows(customers())
        index = next(i for i, r in enumerate(rows) if r[:1] == ["Total for Lobby"])
        variant = rows[:index] + [["Total for Somebody else"] + rows[index][1:]] + rows[index + 1:]
        report = read(variant)
        self.assertTrue(any("doesn't close the customer above it" in p.text and p.section is None
                            for p in report.problems), report.problems)
        self.assertFalse(report.customers[CORAL].totals_match)  # another customer, otherwise fine, is held too

    def test_no_line_ever_disappears(self):
        rows = fx.sbcd_rows(customers())
        for variant in (rows, replaced(rows, "TOTAL", amount=D("1")), [r for r in rows if r[:1] != ["Total for Pool"]],
                        rows[:6] + [["Memo", None, None, None, None, "note", None, None, 5]] + rows[6:]):
            report = read(variant)
            expected = [i for i, r in enumerate(variant, 1) if i > 5 and len(r) > 2 and r[0] is None]
            unknown = [i for i, r in enumerate(variant, 1) if i > 5 and r[:1] == ["Memo"]]
            self.assertEqual(sorted(expected + unknown), sorted(l.row for l in report.lines))


if __name__ == "__main__":
    unittest.main()
