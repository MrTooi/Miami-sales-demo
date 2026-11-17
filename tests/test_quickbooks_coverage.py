"""Issue #128: the owner's coverage confirmation for a Profit and Loss Detail (the 2026-11-17 design review).

A filter in QuickBooks can leave a whole cost account, or some transactions, out of an export without showing in
the file. Made-up example from the review: Labor ($900, Customer X's Kitchen job) left out turns the company's
$3,400 profit after job costs into $4,300, with every total in the file still matching. So every figure of the
company, every customer and every job holds "missing amount unknown" until the owner confirms, for this exact
file and these exact words, that the report includes the whole business's income and costs with no filters.

One test per row of the reviewer's table, plus the explicit limitation test. Every company, customer, vendor and
amount here is made up; every report is built in the layout seen (tests/quickbooks_fixtures.py) and read end to
end from Excel bytes. These tests don't prove that MargenX can detect a missing account: it can't, and says so.
"""
import dataclasses
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

L, S = fx.line, fx.sale
X, Y = "Customer X (fictional)", "Customer Y (fictional)"
KITCHEN, PATIO = (X, "Kitchen"), (Y, "Patio")
MATERIALS, LABOR = ("Expenses", "Job Materials"), ("Expenses", "Labor")
COVERAGE_TITLE = "Does this file include your whole business?"


def income(*, y_too=True):
    return [L(2, "Invoice", "1001", f"{X}:Kitchen", D("4500"), None),
            *([L(3, "Invoice", "1002", f"{Y}:Patio", D("1200"), None)] if y_too else [])]


def materials(*, y_too=True):
    return [L(5, "Bill", "B-1", f"{X}:Kitchen", D("600"), None),
            *([L(6, "Bill", "B-2", f"{Y}:Patio", D("800"), None)] if y_too else [])]


def labor(amount=D("900")):
    return [L(7, "Bill", "B-3", f"{X}:Kitchen", amount, None)]


def pnl(sections, name="pnl.xlsx", saved_at=fx.SAVED_AT) -> qp.ProfitAndLossDetail:
    report = qp.read_profit_and_loss_detail(name, fx.xlsx(fx.report_rows(sections), saved_at=saved_at))
    assert report.reconciled, report.problems
    return report


def full_export(labor_amount=D("900"), saved_at=fx.SAVED_AT):
    """The whole business: X's Kitchen ($4,500 - $600 - $900 = $3,000) and Y's Patio ($1,200 - $800 = $400).
    Another saved_at gives a different workbook that reads exactly the same (a second export)."""
    return pnl({"Income": [("Design income", income())],
                "Expenses": [("Job Materials", materials()), ("Labor", labor(labor_amount))]}, saved_at=saved_at)


def missing_labor():
    """The same export with the Labor account filtered out: every total in it still matches its lines."""
    return pnl({"Income": [("Design income", income())], "Expenses": [("Job Materials", materials())]})


def sales_rows():
    return fx.sbcd_rows([(X, [], [("Kitchen", [S(2, "Invoice", "1001", "Design", 1, 4500)])]),
                         (Y, [], [("Patio", [S(3, "Invoice", "1002", "Design", 1, 1200)])])])


def sales_report(saved_at=fx.SAVED_AT):
    """Sales by Customer Detail listing exactly the same sales as both Profit and Loss files."""
    return qs.read_sales_by_customer_detail("sales.xlsx", fx.xlsx(sales_rows(), saved_at=saved_at))


def base(report, *, check=None, accounts=None) -> qf.OwnerAnswers:
    """Every answer except coverage: sub-customers are jobs, every cost account holds job costs, and (with a
    usable cross-check) both reports were exported with no filter."""
    accounts = accounts if accounts is not None else {
        line.account_path: qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT) for line in report.lines
        if line.section in qf.COST_SECTIONS}
    return qf.OwnerAnswers(report=qf.report_fingerprint(report), sub_customers_are_jobs=True, accounts=accounts,
                           unfiltered_pair=check.pair if check is not None else "")


def coverage_question(report, answers=None, check=None) -> qq.Question:
    return next(q for q in qq.open_questions(report, answers, check).questions if q.kind == qq.COVERAGE)


def say(report, answers, choice, check=None) -> qf.OwnerAnswers:
    """The owner answers the coverage question (yes, no, or "not sure"), as the screen asks it: open, or opened
    again from the review list to change an earlier answer."""
    question = coverage_question(report, dataclasses.replace(answers, coverage=None), check)
    return qq.answer(report, answers, question, choice, cross_check=check)


def every_figure(result: qf.Figures):
    yield "company", result.company
    for name, group in result.customers.items():
        yield name, group
    for key, group in result.jobs.items():
        yield key, group


def statuses(result: qf.Figures) -> set[str]:
    return {figure.status for _, group in every_figure(result) for figure in group.values()}


def coverage_held(result: qf.Figures) -> bool:
    return all(figure.coverage_open for _, group in every_figure(result) for figure in group.values())


def profits(result: qf.Figures) -> dict:
    return {"company": result.company["profit_after_job_costs"].amount,
            **{key: group["profit_after_job_costs"].amount for key, group in (*result.customers.items(),
                                                                                 *result.jobs.items())}}


class MissingLaborTests(unittest.TestCase):
    """Rows 1 and 2: the missing-Labor file, unanswered, "no" or "not sure"; and with a matching sales report."""

    def test_unanswered_no_and_not_sure_hold_the_company_every_customer_and_every_job(self):
        report = missing_labor()
        unanswered = base(report)
        said_no = say(report, unanswered, qf.COVERAGE_NO)
        not_sure = say(report, say(report, unanswered, qf.COVERAGE_YES), qq.NOT_SURE)  # "yes", then "not sure"
        self.assertIsNone(not_sure.coverage)
        for label, answers in (("unanswered", unanswered), ("no", said_no), ("not sure", not_sure)):
            with self.subTest(label):
                result = qf.figures(report, answers)
                self.assertEqual({qp.NEEDS_A_CHECK}, statuses(result))
                self.assertTrue(coverage_held(result))  # X too: nothing in the file says who Labor was for
                self.assertEqual({"company": D("4300"), X: D("3900"), Y: D("400"), KITCHEN: D("3900"),
                                  PATIO: D("400")}, profits(result))  # amounts never change
        self.assertIn(qf.COVERAGE_SAID_MISSING, qr.missing(qf.figures(report, said_no)))  # a line of its own
        missing = qr.missing(qf.figures(report, unanswered))
        self.assertIn(qf.COVERAGE_NOT_YET, missing)
        self.assertIn(qr.plain(qf.ONE_REPORT), missing)  # each whole-report reason on its own line

    def test_a_matching_sales_report_and_the_no_filter_answer_never_lift_the_coverage_hold(self):
        report = missing_labor()
        check = qc.cross_check(report, sales_report())
        self.assertTrue(check.usable, check.reasons)
        result = qf.figures(report, base(report, check=check), cross_check=check)
        self.assertEqual({qp.NEEDS_A_CHECK}, statuses(result))
        for key in (KITCHEN, PATIO):
            # Every hold on a job's profit is the coverage one: the sales match and S3 is answered.
            self.assertEqual({qf.COVERAGE_HOLD}, {h.kind for h in result.jobs[key]["profit_after_job_costs"].holds})
        self.assertEqual([qq.COVERAGE], [q.kind for q in qq.open_questions(report, base(report, check=check),
                                                                           check).questions])


class FullExportTests(unittest.TestCase):
    """Row 3: the full export with an explicit "yes" and every other check satisfied."""

    def test_one_report_makes_customers_and_the_company_complete_but_never_a_job(self):
        report = full_export()
        result = qf.figures(report, say(report, base(report), qf.COVERAGE_YES))
        self.assertEqual(qf.CONFIRMED, result.coverage)
        self.assertEqual((D("3400"), qp.COMPLETE), (result.company["profit_after_job_costs"].amount,
                                                    result.company["profit_after_job_costs"].status))
        self.assertEqual((D("3000"), qp.COMPLETE), (result.customers[X]["profit_after_job_costs"].amount,
                                                    result.customers[X]["profit_after_job_costs"].status))
        self.assertEqual((D("400"), qp.COMPLETE), (result.customers[Y]["profit_after_job_costs"].amount,
                                                   result.customers[Y]["profit_after_job_costs"].status))
        for key in (KITCHEN, PATIO):
            self.assertEqual([qf.ONE_REPORT], [h.reason for h in result.jobs[key]["profit_after_job_costs"].holds])

    def test_with_the_sales_report_and_the_no_filter_answer_jobs_are_complete_too(self):
        report = full_export()
        check = qc.cross_check(report, sales_report())
        answers = say(report, base(report, check=check), qf.COVERAGE_YES, check)
        result = qf.figures(report, answers, cross_check=check)
        self.assertEqual({qp.COMPLETE}, statuses(result))
        self.assertEqual({"company": D("3400"), X: D("3000"), Y: D("400"), KITCHEN: D("3000"), PATIO: D("400")},
                         profits(result))
        self.assertTrue(qq.open_questions(report, answers, check).done)
        # The yes never stands in for the no-filter answer either: without it, jobs keep S3's hold.
        without_s3 = qf.figures(report, dataclasses.replace(answers, unfiltered_pair=""), cross_check=check)
        self.assertEqual([qf.NO_FILTER_YET], [h.reason for h in without_s3.jobs[KITCHEN]["profit_after_job_costs"].holds])
        self.assertEqual(qp.COMPLETE, without_s3.customers[X]["profit_after_job_costs"].status)

    def test_the_question_is_asked_with_one_report_or_two(self):
        report = full_export()
        check = qc.cross_check(report, sales_report())
        for label, given in (("one report", None), ("two reports", check)):
            with self.subTest(label):
                kinds = [q.kind for q in qq.open_questions(report, None, given).questions]
                self.assertEqual(1, kinds.count(qq.COVERAGE))
                self.assertEqual(kinds.index(qq.COVERAGE), max(i for i, k in enumerate(kinds) if k == qq.ACCOUNT) + 1)


class FilteredFileTests(unittest.TestCase):
    """Row 4: every cost-account name present but transactions filtered out; an income account left out; and a
    contradiction the file shows."""

    def test_all_account_names_present_with_transactions_filtered_out_stays_held(self):
        full = full_export()
        # A customer filter: Customer Y's transactions are gone, but every account still has activity.
        filtered = pnl({"Income": [("Design income", income(y_too=False))],
                        "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]})
        self.assertEqual([a.path for a in qf.cost_accounts(full)], [a.path for a in qf.cost_accounts(filtered)])
        # Every account question answered: that is not the coverage confirmation.
        answers = base(filtered)
        self.assertEqual({qp.NEEDS_A_CHECK}, statuses(qf.figures(filtered, answers)))
        self.assertIsNone(answers.coverage)
        # The words asked cover every transaction and the income too, not just the account names.
        statement = coverage_question(filtered).statement
        for words in ("whole business's income and costs", "no filters excluding accounts or transactions"):
            self.assertIn(words, statement)

    def test_an_income_account_left_out_stays_held(self):
        full = pnl({"Income": [("Design income", income()),
                               ("Installation income", [L(4, "Invoice", "1003", f"{Y}:Patio", D("300"), None)])],
                    "Expenses": [("Job Materials", materials()), ("Labor", labor())]})
        left_out = full_export()
        self.assertEqual([a.path for a in qf.cost_accounts(full)], [a.path for a in qf.cost_accounts(left_out)])
        result = qf.figures(left_out, base(left_out))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)  # sales are held too, not just costs
        self.assertTrue(result.customers[Y]["sales"].coverage_open)

    def test_a_contradiction_the_file_shows_still_holds_after_yes(self):
        rows = fx.report_rows({"Income": [("Design income", income())],
                               "Expenses": [("Job Materials", materials()), ("Labor", labor())]})
        rows = [r if r[:1] != ["Total for Labor"] else fx.total("Total for Labor", D("950")) for r in rows]
        report = qp.read_profit_and_loss_detail("pnl.xlsx", fx.xlsx(rows))
        self.assertTrue(report.problems)
        result = qf.figures(report, say(report, base(report), qf.COVERAGE_YES))
        self.assertEqual(qf.CONFIRMED, result.coverage)
        profit = result.company["profit_after_job_costs"]
        self.assertEqual(qp.NEEDS_A_CHECK, profit.status)
        self.assertFalse(profit.coverage_open)
        self.assertTrue(any("totals don't all match" in h.reason for h in profit.holds))


class ChangeOfAnswerTests(unittest.TestCase):
    """Row 5: yes, then no, "not sure" or withdrawn, including after S3 is satisfied."""

    def test_every_dependent_status_updates_at_once_and_amounts_and_other_holds_stay(self):
        fee = ("Miscellaneous", [L(20, "Check", "305", "County Clerk (fictional)", D("50"), None, "", "Checking")])
        report = pnl({"Income": [("Design income", income())],
                      "Expenses": [("Job Materials", materials()), ("Labor", labor())], "Other Expense": [fee]})
        check = qc.cross_check(report, sales_report())
        answers = base(report, check=check)  # the $50 Other Expense isn't answered: it stays held
        yes = say(report, answers, qf.COVERAGE_YES, check)
        confirmed = qf.figures(report, yes, cross_check=check)
        self.assertEqual(qp.COMPLETE, confirmed.jobs[KITCHEN]["profit_after_job_costs"].status)
        self.assertEqual(qp.NEEDS_A_CHECK, confirmed.company["after_overhead"].status)  # the $50
        changes = {"no": say(report, yes, qf.COVERAGE_NO, check),
                   "not sure": say(report, yes, qq.NOT_SURE, check),
                   "withdrawn": dataclasses.replace(yes, coverage=None)}
        for label, answers_now in changes.items():
            with self.subTest(label):
                result = qf.figures(report, answers_now, cross_check=check)
                self.assertTrue(coverage_held(result))
                self.assertEqual({qp.NEEDS_A_CHECK}, statuses(result))
                self.assertEqual(profits(confirmed), profits(result))
                self.assertEqual(confirmed.company["after_overhead"].amount, result.company["after_overhead"].amount)
                self.assertEqual(D("50"), result.company["after_overhead"].held_amount)  # the known $50 hold stays
                self.assertEqual(check.pair, answers_now.unfiltered_pair)  # S3's own answer is untouched


class FileBindingTests(unittest.TestCase):
    """Row 6: a new or changed file, or another question's wording, never inherits the confirmation."""

    def test_a_changed_file_with_the_same_name_and_accounts_needs_a_new_answer(self):
        first = full_export()
        answers = say(first, base(first), qf.COVERAGE_YES)
        corrected = full_export(labor_amount=D("901"))  # same file name, same account names
        self.assertEqual([a.path for a in qf.cost_accounts(first)], [a.path for a in qf.cost_accounts(corrected)])
        result = qf.figures(corrected, answers)
        self.assertIn("given for a different report", " ".join(result.warnings))
        self.assertEqual({qp.NEEDS_A_CHECK}, statuses(result))
        self.assertIn(qq.COVERAGE, [q.kind for q in qq.open_questions(corrected, answers).questions])
        # Even re-bound to the new file by hand, the confirmation was for the old one.
        rebound = dataclasses.replace(answers, report=qf.report_fingerprint(corrected))
        result = qf.figures(corrected, rebound)
        self.assertIn("Your coverage answer was given for another file", " ".join(result.warnings))
        self.assertTrue(coverage_held(result))
        self.assertIn(qq.COVERAGE, [q.kind for q in qq.open_questions(corrected, rebound).questions])

    def test_an_answer_to_other_words_never_counts(self):
        report = full_export()
        narrower = qf.CoverageAnswer(qf.COVERAGE_YES, "Yes, they're all here.", qf.report_fingerprint(report),
                                     report.file_digest)
        answers = dataclasses.replace(base(report), coverage=narrower)
        result = qf.figures(report, answers)
        self.assertTrue(coverage_held(result))
        self.assertIn("for other words than the question asked now", " ".join(result.warnings))
        self.assertIn(qq.COVERAGE, [q.kind for q in qq.open_questions(report, answers).questions])
        # A question showing other words than this file's is refused, never recorded as this one.
        stale = dataclasses.replace(coverage_question(report, base(report)), statement="Yes, they're all here.")
        self.assertEqual(base(report), qq.answer(report, base(report), stale, qf.COVERAGE_YES))

    def test_a_question_asked_about_another_file_changes_nothing(self):
        first, corrected = full_export(), full_export(labor_amount=D("901"))
        question = coverage_question(first)
        self.assertEqual(base(corrected), qq.answer(corrected, base(corrected), question, qf.COVERAGE_YES))

    def test_replacing_only_the_sales_report_keeps_coverage_and_asks_the_no_filter_question_again(self):
        report = full_export()
        check = qc.cross_check(report, sales_report())
        answers = say(report, base(report, check=check), qf.COVERAGE_YES, check)
        other_sales = qs.read_sales_by_customer_detail("sales.xlsx", fx.xlsx(fx.sbcd_rows(
            [(X, [], [("Kitchen", [S(2, "Invoice", "1001", "Design work", 1, 4500)])]),
             (Y, [], [("Patio", [S(3, "Invoice", "1002", "Design", 1, 1200)])])])))
        other = qc.cross_check(report, other_sales)
        self.assertNotEqual(check.pair, other.pair)
        result = qf.figures(report, answers, cross_check=other)
        self.assertEqual(qf.CONFIRMED, result.coverage)  # the Profit and Loss Detail is the same file
        self.assertEqual([qf.NO_FILTER_YET], [h.reason for h in result.jobs[KITCHEN]["profit_after_job_costs"].holds])
        self.assertEqual([qq.NO_FILTER], [q.kind for q in qq.open_questions(report, answers, other).questions])


def upload_page(folder: Path, names: tuple[str, ...]) -> AppTest:
    """The real upload page reading these made-up files from folder; the list of files in use is read on every run
    from folder/files.txt, so a test can remove or replace a file mid-session, as an owner can."""
    import test_quickbooks_upload as up
    (folder / "files.txt").write_text(" ".join(names))
    source = up.PAGE.read_text(encoding="utf-8").replace(
        'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({str(folder)!r})").replace(
        'DEFAULT_SAMPLE_SET = "demo"', 'DEFAULT_SAMPLE_SET = "test"').replace(
        'SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")',
        "SAMPLE_FILES = tuple((SAMPLES / 'files.txt').read_text().split())")
    at = AppTest.from_string(source, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def answer_everything(at, coverage="Yes, I checked") -> None:
    """Every question on the upload page: jobs, the no-filter answer, job-cost accounts, then coverage."""
    import test_quickbooks_upload as up
    for _ in range(8):
        title = up.titles(at)[0]
        if title.startswith("After job costs"):
            return
        radio = up.answer_radio(at)
        label = {"Do you use sub-customers in QuickBooks for jobs?": "Yes, each sub-customer is a job",
                 up.NO_FILTER: "Yes, both have no filter", COVERAGE_TITLE: coverage}.get(title)
        up.save(at, label or next(o for o in radio.options if o.startswith("Job costs")))
    raise AssertionError("questions never ran out")


class OtherWorkbookTests(unittest.TestCase):
    """The PR #148 manual review, blocker 1: a different workbook that reads exactly the same (same name, same
    rows) never inherits the confirmation; replacing only the sales workbook keeps it and asks S3 again."""

    def test_a_different_workbook_that_reads_the_same_needs_its_own_answer(self):
        first, second = full_export(), full_export(saved_at="2026-11-17T09:00:00Z")
        self.assertEqual(qf.report_fingerprint(first), qf.report_fingerprint(second))  # reads exactly the same
        self.assertNotEqual(first.file_digest, second.file_digest)
        answers = say(first, base(first), qf.COVERAGE_YES)
        self.assertTrue(qf.coverage_confirmed(first, answers))
        self.assertFalse(qf.coverage_confirmed(second, answers))
        result = qf.figures(second, answers)
        self.assertNotEqual(qf.CONFIRMED, result.coverage)
        self.assertTrue(coverage_held(result))
        self.assertIn("given for another file", " ".join(result.warnings))
        self.assertEqual([qq.COVERAGE], [q.kind for q in qq.open_questions(second, answers).questions])
        # The first file's question can't record a yes for the second.
        self.assertEqual(answers, qq.answer(second, answers, coverage_question(first, base(first)), qf.COVERAGE_YES))

    def test_a_different_sales_workbook_keeps_coverage_and_asks_the_no_filter_question_again(self):
        report = full_export()
        check = qc.cross_check(report, sales_report())
        answers = say(report, base(report, check=check), qf.COVERAGE_YES, check)
        other = qc.cross_check(report, sales_report(saved_at="2026-11-17T09:00:00Z"))
        self.assertEqual(check.sbcd_fingerprint, other.sbcd_fingerprint)  # reads exactly the same
        self.assertNotEqual(check.pair, other.pair)
        result = qf.figures(report, answers, cross_check=other)
        self.assertEqual(qf.CONFIRMED, result.coverage)
        self.assertEqual([qf.NO_FILTER_YET], [h.reason for h in result.jobs[KITCHEN]["profit_after_job_costs"].holds])
        self.assertEqual([qq.NO_FILTER], [q.kind for q in qq.open_questions(report, answers, other).questions])

    def test_a_cross_check_made_for_another_workbook_is_never_used(self):
        # The automated review of 8d19d7b: workbook A's cross-check, its saved no-filter answer and its no-filter
        # question, passed directly with workbook B, which reads exactly the same.
        a, b = full_export(), full_export(saved_at="2026-11-17T09:00:00Z")
        check_a = qc.cross_check(a, sales_report())
        answers = say(a, base(a, check=check_a), qf.COVERAGE_YES, check_a)  # S3 answered for A's pair
        stale_question = next(q for q in qq.open_questions(a, base(a), check_a).questions if q.kind == qq.NO_FILTER)
        answers = say(b, answers, qf.COVERAGE_YES)  # a fresh coverage yes for B
        self.assertTrue(qf.coverage_confirmed(b, answers))
        result = qf.figures(b, answers, cross_check=check_a)
        self.assertIn("The cross-check was made for another Profit and Loss Detail", " ".join(result.warnings))
        for key in (KITCHEN, PATIO):
            self.assertEqual([qf.ONE_REPORT], [h.reason for h in result.jobs[key]["profit_after_job_costs"].holds])
        self.assertNotIn(qq.NO_FILTER, [q.kind for q in qq.open_questions(b, answers, check_a).questions])
        self.assertEqual(answers, qq.answer(b, answers, stale_question, "yes", cross_check=check_a))
        # With no no-filter answer yet, A's cross-check neither asks A's question for B nor lets it record one.
        fresh = say(b, base(b), qf.COVERAGE_YES)
        self.assertNotIn(qq.NO_FILTER, [q.kind for q in qq.open_questions(b, fresh, check_a).questions])
        self.assertEqual("", qq.answer(b, fresh, stale_question, "yes", cross_check=check_a).unfiltered_pair)
        # B's own cross-check asks B's own no-filter question.
        check_b = qc.cross_check(b, sales_report())
        self.assertEqual([qq.NO_FILTER], [q.kind for q in qq.open_questions(b, answers, check_b).questions])

    def test_not_sure_for_another_workbook_never_withdraws_this_ones_answer(self):
        # The PR #148 manual review, round 2, blocker 1.
        a, b = full_export(), full_export(saved_at="2026-11-17T09:00:00Z")
        answers = say(a, base(a), qf.COVERAGE_YES)
        after_b = say(b, answers, qq.NOT_SURE)  # B's own question, answered "Not sure"
        self.assertEqual(answers.coverage, after_b.coverage)
        self.assertEqual(qf.CONFIRMED, qf.figures(a, after_b).coverage)
        self.assertNotEqual(qf.CONFIRMED, qf.figures(b, after_b).coverage)
        # A's own "Not sure" still withdraws A's answer.
        self.assertIsNone(say(a, answers, qq.NOT_SURE).coverage)

    def test_a_then_b_then_a_on_screen(self):
        def page():
            import sys
            from pathlib import Path
            import streamlit as st
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_results as qresults
            import quickbooks_screens as qscreens
            import test_quickbooks_coverage as t
            report = t.full_export(saved_at=st.session_state.get("saved_at", "2026-10-26T19:04:00Z"))
            answers = qscreens.question_screen(report, key="a-b-a")
            st.session_state["answers"] = answers
            qresults.results_screen(report, answers)

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        save = ScreenTests.save
        save(at, "Yes, each sub-customer is a job")
        for _ in range(2):
            save(at, "Job costs: what's in it is spent on specific jobs")
        save(at, "Yes, I checked")
        self.assertIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])

        at.session_state["saved_at"] = "2026-11-17T09:00:00Z"  # workbook B: the same rows, other bytes
        at.run()
        self.assertEqual(COVERAGE_TITLE, at.subheader[0].value)
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (3)"), review.label)  # A's coverage yes isn't counted
        in_use = review.markdown[:[m.value for m in review.markdown].index(
            "**Earlier answers that don't apply now** (because of a later answer; they count again only if you change "
            "that answer back)")]
        self.assertFalse([m.value for m in in_use if m.value.startswith(COVERAGE_TITLE)])
        self.assertEqual(3, len([b for b in review.button if b.label == "Change"]))  # none for A's coverage answer
        save(at, "Not sure")
        self.assertNotIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])

        at.session_state["saved_at"] = "2026-10-26T19:04:00Z"  # back to workbook A
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertEqual("$3,400.00 · Complete", dict(zip(at.dataframe[0].value["Figure"],
                                                          at.dataframe[0].value["Amount and status"]))[
            "Profit after job costs"])

    def test_replacing_workbooks_on_the_real_upload_page(self):
        # The reviewer's reproduction: the same file names, byte-distinct workbooks, identical rows.
        import tempfile
        import test_quickbooks_upload as up
        folder = Path(tempfile.mkdtemp(dir=up._FOLDERS.name))
        pnl_rows = fx.report_rows({"Income": [("Design income", income())],
                                   "Expenses": [("Job Materials", materials()), ("Labor", labor())]})
        (folder / "pnl.xlsx").write_bytes(fx.xlsx(pnl_rows))
        (folder / "sales.xlsx").write_bytes(fx.xlsx(sales_rows()))
        source = up.PAGE.read_text(encoding="utf-8").replace(
            'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({str(folder)!r})").replace(
            'DEFAULT_SAMPLE_SET = "demo"', 'DEFAULT_SAMPLE_SET = "test"').replace(
            'SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")',
            "SAMPLE_FILES = ('pnl.xlsx', 'sales.xlsx')")
        at = AppTest.from_string(source, default_timeout=60)
        at.run()
        self.assertFalse(at.exception, at.exception)
        for _ in range(6):
            title = up.titles(at)[0]
            if title.startswith("After job costs"):
                break
            radio = up.answer_radio(at)
            label = {"Do you use sub-customers in QuickBooks for jobs?": "Yes, each sub-customer is a job",
                     up.NO_FILTER: "Yes, both have no filter", COVERAGE_TITLE: "Yes, I checked"}.get(title)
            up.save(at, label or next(o for o in radio.options if o.startswith("Job costs")))
        self.assertIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertEqual("$3,400.00 · Complete", up.company(at)["Profit after job costs"])

        # Only the sales workbook replaced: coverage stays, S3's question comes back.
        (folder / "sales.xlsx").write_bytes(fx.xlsx(sales_rows(), saved_at="2026-11-17T09:00:00Z"))
        at.run()
        self.assertEqual(up.NO_FILTER, up.titles(at)[0])
        self.assertIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertEqual("$3,400.00 · Complete", up.company(at)["Profit after job costs"])
        up.save(at, "Yes, both have no filter")

        # The Profit and Loss workbook replaced: both answers about files come back (the pair changed too), and
        # nothing says confirmed.
        (folder / "pnl.xlsx").write_bytes(fx.xlsx(pnl_rows, saved_at="2026-11-17T09:00:00Z"))
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(up.NO_FILTER, up.titles(at)[0])
        self.assertNotIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        up.save(at, "Yes, both have no filter")
        self.assertEqual(COVERAGE_TITLE, up.titles(at)[0])
        self.assertNotIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertEqual("$3,400.00 · Needs a check (missing amount unknown)",
                         up.company(at)["Profit after job costs"])


class ContradictionTests(unittest.TestCase):
    """The PR #148 manual review, blocker 2: when the second report shows sales the Profit and Loss Detail
    doesn't have, the file may leave out more (costs too), so the coverage hold stays on every figure, even
    after a "yes", beside the specific sales reason."""

    def test_sales_missing_from_the_profit_and_loss_detail_keep_every_figure_held_after_yes(self):
        # Filtered to Customer X: Y's $1,200 sale and $800 of materials are gone; the full sales report has them.
        report = pnl({"Income": [("Design income", income(y_too=False))],
                      "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]})
        check = qc.cross_check(report, sales_report())
        self.assertTrue(check.usable, check.reasons)
        self.assertEqual(1, len(check.sbcd_unmatched))
        answers = say(report, base(report, check=check), qf.COVERAGE_YES, check)
        result = qf.figures(report, answers, cross_check=check)
        self.assertEqual(qf.CONTRADICTED, result.coverage)
        costs = result.company["job_costs"]
        self.assertEqual((D("1500"), qp.NEEDS_A_CHECK), (costs.amount, costs.status))  # never $1,500 Complete
        self.assertTrue(coverage_held(result))
        self.assertIn(qf.COVERAGE_CONTRADICTED, [h.reason for h in costs.holds])
        sales_reasons = " ".join(h.reason for h in result.company["sales"].holds)
        self.assertIn("isn't in Profit and Loss Detail, so the two reports don't agree on it", sales_reasons)
        self.assertIn("missing amount unknown", qr.cell(costs))
        self.assertIn("Sales by Customer Detail has sales this file doesn't", qr.headline(report, result))
        # Without a yes the hold is there too, as for any unconfirmed file.
        unconfirmed = qf.figures(report, base(report, check=check), cross_check=check)
        self.assertEqual(qf.NOT_CONFIRMED, unconfirmed.coverage)
        self.assertTrue(coverage_held(unconfirmed))

    def test_removing_the_sales_report_keeps_the_contradiction_for_that_file(self):
        # The PR #148 manual review, round 2, blocker 2, through the real upload page.
        import tempfile
        import test_quickbooks_upload as up
        folder = Path(tempfile.mkdtemp(dir=up._FOLDERS.name))
        filtered = fx.report_rows({"Income": [("Design income", income(y_too=False))],
                                   "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]})
        (folder / "pnl.xlsx").write_bytes(fx.xlsx(filtered))
        (folder / "sales.xlsx").write_bytes(fx.xlsx(sales_rows()))
        at = upload_page(folder, ("pnl.xlsx", "sales.xlsx"))
        answer_everything(at)
        self.assertEqual("$1,500.00 · Needs a check (missing amount unknown)", up.company(at)["Job costs"])
        self.assertIn(qf.COVERAGE_CONTRADICTED, [w.value for w in at.warning])

        (folder / "files.txt").write_text("pnl.xlsx")  # the sales report removed
        at.run()
        self.assertFalse(at.exception, at.exception)
        company = up.company(at)
        self.assertEqual("$1,500.00 · Needs a check (missing amount unknown)", company["Job costs"])
        self.assertEqual("$3,000.00 · Needs a check (missing amount unknown)", company["Profit after job costs"])
        self.assertIn(qf.COVERAGE_CONTRADICTED, [w.value for w in at.warning])
        self.assertNotIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])

        # Another Profit and Loss file (here the full export) starts without that evidence.
        (folder / "pnl.xlsx").write_bytes(fx.xlsx(fx.report_rows({
            "Income": [("Design income", income())],
            "Expenses": [("Job Materials", materials()), ("Labor", labor())]})))
        at.run()
        answer_everything(at)
        self.assertEqual("$3,400.00 · Complete", up.company(at)["Profit after job costs"])

    def test_the_contradiction_is_remembered_even_if_seen_before_the_yes(self):
        report = pnl({"Income": [("Design income", income(y_too=False))],
                      "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]})
        check = qc.cross_check(report, sales_report())
        seen = qf.record_contradiction(report, base(report), check)  # the screen records it while both are uploaded
        self.assertEqual((report.file_digest,), seen.sales_missing_seen)
        later_yes = say(report, seen, qf.COVERAGE_YES)  # the sales report removed, then "yes"
        result = qf.figures(report, later_yes)
        self.assertEqual(qf.CONTRADICTED, result.coverage)
        self.assertTrue(coverage_held(result))
        # It's about that file only: another workbook, even one that reads the same, isn't touched.
        other = pnl({"Income": [("Design income", income(y_too=False))],
                     "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]},
                    saved_at="2026-11-17T09:00:00Z")
        self.assertEqual(qf.CONFIRMED, qf.figures(other, say(other, seen, qf.COVERAGE_YES)).coverage)
        self.assertEqual(seen, qf.record_contradiction(report, seen, qc.cross_check(report, sales_report())))  # once

    def test_a_matching_sales_report_never_contradicts(self):
        report = full_export()
        check = qc.cross_check(report, sales_report())
        result = qf.figures(report, say(report, base(report, check=check), qf.COVERAGE_YES, check), cross_check=check)
        self.assertEqual(qf.CONFIRMED, result.coverage)


class NoSilentYesTests(unittest.TestCase):
    """Row 7: no answer, every other answer, the second report: none of these records a "yes"."""

    def test_answering_everything_else_and_adding_the_second_report_never_records_yes(self):
        report = full_export()
        check = qc.cross_check(report, sales_report())
        answers = None
        for _ in range(20):
            questions = [q for q in qq.open_questions(report, answers, check).questions if q.kind != qq.COVERAGE]
            if not questions:
                break
            question = questions[0]
            choice = {qq.JOBS: "yes", qq.NO_FILTER: "yes", qq.ACCOUNT: qf.JOB_COSTS_ACCOUNT}[question.kind]
            answers = qq.answer(report, answers, question, choice, cross_check=check)
        self.assertIsNone(answers.coverage)
        self.assertEqual(check.pair, answers.unfiltered_pair)
        self.assertEqual([qq.COVERAGE], [q.kind for q in qq.open_questions(report, answers, check).questions])
        self.assertTrue(coverage_held(qf.figures(report, answers, cross_check=check)))
        # Skipping it, or "not sure", leaves it unanswered.
        self.assertIsNone(say(report, answers, qq.NOT_SURE, check).coverage)

    def test_only_the_coverage_question_ever_records_a_coverage_answer(self):
        # A guard on the product code: the only place that builds a CoverageAnswer is quickbooks_questions.answer,
        # for the coverage question. No upload, meeting step or other answer can record one.
        root = Path(__file__).resolve().parents[1]
        builders = sorted(p.name for p in root.glob("*.py") if "CoverageAnswer(" in p.read_text(encoding="utf-8"))
        self.assertEqual(["quickbooks_questions.py"], builders)
        source = (root / "quickbooks_questions.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("CoverageAnswer("))
        answer = source[source.index("\ndef answer("):]
        answer = answer[:answer.index("\ndef ", 1)]
        self.assertIn("qf.CoverageAnswer(choice", answer)  # only inside answer(), under the coverage question
        self.assertIn("if question.kind == COVERAGE:", answer[:answer.index("qf.CoverageAnswer(choice")])


class AccountListTests(unittest.TestCase):
    """Row 8: every cost account with activity is listed with its exact total."""

    def test_overhead_mixed_unanswered_negative_and_zero_net_accounts_are_all_listed_exactly(self):
        report = pnl({
            "Income": [("Design income", income())],
            "Cost of Goods Sold": [("Cost of Goods Sold", [L(4, "Invoice", "1001", f"{X}:Kitchen", D("0.10"), None),
                                                           L(4, "Invoice", "1001", f"{X}:Kitchen", D("0.20"), None)])],
            "Expenses": [("Job Materials", materials()),
                         ("Office Supplies", [L(8, "Expense", "", "Office Depot (fictional)", D("50"), None, "",
                                                "Checking")]),
                         ("Subcontractors", [L(9, "Bill", "B-4", f"{Y}:Patio", D("120"), None)]),
                         ("Tools", [L(10, "Vendor Credit", "VC-1", "Tool Shop (fictional)", D("-25"), None)]),
                         ("Rentals", [L(11, "Bill", "B-5", "Rent-All (fictional)", D("75"), None),
                                      L(12, "Vendor Credit", "VC-2", "Rent-All (fictional)", D("-75"), None)]),
                         ("Uncategorized", [L(13, "Bill", "B-6", "Someone (fictional)", D("10"), None)])]})
        office = ("Expenses", "Office Supplies")
        answers = qf.OwnerAnswers(report=qf.report_fingerprint(report), accounts={
            MATERIALS: qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT),
            office: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, qf.entry_keys(report, office)),
            ("Expenses", "Subcontractors"): qf.AccountAnswer(qf.MIXED_ACCOUNT)})
        accounts = {a.path: a for a in qf.cost_accounts(report)}
        self.assertEqual({("Cost of Goods Sold", "Cost of Goods Sold"): D("0.30"), MATERIALS: D("1400"),
                          office: D("50"), ("Expenses", "Subcontractors"): D("120"), ("Expenses", "Tools"): D("-25"),
                          ("Expenses", "Rentals"): D("0"), ("Expenses", "Uncategorized"): D("10")},
                         {path: a.total for path, a in accounts.items()})
        self.assertTrue(all(isinstance(a.total, D) for a in accounts.values()))
        self.assertEqual("0.30", str(accounts[("Cost of Goods Sold", "Cost of Goods Sold")].total))  # never 0.30000000000000004
        question = coverage_question(report, answers)
        details = list(question.details)
        listed = details[details.index("The cost accounts in this file's Cost of Goods Sold and Expenses sections (7):")
                         + 1:][:7]
        self.assertEqual([
            "Cost of Goods Sold › Cost of Goods Sold (Cost of Goods Sold): 2 entries, $0.30 in all · not answered yet",
            "Expenses › Job Materials (Expenses): 2 entries, $1,400.00 in all · you said: job costs",
            "Expenses › Office Supplies (Expenses): 1 entry, $50.00 in all · you said: overhead",
            "Expenses › Subcontractors (Expenses): 1 entry, $120.00 in all · you said: mixed",
            "Expenses › Tools (Expenses): 1 entry, -$25.00 in all · not answered yet",
            "Expenses › Rentals (Expenses): 2 entries, $0.00 in all · not answered yet",
            "Expenses › Uncategorized (Expenses): 1 entry, $10.00 in all · not answered yet"], listed)
        self.assertNotIn("Design income", " ".join(listed))  # the list is of cost accounts; the words cover income
        self.assertIn("Accounts with no activity in these dates don't appear in the report, and don't need to. Other "
                      "income and other expense accounts aren't listed here, but the words below cover them too.",
                      details)
        self.assertEqual(f"\"{qf.coverage_statement(report)}\"", details[-1])

    def test_an_unreadable_amount_is_said_never_left_out_of_an_account_total(self):
        report = full_export()
        bill = next(l for l in report.lines if l.num == "B-3")
        broken = dataclasses.replace(report, lines=tuple(
            dataclasses.replace(l, amount=None, outcome=qp.NOT_RESOLVED) if l is bill else l for l in report.lines))
        details = " ".join(coverage_question(broken).details)
        self.assertIn("Expenses › Labor (Expenses): 1 entry, $0.00 that MargenX can read, plus 1 with an amount it "
                      "can't read", details)

    def test_the_question_has_the_reviewers_words_three_choices_and_no_default(self):
        report = full_export()
        question = coverage_question(report)
        self.assertEqual(COVERAGE_TITLE, question.title)
        self.assertEqual("I checked the QuickBooks export settings and this account list. This Profit and Loss Detail "
                         "includes the whole business's income and costs recorded in QuickBooks for January 1-October "
                         "26, 2026, on accrual basis, with no filters excluding accounts or transactions. All cost "
                         "accounts with activity in this period are included.", question.statement)
        self.assertEqual([("yes", "Yes, I checked"), ("no", "No, something is missing"), (qq.NOT_SURE, "Not sure")],
                         [(c.value, c.label) for c in question.choices])
        empty = pnl({"Income": [("Design income", income())]})
        self.assertIn("This file has no cost accounts with activity in its Cost of Goods Sold and Expenses sections.",
                      coverage_question(empty).details)


class DisplayTests(unittest.TestCase):
    """Row 9: the unknown omitted amount is said, never made up, never $0; known held amounts stay."""

    def test_missing_amount_unknown_is_shown_never_900_never_zero(self):
        office = ("Office Supplies", [L(8, "Expense", "", "Office Depot (fictional)", D("50"), None, "", "Checking")])
        report = pnl({"Income": [("Design income", income())], "Expenses": [("Job Materials", materials()), office]})
        result = qf.figures(report, base(report, accounts={MATERIALS: qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)}))
        company = {row["Figure"]: row["Amount and status"] for row in qr.company_rows(result)}
        self.assertEqual("$5,700.00 · Needs a check (missing amount unknown)", company["Sales"])
        self.assertEqual("$4,300.00 · Needs a check ($50.00 held; missing amount unknown)",
                         company["Profit after job costs"])
        customers = qr.group_rows(result.customers, "Customer")
        # The $50 office expense (account not answered yet) could be anyone's, so it holds every customer too.
        self.assertEqual("$3,900.00 · Needs a check ($50.00 held; missing amount unknown)",
                         next(r for r in customers if r["Customer"] == X)["Profit after job costs"])
        shown = " ".join([qr.headline(report, result), *company.values(), *qr.missing(result),
                          *(v for r in customers for v in r.values())])
        self.assertNotIn("$900", shown)
        self.assertNotIn("$0.00 held", shown)
        self.assertIn("missing amount unknown", qr.headline(report, result))
        self.assertEqual(D("50"), result.company["profit_after_job_costs"].held_amount)  # the coverage hold adds nothing

    def test_derived_figures_keep_the_hold_and_their_arithmetic(self):
        report = full_export()
        held = qf.figures(report, base(report))
        confirmed = qf.figures(report, say(report, base(report), qf.COVERAGE_YES))
        for key in ("sales", "job_costs", "profit_after_job_costs", "overhead", "other", "after_overhead"):
            with self.subTest(key):
                self.assertTrue(held.company[key].coverage_open)
                self.assertEqual(confirmed.company[key].amount, held.company[key].amount)
        self.assertEqual(held.company["sales"].amount - held.company["job_costs"].amount,
                         held.company["profit_after_job_costs"].amount)


class NoFileTests(unittest.TestCase):
    """The PR #148 manual review, round 2, warning: a report not read from an uploaded file has no file fingerprint,
    so no confirmation, and no cross-check, can be tied to it."""

    def test_a_report_without_a_file_fingerprint_is_never_confirmed(self):
        report = dataclasses.replace(full_export(), file_digest="")
        question = coverage_question(report, base(report))
        self.assertEqual(base(report), qq.answer(report, base(report), question, qf.COVERAGE_YES))
        forced = dataclasses.replace(base(report), coverage=qf.CoverageAnswer(
            qf.COVERAGE_YES, qf.coverage_statement(report), qf.report_fingerprint(report), ""))
        self.assertFalse(qf.coverage_confirmed(report, forced))
        result = qf.figures(report, forced)
        self.assertTrue(coverage_held(result))
        self.assertIn("can't tell which uploaded file", " ".join(result.warnings))

    def test_a_cross_check_with_a_sales_report_without_a_file_fingerprint_is_never_used(self):
        # The automated review of f3861fd: the no-filter answer is bound to both uploaded workbooks.
        report = full_export()
        sales = dataclasses.replace(sales_report(), file_digest="")
        check = qc.cross_check(report, sales)
        self.assertTrue(check.usable, check.reasons)
        self.assertNotIn(qq.NO_FILTER, [q.kind for q in qq.open_questions(report, base(report), check).questions])
        answers = say(report, dataclasses.replace(base(report), unfiltered_pair=check.pair), qf.COVERAGE_YES)
        result = qf.figures(report, answers, cross_check=check)
        self.assertEqual([qf.ONE_REPORT], [h.reason for h in result.jobs[KITCHEN]["profit_after_job_costs"].holds])

    def test_a_cross_check_for_a_report_without_a_file_fingerprint_is_never_used(self):
        report = dataclasses.replace(full_export(), file_digest="")
        check = qc.cross_check(report, sales_report())
        self.assertEqual("", check.pnl_file)
        result = qf.figures(report, base(report, check=check), cross_check=check)
        self.assertIn("The cross-check was made for another Profit and Loss Detail", " ".join(result.warnings))
        self.assertNotIn(qq.NO_FILTER, [q.kind for q in qq.open_questions(report, base(report), check).questions])

    def test_a_sales_report_without_a_file_fingerprint_never_creates_a_remembered_contradiction(self):
        # The PR #148 manual review, round 3, follow-up: the figures refused such a cross-check, but its missing sales
        # could still be remembered as a contradiction. Now neither uses it.
        report = pnl({"Income": [("Design income", income(y_too=False))],
                      "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]})
        check = qc.cross_check(report, dataclasses.replace(sales_report(), file_digest=""))
        self.assertTrue(check.usable and check.sbcd_unmatched, check.reasons)
        self.assertFalse(qf.contradicts(report, check))
        self.assertEqual(base(report), qf.record_contradiction(report, base(report), check))
        result = qf.figures(report, say(report, base(report), qf.COVERAGE_YES), cross_check=check)
        self.assertIn("The cross-check was made for another Profit and Loss Detail", " ".join(result.warnings))
        self.assertEqual(qf.CONFIRMED, result.coverage)  # the cross-check isn't used at all; jobs keep S3
        self.assertIn(qf.ONE_REPORT, [h.reason for h in result.jobs[KITCHEN]["profit_after_job_costs"].holds])

    def test_the_figures_the_questions_and_the_contradiction_use_the_same_cross_checks(self):
        # One rule (qf.made_for) decides whether a cross-check belongs to this upload, wherever it's used.
        def filtered(saved_at=fx.SAVED_AT):
            return pnl({"Income": [("Design income", income(y_too=False))],
                        "Expenses": [("Job Materials", materials(y_too=False)), ("Labor", labor())]},
                       saved_at=saved_at)
        report = filtered()
        cases = {
            "this upload": (report, qc.cross_check(report, sales_report())),
            "another workbook that reads the same": (report, qc.cross_check(filtered("2026-11-17T09:00:00Z"),
                                                                            sales_report())),
            "another report": (report, qc.cross_check(
                pnl({"Income": [("Design income", income(y_too=False))],
                     "Expenses": [("Job Materials", materials(y_too=False))]}), sales_report())),
            "no sales file fingerprint": (report, qc.cross_check(report, dataclasses.replace(sales_report(),
                                                                                             file_digest=""))),
            # The PR #149 review warning: the same uploaded workbook (same file fingerprint) with other content, so
            # only the content fingerprint tells them apart.
            "another report's content, this upload's file fingerprint": (report, dataclasses.replace(
                qc.cross_check(pnl({"Income": [("Design income", income(y_too=False))],
                                    "Expenses": [("Job Materials", materials(y_too=False))]}), sales_report()),
                pnl_file=report.file_digest)),
            "no Profit and Loss file fingerprint": (dataclasses.replace(report, file_digest=""),
                                                    qc.cross_check(dataclasses.replace(report, file_digest=""),
                                                                   sales_report())),
        }
        for name, (pnl_report, check) in cases.items():
            with self.subTest(name):
                self.assertTrue(check.usable and check.sbcd_unmatched, check.reasons)
                result = qf.figures(pnl_report, say(pnl_report, base(pnl_report), qf.COVERAGE_YES),
                                    cross_check=check)
                used_by_figures = "The cross-check was made for another" not in " ".join(result.warnings)
                # Not only the warning: what the figures do with it. A used one contradicts the yes (its sales are
                # missing from the report); a refused one leaves the yes as it was.
                expected = qf.CONTRADICTED if used_by_figures else (
                    qf.CONFIRMED if pnl_report.file_digest else qf.NOT_CONFIRMED)
                self.assertEqual(expected, result.coverage)
                used_by_questions = qq._cross_check_for(pnl_report, check)
                contradiction = qf.contradicts(pnl_report, check)
                self.assertEqual(name == "this upload", used_by_figures)
                self.assertEqual(used_by_figures, used_by_questions)
                self.assertEqual(used_by_figures, contradiction)


class LimitationTests(unittest.TestCase):
    """The limitation the owner accepted on 2026-11-17: MargenX can't detect an account filtered out of the file.
    If the owner wrongly confirms coverage of an incomplete export, its figures can be Complete. This test shows
    that limitation; it proves nothing about detecting a missing account."""

    def test_an_undetectably_incomplete_file_with_a_wrong_yes_can_be_complete(self):
        report = missing_labor()
        result = qf.figures(report, say(report, base(report), qf.COVERAGE_YES))
        self.assertEqual((D("4300"), qp.COMPLETE), (result.company["profit_after_job_costs"].amount,
                                                    result.company["profit_after_job_costs"].status))
        self.assertEqual((D("3900"), qp.COMPLETE), (result.customers[X]["profit_after_job_costs"].amount,
                                                    result.customers[X]["profit_after_job_costs"].status))
        # What the owner sees says the figures rely on that confirmation.
        self.assertIn("beyond your confirmation that it includes the whole business's income and costs", result.scope)
        self.assertIn("it does not guarantee that nothing was omitted", qf.RELIANCE)

    def test_the_screen_never_says_nothing_is_missing(self):
        # The PR #148 manual review, blocker 3: the missing-Labor file, matching sales and a mistaken yes. Every
        # figure is Complete under the accepted rule, and the screen says what that means, never "nothing is missing".
        def page():
            import sys
            from pathlib import Path
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_crosscheck as qc
            import quickbooks_figures as qf
            import quickbooks_results as qresults
            import test_quickbooks_coverage as t
            report = t.missing_labor()
            check = qc.cross_check(report, t.sales_report())
            qresults.results_screen(report, t.say(report, t.base(report, check=check), qf.COVERAGE_YES, check), check)

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        texts = [e.value.replace("\\$", "$") for e in (*at.markdown, *at.subheader, *at.caption, *at.success, *at.info)]
        self.assertIn(qr.CHECKS_DONE, [s.value for s in at.success])
        self.assertIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertIn(qf.RELIANCE, texts)
        self.assertFalse([t for t in texts if "othing is missing" in t], texts)
        self.assertIn("$4,300.00 · Complete", list(at.dataframe[0].value["Amount and status"]))


class ScreenTests(unittest.TestCase):
    """The question and the results on screen (AppTest), with the made-up missing-Labor and full files."""

    @staticmethod
    def page():
        import sys
        from pathlib import Path
        import streamlit as st
        for folder in (Path.cwd(), Path.cwd() / "tests"):
            sys.path.insert(0, str(folder))
        import quickbooks_results as qresults
        import quickbooks_screens as qscreens
        import test_quickbooks_coverage as t
        report = t.full_export()
        answers = qscreens.question_screen(report, key="coverage-test")
        st.session_state["answers"] = answers
        qresults.results_screen(report, answers)

    def start(self):
        at = AppTest.from_function(self.page, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    @staticmethod
    def save(at, label):
        radio = next(r for r in at.radio if r.label == "Your answer")
        radio.set_value(label).run()
        next(b for b in at.button if b.label == "Save answer").click().run()
        assert not at.exception, at.exception

    @staticmethod
    def texts(at):
        return [e.value.replace("\\$", "$") for e in (*at.markdown, *at.subheader, *at.caption, *at.info, *at.warning,
                                                      *at.success)]

    def reach_coverage(self, at):
        self.save(at, "Yes, each sub-customer is a job")
        for _ in range(2):
            self.save(at, "Job costs: what's in it is spent on specific jobs")
        self.assertEqual(COVERAGE_TITLE, at.subheader[0].value)

    def test_the_question_shows_the_list_and_the_words_with_nothing_chosen(self):
        at = self.start()
        self.reach_coverage(at)
        radio = next(r for r in at.radio if r.label == "Your answer")
        self.assertIsNone(radio.value)
        self.assertEqual(["Yes, I checked", "No, something is missing", "Not sure"], radio.options)
        texts = self.texts(at)
        self.assertIn("Expenses › Labor (Expenses): 1 entry, $900.00 in all · you said: job costs", texts)
        self.assertTrue(any(t.startswith("\"I checked the QuickBooks export settings") for t in texts))
        self.assertIn(qf.COVERAGE_NOT_YET, texts)
        self.assertIn(qf.RELIANCE, texts)
        self.assertIsNone(at.session_state["answers"].coverage)

    def test_yes_shows_the_confirmation_and_changing_it_to_no_holds_again(self):
        at = self.start()
        self.reach_coverage(at)
        self.save(at, "Yes, I checked")
        self.assertIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertEqual(qf.COVERAGE_YES, at.session_state["answers"].coverage.choice)
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        change = [b for b in review.button if b.label == "Change"][-1]  # the coverage answer, the latest
        change.click().run()
        self.assertIn("**Changing an earlier answer.** You said: Yes, I checked", self.texts(at))
        self.save(at, "No, something is missing")
        self.assertEqual(qf.COVERAGE_NO, at.session_state["answers"].coverage.choice)
        self.assertNotIn(qf.COVERAGE_CONFIRMED, [s.value for s in at.success])
        self.assertIn(qf.COVERAGE_SAID_MISSING, [w.value for w in at.warning])

    def test_not_sure_leaves_it_open_and_on_needs_a_check(self):
        at = self.start()
        self.reach_coverage(at)
        self.save(at, "Not sure")
        self.assertIsNone(at.session_state["answers"].coverage)
        self.assertIn(qf.COVERAGE_NOT_YET, [i.value for i in at.info])
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertIn(f"{COVERAGE_TITLE} (skipped)", [m.value for m in review.markdown])


if __name__ == "__main__":
    unittest.main()
