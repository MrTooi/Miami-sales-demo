"""Issue #128, the switch-on: QuickBooks reports through the real upload page (pages/1_MargenX_Import.py).

Driven through Streamlit's AppTest on made-up files only. The page's sample files are pointed at a temporary
folder of made-up reports, so every file goes through the same path an upload does (the list of (name, bytes)).
Covers: a recognised Profit and Loss Detail goes to the questions and results; Sales by Customer Detail only
cross-checks it; a look-alike is still refused (S2); QuickBooks reports are never mixed with other files; plain
lists still go through the reader for plain lists, unchanged; the $405 of Cost of Goods Sold "Invoice" lines is
never a sale on the page.
"""
import re
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from streamlit.testing.v1 import AppTest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_upload as qflow  # noqa: E402
import test_quickbooks_rules as rules  # noqa: E402

PAGE = HERE.parent / "pages" / "1_MargenX_Import.py"
L, S = fx.line, fx.sale
X, Y = "Customer X (fictional)", "Customer Y (fictional)"
NO_FILTER = "Did you export both reports for the whole business, with no filter?"


def made_up_pnl(job_b_materials=D("2100")) -> bytes:
    """Job A for Customer X ($4,000 invoice, $1,000 of materials); Job B for Customer Y ($1,500 invoice, $2,100 of
    materials: a job losing money); a $500 office expense. All fictional."""
    return fx.xlsx(fx.report_rows({
        "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                      L(3, "Invoice", "1002", f"{Y}:Job B", D("1500"), None)])],
        "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", D("1000"), None),
                                        L(6, "Bill", "B-2", f"{Y}:Job B", job_b_materials, None)]),
                     ("Office Supplies", [L(7, "Expense", "", "Office Depot (fictional)", D("500"), None)])]}))


def made_up_sbcd() -> bytes:
    """The same two sales, as Sales by Customer Detail lists them."""
    return fx.xlsx(fx.sbcd_rows([(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)])]),
                                 (Y, [], [("Job B", [S(3, "Invoice", "1002", "Design", 1, 1500)])])]))


SAMPLES = HERE.parent / "sample_data" / "marginx"
PLAIN_SALES = (SAMPLES / "demo_sign_shop_invoices.csv").read_bytes()  # made-up
PLAIN_COSTS = (SAMPLES / "demo_sign_shop_costs.csv").read_bytes()  # made-up


_FOLDERS = tempfile.TemporaryDirectory()  # kept until the tests end: the page reads its files on every rerun


def tearDownModule():
    _FOLDERS.cleanup()


def page(files: dict[str, bytes]) -> AppTest:
    """The real upload page, with these made-up files in place of the sample files."""
    tmp = tempfile.mkdtemp(dir=_FOLDERS.name)
    for name, data in files.items():
        Path(tmp, name).write_bytes(data)
    source = PAGE.read_text(encoding="utf-8").replace(
        'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({tmp!r})").replace(
        'DEFAULT_SAMPLE_SET = "demo"', 'DEFAULT_SAMPLE_SET = "test"').replace(
        'SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")', f"SAMPLE_FILES = {tuple(files)!r}")
    at = AppTest.from_string(source, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def shown(value: str) -> str:
    return value.replace("\\$", "$")


def everything(at) -> str:
    elements = [*at.markdown, *at.subheader, *at.caption, *at.info, *at.warning, *at.error, *at.success, *at.text]
    return " | ".join(shown(e.value) for e in elements)


def titles(at) -> list[str]:
    return [shown(s.value) for s in at.subheader]


def answer_radio(at):
    return next(r for r in at.radio if r.label == "Your answer")


def save(at, label):
    radio = answer_radio(at)
    assert label in radio.options, (label, radio.options)
    radio.set_value(label).run()
    next(b for b in at.button if b.label == "Save answer").click().run()
    assert not at.exception, at.exception


def company(at) -> dict[str, str]:
    table = next(d.value for d in at.dataframe if "Figure" in d.value.columns)
    return dict(zip(table["Figure"], table["Amount and status"]))


class RoutingTests(unittest.TestCase):
    def test_only_an_exact_layout_is_routed_to_the_quickbooks_flow(self):
        self.assertEqual(qflow.PNL, qflow.recognised_report("p.xlsx", made_up_pnl()))
        self.assertEqual(qflow.SBCD, qflow.recognised_report("s.xlsx", made_up_sbcd()))
        # A look-alike (a filter line in row 4), the CSV version, a plain list and a two-sheet workbook aren't.
        self.assertIsNone(qflow.recognised_report("p.xlsx", fx.xlsx(fx.pnl_rows(row4=["Customer: Coral Cafe"]))))
        self.assertIsNone(qflow.recognised_report("p.csv", fx.csv_bytes(fx.pnl_rows())))
        self.assertIsNone(qflow.recognised_report("p.xlsx", fx.csv_bytes(fx.pnl_rows())))  # name and contents differ
        self.assertIsNone(qflow.recognised_report("sales.csv", PLAIN_SALES))
        self.assertIsNone(qflow.recognised_report("p.xlsx", fx.xlsx(fx.pnl_rows(), sheets=2)))

    def test_files_are_sorted_by_what_they_are(self):
        found = qflow.sort_files([("p.xlsx", made_up_pnl()), ("sales.csv", PLAIN_SALES), ("s.xlsx", made_up_sbcd())])
        self.assertEqual((["p.xlsx"], ["s.xlsx"], ["sales.csv"]),
                         ([u.name for u in found.pnl], [u.name for u in found.sbcd], [u.name for u in found.other]))
        self.assertTrue(found.quickbooks)
        self.assertFalse(qflow.sort_files([("sales.csv", PLAIN_SALES)]).quickbooks)


class PageTests(unittest.TestCase):
    def test_a_profit_and_loss_detail_alone_asks_its_questions_and_shows_results(self):
        at = page({"pnl.xlsx": made_up_pnl()})
        text = everything(at)
        self.assertIn("Read as QuickBooks' Profit and Loss Detail for Biscayne Landscaping (fictional) (January "
                      "1-October 26, 2026, accrual basis): your sales and costs come from it.", text)
        self.assertEqual("Do you use sub-customers in QuickBooks for jobs?", titles(at)[0])
        self.assertIn("**Question 1 of 5**", text)  # jobs, two accounts, coverage, job costs
        self.assertIsNone(answer_radio(at).value)  # nothing pre-selected
        headline = titles(at)[-1]
        self.assertTrue(headline.startswith("After job costs, Biscayne Landscaping (fictional)"), headline)
        self.assertIn("isn't final yet", headline)
        # Nothing is final before the owner confirms the file's coverage, not even sales.
        self.assertEqual("$5,500.00 · Needs a check (missing amount unknown)", company(at)["Sales"])
        self.assertNotIn("This file can't be read", text)
        self.assertNotIn("Here's where your money was made", text)  # the plain-list results never show
        steps = next(m.value for m in at.markdown if m.value.startswith('<div class="mx-nav-l">'))
        self.assertIn('<div class="mx-nav on"><div class="n">2</div>', steps)  # questions still open
        bare = [e.value for e in (*at.markdown, *at.subheader, *at.caption, *at.info, *at.error, *at.success)
                if re.search(r"(?<!\\)\$", e.value)]
        self.assertEqual([], bare)  # a bare "$" starts a math formula

    def test_with_the_cross_check_every_answer_makes_the_figures_final(self):
        at = page({"pnl.xlsx": made_up_pnl(), "sbcd.xlsx": made_up_sbcd()})
        self.assertIn("used only to check the sales in the Profit and Loss Detail; its amounts are never added",
                      everything(at))
        save(at, "Yes, each sub-customer is a job")
        self.assertEqual(NO_FILTER, titles(at)[0])
        save(at, "Yes, both have no filter")
        for _ in range(2):  # the two accounts, in the order asked
            account = titles(at)[0]
            radio = answer_radio(at)
            wanted = "Overhead" if "Office Supplies" in account else "Job costs"
            save(at, next(o for o in radio.options if o.startswith(wanted)))
        self.assertEqual("Does this file include your whole business?", titles(at)[0])
        save(at, "Yes, I checked")
        self.assertEqual("Is every job cost for these dates in this report, on its job?", titles(at)[0])
        self.assertIn("How MargenX counted your costs for January 1-October 26, 2026:", everything(at))
        save(at, "Yes, I checked")
        text = everything(at)
        self.assertIn("No questions left.", text)
        self.assertIn("Coverage confirmed by you for this file.", text)
        self.assertIn("Job costs confirmed by you for this file.", text)
        headline = titles(at)[-1]
        self.assertTrue(headline.endswith("the business made $2,400.00. This figure is Complete for this report."),
                        headline)
        self.assertIn("The required checks and confirmations are complete for this report.", text)
        self.assertNotIn("Nothing is missing", text)
        steps = next(m.value for m in at.markdown if m.value.startswith('<div class="mx-nav-l">'))
        self.assertIn('<div class="mx-nav on"><div class="n">3</div>', steps)  # See your money
        jobs = next(d.value for d in at.dataframe if "Customer › Job" in d.value.columns)
        self.assertEqual("-$600.00 · Complete", jobs.iloc[0]["Profit after job costs"])  # losing money first

    def test_without_the_cross_check_jobs_are_never_final(self):
        at = page({"pnl.xlsx": made_up_pnl()})
        save(at, "Yes, each sub-customer is a job")
        for _ in range(2):
            radio = answer_radio(at)
            wanted = "Overhead" if "Office Supplies" in titles(at)[0] else "Job costs"
            save(at, next(o for o in radio.options if o.startswith(wanted)))
        jobs = next(d.value for d in at.dataframe if "Customer › Job" in d.value.columns)
        self.assertTrue(all("Needs a check" in v for v in jobs["Profit after job costs"]), list(jobs.values))
        self.assertIn("One report alone can't make a job's profit Complete", everything(at))

    def test_the_405_dollars_of_cost_of_goods_sold_invoices_are_never_sales_on_the_page(self):
        at = page({"pnl.xlsx": rules.xlsx(rules.PNL_REPORT)})
        # The report's own Income lines are $1,800 (held here: this short made-up report has no summary rows, so its
        # sections aren't verified). The six Cost of Goods Sold "Invoice" lines ($405) are never sales: $2,205 never
        # appears, and the sales figure is never Complete while its section isn't verified.
        sales = company(at)["Sales"]
        self.assertIn("$1,800.00", sales)
        self.assertNotIn("Complete", sales)
        self.assertNotIn("2,205", everything(at) + " ".join(company(at).values()))

    def test_a_look_alike_is_still_refused_by_the_reader_for_plain_lists(self):
        at = page({"pnl.xlsx": fx.xlsx(fx.pnl_rows(row4=["Customer: Coral Cafe (fictional)"]))})
        errors = " ".join(e.value for e in at.error)
        self.assertIn("This file can't be read: This looks like a QuickBooks report (it has the title 'Profit and "
                      "Loss Detail'), but it isn't exactly in the layout MargenX knows", errors)
        self.assertEqual([], [r for r in at.radio if r.label == "Your answer"])
        self.assertNotIn("After job costs", " ".join(titles(at)))

    def test_quickbooks_reports_are_never_mixed_with_other_files(self):
        at = page({"pnl.xlsx": made_up_pnl(), "costs.csv": PLAIN_COSTS})
        errors = " ".join(shown(e.value) for e in at.error)
        self.assertIn("doesn't use other sales or cost files with it: the same money could be counted twice. Remove "
                      "costs.csv", errors)
        self.assertEqual([], titles(at))  # no questions, no results
        self.assertIn("Not used: MargenX doesn't combine this file with a QuickBooks report", everything(at))
        self.assertNotIn("Here's where your money was made", everything(at))

    def test_sales_by_customer_detail_alone_asks_for_the_profit_and_loss_detail(self):
        at = page({"sbcd.xlsx": made_up_sbcd()})
        self.assertIn(qflow.SBCD_ALONE, [i.value for i in at.info])
        self.assertEqual([], titles(at))
        at = page({"sbcd.xlsx": made_up_sbcd(), "sales.csv": PLAIN_SALES})
        self.assertIn("Remove sales.csv", " ".join(e.value for e in at.error))
        self.assertEqual([], titles(at))

    def test_two_different_profit_and_loss_reports_are_refused_and_an_identical_copy_is_used_once(self):
        at = page({"a.xlsx": made_up_pnl(), "b.xlsx": made_up_pnl(job_b_materials=D("2000"))})
        self.assertIn(qflow.ONE_PNL.format(count=2), [e.value for e in at.error])
        self.assertEqual([], titles(at))
        at = page({"a.xlsx": made_up_pnl(), "copy.xlsx": made_up_pnl()})
        self.assertIn("copy.xlsx is identical to a.xlsx", " ".join(w.value for w in at.warning))
        self.assertEqual("$5,500.00 · Needs a check (missing amount unknown)", company(at)["Sales"])  # counted once

    def test_two_different_sales_reports_are_refused(self):
        other = fx.xlsx(fx.sbcd_rows([(X, [], [("Job A", [S(2, "Invoice", "1001", "Design work", 1, 4000)])])]))
        at = page({"pnl.xlsx": made_up_pnl(), "s1.xlsx": made_up_sbcd(), "s2.xlsx": other})
        self.assertIn(qflow.ONE_SBCD.format(count=2), [e.value for e in at.error])
        self.assertEqual([], titles(at))

    def test_plain_lists_still_go_through_the_reader_for_plain_lists(self):
        at = page({"sales.csv": PLAIN_SALES, "costs.csv": PLAIN_COSTS})
        text = everything(at)
        self.assertIn("Here's where your money was made", text)
        self.assertEqual([], [r for r in at.radio if r.label == "Your answer"])

    def test_the_trial_still_has_no_upload_box(self):
        # Trial uploads stay off (#137): the page's own switch, unchanged by this PR.
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("use_samples = True if TRIAL else st.toggle(", source)


if __name__ == "__main__":
    unittest.main()
