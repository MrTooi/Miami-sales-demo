"""Issue #128, step 5b: Profit and Loss Detail cross-checked by Sales by Customer Detail (S3, S4).

Every report is made up, built in the layouts seen (tests/quickbooks_fixtures.py) and read end to end from
Excel bytes. Sales come only from Profit and Loss Detail; the second report only confirms or questions them.
"""
from decimal import Decimal
import dataclasses
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

D = Decimal
L, S = fx.line, fx.sale
X, Y = "Customer X (fictional)", "Customer Y (fictional)"
A, B = (X, "Job A"), (X, "Job B")
MATERIALS = ("Expenses", "Job Materials")
JOB_COSTS = {MATERIALS: qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)}


def pnl(income, costs=()):
    sections = {"Income": [("Design income", list(income))]}
    if costs:
        sections["Expenses"] = [("Job Materials", list(costs))]
    report = qp.read_profit_and_loss_detail("pnl.xlsx", fx.xlsx(fx.report_rows(sections)))
    assert report.reconciled, report.problems
    return report


def sbcd(customers, **kw):
    return qs.read_sales_by_customer_detail("sales.xlsx", fx.xlsx(fx.sbcd_rows(customers, **kw)))


def both_jobs_income(*extra):
    return [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0), L(3, "Invoice", "1002", f"{X}:Job B", 2000.0, 6000.0),
            *extra]


def both_jobs_sales(*extra_x, extra_customers=()):
    return [(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)]),
                     ("Job B", [S(3, "Invoice", "1002", "Design", 1, 2000), *extra_x])]), *extra_customers]


COSTS = [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0), L(6, "Bill", "B-2", f"{X}:Job B", 500.0, 1500.0)]


def figures(report, check, lines=None, accounts=None):
    answers = qf.OwnerAnswers(report=qf.report_fingerprint(report), sub_customers_are_jobs=True,
                              accounts=accounts if accounts is not None else JOB_COSTS, lines=lines or {})
    return qf.figures(report, answers, cross_check=check)


def holds(figure):
    return {(h.report, h.row) for h in figure.holds}


class MatchingTests(unittest.TestCase):
    def test_two_matching_reports_lift_the_one_report_rule(self):
        report = pnl(both_jobs_income(), COSTS)
        check = qc.cross_check(report, sbcd(both_jobs_sales()))
        self.assertTrue(check.usable, check.reasons)
        self.assertEqual(2, len(check.matched))
        self.assertEqual(((), ()), (check.pnl_unmatched, check.sbcd_unmatched))
        result = figures(report, check)
        for job, profit in ((A, D("3000")), (B, D("1500"))):
            figure = result.jobs[job]["profit_after_job_costs"]
            self.assertEqual((profit, qp.COMPLETE), (figure.amount, figure.status), figure.holds)
        # Without the second report, the one-report rule (S3) stays.
        alone = figures(report, None)
        self.assertEqual([qf.ONE_REPORT], [h.reason for h in alone.jobs[A]["profit_after_job_costs"].holds])

    def test_the_plans_s8_example_with_both_reports(self):
        # Job A ($4,000 sales, $1,000 costs), Job B ($2,000, $500), sales matching across both reports, and a $900
        # Job Materials cost with only a vendor name: both margins held until it's assigned; then Job A $2,100 and
        # Job B Complete.
        report = pnl(both_jobs_income(), [*COSTS, L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 2400.0)])
        check = qc.cross_check(report, sbcd(both_jobs_sales()))
        vendor = next(l.row for l in report.lines if l.amount == D("900.0"))
        before = figures(report, check)
        for job in (A, B):
            self.assertEqual(qp.NEEDS_A_CHECK, before.jobs[job]["profit_after_job_costs"].status)
        after = figures(report, check, lines={vendor: qf.LineAnswer(qf.JOB_COST, X, "Job A")})
        self.assertEqual(D("2100"), after.jobs[A]["profit_after_job_costs"].amount)
        self.assertEqual((D("1500"), qp.COMPLETE), (after.jobs[B]["profit_after_job_costs"].amount,
                                                   after.jobs[B]["profit_after_job_costs"].status))

    def test_the_plans_s4_example_a_300_invoice_missing_from_profit_and_loss(self):
        # Sales by Customer Detail has a $300 invoice for Customer Y that Profit and Loss Detail doesn't: the company's
        # sales, every customer's and every job's need a check, with the $300 beside them; no amount comes from it.
        report = pnl(both_jobs_income(), COSTS)
        check = qc.cross_check(report, sbcd(both_jobs_sales(extra_customers=[
            (Y, [S(4, "Invoice", "1003", "Design", 1, 300)], [])])))
        self.assertEqual(1, len(check.sbcd_unmatched))
        result = figures(report, check)
        self.assertEqual((D("6000"), qp.NEEDS_A_CHECK, D("300")),
                         (result.company["sales"].amount, result.company["sales"].status,
                          result.company["sales"].held_amount))
        for job in (A, B):
            self.assertEqual(qp.NEEDS_A_CHECK, result.jobs[job]["profit_after_job_costs"].status)
        self.assertNotIn(Y, result.customers)  # never a customer from the second report alone

    def test_a_profit_and_loss_line_missing_from_the_second_report_holds_its_job(self):
        report = pnl(both_jobs_income(L(4, "Invoice", "1004", f"{X}:Job B", 250.0, 6250.0)), COSTS)
        check = qc.cross_check(report, sbcd(both_jobs_sales()))
        missing = next(l.row for l in report.lines if l.num == "1004")
        self.assertEqual((missing,), check.pnl_unmatched)
        result = figures(report, check)
        self.assertIn(("Profit and Loss Detail", missing), holds(result.jobs[B]["sales"]))
        self.assertEqual(qp.COMPLETE, result.jobs[A]["profit_after_job_costs"].status)  # its own job only
        self.assertEqual(D("2250"), result.jobs[B]["sales"].amount)  # the amount still comes from Profit and Loss

    def test_identical_lines_are_matched_by_count(self):
        # Two identical $100 lines need two matches, never one.
        twice = [L(4, "Invoice", "1005", f"{X}:Job B", 100.0, 6100.0), L(4, "Invoice", "1005", f"{X}:Job B", 100.0, 6200.0)]
        report = pnl(both_jobs_income(*twice), COSTS)
        once = qc.cross_check(report, sbcd(both_jobs_sales(S(4, "Invoice", "1005", "Pots", 1, 100))))
        self.assertEqual(1, len(once.pnl_unmatched))
        self.assertEqual(qp.NEEDS_A_CHECK, figures(report, once).jobs[B]["sales"].status)
        two = qc.cross_check(report, sbcd(both_jobs_sales(S(4, "Invoice", "1005", "Pots", 1, 100),
                                                          S(4, "Invoice", "1005", "Pots", 1, 100))))
        self.assertEqual((), two.pnl_unmatched)
        self.assertEqual(qp.COMPLETE, figures(report, two).jobs[B]["sales"].status)

    def test_a_contradicting_job_or_customer_is_no_match(self):
        report = pnl(both_jobs_income(), COSTS)
        swapped = [(X, [], [("Job A", [S(3, "Invoice", "1002", "Design", 1, 2000)]),
                            ("Job B", [S(2, "Invoice", "1001", "Design", 1, 4000)])])]
        check = qc.cross_check(report, sbcd(swapped))
        self.assertEqual((2, 2), (len(check.pnl_unmatched), len(check.sbcd_unmatched)))
        result = figures(report, check)
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)
        other = qc.cross_check(report, sbcd([(Y, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)]),
                                                      ("Job B", [S(3, "Invoice", "1002", "Design", 1, 2000)])])]))
        self.assertEqual(2, len(other.pnl_unmatched))

    def test_a_different_date_amount_or_number_is_no_match(self):
        report = pnl(both_jobs_income(), COSTS)
        for changed in (S(9, "Invoice", "1002", "Design", 1, 2000), S(3, "Invoice", "1002", "Design", 1, "2000.01"),
                        S(3, "Invoice", "1099", "Design", 1, 2000), S(3, "Sales Receipt", "1002", "Design", 1, 2000)):
            with self.subTest(changed[1:4] + [changed[8]]):
                check = qc.cross_check(report, sbcd([(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)]),
                                                              ("Job B", [changed])])]))
                self.assertEqual(1, len(check.pnl_unmatched))
                self.assertEqual(qp.NEEDS_A_CHECK, figures(report, check).jobs[B]["sales"].status)

    def test_an_answer_that_contradicts_the_second_report_holds(self):
        # A $700 invoice named only "Customer X", answered as Job A, but listed under Job B in Sales by Customer Detail.
        report = pnl(both_jobs_income(L(4, "Invoice", "1003", X, 700.0, 6700.0)), COSTS)
        check = qc.cross_check(report, sbcd(both_jobs_sales(S(4, "Invoice", "1003", "Design", 1, 700))))
        self.assertEqual((), check.pnl_unmatched)
        row = next(l.row for l in report.lines if l.num == "1003")
        result = figures(report, check, lines={row: qf.LineAnswer(qf.REVENUE, job="Job A")})
        self.assertIn(("Profit and Loss Detail", row), holds(result.jobs[A]["sales"]))
        self.assertIn(("Profit and Loss Detail", row), holds(result.jobs[B]["sales"]))
        agreeing = figures(report, check, lines={row: qf.LineAnswer(qf.REVENUE, job="Job B")})
        self.assertEqual((D("2700"), qp.COMPLETE), (agreeing.jobs[B]["sales"].amount, agreeing.jobs[B]["sales"].status))

    def test_lines_that_arent_sales_forms_arent_expected_in_the_second_report(self):
        report = pnl(both_jobs_income(L(4, "Deposit", "", f"{X}:Job A", 50.0, 6050.0, "", "Checking")), COSTS)
        check = qc.cross_check(report, sbcd(both_jobs_sales()))
        self.assertEqual((), check.pnl_unmatched)
        result = figures(report, check)
        deposit = next(l.row for l in report.lines if l.transaction_type == "Deposit")
        self.assertIn(("Profit and Loss Detail", deposit), holds(result.jobs[A]["sales"]))  # still held: never counted
        self.assertEqual(qp.COMPLETE, result.jobs[B]["profit_after_job_costs"].status)


class ScopeTests(unittest.TestCase):
    """S4: two reports are combined only for the same company, dates and basis; otherwise the rule of one stays."""

    def assert_unusable(self, check, says):
        self.assertFalse(check.usable)
        self.assertTrue(any(says in r for r in check.reasons), check.reasons)

    def test_different_scopes_are_never_combined(self):
        report = pnl(both_jobs_income(), COSTS)
        cases = {
            "can't be shown to cover the same dates": sbcd(both_jobs_sales(), period="All Dates"),
            "they cover different dates": sbcd(both_jobs_sales(), period="January 1-October 31, 2026"),
            "different companies": sbcd(both_jobs_sales(), company="Another shop (fictional)"),
        }
        for says, other in cases.items():
            with self.subTest(says):
                check = qc.cross_check(report, other)
                self.assert_unusable(check, says)
                result = figures(report, check)
                self.assertIn("couldn't be used as the cross-check", " ".join(result.warnings))
                self.assertEqual([qf.ONE_REPORT], [h.reason for h in result.jobs[A]["profit_after_job_costs"].holds])

    def test_a_second_report_whose_totals_dont_match_proves_nothing(self):
        report = pnl(both_jobs_income(), COSTS)
        rows = fx.sbcd_rows(both_jobs_sales())
        rows = [r if r[:1] != ["TOTAL"] else [*r[:8], D("6000.01")] for r in rows]
        check = qc.cross_check(report, qs.read_sales_by_customer_detail("sales.xlsx", fx.xlsx(rows)))
        self.assert_unusable(check, "own totals don't all match")
        self.assertEqual(qp.NEEDS_A_CHECK, figures(report, check).jobs[A]["profit_after_job_costs"].status)

    def test_a_cross_check_made_for_another_report_isnt_used(self):
        report = pnl(both_jobs_income(), COSTS)
        other = pnl(both_jobs_income(L(4, "Invoice", "1004", f"{X}:Job B", 250.0, 6250.0)), COSTS)
        check = qc.cross_check(other, sbcd(both_jobs_sales()))
        result = figures(report, check)
        self.assertIn("made for another Profit and Loss Detail", " ".join(result.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, result.jobs[A]["profit_after_job_costs"].status)

    def test_amounts_never_come_from_the_second_report(self):
        report = pnl(both_jobs_income(), COSTS)
        extra = sbcd(both_jobs_sales(S(8, "Invoice", "1010", "Design", 1, 999)))
        result = figures(report, qc.cross_check(report, extra))
        self.assertEqual(D("6000"), result.company["sales"].amount)
        self.assertEqual(D("2000"), result.jobs[B]["sales"].amount)


if __name__ == "__main__":
    unittest.main()
