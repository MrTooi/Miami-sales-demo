"""Issue #128, step 5a: MargenX's reading of Sales by Customer Detail against known answers.

tests/qbo_sbcd_reports.py generates made-up reports and works out their right answers in whole cents
without any MargenX code. Each is written as an Excel file and read by MargenX end to end: every line
must be there, and each customer's sum, what is counted, what is held and its status must match. One
report in four has a total a cent (or a fraction of a cent) off: that customer, or for the grand TOTAL
every customer, must be held. It proves sums, statuses and row presence for the layouts and types the
generator makes; tests/test_quickbooks_sbcd.py holds the targeted cases.

Set QBO_SBCD_REPORTS to run more locally.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qbo_sbcd_reports as gen  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

REPORTS = int(os.environ.get("QBO_SBCD_REPORTS", "300"))


def cents(amount) -> int:
    value = amount * 100
    assert value == value.to_integral_value(), amount
    return int(value)


class KnownAnswerTests(unittest.TestCase):
    def test_random_reports_match_their_known_answers(self):
        broken = complete = held = 0
        for seed in range(REPORTS):
            report = gen.make_report(seed)
            with self.subTest(seed=seed):
                result = qs.read_sales_by_customer_detail(f"seed-{seed}.xlsx", fx.xlsx(report.rows, stored=report.stored))
                self.assertEqual(sorted(report.line_rows), sorted(line.row for line in result.lines))
                self.assertEqual(report.totals, len(result.checks))
                self.assertEqual(set(report.expected), set(result.customers))
                for name, want in report.expected.items():
                    got = result.customers[name]
                    self.assertEqual(
                        (want.lines, want.line_sum, want.included, want.included_lines, want.not_resolved,
                         want.not_resolved_lines, want.complete, not want.broken),
                        (got.lines, cents(got.line_sum), cents(got.included), got.included_lines,
                         cents(got.not_resolved), got.not_resolved_lines, got.all_counted, got.totals_match),
                        name)
                    broken += want.broken
                    complete += want.complete
                    held += not want.complete
                if not any(e.broken for e in report.expected.values()):
                    self.assertEqual((), result.problems)
        self.assertGreater(broken, REPORTS // 8)
        self.assertGreater(complete, REPORTS // 4)
        self.assertGreater(held, REPORTS // 4)


if __name__ == "__main__":
    unittest.main()
