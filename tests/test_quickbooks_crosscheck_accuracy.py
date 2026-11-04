"""Issue #128, step 5b: the cross-check against known answers (tests/qbo_crosscheck_reports.py).

Each made-up pair of reports is read end to end. The number of unmatched lines in each report, every job's
sales and whether each job's sales and profit can be Complete must match the answers worked out without any
MargenX code. It proves those counts and statuses for the pairs the generator makes; the targeted cases are in
tests/test_quickbooks_crosscheck.py. Set QBO_CROSSCHECK_PAIRS to run more locally.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qbo_crosscheck_reports as gen  # noqa: E402
import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

PAIRS = int(os.environ.get("QBO_CROSSCHECK_PAIRS", "300"))


class KnownAnswerTests(unittest.TestCase):
    def test_random_pairs_match_their_known_answers(self):
        complete = held = 0
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
                result = qf.figures(pnl, qf.OwnerAnswers(report=qf.report_fingerprint(pnl), sub_customers_are_jobs=True),
                                    cross_check=check)
                self.assertEqual(set(pair.jobs), set(result.jobs))
                for job, (cents, ok) in pair.jobs.items():
                    figures = result.jobs[job]
                    self.assertEqual(cents, int(figures["sales"].amount * 100), job)
                    self.assertEqual(ok, figures["sales"].status == qp.COMPLETE, (job, figures["sales"].holds))
                    self.assertEqual(ok, figures["profit_after_job_costs"].status == qp.COMPLETE, job)
                    complete += ok
                    held += not ok
        self.assertGreater(complete, PAIRS // 2)
        self.assertGreater(held, PAIRS // 2)


if __name__ == "__main__":
    unittest.main()
