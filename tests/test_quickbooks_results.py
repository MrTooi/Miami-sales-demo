"""Issue #128, step 7: a QuickBooks report's results, in layers (plan v7, step 7).

Made-up reports only (tests/qbo_results_app.py). The one-sentence answer says "final" only when the figure is
Complete; every figure that isn't final shows its status and the amount held in the same cell; what's missing
is listed in plain words with amounts; the details are folded away.
"""
import re
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_questions as qq  # noqa: E402
import quickbooks_results as qr  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

PAGE = str(Path(__file__).resolve().parent / "qbo_results_app.py")
L, S = fx.line, fx.sale
X, Y = "Customer X (fictional)", "Customer Y (fictional)"


def reports():
    pnl = qp.read_profit_and_loss_detail("p.xlsx", fx.xlsx(fx.report_rows({
        "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                      L(3, "Invoice", "1002", f"{Y}:Job B", D("1500"), None)])],
        "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", D("1000"), None),
                                        L(6, "Bill", "B-2", f"{Y}:Job B", D("2100"), None)]),
                     ("Office Supplies", [L(7, "Expense", "", "Office Depot (fictional)", D("500"), None)])]})))
    sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
        [(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)])]),
         (Y, [], [("Job B", [S(3, "Invoice", "1002", "Design", 1, 1500)])])])))
    return pnl, qc.cross_check(pnl, sales)


def answer_everything(report, check):
    """Sub-customers are jobs, Job Materials is job costs, Office Supplies is overhead, no filter."""
    picks = {qq.JOBS: "yes", qq.NO_FILTER: "yes"}
    accounts = {"Job Materials": qf.JOB_COSTS_ACCOUNT, "Office Supplies": qf.OVERHEAD_ACCOUNT}
    answers = None
    for _ in range(10):
        questions = qq.open_questions(report, answers, check).questions
        if not questions:
            return answers
        q = questions[0]
        choice = picks.get(q.kind) or accounts[q.account[-1]]
        answers = qq.answer(report, answers, q, choice, cross_check=check)
    raise AssertionError("questions never ran out")


class LayerTests(unittest.TestCase):
    def test_nothing_answered_is_never_called_final(self):
        report, check = reports()
        figures = qf.figures(report, None, check)
        line = qr.headline(report, figures)
        self.assertIn("so far, but this isn't final yet", line)
        self.assertIn("3 lines are still held back ($3,600.00)", line)
        self.assertNotIn("final for this report", line)
        cells = [r["Amount and status"] for r in qr.company_rows(figures)]
        self.assertIn("$0.00 · Needs a check ($3,600.00 held)", cells)
        for text in cells:
            self.assertTrue(text.endswith("· Complete") or "· Needs a check (" in text, text)

    def test_everything_answered_and_cross_checked_is_final(self):
        report, check = reports()
        answers = answer_everything(report, check)
        figures = qf.figures(report, answers, check)
        self.assertEqual((), figures.warnings)
        self.assertEqual("After job costs, Biscayne Landscaping (fictional), January 1-October 26, 2026: the business "
                         "made $2,400.00. This figure is final for this report.", qr.headline(report, figures))
        self.assertEqual([], qr.missing(figures))
        jobs = qr.group_rows(figures.jobs, "Customer › Job")
        self.assertEqual(f"{Y} › Job B", jobs[0]["Customer › Job"])  # losing money first
        self.assertEqual("-$600.00 · Complete", jobs[0]["Profit after job costs"])
        self.assertEqual("$3,000.00 · Complete", jobs[1]["Profit after job costs"])
        self.assertEqual("$500.00 · Complete", dict((r["Figure"], r["Amount and status"])
                                                   for r in qr.company_rows(figures))["Overhead"])

    def test_without_the_second_report_jobs_stay_held_and_say_why(self):
        report, check = reports()
        answers = answer_everything(report, None)
        figures = qf.figures(report, answers)
        self.assertTrue(all(f["profit_after_job_costs"].status == qp.NEEDS_A_CHECK for f in figures.jobs.values()))
        self.assertIn("One report alone can't make a job's profit Complete: a second report has to cross-check its "
                      "sales first.", qr.missing(figures))  # the rule code is left out
        cell = qr.group_rows(figures.jobs, "Customer › Job")[0]["Profit after job costs"]
        self.assertEqual("-$600.00 · Needs a check (see why below)", cell)
        self.assertIn("This figure is final for this report.", qr.headline(report, figures))  # the business's own

    def test_the_headline_counts_only_the_lines_holding_its_own_figure(self):
        # The automated review of 9234135: the $700 sale with no job holds only Customer X's jobs, never the business.
        report = qp.read_profit_and_loss_detail("p.xlsx", fx.xlsx(fx.report_rows({
            "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                          L(3, "Invoice", "1002", X, D("700"), None)])],
            "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", D("1000"), None)])]})))
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        figures = qf.figures(report, answers)
        self.assertEqual(2, len([key for key in qr.held_lines(figures) if key[1] is not None]))  # across all figures
        self.assertIn("1 line is still held back ($1,000.00)", qr.headline(report, figures))

    def test_an_amount_that_cant_be_read_is_said_never_left_out(self):
        # The automated review of 8a41156: known, unknown-only and mixed holds.
        def figure(*amounts):
            return qf.Figure(D("100"), tuple(qf.Hold(row, amount, "held") for row, amount in enumerate(amounts, 1)))

        self.assertEqual("$100.00 · Needs a check ($50.00 held)", qr.cell(figure(D("50"))))
        self.assertEqual("$100.00 · Needs a check (1 line of unknown amount held)", qr.cell(figure(None)))
        self.assertEqual("$100.00 · Needs a check ($50.00 plus 2 lines of unknown amount held)",
                         qr.cell(figure(D("50"), None, None)))
        self.assertEqual("$100.00 · Needs a check (see why below)",
                         qr.cell(qf.Figure(D("100"), (qf.Hold(None, None, "the whole report"),))))

    def test_a_loss_is_called_a_loss(self):
        report = qp.read_profit_and_loss_detail("p.xlsx", fx.xlsx(fx.report_rows({
            "Income": [("Design income", [L(2, "Invoice", "1001", X, D("100"), None)])],
            "Expenses": [("Job Materials", [L(3, "Bill", "B-1", X, D("250"), None)])]})))
        self.assertIn("the business made $100.00 so far", qr.headline(report, qf.figures(report)))
        answers = qf.OwnerAnswers(report=qf.report_fingerprint(report), accounts={
            ("Expenses", "Job Materials"): qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT, (), "")})
        self.assertIn("the business lost $150.00. This figure is final for this report.",
                      qr.headline(report, qf.figures(report, answers)))

    def test_reasons_are_plain_words_with_dollar_amounts(self):
        self.assertEqual("Row 16 ($1,000.00) is a cost.", qr.plain("Row 16 (1,000.00) is a cost."))
        self.assertEqual("Row 3 (-$40.00) is held.", qr.plain("Row 3 (-40.00) is held."))
        self.assertEqual("It's held.", qr.plain("It's held (AGENTS.md rule 4)."))

    def test_names_from_the_report_are_spreadsheet_safe(self):
        report = qp.read_profit_and_loss_detail("p.xlsx", fx.xlsx(fx.report_rows({
            "Income": [("Design income", [L(2, "Invoice", "1001", "@SUM(1) (fictional)", D("100"), None)])]})))
        rows = qr.group_rows(qf.figures(report).customers, "Customer")
        self.assertEqual("'@SUM(1) (fictional)", rows[0]["Customer"])


def walk(node, out=None):
    """Every element on the page, in the order shown."""
    out = [] if out is None else out
    children = getattr(node, "children", None)
    if children:
        for key in sorted(children):
            walk(children[key], out)
    else:
        out.append((node.type, str(getattr(node, "value", ""))))
    return out


class ScreenTests(unittest.TestCase):
    def test_the_screen_shows_the_layers_in_order(self):
        at = AppTest.from_file(PAGE, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        # The automated review of 9234135 (warning): the order itself, as shown on the page.
        shown = [(kind, value) for kind, value in walk(at.main) if kind in ("subheader", "markdown", "caption")]
        after_questions = shown[[i for i, (kind, _) in enumerate(shown) if kind == "subheader"][-1]:]
        order = [next(i for i, (_, value) in enumerate(after_questions) if value.startswith(start))
                 for start in ("After job costs,", "**Your business**", "**By customer**", "**What's missing**",
                               "Within QuickBooks' Profit and Loss Detail")]
        self.assertEqual(sorted(order), order)
        bare = [v for v in [e.value for e in (*at.markdown, *at.subheader, *at.caption, *at.success, *at.warning)]
                if re.search(r"(?<!\\)\$", v)]
        self.assertEqual([], bare)  # a bare "$" starts a math formula (found in the browser)
        headline = at.subheader[-1].value.replace("\\$", "$")
        self.assertTrue(headline.startswith("After job costs,"), headline)
        self.assertIn("isn't final yet", headline)
        company = at.dataframe[0].value
        self.assertEqual(["Figure", "Amount and status"], list(company.columns))
        texts = [m.value.replace("\\$", "$") for m in at.markdown]
        self.assertIn("**What's missing** (3)", texts)
        self.assertIn("- Row 16 ($1,000.00) is a cost, but whether it's a job cost or overhead isn't known yet.", texts)
        details = next(e for e in at.expander if e.label.startswith("Details:"))
        self.assertTrue(details.caption[0].value.startswith("Within QuickBooks' Profit and Loss Detail"))
        self.assertEqual([], [s for s in at.success if "Nothing is missing" in s.value])

    def test_everything_answered_shows_jobs_and_says_nothing_is_missing(self):
        # The automated review of 8a41156 (warning): the fully answered screen, rendered.
        def page():
            import sys
            from pathlib import Path
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_results as qresults
            import test_quickbooks_results as t
            report, check = t.reports()
            qresults.results_screen(report, t.answer_everything(report, check), check)

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        headline = at.subheader[0].value.replace("\\$", "$")
        self.assertTrue(headline.endswith("made $2,400.00. This figure is final for this report."), headline)
        self.assertIn("**By job** (losing money first)", [m.value for m in at.markdown])
        jobs = next(d.value for d in at.dataframe if "Customer › Job" in d.value.columns)
        self.assertEqual("-$600.00 · Complete", jobs.iloc[0]["Profit after job costs"])
        self.assertIn("Nothing is missing: every figure above is final for this report.", [s.value for s in at.success])
        self.assertNotIn("**What's missing**", " ".join(m.value for m in at.markdown))

    def test_the_company_name_is_never_read_as_markdown(self):
        def page():
            import sys
            from decimal import Decimal as D
            from pathlib import Path
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_fixtures as fx
            import quickbooks_pnl as qp
            import quickbooks_results as qresults
            rows = fx.report_rows({"Income": [("Design income", [
                fx.line(2, "Invoice", "1001", "Customer X (fictional)", D("100"), None)])]})
            rows[0] = ["![x](https://example.invalid/x.png) (fictional)"]
            qresults.results_screen(qp.read_profit_and_loss_detail("p.xlsx", fx.xlsx(rows)))

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn(r"\!\[x\](https://example.invalid/x.png)", at.subheader[0].value)

    def test_no_page_of_the_app_uses_the_results_yet(self):
        root = Path(__file__).resolve().parents[1]
        pages = [root / "app.py", root / "trial_app.py", root / "marginx_pilot.py", *(root / "pages").glob("*.py")]
        self.assertEqual([], [p.name for p in pages if "quickbooks_results" in p.read_text()])


if __name__ == "__main__":
    unittest.main()
