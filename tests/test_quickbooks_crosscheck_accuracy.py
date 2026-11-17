"""Issue #128, step 5b: the cross-check against known answers (tests/qbo_crosscheck_reports.py).

Each made-up pair of reports is read end to end. The number of unmatched lines in each report, every job's
sales and whether each job's sales and profit can be Complete must match the answers worked out without any
MargenX code, including the owner's coverage answer (matching sales never stand in for it). It proves those counts and statuses for the pairs the generator makes; the targeted cases are in
tests/test_quickbooks_crosscheck.py. Set QBO_CROSSCHECK_PAIRS to run more locally.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qbo_crosscheck_reports as gen  # noqa: E402
from test_quickbooks_pnl_accuracy import coverage_answer  # noqa: E402
import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

# A local run may check more, never fewer (the automated review of d05510c: a negative value skipped them all).
PAIRS = max(300, int(os.environ.get("QBO_CROSSCHECK_PAIRS", "300")))


class KnownAnswerTests(unittest.TestCase):
    def test_random_pairs_match_their_known_answers(self):
        complete = held = matched_but_uncovered = 0
        for seed in range(PAIRS):
            pair = gen.make_pair(seed)
            if pair.pnl_rows is None:
                continue
            with self.subTest(seed=seed):
                pnl = qp.read_profit_and_loss_detail("pnl.xlsx", fx.xlsx(pair.pnl_rows))
                sbcd = qs.read_sales_by_customer_detail("sales.xlsx", fx.xlsx(pair.sbcd_rows))
                check = qc.cross_check(pnl, sbcd)
                self.assertTrue(check.usable, check.reasons)
                self.assertEqual((pair.unmatched_pnl, pair.unmatched_sbcd),
                                 (len(check.pnl_unmatched), len(check.sbcd_unmatched)))
                result = qf.figures(pnl, qf.OwnerAnswers(report=qf.report_fingerprint(pnl), sub_customers_are_jobs=True,
                                                         unfiltered_pair=check.pair,
                                                         coverage=coverage_answer(pair.coverage, pnl)), cross_check=check)
                self.assertEqual(set(pair.jobs), set(result.jobs))
                for job, (cents, ok) in pair.jobs.items():
                    figures = result.jobs[job]
                    self.assertEqual(cents, int(figures["sales"].amount * 100), job)
                    self.assertEqual(ok, figures["sales"].status == qp.COMPLETE, (job, figures["sales"].holds))
                    self.assertEqual(ok, figures["profit_after_job_costs"].status == qp.COMPLETE, job)
                    self.assertEqual(pair.coverage != "yes", figures["profit_after_job_costs"].coverage_open, job)
                    complete += ok
                    held += not ok
                    matched_but_uncovered += pair.coverage != "yes" and figures["sales"].holds and all(
                        h.kind == qf.COVERAGE_HOLD for h in figures["sales"].holds)
        self.assertGreater(complete, PAIRS // 2)
        self.assertGreater(held, PAIRS // 2)
        # Pairs whose sales agree line by line, held only because the owner hasn't confirmed coverage, came up.
        self.assertGreater(matched_but_uncovered, PAIRS // 10)


if __name__ == "__main__":
    unittest.main()
