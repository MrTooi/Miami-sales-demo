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

    def with_files(self, invoices_csv, costs_csv):
        """AppTest can't upload files, so point the page's sample folder at temp made-up files."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, "fictional_invoices.csv").write_text(invoices_csv, encoding="utf-8")
        Path(tmp.name, "fictional_costs.csv").write_text(costs_csv, encoding="utf-8")
        source = Path(PAGE).read_text(encoding="utf-8").replace(
            'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({tmp.name!r})")
        self.assertIn(repr(tmp.name), source)
        at = run_source(source)
        self.assertFalse(at.exception, at.exception)
        return at

    def test_unrecognised_file_asks_what_it_is_and_which_column(self):
        at = self.with_files("Num,Date,(not in this file),Amount\nX-1,10/31/2026,Example Co (fictional),1.00\n",
                             "Date,Payee,Amount\n10/31/2026,A,1.00\n")
        radio(at, "Is fictional_invoices.csv a list of sales or of costs?").set_value("invoices").run()
        # A header literally named like the "no column" choice can still be picked.
        ask = next(s for s in at.selectbox if s.label == "Which column has the customer?")
        ask.select_index(ask.options.index("(not in this file)", 1)).run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("1 invoice imported", page_text(at))

    def test_mixed_date_styles_fall_back_to_picking_the_main_format(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,2026-10-06,X,1.00\nB,10/31/2026,Y,2.00\n",
                             "Date,Payee,Amount\n10/31/2026,A,1.00\n")
        pick = radio(at, "Which date format does fictional_invoices.csv mainly use?")
        pick.set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        text = page_text(at)
        self.assertIn("1 row of 2 couldn't be imported", text)
        self.assertIn("1 invoice imported", text)

    def test_unreadable_dates_are_still_accounted_for(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,someday,X,1.00\nB,,Y,2.00\n",
                             "Date,Payee,Amount\n10/31/2026,A,1.00\n")
        radio(at, "Which date format does fictional_invoices.csv mainly use?").set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 rows of 2 couldn't be imported", page_text(at))
        self.assertIn("No invoices were imported", page_text(at))
        self.assertEqual(1, len(at.get("download_button")))

    def test_automatic_date_format_can_be_changed_and_report_recomputes(self):
        at = self.run_page()
        self.assertIn("1 row of 9 couldn't be imported", page_text(at))
        override = next(s for s in at.selectbox if s.label == "Date format" and "10/01/2026" in s.options[1]
                        and s.value == "MM/DD/YYYY")
        override.set_value("DD/MM/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 rows of 9 couldn't be imported", page_text(at))  # 10/31/2026 isn't a valid DD/MM date
        self.assertIn("Read as costs / bills, dates as DD/MM/YYYY.", [c.value for c in at.caption])

    def test_automatic_file_type_can_be_changed(self):
        at = self.run_page()
        costs_type = next(r for r in at.radio if r.label == "File type" and r.value == "costs")
        costs_type.set_value("invoices").run()
        self.assertFalse(at.exception, at.exception)
        labels = [s.label for s in at.selectbox]
        self.assertIn("Which column has the invoice number?", labels)
        self.assertNotIn("imported costs", page_text(at))

    def test_identical_files_both_get_reported(self):
        same = "Date,Payee,Amount\n10/31/2026,A,1.00\n"
        at = self.with_files(same, same)
        self.assertEqual(2, page_text(at).count("1 cost imported"))


if __name__ == "__main__":
    unittest.main()
