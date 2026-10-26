"""What the MargenX results screen says: headline coverage, the after-costs line, escaping, no outside requests."""
from pathlib import Path
import re
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
        self.assertIn('<div class="s">From 1 of 2 jobs</div>', html)
        # The margin is of the same jobs, and says so.
        self.assertIn('<div class="l">Profit margin</div><div class="v ">50%</div>'
                      '<div class="s">After job costs, before rent and overhead · from 1 of 2 jobs</div>', html)
        self.assertIn('0 of 1</div><div class="s">jobs with complete costs', html)  # jobs losing money
        self.assertIn("A total after them isn't shown yet", html)
        self.assertIn("The totals leave out 1 job without a figure", html)
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
        self.assertIn('<div class="mx-row loss">', html)  # C lost $20: its row is red
        self.assertIn('<div>$40</div><div class="lft">-$20</div><div class="mg">-50%</div>', html)
        self.assertIn("Not listed, no figure yet: B.", html)  # B has sales but no costs

    def test_rows_that_could_not_be_read_are_disclosed_and_withhold_the_after_costs_total(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,J-2,50.0x\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1 + b"B-3,10/01/2026,Landlord,,Rent,10.00\n"
            b"B-4,10/01/2026,Paper,J-1,Materials,abc\n"))
        self.assertIn("2 jobs · 1 row couldn&#x27;t be read and isn&#x27;t included", html)  # Sales card
        self.assertIn("1 sales row and 1 cost row couldn&#x27;t be read and aren&#x27;t included", html)
        self.assertIn("A total after them isn't shown yet", html)
        self.assertIn("The totals leave out 1 job without a figure and 2 rows that couldn&#x27;t be read", html)
        self.assertNotIn("these files leave", html)
        self.assertNotIn("Sales minus every cost", html)

    def test_a_possible_loss_is_not_counted_as_a_confirmed_one(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,A,J-1,50.0x\n",
            b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,60.00\n"
            b"B-2,10/01/2026,Paper,J-1,Materials,60.00\n"))
        self.assertIn('<div class="l">Jobs losing money</div><div class="v amber">—</div>'
                      '<div class="s">No job has complete costs yet · 1 may have lost money, still needs a check</div>', html)
        self.assertIn("Job J-1 may have lost $20", html)
        self.assertNotIn("J-1 lost", html)

    def test_margin_card_tells_zero_sales_apart_from_no_figures(self):
        # A job sold and fully refunded has a figure (it lost its costs) but $0 of sales: there's no
        # margin, and the card says why instead of claiming no job has a figure.
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/02/2026,A,J-1,-100.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1))
        self.assertIn('<div class="l">Left after job costs</div><div class="v ">-$50</div>', html)
        self.assertIn('<div class="l">Profit margin</div><div class="v ">—</div><div class="s">Sales on these jobs '
                      "add up to $0, so there&#x27;s no margin to show</div>", html)
        self.assertNotIn("No job has a figure yet", html)
        # More refunded than sold: sales add up to less than $0. Still no percentage, and the card says why.
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/02/2026,A,J-1,-150.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1))
        self.assertIn('<div class="l">Left after job costs</div><div class="v ">-$100</div>', html)
        self.assertIn('<div class="l">Profit margin</div><div class="v ">—</div><div class="s">Sales on these jobs '
                      "add up to -$50, so there&#x27;s no margin to show</div>", html)
        self.assertNotRegex(html, r'Profit margin</div><div class="v [^"]*">-?\d+%')
        # With no figure at all, the card says that.
        html = render(report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
                                  b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-2,Labor,20.00\n"))
        self.assertIn('<div class="l">Profit margin</div><div class="v ">—</div><div class="s">No job has a figure '
                      "yet</div>", html)

    def test_demo_shop(self):
        html = render(report_from((SAMPLES / "demo_sign_shop_invoices.csv").read_bytes(),
                                  (SAMPLES / "demo_sign_shop_costs.csv").read_bytes()))
        self.assertIn("From all 8 jobs · some still need a check", html)
        # A margin that counts jobs still needing a check says it may change (a missing cost or sale could move it
        # either way), beside the complete jobs' margin.
        self.assertIn('<div class="l">Profit margin</div><div class="v ">33%</div><div class="s">After job costs, '
                      "before rent and overhead · may change, some jobs need a check · jobs with complete "
                      "costs: 30%</div>", html)
        self.assertIn("After the $2,000 of costs not tied to any job (overhead such as rent), these files leave "
                      "<b>$1,640</b>, a 15% margin on all sales", html)
        self.assertIn("Some jobs still need a check, so this may be too high.", html)


class AppFrameTests(unittest.TestCase):
    def frame(self, fn, *args):
        out = []
        with mock.patch.object(ui, "_html", out.append):
            fn(*args)
        return "\n".join(out)

    def test_steps_mark_the_current_step_and_check_off_earlier_ones(self):
        html = self.frame(ui.steps, 3)
        self.assertEqual(2, html.count('<div class="mx-nav done">'))
        self.assertIn('<div class="mx-nav on"><div class="n">3</div>', html)

    def test_file_status_follows_what_marginx_read(self):
        self.assertIn("<b>Sales report</b> · read", self.frame(ui.file_slots, {"invoices"}))
        self.assertIn("<b>Cost report</b> · waiting", self.frame(ui.file_slots, {"invoices"}))
        both = self.frame(ui.file_slots, {"invoices", "costs"})
        self.assertEqual(2, both.count('class="mx-slot ok"'))

    def test_the_top_bar_says_which_kind_of_session_it_is(self):
        self.assertIn("Pilot session · this laptop only", self.frame(ui.top_bar, True))
        self.assertIn("Example data only", self.frame(ui.top_bar, False))
        self.assertIn(ui.TAGLINE, self.frame(ui.top_bar, False))

    def test_the_app_frame_loads_nothing_from_outside(self):
        # Icons are drawn inline, the logo is embedded image data, and the frame's style sheet names no
        # font, image or outside address.
        bars = [self.frame(ui.top_bar, True), self.frame(ui.top_bar, False)]
        for markup in (ui._APP_CSS, self.frame(ui.privacy_points, True), self.frame(ui.privacy_points, False),
                       self.frame(ui.locked_drop),
                       self.frame(ui.steps, 2), self.frame(ui.what_you_get), self.frame(ui.file_slots, set()), *bars):
            outside = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "", markup)  # the embedded logo
            self.assertNotRegex(outside, r"https?://|@import|url\(|//[a-z]")
        for bar in bars:
            self.assertEqual(["data:image/png;base64,"], [m[:22] for m in re.findall(r'src="([^"]+)"', bar)])


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

    def test_job_breakdown_includes_fees_on_the_job_and_adds_up(self):
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1 + b"B-3,10/01/2026,Bank,J-1,Bank fees,5.00\n"))
        # $100 − $30 − $20 − $5 = $45: every line that's subtracted is shown.
        self.assertIn('<tr><td>Sold for</td><td class="r">$100</td></tr><tr><td>Materials</td><td class="r">−$30</td>'
                      '</tr><tr><td>Labor</td><td class="r">−$20</td></tr><tr><td>Fees &amp; overhead on this job</td>'
                      '<td class="r">−$5</td></tr><tr class="tot"><td>Left after job costs</td><td class="r">$45</td>',
                      html)

    def test_a_customer_losing_a_few_cents_is_still_shown_as_a_loss(self):
        # B lost $0.01 on $100: its margin rounds to 0%, but the row is a loss, its amount is negative,
        # and nothing on it reads as a profit.
        html = render(report_from(
            b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\nI-2,10/01/2026,B,J-2,100.00\n",
            b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1
            + b"B-3,10/01/2026,Crew,J-2,Labor,50.00\nB-4,10/01/2026,Paper,J-2,Materials,50.01\n"))
        self.assertIn('<div class="mx-row loss"><div class="n">B<', html)  # the row is styled as a loss
        self.assertIn('<div>$100</div><div class="lft">-$0.01</div><div class="mg">0%</div>', html)
        self.assertIn("Job J-2 lost $0.01", html)  # and the attention list names the loss

    def test_customer_table_shows_sales_what_is_left_and_margin(self):
        # One row per customer: what they paid, what's left after job costs and the margin, the same
        # rounded percent as the attention list. A customer whose jobs need a check shows "so far".
        html = render(report_from((SAMPLES / "demo_contractor_invoices.csv").read_bytes(),
                                  (SAMPLES / "demo_contractor_costs.csv").read_bytes()))
        self.assertIn('<div class="mx-row head"><div class="n">Customer</div><div>Sales</div>'
                      '<div>Left after job costs</div><div>Margin</div></div>', html)
        self.assertIn('<div>$33,600</div><div class="lft">$1,900</div><div class="mg">6%</div>', html)  # Ocean View
        self.assertIn('<div>$6,300</div><div class="lft">$3,200</div><div class="mg">51% so far</div>', html)
        self.assertIn('<small class="chk">Needs a check</small>', html)  # Kendall Pediatrics, no labor cost
        self.assertIn('<div class="mx-row loss">', html)  # Gomez Family lost $650
        self.assertNotIn("mx-bar", html)

    def test_every_result_ends_with_the_how_to_read_note(self):
        # Rounded percentages and estimated prices are never mistaken for exact facts, and the tool is
        # never mistaken for professional advice. Shown with or without findings.
        demo = report_from((SAMPLES / "demo_sign_shop_invoices.csv").read_bytes(),
                           (SAMPLES / "demo_sign_shop_costs.csv").read_bytes())
        for report in (demo, report_from(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,A,J-1,100.00\n",
                                                  b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                                                  b"B-2,10/01/2026,Paper,J-1,Materials,30.00\n")):
            html = render(report)
            self.assertTrue(html.rstrip().endswith(f'<div class="mx-legend mx-fine">{ui.READING_NOTE}</div>'))
        # The wording is spelled out here, not taken from the constant, so a change to what it promises is
        # a deliberate test change. Each claim holds on main: sums are exact Decimal (#118), "Needs a check"
        # marks Provisional figures, percentages are rounded only for display (#119), prices say "about".
        self.assertEqual("How to read these numbers: sales and costs are added up exactly, to the cent, from the "
                         "files you gave MargenX. Figures marked \"Needs a check\" may be missing costs. Percentages "
                         "are rounded to whole numbers, and suggested prices are estimates. MargenX is a tool to help "
                         "you look at your own numbers. It isn't accounting, tax or financial advice.", ui.READING_NOTE)

    def test_html_blocks_stay_on_one_line_so_markdown_never_runs(self):
        out = []
        report = report_from(b'Invoice,Date,Customer,Job,Description,Amount\n'
                             b'I-1,10/01/2026,A,J-1,"Banner\n\n![t](https://e.example/p.png)\n\nend",100.00\n',
                             b"Bill,Date,Vendor,Job,Type,Amount\n" + COMPLETE_J1)
        with mock.patch.object(ui.st, "markdown", lambda text, **kw: out.append(text)):
            ui.results(report, mi.summarize(report), mi.attention(report), "Sales dated Oct 1, 2026")
        self.assertTrue(any("e.example" in m for m in out))
        for markup in out:
            self.assertNotIn("\n", markup)

    def test_md_text_neutralises_images_links_and_html_but_keeps_ordinary_text(self):
        self.assertEqual("a \\!\\[t\\](https://e.example/p.png) b \\<img\\>",
                         ui.md_text("a\n\n![t](https://e.example/p.png)\n\nb <img>"))
        self.assertEqual("fictional_invoices.csv", ui.md_text("fictional_invoices.csv"))
        self.assertEqual("Bayside Realty (fictional) keeps 13%.", ui.md_text("Bayside Realty (fictional) keeps 13%."))

    def test_styles_make_no_outside_requests(self):
        self.assertNotIn("http", ui._CSS)
        self.assertNotIn("@import", ui._CSS)


if __name__ == "__main__":
    unittest.main()
