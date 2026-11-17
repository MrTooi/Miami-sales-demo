"""Issue #128, step 3: MargenX's reading of Profit and Loss Detail against known answers.

Like docs/ACCURACY.md's random shops: tests/qbo_pnl_reports.py generates made-up reports and works
out their right answers in whole cents without any MargenX code. Each report is written as an Excel
file and read by MargenX end to end. Line counts, each section's sum, what is counted as sales and
costs, what is held and each section's status must all match exactly; so must each customer's and each
job's sales and job costs (step 4).

Each report also gets one owner coverage answer (gen.COVERAGE_CASES); only a "yes" for this exact file and
wording lets any customer or company figure be Complete, and the hold reaches every profit.

What this proves, and what it doesn't (the PR #136 review): section and customer/job sums, section and
customer statuses (the PR #138 automated review), and row presence, for the layouts and transaction types the generator makes. It doesn't prove each row's own
outcome, or layouts outside that family: tests/test_quickbooks_pnl.py and test_quickbooks_figures.py
hold those targeted cases. One report in four has a total
that is a cent off, or a fraction of a cent off, which must hold that section and nothing else.

Set QBO_PNL_REPORTS to run more (for example 5000) locally.
"""
from decimal import Decimal
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qbo_pnl_reports as gen  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_rules as qr  # noqa: E402

# A local run may check more, never fewer (the automated review of d05510c: a negative value skipped them all).
REPORTS = max(300, int(os.environ.get("QBO_PNL_REPORTS", "300")))
SECTION_KEYS = {"Income": "Income", "Cost of Goods Sold": "Cost of Goods Sold", "Expenses": "Expenses",
                "Other Income": "Other Income", "Other Expense": "Other Expenses"}


def cents(amount: Decimal) -> int:
    value = amount * 100
    assert value == value.to_integral_value(), amount
    return int(value)


def coverage_answer(case: str, report: qp.ProfitAndLossDetail) -> qf.CoverageAnswer | None:
    """The owner's coverage answer the generator chose (gen.COVERAGE_CASES), for this report."""
    statement, fingerprint = qf.coverage_statement(report), qf.report_fingerprint(report)
    return {"yes": qf.CoverageAnswer(qf.COVERAGE_YES, statement, fingerprint),
            "no": qf.CoverageAnswer(qf.COVERAGE_NO, statement, fingerprint),
            "none": None,
            "another file": qf.CoverageAnswer(qf.COVERAGE_YES, statement, "0" * 64),
            "other words": qf.CoverageAnswer(qf.COVERAGE_YES, "All my cost accounts are on the list.", fingerprint),
            }[case]


class KnownAnswerTests(unittest.TestCase):
    coverage_seen: dict = {}
    jobs_seen = 0
    statuses_seen = {(True, True): 0, (True, False): 0, (False, True): 0, (False, False): 0}

    def assert_figures(self, report, result):
        """Step 4: with sub-customers as jobs and every cost account answered "job costs"."""
        accounts = {line.account_path: qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT) for line in result.lines
                    if line.section in ("Cost of Goods Sold", "Expenses")}
        got = qf.figures(result, qf.OwnerAnswers(report=qf.report_fingerprint(result), sub_customers_are_jobs=True,
                                                 accounts=accounts, coverage=coverage_answer(report.coverage, result)))
        customers, jobs = gen.expected_figures(report)
        self.assertEqual(set(customers), set(got.customers))
        self.assertEqual(set(jobs), set(got.jobs))
        for name, (sales, costs) in customers.items():
            figures = got.customers[name]
            self.assertEqual((sales, costs), (cents(figures["sales"].amount), cents(figures["job_costs"].amount)), name)
        for job, (sales, costs) in jobs.items():
            figures = got.jobs[job]
            self.assertEqual((sales, costs), (cents(figures["sales"].amount), cents(figures["job_costs"].amount)), job)
            self.assertEqual(qp.NEEDS_A_CHECK, figures["profit_after_job_costs"].status)  # one report never suffices
        for name, (sales_complete, costs_complete) in gen.expected_customer_status(report).items():
            figures = got.customers[name]
            self.assertEqual((sales_complete, costs_complete),
                             (figures["sales"].status == qp.COMPLETE, figures["job_costs"].status == qp.COMPLETE), name)
            self.__class__.statuses_seen[(sales_complete, costs_complete)] += 1
        self.__class__.jobs_seen += len(jobs)
        income = report.expected["Income"]
        cost_sections = [report.expected[s] for s in ("Cost of Goods Sold", "Expenses") if s in report.expected]
        self.assertEqual(income.complete and report.covered, got.company["sales"].status == qp.COMPLETE)
        self.assertEqual(all(e.complete for e in cost_sections) and report.covered,
                         got.company["job_costs"].status == qp.COMPLETE)
        # The coverage hold never changes an amount and never disappears on the way to a profit (derived figures).
        for figure in (got.company["profit_after_job_costs"], got.company["after_overhead"],
                       *(f["profit_after_job_costs"] for f in (*got.customers.values(), *got.jobs.values()))):
            self.assertEqual(not report.covered, figure.coverage_open)
        self.__class__.coverage_seen[report.coverage] = self.__class__.coverage_seen.get(report.coverage, 0) + 1
        self.assertEqual(cents(got.company["sales"].amount), income.sales)
        self.assertEqual(cents(got.company["job_costs"].amount), sum(e.costs for e in cost_sections))

    def test_random_reports_match_their_known_answers(self):
        broken = noisy = 0
        for seed in range(REPORTS):
            report = gen.make_report(seed)
            noisy += any("E" in text or len(text.split(".")[-1]) > 2 for text in report.stored.values())
            data = fx.xlsx(report.rows, stored=report.stored)
            with self.subTest(seed=seed):
                result = qp.read_profit_and_loss_detail(f"seed-{seed}.xlsx", data)
                self.assertEqual(sorted(report.line_rows), sorted(line.row for line in result.lines))
                self.assertEqual(report.total_rows, len(result.checks))
                for name, want in report.expected.items():
                    got = result.sections[SECTION_KEYS[name]]
                    broken += want.broken
                    self.assertEqual(
                        (want.lines, want.line_sum, want.included, want.included_lines, want.not_resolved,
                         want.not_resolved_lines, want.complete, not want.broken),
                        (got.lines, cents(got.line_sum), cents(got.included), got.included_lines,
                         cents(got.not_resolved), got.not_resolved_lines, got.status == qp.COMPLETE, got.verified),
                        name)
                    if not want.broken:
                        self.assertTrue(got.adds_up, name)
                    mine = [line for line in result.lines if line.section == SECTION_KEYS[name]]
                    self.assertEqual(want.sales, sum(cents(l.amount) for l in mine if l.counts_as == qr.SALE))
                    self.assertEqual(want.costs, sum(cents(l.amount) for l in mine if l.counts_as == qr.COST))
                if not any(want.broken for want in report.expected.values()):
                    self.assertEqual((), result.problems)
                self.assert_figures(report, result)
        # The generator really exercised what it should.
        self.assertGreater(self.jobs_seen, REPORTS)
        self.assertTrue(all(self.statuses_seen.values()), self.statuses_seen)  # every status mix came up
        self.assertEqual(set(gen.COVERAGE_CASES), set(self.coverage_seen), self.coverage_seen)  # every coverage case
        self.assertGreater(broken, REPORTS // 8)
        self.assertGreater(noisy, REPORTS // 4)


if __name__ == "__main__":
    unittest.main()
