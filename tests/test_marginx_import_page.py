from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_MarginX_Import.py")


def markdown_text(at):
    return " | ".join(m.value for m in at.markdown)


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

    def test_invoice_sample_report_after_choosing_date_format(self):
        at = self.run_page()
        at.selectbox(key="datefmt-invoices").set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        report = markdown_text(at)
        self.assertIn("4 rows of 10 couldn't be imported", report)
        self.assertIn("1 of 6 imported invoices have no job number", report)
        rejected_table = at.dataframe[0].value
        self.assertEqual([7, 8, 10, 11], list(rejected_table["Row in file"]))
        self.assertTrue(all(rejected_table["Why"].str.len() > 0))

    def test_cost_sample_report(self):
        at = self.run_page()
        at.radio[0].set_value("costs").run()
        report = markdown_text(at)
        self.assertIn("3 of 8 imported costs aren't linked to a job", report)
        self.assertIn("No labor costs were found", report)

    def test_own_upload_requires_made_up_data_confirmation(self):
        at = self.run_page()
        at.toggle[0].set_value(False).run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(1, len(at.checkbox))
        self.assertIn("made-up or anonymized", at.checkbox[0].label)
        self.assertNotIn("couldn't be imported", markdown_text(at))


if __name__ == "__main__":
    unittest.main()
