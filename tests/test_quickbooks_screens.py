"""Issue #128, step 6b: the owner's questions on screen (plan v7, step 6).

Driven through Streamlit's AppTest on a made-up report (tests/qbo_question_screen_app.py): one question at a
time with its progress, the original row and amount, nothing pre-selected, skip, "Not sure yet", go back,
change an answer, what's left, the held money with its amount, and "no questions left" never read as final.
"""
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


def title(at):
    return [s.value for s in at.subheader]


def text(at):
    return " | ".join(m.value for m in at.markdown)


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
        self.assertIn("($50.00)", " ".join(m.value for m in held.markdown))

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
        self.assertIn(f"{JOBS} (skipped)", [m.value for m in review.markdown])

    def test_change_from_the_review_list(self):
        at = save(start(), "Yes, each sub-customer is a job")
        save(at, "Job costs: what's in it is spent on specific jobs")
        button(at, "Change").click().run()  # the first answer in the list
        self.assertIn("You said: Yes, each sub-customer is a job", text(at))

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

    def test_the_upload_page_still_refuses_quickbooks_reports(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import job_intake as ji
        import quickbooks_fixtures as fx
        with self.assertRaises(ji.IntakeError):
            ji.read_file("report.xlsx", fx.xlsx(fx.pnl_rows(), formulas=fx.FORMULAS, stored=fx.STORED))

    def test_no_page_of_the_app_uses_the_screen_yet(self):
        root = Path(__file__).resolve().parents[1]
        pages = [root / "app.py", root / "trial_app.py", root / "marginx_pilot.py", *(root / "pages").glob("*.py")]
        self.assertEqual([], [p.name for p in pages if "quickbooks_screens" in p.read_text()])


if __name__ == "__main__":
    unittest.main()
