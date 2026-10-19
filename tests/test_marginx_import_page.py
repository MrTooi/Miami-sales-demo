from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_MarginX_Import.py")
CONFIRM = "These columns and the date format are right"


def markdown_text(at):
    # Report lines and file details are rendered as plain text (st.text).
    return " | ".join(t.value for t in at.text)


def confirm_box(at):
    return next(c for c in at.checkbox if c.label == CONFIRM)


class MarginXImportPageTests(unittest.TestCase):
    def run_page(self):
        at = AppTest.from_file(PAGE, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_pilot_warning_is_always_shown(self):
        at = self.run_page()
        self.assertIn("made-up data only", at.warning[0].value)

    def test_ambiguous_dates_require_a_choice_before_any_report(self):
        at = self.run_page()
        self.assertIn("Choose the date format used in the file.", [i.value for i in at.info])
        self.assertNotIn("couldn't be imported", markdown_text(at))

    def test_no_report_until_the_owner_confirms_the_columns(self):
        at = self.run_page()
        at.selectbox(key="datefmt-invoices").set_value("MM/DD/YYYY").run()
        self.assertNotIn("couldn't be imported", markdown_text(at))
        self.assertIn("tick the box", " ".join(i.value for i in at.info))
        self.assertFalse(confirm_box(at).value)

    def test_invoice_sample_report_after_confirming(self):
        at = self.run_page()
        at.selectbox(key="datefmt-invoices").set_value("MM/DD/YYYY").run()
        confirm_box(at).check().run()
        self.assertFalse(at.exception, at.exception)
        report = markdown_text(at)
        self.assertIn("4 rows of 10 couldn't be imported", report)
        self.assertIn("1 of 6 imported invoices have no job number", report)
        rejected_table = at.dataframe[0].value
        self.assertEqual([7, 8, 10, 11], list(rejected_table["Row in file"]))
        self.assertTrue(all(rejected_table["Why"].str.len() > 0))

    def test_changing_a_column_needs_a_fresh_confirmation(self):
        at = self.run_page()
        at.selectbox(key="datefmt-invoices").set_value("MM/DD/YYYY").run()
        confirm_box(at).check().run()
        at.selectbox(key="map-invoices-job_id").select_index(0).run()  # "(not in this file)"
        self.assertFalse(confirm_box(at).value)
        self.assertNotIn("couldn't be imported", markdown_text(at))

    def test_cost_sample_report(self):
        at = self.run_page()
        at.radio[0].set_value("costs").run()
        confirm_box(at).check().run()
        report = markdown_text(at)
        self.assertIn("3 of 8 imported costs aren't linked to a job", report)
        self.assertIn("No labor costs were found", report)

    def test_a_header_named_like_the_no_column_choice_can_still_be_mapped(self):
        # AppTest can't upload files, so point the page's sample folder at a temp file.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "fictional_invoices.csv").write_text(
                "Num,Date,(not in this file),Amount\nX-1,10/01/2026,Example Co (fictional),1.00\n", encoding="utf-8")
            source = Path(PAGE).read_text(encoding="utf-8").replace(
                'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({tmp!r})")
            self.assertIn(repr(tmp), source)
            at = AppTest.from_string(source, default_timeout=30)
            at.run()
            customer = at.selectbox(key="map-invoices-customer")
            customer.select_index(customer.options.index("(not in this file)", 1)).run()
            at.selectbox(key="datefmt-invoices").set_value("MM/DD/YYYY").run()  # 10/01 fits two formats
            confirm_box(at).check().run()
            self.assertFalse(at.exception, at.exception)
            self.assertIn("1 invoice imported", markdown_text(at))

    def test_own_upload_requires_made_up_data_confirmation(self):
        at = self.run_page()
        at.toggle[0].set_value(False).run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(["This file is made-up or anonymized (no real customer, invoice or bank data)."],
                         [c.label for c in at.checkbox])
        self.assertNotIn("couldn't be imported", markdown_text(at))


if __name__ == "__main__":
    unittest.main()
