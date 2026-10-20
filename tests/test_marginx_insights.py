from decimal import Decimal
from pathlib import Path
import unittest

import job_intake as ji
import job_profit as jp
import marginx_insights as mi

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"


def report_from(invoices: bytes, costs: bytes):
    results = {}
    for data, kind in ((invoices, "invoices"), (costs, "costs")):
        headers, rows = ji.read_csv(data)
        results[kind] = ji.intake(headers, rows, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY")
    return jp.job_profit(results["invoices"], results["costs"])


def demo_report():
    return report_from((SAMPLES / "demo_sign_shop_invoices.csv").read_bytes(),
                       (SAMPLES / "demo_sign_shop_costs.csv").read_bytes())


class SummaryTests(unittest.TestCase):
    def test_demo_shop_headline_numbers(self):
        summary = mi.summarize(demo_report())
        self.assertEqual((Decimal("11000.00"), Decimal("3640.00"), 33), (summary.sales, summary.left_after_job_costs,
                                                                         summary.share_percent))
        self.assertEqual((8, 1, 1, True), (summary.jobs, summary.losing_jobs, summary.jobs_to_check,
                                          summary.figure_is_provisional))
        self.assertIsInstance(summary.left_after_job_costs, Decimal)

    def test_sales_include_lines_without_a_job_and_unavailable_jobs_add_no_figure(self):
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,,40.00\n"
                             b"I-3,10/01/2026,B,J-2,60.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,30.00\n")
        summary = mi.summarize(report)
        self.assertEqual(Decimal("200.00"), summary.sales)  # 100 + 60 (J-2, no costs) + 40 (no job)
        self.assertEqual(Decimal("50.00"), summary.left_after_job_costs)  # only J-1 has a figure
        self.assertEqual(50, summary.share_percent)

    def test_money_is_exact_and_drops_only_zero_cents(self):
        self.assertEqual(["$1,300", "$12.50", "-$140", "$0.05"],
                         [mi.money(Decimal(v)) for v in ("1300.00", "12.50", "-140.00", "0.05")])

    def test_percent_rounds_half_up_for_display_only(self):
        self.assertEqual(13, mi.percent(Decimal("750"), Decimal("5850")))
        self.assertEqual(1, mi.percent(Decimal("1"), Decimal("200")))
        self.assertIsNone(mi.percent(Decimal("5"), Decimal("0")))


class PricingTests(unittest.TestCase):
    def test_usual_margin_uses_complete_jobs_only_and_needs_enough_of_them(self):
        report = demo_report()
        # J-101..J-107 are complete: $3,120 left of $10,300 sales. J-108 (no labor) is left out.
        self.assertEqual(Decimal("3120.00") / Decimal("10300.00"), mi.usual_margin(report))
        two_jobs = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,J-2,100.00\n",
                               b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                               b"B-2,10/01/2026,Paper,J-1,Materials,30.00\nB-3,10/01/2026,Crew,J-2,Labor,20.00\n"
                               b"B-4,10/01/2026,Paper,J-2,Materials,30.00\n")
        self.assertIsNone(mi.usual_margin(two_jobs))
        self.assertIsNone(mi.pricing(two_jobs.jobs[0], mi.usual_margin(two_jobs))["at_usual"])

    def test_prices_come_from_the_jobs_own_costs_and_never_from_incomplete_ones(self):
        report = demo_report()
        jobs = {j.job_id: j for j in report.jobs}
        usual = mi.usual_margin(report)
        price = mi.pricing(jobs["J-105"], usual)
        self.assertEqual((Decimal("740.00"), 30, Decimal("1062")), (price["break_even"], price["usual"], price["at_usual"]))
        self.assertIsNone(mi.pricing(jobs["J-108"], usual))  # missing labor: any price would be too low

    def test_after_unlinked_costs_is_exact(self):
        summary = mi.summarize(demo_report())
        self.assertEqual((Decimal("2000.00"), Decimal("1640.00")), (summary.unlinked_costs, summary.after_unlinked_costs))


class AttentionTests(unittest.TestCase):
    def test_demo_shop_findings_in_order(self):
        items = mi.attention(demo_report())
        self.assertEqual([
            ("loss", "Rush banner (next-day) · J-105 lost $140"),
            ("warn", "Vehicle wrap · J-107 kept only 4%"),
            ("warn", "Bayside Realty (fictional) is your biggest customer, but keeps only 13%"),
            ("warn", "Class schedule banners · J-108 needs a check"),
        ], [(i.level, i.title) for i in items])
        self.assertEqual("Sold for $600, cost $740. To break even it needed $740; at your usual 30% margin, "
                         "about $1,062.", items[0].detail)
        # A profitable but thin job gets the usual-margin price, not a pointless break-even.
        self.assertEqual("Sold for $3,200, cost $3,070. At your usual 30% margin, about $4,404.", items[1].detail)
        # Compared with a customer whose figures are complete (not Palm Gym, whose J-108 lacks labor).
        self.assertIn("Little Havana Cafe (fictional) keeps 55%", items[2].detail)  # $600 of $1,100
        self.assertIn("No labor recorded.", items[3].detail)

    def test_no_thin_customer_finding_when_margins_are_close(self):
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,1000.00\nI-2,10/01/2026,B,J-2,500.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,300.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,300.00\nB-3,10/01/2026,Crew,J-2,Labor,150.00\n"
                             b"B-4,10/01/2026,Paper,J-2,Materials,100.00\n")
        self.assertEqual([], mi.attention(report))  # 40% vs 50%: within 15 points, nothing to flag

    def test_unavailable_jobs_and_unlinked_job_costs_are_listed(self):
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,J-2,50.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,30.00\nB-3,10/02/2026,Paper,,Materials,15.00\n")
        titles = [i.title for i in mi.attention(report)]
        self.assertIn("1 job without a figure yet", titles)
        self.assertIn("$15 of costs aren't linked to a job", titles)

    def test_many_jobs_to_check_are_summarized(self):
        invoices = b"Invoice,Date,Customer,Job,Amount\n" + b"".join(
            f"I-{n},10/01/2026,A,J-{n},100.00\n".encode() for n in range(1, 6))
        costs = b"Bill,Date,Vendor,Job,Type,Amount\n" + b"".join(
            f"B-{n},10/01/2026,Paper,J-{n},Materials,10.00\n".encode() for n in range(1, 6))
        titles = [i.title for i in mi.attention(report_from(invoices, costs))]
        self.assertEqual(4, sum(1 for t in titles if "need" in t))
        self.assertIn("2 more jobs need a check", titles)


if __name__ == "__main__":
    unittest.main()
