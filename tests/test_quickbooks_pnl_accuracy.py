"""Issue #128, step 3: MargenX's reading of Profit and Loss Detail against known answers.

Like docs/ACCURACY.md's random shops: tests/qbo_pnl_reports.py generates made-up reports and works
out their right answers in whole cents without any MargenX code. Each report is written as an Excel
file and read by MargenX end to end. Line counts, each section's sum, what is counted as sales and
costs, what is held and each section's status must all match exactly. One report in four has a total
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
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_rules as qr  # noqa: E402

REPORTS = int(os.environ.get("QBO_PNL_REPORTS", "300"))
SECTION_KEYS = {"Income": "Income", "Cost of Goods Sold": "Cost of Goods Sold", "Expenses": "Expenses",
                "Other Income": "Other Income", "Other Expense": "Other Expenses"}


def cents(amount: Decimal) -> int:
    value = amount * 100
    assert value == value.to_integral_value(), amount
    return int(value)


class KnownAnswerTests(unittest.TestCase):
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
        # The generator really exercised what it should.
        self.assertGreater(broken, REPORTS // 8)
        self.assertGreater(noisy, REPORTS // 4)


if __name__ == "__main__":
    unittest.main()
