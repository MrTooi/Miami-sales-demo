"""What the MarginX results screen says: headline coverage, the after-costs line, escaping, no outside requests."""
from pathlib import Path
import unittest
from unittest import mock

import job_intake as ji
import job_profit as jp
import marginx_insights as mi
import marginx_ui as ui

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"


def report_from(invoices: bytes, costs: bytes):
    results = {}
    for data, kind in ((invoices, "invoices"), (costs, "costs")):
        headers, rows = ji.read_csv(data)
        results[kind] = ji.intake(headers, rows, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY")
    return jp.job_profit(results["invoices"], results["costs"])


def render(report) -> str:
    """The results screen's HTML, as one string."""
    out = []
    with mock.patch.object(ui, "_html", out.append):
        ui.results(report, mi.summarize(report), mi.attention(report), "Sales dated Oct 1, 2026")
    return "\n".join(out)


COMPLETE_J1 = (b"B-1,10/01/2026,Crew,J-1,Labor,20.00\n"
               b"B-2,10/01/2026,Paper,J-1,Materials,30.00\n")


class HeadlineTests(unittest.TestCase):
    def test_partial_total_says_which_jobs_it_covers_and_withholds_the_after_costs_total(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,B,J-2,60.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1 + b"B-3,10/01/2026,Landlord,,Rent,10.00\n"))
        self.assertIn("From 1 of 2 jobs · 50% of their sales", html)
        self.assertIn('0 of 1</div><div class="s">jobs with a figure', html)  # jobs losing money
        self.assertIn("A total after them isn't shown yet", html)
        self.assertIn("The job total leaves out 1 job without a figure", html)
        self.assertNotIn("these files leave", html)
        self.assertNotIn("real profit only if", html)

    def test_no_job_with_a_figure_shows_a_dash_not_zero(self):
        html = render(report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
                                  b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Landlord,,Rent,10.00\n"))
        self.assertIn('<div class="v ">—</div><div class="s">No job has a figure yet', html)

    def test_full_total_keeps_overhead_apart_from_costs_with_no_job_number(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1 + b"B-3,10/01/2026,Landlord,,Rent,10.00\n"
            b"B-4,10/01/2026,Paper,,Materials,15.00\n"))
        self.assertIn("From all 1 job", html)
        self.assertIn("After the $25 of costs not tied to any job ($10 of overhead such as rent, and $15 with no "
                      "job number that may belong to jobs), these files leave <b>$25</b>", html)
        self.assertIn("Sales minus every cost in these files, before tax.", html)
        self.assertNotIn("rent and other overhead", html)

    def test_sales_with_no_job_number_are_never_hidden_behind_nothing_stands_out(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,,40.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1))
        self.assertIn("$40 of sales have no job number", html)
        self.assertNotIn("Nothing stands out", html)

    def test_customer_list_shows_losses_and_names_customers_left_out(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,B,J-2,60.00\n"
            b"I-3,10/01/2026,C,J-3,40.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1
            + b"B-3,10/01/2026,Crew,J-3,Labor,50.00\nB-4,10/01/2026,Paper,J-3,Materials,10.00\n"))
        self.assertIn('<i class="neg" style="width:20%">', html)  # C lost $20: a visible red bar
        self.assertIn("Not listed, no figure yet: B.", html)  # B has sales but no costs

    def test_demo_shop(self):
        html = render(report_from((SAMPLES / "demo_sign_shop_invoices.csv").read_bytes(),
                                  (SAMPLES / "demo_sign_shop_costs.csv").read_bytes()))
        self.assertIn("From all 8 jobs · 33% of their sales · some still need a check", html)
        self.assertIn("After the $2,000 of costs not tied to any job (overhead such as rent), these files leave "
                      "<b>$1,640</b>", html)
        self.assertIn("Some jobs still need a check, so this may be too high.", html)


class SafetyTests(unittest.TestCase):
    def test_values_from_a_file_are_escaped(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Description,Amount\n"
            b"I-1,10/01/2026,<script>alert(1)</script>,J-1,<b>Banner</b>,100.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1))
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>Banner</b>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;Banner&lt;/b&gt;", html)

    def test_a_net_credit_is_added_back_not_shown_as_a_double_negative(self):
        # Intake rejects negative cost lines today, so this is built by hand: the display must still
        # never show "−-$10" if a category ever nets to a credit.
        from decimal import Decimal
        report = report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
                             b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1)
        report.jobs[0].costs["materials"] = Decimal("-10.00")
        html = render(report)
        self.assertNotIn("−-", html)
        # $100 sold − $20 labor + $10 materials credit = $90 left: the breakdown adds up.
        self.assertIn('<td>Sold for</td><td class="r">$100</td>', html)
        self.assertIn('<td>Labor</td><td class="r">−$20</td>', html)
        self.assertIn('<td>Materials (credit)</td><td class="r">+$10</td>', html)
        self.assertIn('<td>Left after job costs</td><td class="r">$90</td>', html)

    def test_job_ids_and_reasons_from_a_file_are_escaped(self):
        # Labor only, so the job needs a check: its ID appears in the attention list and the breakdown.
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,<i>J-1</i>,100.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,<i>J-1</i>,Labor,20.00\n"))
        self.assertNotIn("<i>J-1</i>", html)
        self.assertIn("Job &lt;i&gt;J-1&lt;/i&gt; needs a check", html)  # attention list
        self.assertIn("· &lt;i&gt;J-1&lt;/i&gt;</small>", html)  # job list
        self.assertIn('<div class="why">No materials or outsourced work recorded.', html)  # reasons, escaped text

    def test_usual_margin_is_described_as_a_share_of_sales_not_an_average(self):
        html = render(report_from((SAMPLES / "demo_sign_shop_invoices.csv").read_bytes(),
                                  (SAMPLES / "demo_sign_shop_costs.csv").read_bytes()))
        self.assertIn("Your usual margin (30%) is the share of sales you kept across all your jobs with "
                      "complete costs, added together.", html)
        self.assertNotIn("average", html)

    def test_styles_make_no_outside_requests(self):
        self.assertNotIn("http", ui._CSS)
        self.assertNotIn("@import", ui._CSS)


if __name__ == "__main__":
    unittest.main()
