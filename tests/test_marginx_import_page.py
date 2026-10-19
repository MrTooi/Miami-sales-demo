from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_MarginX_Import.py")
INVOICE_DATE_QUESTION = "In fictional_invoices.csv, what date is 10/01/2026?"


def page_text(at):
    # Report lines are rendered as plain text (st.text).
    return " | ".join(t.value for t in at.text)


def radio(at, label):
    return next(r for r in at.radio if r.label == label)


def run_source(source):
    at = AppTest.from_string(source, default_timeout=30)
    at.run()
    return at


class MarginXImportPageTests(unittest.TestCase):
    def run_page(self):
        at = AppTest.from_file(PAGE, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_pilot_warning_is_always_shown(self):
        self.assertIn("made-up data only", self.run_page().warning[0].value)

    def test_costs_sample_needs_no_input_at_all(self):
        at = self.run_page()
        text = page_text(at)
        self.assertIn("3 of 8 imported costs aren't linked to a job", text)
        self.assertIn("No labor costs were found", text)
        self.assertIn("Read as costs / bills, dates as MM/DD/YYYY.", [c.value for c in at.caption])
        self.assertEqual([], [c for c in at.checkbox])  # no confirmation boxes in sample mode

    def test_ambiguous_dates_ask_one_plain_question(self):
        at = self.run_page()
        question = radio(at, INVOICE_DATE_QUESTION)
        self.assertEqual(["October 1, 2026", "January 10, 2026"], question.options)
        self.assertNotIn("of 10 couldn't be imported", page_text(at))  # no invoice report until answered
        self.assertNotIn("imported invoices", page_text(at))

    def test_invoice_report_after_answering_the_date_question(self):
        at = self.run_page()
        radio(at, INVOICE_DATE_QUESTION).set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        text = page_text(at)
        self.assertIn("4 rows of 10 couldn't be imported", text)
        self.assertIn("1 of 6 imported invoices have no job number", text)
        rejected_table = at.dataframe[0].value
        self.assertEqual([7, 8, 10, 11], list(rejected_table["Row in file"]))
        self.assertTrue(all(rejected_table["Why"].str.len() > 0))

    def test_own_upload_requires_made_up_confirmation(self):
        at = self.run_page()
        at.toggle[0].set_value(False).run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(["These files are made-up (no real customer, invoice or bank data)."],
                         [c.label for c in at.checkbox])
        self.assertNotIn("couldn't be imported", page_text(at))

    def test_unrecognised_file_asks_what_it_is_and_which_column(self):
        # AppTest can't upload files, so point the page's sample folder at temp made-up files.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "fictional_invoices.csv").write_text(
                "Num,Date,(not in this file),Amount\nX-1,10/31/2026,Example Co (fictional),1.00\n", encoding="utf-8")
            Path(tmp, "fictional_costs.csv").write_text("Date,Payee,Amount\n10/31/2026,A,1.00\n", encoding="utf-8")
            source = Path(PAGE).read_text(encoding="utf-8").replace(
                'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({tmp!r})")
            self.assertIn(repr(tmp), source)
            at = run_source(source)
            radio(at, "Is fictional_invoices.csv a list of sales or of costs?").set_value("invoices").run()
            # A header literally named like the "no column" choice can still be picked.
            ask = next(s for s in at.selectbox if s.label == "Which column has the customer?")
            ask.select_index(ask.options.index("(not in this file)", 1)).run()
            self.assertFalse(at.exception, at.exception)
            self.assertIn("1 invoice imported", page_text(at))


if __name__ == "__main__":
    unittest.main()
