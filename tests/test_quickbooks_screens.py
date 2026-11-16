"""Issue #128, step 6b: the owner's questions on screen (plan v7, step 6).

Driven through Streamlit's AppTest on a made-up report (tests/qbo_question_screen_app.py): one question at a
time with its progress, the original row and amount, nothing pre-selected, skip, "Not sure yet", go back,
change an answer, what's left, the held money with its amount, and "no questions left" never read as final.
"""
import re
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parent / "qbo_question_screen_app.py")
JOBS = "Do you use sub-customers in QuickBooks for jobs?"
MATERIALS = 'How do you usually use the account "Job Materials"?'


def start():
    at = AppTest.from_file(PAGE, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def shown(value):
    """What the owner reads: Streamlit shows "\\$" as "$" (a bare "$" would start a math formula)."""
    return value.replace("\\$", "$")


def title(at):
    return [shown(s.value) for s in at.subheader]


def text(at):
    return " | ".join(shown(m.value) for m in at.markdown)


def bare_dollars(at):
    """Every element Streamlit reads as Markdown that has an unescaped "$" (it would show garbled)."""
    elements = [*at.markdown, *at.subheader, *at.caption, *at.info, *at.warning, *at.error, *at.success]
    labels = [o for r in at.radio for o in r.options]
    return [v for v in [e.value for e in elements] + labels if re.search(r"(?<!\\)\$", v)]


def button(at, label):
    return next(b for b in at.button if b.label == label)


def save(at, label):
    """Pick the option shown with this label and save it. (AppTest sends the label shown, as a browser does.)"""
    radio = at.radio[0]
    assert label in radio.options, (label, radio.options)
    radio.set_value(label).run()
    button(at, "Save answer").click().run()
    assert not at.exception, at.exception
    return at


def answers(at):
    return at.session_state["qbo-test-answers"]


class QuestionScreenTests(unittest.TestCase):
    def test_one_question_at_a_time_with_progress_and_nothing_pre_selected(self):
        at = start()
        self.assertEqual([JOBS], title(at))
        self.assertIn("**Question 1 of 4**", text(at))
        self.assertEqual(1, len(at.radio))
        self.assertIsNone(at.radio[0].value)  # no default answer
        self.assertTrue(button(at, "Save answer").disabled)
        self.assertIn('Not sure yet: leave it on "Needs a check"', at.radio[0].options)
        self.assertNotIn("Back", [b.label for b in at.button])  # nothing answered yet

    def test_held_money_is_shown_with_its_amount(self):
        at = start()
        held = next(e for e in at.expander if e.label.startswith("Money MargenX holds without asking"))
        self.assertIn("($50.00)", " ".join(shown(m.value) for m in held.markdown))

    def test_saving_moves_on_and_counts_what_is_answered(self):
        at = save(start(), "Yes, each sub-customer is a job")
        self.assertIs(True, answers(at).sub_customers_are_jobs)
        self.assertEqual([MATERIALS], title(at))
        self.assertIn("**Question 2 of", text(at))
        self.assertIn("Saved.", [i.value for i in at.info])
        self.assertIsNone(at.radio[0].value)  # the next question starts with nothing chosen

    def test_a_line_question_shows_its_row_and_amount(self):
        at = save(start(), "Yes, each sub-customer is a job")
        self.assertRegex(text(at), r"Row \d+ · 10/05/2026 · Bill B-1 · Customer X \(fictional\):Job A · \$1,000\.00")

    def test_skip_then_come_back_to_skipped_questions(self):
        at = start()
        for _ in range(4):
            button(at, "Skip for now").click().run()
        self.assertEqual([], title(at))
        self.assertIn('You skipped 4 questions. They stay on "Needs a check" until you answer them.',
                      [i.value for i in at.info])
        self.assertIsNone(answers(at).sub_customers_are_jobs)
        button(at, "Go through the skipped questions").click().run()
        self.assertEqual([JOBS], title(at))

    def test_back_and_change_an_earlier_answer(self):
        at = save(start(), "Yes, each sub-customer is a job")
        button(at, "Back").click().run()
        self.assertIn("**Changing an earlier answer.** You said: Yes, each sub-customer is a job", text(at))
        self.assertIsNone(at.radio[0].value)
        save(at, "No, show profit by customer")
        self.assertIs(False, answers(at).sub_customers_are_jobs)

    def test_saving_the_same_answer_again_says_it_is_unchanged(self):
        # The automated reviews of 1a4bc4a and d2bb8b5: with the clock frozen the answers are identical; that's
        # "unchanged", never "changed since".
        from unittest import mock
        with mock.patch("quickbooks_screens._now", return_value="2026-11-15T00:00:00+00:00"):
            at = save(start(), "Yes, each sub-customer is a job")
            before = answers(at)
            button(at, "Back").click().run()
            save(at, "Yes, each sub-customer is a job")
        infos = [i.value for i in at.info]
        self.assertIn("Your answer is unchanged.", infos)
        self.assertNotIn("changed since", " ".join(infos))
        self.assertEqual(before.sub_customers_are_jobs, answers(at).sub_customers_are_jobs)
        self.assertEqual([MATERIALS], title(at))

    def test_keep_my_answer_changes_nothing(self):
        at = save(start(), "Yes, each sub-customer is a job")
        before = answers(at)
        button(at, "Back").click().run()
        button(at, "Keep my answer").click().run()
        self.assertEqual(before, answers(at))
        self.assertEqual([MATERIALS], title(at))

    def test_not_sure_on_an_earlier_answer_clears_it(self):
        at = save(start(), "Yes, each sub-customer is a job")
        button(at, "Back").click().run()
        save(at, 'Not sure yet: leave it on "Needs a check"')
        self.assertIsNone(answers(at).sub_customers_are_jobs)
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertIn(f"{JOBS} (skipped)", [shown(m.value) for m in review.markdown])

    def test_change_from_the_review_list(self):
        at = save(start(), "Yes, each sub-customer is a job")
        save(at, "Job costs: what's in it is spent on specific jobs")
        button(at, "Change").click().run()  # the first answer in the list
        self.assertIn("You said: Yes, each sub-customer is a job", text(at))

    def test_answers_a_later_answer_makes_not_apply_are_shown_apart_and_not_counted(self):
        # The automated review of a2a7063: the $700 sale is given Job A, then sub-customers are no longer jobs.
        at = save(start(), "Yes, each sub-customer is a job")
        while "Which job is this $700.00 for?" not in title(at):
            button(at, "Skip for now").click().run()
        save(at, at.radio[0].options[0])  # Job A
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (2)"), review.label)
        button(at, "Change").click().run()  # the job-use answer, first in the list
        save(at, "No, show profit by customer")
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (1)"), review.label)
        listed = [shown(m.value) for m in review.markdown]
        self.assertIn("Which job is this $700.00 for? → Job \"Job A\"", listed[listed.index(next(
            m for m in listed if m.startswith("**Earlier answers that don't apply now**"))) + 1:])
        self.assertEqual(1, len([b for b in at.button if b.label == "Change"]))  # only the answer in use
        self.assertIn("of 4**", text(at))  # 1 answer in use + 3 open; the answer apart isn't counted (it would be 5)

    def test_an_outside_job_needs_its_name(self):
        at = save(start(), "Yes, each sub-customer is a job")
        save(at, "Job costs: what's in it is spent on specific jobs")
        save(at, "Overhead: what's in it is a cost of running the business (I've checked every entry below)")
        while "Which job is this $700.00 for?" not in title(at):
            button(at, "Skip for now").click().run()
        before = answers(at)
        save(at, "A job that isn't in this report (I'll name it)")
        self.assertEqual(before, answers(at))
        self.assertIn("Please type the job's name, or pick another answer.", [i.value for i in at.info])
        # The choice stays, so only the name is needed (the automated review of ebeb09a).
        self.assertEqual("A job that isn't in this report (I'll name it)", at.radio[0].options[at.radio[0].index])
        at.text_input[0].set_value("Job Z").run()
        button(at, "Save answer").click().run()
        self.assertIn("Job Z", [a.outside_job for a in answers(at).lines.values()])
        # The name is what the review list and the change screen show (the automated review of a2a7063).
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        mine = 'Which job is this $700.00 for? → A job that isn\'t in this report: "Job Z"'
        self.assertIn(mine, [shown(m.value) for m in review.markdown])
        list(b for b in at.button if b.label == "Change")[-1].click().run()
        self.assertIn('You said: A job that isn\'t in this report: "Job Z"', text(at))

    def test_no_dollar_sign_is_ever_read_as_a_formula(self):
        # Found in the browser in step 7: Streamlit reads the text between two "$" as math. Walk the whole screen.
        at = start()
        for _ in range(12):
            self.assertEqual([], bare_dollars(at))
            for expander in at.expander:
                self.assertEqual([], [m.value for m in expander.markdown if re.search(r"(?<!\\)\$", m.value)])
            if not at.radio:
                break
            save(at, at.radio[0].options[0])

    def test_the_end_says_no_questions_left_is_not_final(self):
        at = start()
        for _ in range(12):
            if not at.radio:
                break
            save(at, at.radio[0].options[0])
        self.assertEqual([], [r for r in at.radio])
        self.assertIn("No questions left.", [s.value for s in at.success])
        self.assertIn("doesn't mean every figure is final", " ".join(c.value for c in at.caption))
        # The held deposit is still shown with its amount.
        self.assertTrue(any(e.label.startswith("Money MargenX holds without asking") for e in at.expander))


class SafetyTests(unittest.TestCase):
    def test_text_from_the_report_is_never_read_as_markdown(self):
        def page():
            import sys
            from decimal import Decimal as D
            from pathlib import Path
            here = Path(sys.argv[0] if sys.argv and sys.argv[0] else ".").resolve().parent
            for folder in (here, here / "tests", Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_fixtures as fx
            import quickbooks_pnl as qp
            import quickbooks_screens as qscreens
            name = "![x](https://example.invalid/x.png) (fictional)"
            data = fx.xlsx(fx.report_rows({"Income": [("Design income", [
                fx.line(2, "Invoice", "1001", f"{name}:Job A", D("4000"), None),
                fx.line(3, "Invoice", "1002", name, D("700"), None)])]}))
            qscreens.question_screen(qp.read_profit_and_loss_detail("p.xlsx", data))

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        shown = text(at)
        self.assertIn(r"\!\[x\](https://example.invalid/x.png)", shown)
        self.assertNotIn("](https://example.invalid/x.png)", shown.replace(r"\]", ""))

    def test_another_report_never_inherits_an_unsaved_choice(self):
        # The automated review of ebeb09a: a choice is made but not saved, then the report is replaced.
        def page():
            import sys
            from decimal import Decimal as D
            from pathlib import Path
            import streamlit as st
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_fixtures as fx
            import quickbooks_pnl as qp
            import quickbooks_screens as qscreens
            amount = D("4000") if st.session_state.get("which", "a") == "a" else D("4100")
            data = fx.xlsx(fx.report_rows({"Income": [("Design income", [
                fx.line(2, "Invoice", "1001", "Customer X (fictional):Job A", amount, None),
                fx.line(3, "Invoice", "1002", "Customer X (fictional)", D("700"), None)])]}))
            qscreens.question_screen(qp.read_profit_and_loss_detail("p.xlsx", data))

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        at.radio[0].set_value("Yes, each sub-customer is a job").run()
        self.assertFalse(button(at, "Save answer").disabled)
        at.session_state["which"] = "b"
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual([JOBS], title(at))
        self.assertIsNone(at.radio[0].value)
        self.assertTrue(button(at, "Save answer").disabled)

    def test_two_screens_on_one_page_never_share_widgets(self):
        def page():
            import sys
            from decimal import Decimal as D
            from pathlib import Path
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_fixtures as fx
            import quickbooks_pnl as qp
            import quickbooks_screens as qscreens
            data = fx.xlsx(fx.report_rows({"Income": [("Design income", [
                fx.line(2, "Invoice", "1001", "Customer X (fictional):Job A", D("4000"), None)])]}))
            report = qp.read_profit_and_loss_detail("p.xlsx", data)
            qscreens.question_screen(report, key="one")
            qscreens.question_screen(report, key="two")

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(2, len(at.radio))
        at.radio[0].set_value("Yes, each sub-customer is a job").run()
        self.assertIsNone(at.radio[1].value)

    def test_a_question_that_no_longer_fits_saves_nothing_and_says_so(self):
        # The automated review of a2a7063 (warning): 6a refuses a stale question; the screen says nothing was saved.
        def page():
            import sys
            from decimal import Decimal as D
            from pathlib import Path
            import streamlit as st
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_figures as qf
            import quickbooks_fixtures as fx
            import quickbooks_pnl as qp
            import quickbooks_screens as qscreens
            data = fx.xlsx(fx.report_rows({
                "Income": [("Design income", [fx.line(2, "Invoice", "1001", "Customer X (fictional):Job A", D("4000"),
                                                      None)])],
                "Expenses": [("Job Materials", [fx.line(5, "Journal Entry", "JE-1", "Vendor (fictional)", D("10"),
                                                        None)])]}))
            report = qp.read_profit_and_loss_detail("p.xlsx", data)
            st.session_state["screen"] = f"qbo-{qf.report_fingerprint(report)}"
            st.session_state["answers"] = qscreens.question_screen(report)

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        save(at, "Yes, each sub-customer is a job")
        save(at, "A cost of a job")
        job_question = title(at)[0]
        self.assertIn("Which job", job_question)
        save(at, at.radio[0].options[0])  # Job A
        state = at.session_state[at.session_state["screen"]]
        old_job = next(e for e in state.history if e.question.key.startswith("job:"))
        # The line is answered as overhead since: the job answer is replaced, so it leaves the list...
        state.changing = next(i for i, e in enumerate(state.history) if e.question.key.startswith("line:"))
        at.run()
        save(at, "Overhead (a cost of running the business, not of one job)")
        state = at.session_state[at.session_state["screen"]]
        self.assertFalse(any(e.question.key.startswith("job:") for e in state.history))
        before = at.session_state["answers"]
        # ...and if the old job question is answered anyway (another tab, say), nothing is saved and the screen says so.
        state.history.append(old_job)
        state.changing = len(state.history) - 1
        at.run()
        save(at, at.radio[0].options[0])
        self.assertEqual(before, at.session_state["answers"])
        self.assertIn("That question has changed since, so nothing was saved. The questions shown now are the current "
                      "ones.", [i.value for i in at.info])

    @staticmethod
    def two_reports():
        """A page with a Profit and Loss report and a Sales by Customer Detail; session_state["product"] picks
        which second report, so only the second report can be swapped."""
        def page():
            import sys
            from decimal import Decimal as D
            from pathlib import Path
            import streamlit as st
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_crosscheck as qc
            import quickbooks_fixtures as fx
            import quickbooks_pnl as qp
            import quickbooks_sbcd as qs
            import quickbooks_screens as qscreens
            x = "Customer X (fictional)"
            report = qp.read_profit_and_loss_detail("p.xlsx", fx.xlsx(fx.report_rows({"Income": [("Design income", [
                fx.line(2, "Invoice", "1001", f"{x}:Job A", D("4000"), None)])]})))
            product = st.session_state.get("product", "Design")
            sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
                [(x, [], [("Job A", [fx.sale(2, "Invoice", "1001", product, 1, 4000)])])])))
            check = qc.cross_check(report, sales)
            st.session_state["pair"] = check.pair
            st.session_state["answers"] = qscreens.question_screen(report, check)

        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        save(at, "Yes, each sub-customer is a job")
        assert title(at) == ["Did you export both reports for the whole business, with no filter?"], title(at)
        return at

    def swap_second_report(self, at):
        first_pair = at.session_state["pair"]
        at.session_state["product"] = "Design work"
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertNotEqual(first_pair, at.session_state["pair"])

    def test_an_unsaved_no_filter_yes_never_carries_to_another_pair(self):
        # The PR #143 manual review, blocker: "Yes" picked for pair A, not saved; only the second report is replaced.
        at = self.two_reports()
        at.radio[0].set_value("Yes, both have no filter").run()
        self.assertFalse(button(at, "Save answer").disabled)
        self.swap_second_report(at)
        self.assertEqual(["Did you export both reports for the whole business, with no filter?"], title(at))
        self.assertIsNone(at.radio[0].value)
        self.assertTrue(button(at, "Save answer").disabled)
        self.assertEqual("", at.session_state["answers"].unfiltered_pair)

    def test_skipping_one_pair_never_skips_another(self):
        at = self.two_reports()
        button(at, "Skip for now").click().run()
        self.assertEqual([], title(at))
        self.swap_second_report(at)
        self.assertEqual(["Did you export both reports for the whole business, with no filter?"], title(at))

    def test_a_confirmation_counts_only_for_the_pair_in_use(self):
        at = self.two_reports()
        save(at, "Yes, both have no filter")
        self.assertEqual(at.session_state["pair"], at.session_state["answers"].unfiltered_pair)
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (2)"), review.label)
        self.swap_second_report(at)
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (1)"), review.label)
        self.assertEqual(["Did you export both reports for the whole business, with no filter?"], title(at))

    def swap_back(self, at):
        at.session_state["product"] = "Design"
        at.run()
        self.assertFalse(at.exception, at.exception)

    def test_changing_a_no_filter_answer_is_dropped_when_its_pair_is_replaced(self):
        # The automated review of 8763ef2, carried from PR #143: save pair A's "no filter", click Change, pick an
        # unsaved answer, then replace only the second report. The old pair's question must not stay on screen.
        at = self.two_reports()
        save(at, "Yes, both have no filter")
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        changes = [b for b in review.button if b.label == "Change"]
        self.assertEqual(2, len(changes))
        changes[1].click().run()
        self.assertIn("**Changing an earlier answer.**", text(at))
        at.radio[0].set_value("Not sure yet: leave it on \"Needs a check\"").run()
        self.swap_second_report(at)
        self.assertNotIn("Changing an earlier answer", text(at))
        self.assertEqual(["Did you export both reports for the whole business, with no filter?"], title(at))
        self.assertIn("**Question 2 of 2**", text(at))
        self.assertIsNone(at.radio[0].value)
        self.assertTrue(button(at, "Save answer").disabled)
        self.assertNotIn("Keep my answer", [b.label for b in at.button])
        self.assertIn("The reports changed while you were changing an answer, so that change was dropped. The "
                      "questions shown now are about the files you uploaded.", [i.value for i in at.info])
        self.assertNotIn("Your answer is unchanged.", [i.value for i in at.info])
        # Pair A's own confirmation is untouched, and counts again once pair A is back.
        self.assertNotEqual(at.session_state["pair"], at.session_state["answers"].unfiltered_pair)
        self.swap_back(at)
        self.assertEqual(at.session_state["pair"], at.session_state["answers"].unfiltered_pair)
        self.assertEqual([], title(at))

    def test_going_through_skipped_questions_reopens_only_the_ones_open_now(self):
        # The PR #143 manual review, warning: skip pair A's question, then pair B's; "Go through the skipped
        # questions" for pair B must leave pair A's skipped.
        at = self.two_reports()
        button(at, "Skip for now").click().run()
        self.swap_second_report(at)
        button(at, "Skip for now").click().run()
        self.assertEqual([], title(at))
        button(at, "Go through the skipped questions").click().run()
        self.assertEqual(["Did you export both reports for the whole business, with no filter?"], title(at))
        self.swap_back(at)
        self.assertEqual([], title(at))
        self.assertIn("You skipped 1 question.", " ".join(i.value for i in at.info))

    def test_the_plain_list_reader_still_refuses_quickbooks_reports(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import job_intake as ji
        import quickbooks_fixtures as fx
        with self.assertRaises(ji.IntakeError):
            ji.read_file("report.xlsx", fx.xlsx(fx.pnl_rows(), formulas=fx.FORMULAS, stored=fx.STORED))

    def test_the_upload_page_shows_the_screen_only_through_the_quickbooks_flow(self):
        root = Path(__file__).resolve().parents[1]
        pages = [root / "app.py", root / "trial_app.py", root / "marginx_pilot.py", *(root / "pages").glob("*.py")]
        self.assertEqual([], [p.name for p in pages if "quickbooks_screens" in p.read_text()])
        self.assertIn("qscreens.question_screen(report, check", (root / "quickbooks_upload.py").read_text())
        self.assertIn("import quickbooks_upload", (root / "pages" / "1_MargenX_Import.py").read_text())


if __name__ == "__main__":
    unittest.main()
