from decimal import Decimal
from pathlib import Path
import unittest

import job_intake as ji
import job_profit as jp
import marginx_insights as mi
from job_profit import ZERO

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

    def test_total_says_which_jobs_it_covers_when_some_have_no_figure(self):
        # J-1 complete, J-2 has sales but no costs (no figure): the total covers 1 of 2 jobs.
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,B,J-2,60.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,30.00\nB-3,10/01/2026,Landlord,,Rent,10.00\n")
        summary = mi.summarize(report)
        self.assertEqual((1, 2, 1, Decimal("100.00")), (summary.jobs_with_figure, summary.jobs,
                                                         summary.jobs_without_figure, summary.sales_with_figure))
        self.assertTrue(summary.figure_is_partial)
        self.assertFalse(summary.figure_is_provisional)  # J-1 itself is complete
        self.assertIsNone(summary.after_unlinked_costs)  # withheld: J-2's sales aren't in the job total

    def test_no_job_with_a_figure_gives_no_share_and_no_total(self):
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Landlord,,Rent,10.00\n")
        summary = mi.summarize(report)
        self.assertEqual((0, ZERO, None, None), (summary.jobs_with_figure, summary.left_after_job_costs,
                                                summary.share_percent, summary.after_unlinked_costs))
        self.assertTrue(summary.figure_is_partial)

    def test_sales_without_a_job_number_withhold_the_total(self):
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,,40.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,30.00\nB-3,10/01/2026,Landlord,,Rent,10.00\n")
        summary = mi.summarize(report)
        self.assertEqual((0, 1, Decimal("40.00")), (summary.jobs_without_figure, summary.unlinked_sales_lines,
                                                    summary.unlinked_sales))
        self.assertTrue(summary.figure_is_partial)
        self.assertIsNone(summary.after_unlinked_costs)

    def test_overhead_is_kept_apart_from_costs_with_no_job_number(self):
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,30.00\nB-3,10/01/2026,Landlord,,Rent,10.00\n"
                             b"B-4,10/01/2026,Paper,,Materials,15.00\n")
        summary = mi.summarize(report)
        self.assertEqual((Decimal("25.00"), Decimal("10.00"), Decimal("15.00")),
                         (summary.unlinked_costs, summary.overhead_costs, summary.unassigned_job_costs))
        # Every sale is in the job total, so sales minus every cost in the files is exact: 50 - 25.
        self.assertFalse(summary.figure_is_partial)
        self.assertEqual(Decimal("25.00"), summary.after_unlinked_costs)

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
        self.assertEqual((Decimal("2000.00"), ZERO), (summary.overhead_costs, summary.unassigned_job_costs))
        self.assertFalse(summary.figure_is_partial)  # all 8 demo jobs have a figure


class AttentionTests(unittest.TestCase):
    def test_demo_shop_findings_in_order(self):
        items = mi.attention(demo_report())
        self.assertEqual([
            ("loss", "Rush banner (next-day) · J-105 lost $140"),
            ("warn", "Vehicle wrap · J-107 kept only 4%"),
            # Palm Gym needs a check (J-108 has no labor), so the claim is limited to complete customers.
            ("warn", "Of customers with complete figures, Bayside Realty (fictional) is the biggest, but keeps only 13%"),
            ("warn", "Class schedule banners · J-108 needs a check"),
        ], [(i.level, i.title) for i in items])
        self.assertEqual("Sold for $600, cost $740. To cover its job costs it needed $740; at your usual 30% margin, "
                         "about $1,062.", items[0].detail)
        # A profitable but thin job gets the usual-margin price, not a pointless break-even.
        self.assertEqual("Sold for $3,200, cost $3,070. At your usual 30% margin, about $4,404.", items[1].detail)
        # Compared with a customer whose figures are complete (not Palm Gym, whose J-108 lacks labor).
        self.assertIn("Little Havana Cafe (fictional) keeps 55%", items[2].detail)  # $600 of $1,100
        self.assertIn("No labor recorded.", items[3].detail)

    def test_biggest_customer_is_qualified_when_a_bigger_one_may_be_hidden(self):
        # C has the most sales ($1,000) but no costs, so no figure. A ($300, 10%) and B ($100, 90%) have figures.
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,300.00\n"
                             b"I-2,10/01/2026,B,J-2,100.00\nI-3,10/01/2026,C,J-3,1000.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,150.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,120.00\nB-3,10/01/2026,Crew,J-2,Labor,5.00\n"
                             b"B-4,10/01/2026,Paper,J-2,Materials,5.00\n")
        titles = [i.title for i in mi.attention(report)]
        self.assertIn("Of customers with complete figures, A is the biggest, but keeps only 10%", titles)
        self.assertFalse(any("your biggest customer" in t for t in titles))

    def test_thin_customer_gap_is_measured_before_rounding(self):
        def titles(a_materials: str, b_materials: str):
            # A: $1,000 sales, $300 labor. B: $500 sales, $50 labor. A is the biggest customer.
            return [i.title for i in mi.attention(report_from(
                b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,1000.00\nI-2,10/01/2026,B,J-2,500.00\n",
                b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,300.00\n"
                b"B-2,10/01/2026,Paper,J-1,Materials," + a_materials.encode() + b"\n"
                b"B-3,10/01/2026,Crew,J-2,Labor,50.00\nB-4,10/01/2026,Paper,J-2,Materials," + b_materials.encode()
                + b"\n"))]
        # 35.4% vs 49.6% overall: shown as 35% and 50%, but the real gap is 14.2 points, under 15.
        self.assertFalse(any("biggest" in t for t in titles("346.00", "60.00")))
        # 35% vs 50% overall: exactly 15 points, flagged.
        self.assertIn("A is your biggest customer, but keeps only 35%", titles("350.00", "50.00"))

    def test_a_loss_on_a_job_that_needs_a_check_is_possible_not_confirmed(self):
        # $100 sale read, a $50 sale that couldn't be read, $120 of costs: shows -$20, but the missing
        # sale would make it +$30.
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,J-1,50.0x\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,60.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,60.00\n")
        summary = mi.summarize(report)
        self.assertEqual((0, 1, 1), (summary.losing_jobs, summary.possible_losses, summary.rejected_sales_lines))
        items = mi.attention(report)
        self.assertEqual([("warn", "Job J-1 may have lost $20")], [(i.level, i.title) for i in items])
        self.assertEqual("The rows MargenX could read show sold for $100, cost $120. Not confirmed: 1 of its sales "
                         "lines couldn't be imported (see 'Rows that couldn't be used' under Your files).", items[0].detail)
        self.assertIsNone(summary.after_unlinked_costs)

    def test_missing_costs_elsewhere_never_inflate_the_customer_benchmark(self):
        # A ($1,000, 30%) and C ($500, 60%) are complete; B ($500, 98%) has no labor recorded.
        # Complete customers only: 40% overall, A is 10 points below, so nothing is flagged.
        # With B's understated costs counted, the benchmark would be 54.5% and A would be flagged.
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,1000.00\n"
                             b"I-2,10/01/2026,B,J-2,500.00\nI-3,10/01/2026,C,J-3,500.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,400.00\n"
                             b"B-2,10/01/2026,Paper,J-1,Materials,300.00\nB-3,10/01/2026,Paper,J-2,Materials,10.00\n"
                             b"B-4,10/01/2026,Crew,J-3,Labor,100.00\nB-5,10/01/2026,Paper,J-3,Materials,100.00\n")
        self.assertEqual("provisional", next(c for c in report.customers if c.customer == "B").status)
        self.assertFalse(any("biggest" in i.title for i in mi.attention(report)))

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
