"""Issue #128, step 2: recognising QuickBooks Online's Profit and Loss Detail report, and the #129
review follow-ups (a QuickBooks-only column alone in a row; clearer refusal reasons).

Every row is made up (tests/quickbooks_fixtures.py). Only the layout copies the export seen on
2026-10-26. A recognised report is still refused for now: its lines are read in steps 3 and 4.
"""
from datetime import date
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_fixtures as fx  # noqa: E402
import job_intake as ji  # noqa: E402
import quickbooks_layouts as qlayouts  # noqa: E402
import quickbooks_rules as qr  # noqa: E402

GOOD = fx.xlsx(fx.pnl_rows(), formulas=fx.FORMULAS, stored=fx.STORED)


def table(data: bytes, *, is_xlsx: bool = True):
    return ji._xlsx_rows(data) if is_xlsx else ji._csv_rows(data)


def recognise(data: bytes, *, is_xlsx: bool = True) -> qlayouts.Recognition:
    return qlayouts.recognise_profit_and_loss_detail(table(data, is_xlsx=is_xlsx), is_xlsx=is_xlsx)


def refusal(data: bytes, name: str = "report.xlsx") -> str:
    with unittest.TestCase().assertRaises(ji.IntakeError) as caught:
        ji.read_file(name, data)
    return str(caught.exception)


class RecognisedLayoutTests(unittest.TestCase):
    """The layout seen is recognised, with its company, dates, basis and columns, and nothing counted."""

    def test_the_layout_seen_is_recognised(self):
        found = recognise(GOOD)
        self.assertEqual((), found.problems)
        layout = found.layout
        self.assertEqual(fx.COMPANY, layout.company)
        self.assertEqual(fx.PERIOD, layout.period)
        self.assertEqual((date(2026, 1, 1), date(2026, 10, 26)), (layout.period_start, layout.period_end))
        self.assertEqual("Accrual", layout.basis)
        self.assertEqual(fx.FOOTER, layout.footer)
        self.assertEqual((5, fx.FOOTER_ROW), (layout.header_row, layout.footer_row))
        self.assertEqual({"Transaction date": 1, "Transaction type": 2, "Num": 3, "Name": 4, "Location": 5,
                          "Class full name": 6, "Description": 7, "Item split account": 8, "Amount": 9,
                          "Balance": 10}, layout.columns)

    def test_every_report_row_is_kept_for_step_3_with_its_excel_row_number(self):
        # Rows 6 to 36, worked out from the fixture by hand: 31 rows, none left behind.
        body = recognise(GOOD).layout.body
        self.assertEqual(list(range(fx.FIRST_BODY_ROW, 37)), [number for number, _ in body])
        self.assertEqual(len(fx.BODY), len(body))
        self.assertEqual("Other Income", body[29 - fx.FIRST_BODY_ROW][1][1])  # the heading in column B
        # Stored totals are kept exactly as stored, never rounded: the float rule is step 3's.
        self.assertEqual("349.40999999999997", dict(body)[24][9])
        self.assertEqual(("", "10/02/2026", "Invoice", "1001", "Coral Cafe (fictional):Patio"), dict(body)[9][:5])

    def test_totals_written_as_formulas_are_read_from_their_saved_results(self):
        with_formulas, plain = recognise(GOOD).layout, recognise(fx.xlsx(fx.pnl_rows(), stored=fx.STORED)).layout
        self.assertEqual(plain.body, with_formulas.body)

    def test_a_total_whose_formula_has_no_saved_result_refuses_the_file(self):
        rows = fx.pnl_rows()
        rows[10] = fx.total("Total for Design income", "=J9+J10")  # Excel row 11, never calculated
        reason = refusal(fx.xlsx(rows))
        self.assertIn("Cell J11 holds a formula with no saved result", reason)

    def test_optional_columns_may_be_left_out(self):
        columns = [c for c in fx.COLUMNS if c not in ("Location", "Class full name")]
        body = [row if len(row) < 10 else row[:5] + row[7:] for row in fx.BODY]
        layout = recognise(fx.xlsx(fx.pnl_rows(columns=columns, body=body))).layout
        self.assertIsNotNone(layout)
        self.assertEqual({"Transaction date": 1, "Transaction type": 2, "Num": 3, "Name": 4, "Description": 5,
                          "Item split account": 6, "Amount": 7, "Balance": 8}, layout.columns)

    def test_a_period_across_two_years_and_another_time_zone_are_recognised(self):
        layout = recognise(fx.xlsx(fx.pnl_rows(period="November 1, 2025-October 31, 2026",
                                               footer="Accrual Basis Tuesday, November 3, 2026 09:15 AM GMT-05:00"))).layout
        self.assertEqual((date(2025, 11, 1), date(2026, 10, 31)), (layout.period_start, layout.period_end))
        for offset in ("+14:00", "+05:30", "+05:45", "-00:00"):
            with self.subTest(offset):
                footer = f"Accrual Basis Monday, October 26, 2026 07:04 PM GMT{offset}"
                self.assertIsNotNone(recognise(fx.xlsx(fx.pnl_rows(footer=footer))).layout)

    def test_repeated_spaces_in_the_title_rows_change_nothing(self):
        layout = recognise(fx.xlsx(fx.pnl_rows(company=" Biscayne  Landscaping (fictional)",
                                               title="Profit  and Loss  Detail"))).layout
        self.assertEqual(fx.COMPANY, layout.company)

    def test_a_recognised_report_is_still_refused_and_says_what_was_recognised(self):
        reason = refusal(GOOD)
        self.assertEqual(
            "This is QuickBooks' Profit and Loss Detail report for Biscayne Landscaping (fictional) (January 1-October "
            "26, 2026, accrual basis). MargenX recognises this report, but reading its lines is still being built, so "
            "nothing from this file was used. For now, upload a plain list with one row per sale or cost, with "
            "columns such as Date, Customer, Job and Amount.", reason)
        for amount in ("900", "1,200", "150", "349"):
            self.assertNotIn(amount, reason)


class VariantTests(unittest.TestCase):
    """Variants that aren't the layout seen fail closed, each with its own plain reason (S2)."""

    def assert_refused(self, data: bytes, says: str, name: str = "report.xlsx"):
        found = recognise(data, is_xlsx=name.endswith(".xlsx"))
        self.assertIsNone(found.layout)
        self.assertTrue(any(says in problem for problem in found.problems), found.problems)
        reason = refusal(data, name)
        self.assertIn("This looks like a QuickBooks report (it has the title 'Profit and Loss Detail'), but it isn't "
                      "exactly in the layout MargenX knows", reason)
        self.assertIn("Nothing from this file was used.", reason)
        return reason

    def test_each_variant_is_refused_with_its_reason(self):
        body_with_value_past_balance = [*fx.BODY[:3], fx.line(2, "Invoice", "1001", "A (fictional)", 9.0, 9.0) + ["x"],
                                        *fx.BODY[4:]]
        cases = {
            "it's a cash-basis report": fx.pnl_rows(footer="Cash Basis Monday, October 26, 2026 07:04 PM GMTZ"),
            "can't tell whether it's accrual or cash": fx.pnl_rows(footer=None),
            "isn't the basis line MargenX knows": fx.pnl_rows(footer="Accrual basis Monday, October 26, 2026 07:04 PM"),
            "doesn't hold a real date and time": fx.pnl_rows(footer="Accrual Basis Sunday, October 26, 2026 07:04 PM GMTZ"),
            "'Accrual Basis Monday, October 26, 2026 13:04 PM GMTZ', doesn't hold a real date and time":
                fx.pnl_rows(footer="Accrual Basis Monday, October 26, 2026 13:04 PM GMTZ"),
            "'Accrual Basis Monday, October 26, 2026 07:60 PM GMTZ', doesn't hold a real date and time":
                fx.pnl_rows(footer="Accrual Basis Monday, October 26, 2026 07:60 PM GMTZ"),
            # Automated review of 51ca08f: an offset that can't exist must not pass.
            "'Accrual Basis Monday, October 26, 2026 07:04 PM GMT+99:99', doesn't hold a real date and time":
                fx.pnl_rows(footer="Accrual Basis Monday, October 26, 2026 07:04 PM GMT+99:99"),
            "'Accrual Basis Monday, October 26, 2026 07:04 PM GMT-05:75', doesn't hold a real date and time":
                fx.pnl_rows(footer="Accrual Basis Monday, October 26, 2026 07:04 PM GMT-05:75"),
            "'Accrual Basis Monday, October 26, 2026 07:04 PM GMT+15:00', doesn't hold a real date and time":
                fx.pnl_rows(footer="Accrual Basis Monday, October 26, 2026 07:04 PM GMT+15:00"),
            "row 4 should be empty, but it holds 'Customer: Coral Cafe (fictional)'":
                fx.pnl_rows(row4=["Customer: Coral Cafe (fictional)"]),
            "row 4 should be empty, but it holds 'Currency: USD'": fx.pnl_rows(row4=["Currency: USD"]),
            "row 1 should hold only the company name": fx.pnl_rows(company=None),
            "row 2 should hold only the title": fx.pnl_rows(title="Profit and Loss Detail by Class")[:1]
                + [["Profit and Loss Detail", "Example (fictional)"]] + fx.pnl_rows()[2:],
            "row 3 says 'All Dates', which isn't a date range MargenX can read": fx.pnl_rows(period="All Dates"),
            "row 3 says 'October 2026'": fx.pnl_rows(period="October 2026"),
            "row 3 says 'February 30-March 3, 2026', which isn't a real date range":
                fx.pnl_rows(period="February 30-March 3, 2026"),
            "row 3 says 'October 26-January 1, 2026', which starts after it ends":
                fx.pnl_rows(period="October 26-January 1, 2026"),
            "it has a column MargenX doesn't know: 'Memo/Description'":
                fx.pnl_rows(columns=[c if c != "Description" else "Memo/Description" for c in fx.COLUMNS]),
            "it has a column MargenX doesn't know: 'Foreign Amount'": fx.pnl_rows(columns=[*fx.COLUMNS, "Foreign Amount"]),
            "it's missing the column 'Name'": fx.pnl_rows(columns=[c if c != "Name" else "Location" for c in fx.COLUMNS]),
            "the column 'Location' appears twice": fx.pnl_rows(columns=[c if c != "Class full name" else "Location"
                                                                        for c in fx.COLUMNS]),
            "column A of row 5 should have no name": fx.pnl_rows(columns=["Account", *fx.COLUMNS[1:]]),
            "the column in F has no name": fx.pnl_rows(columns=[c if c != "Location" else None for c in fx.COLUMNS]),
            "row 9 has a value in column L, which has no name": fx.pnl_rows(body=body_with_value_past_balance),
            "row 20 looks like a second basis line": fx.pnl_rows(body=[*fx.BODY[:14], [fx.FOOTER], *fx.BODY[15:]]),
            "no rows between the column names and the basis line": fx.pnl_rows(body=[]),
        }
        for says, rows in cases.items():
            with self.subTest(says):
                self.assert_refused(fx.xlsx(rows), says)

    def test_the_csv_version_is_refused_with_how_to_export_excel(self):
        for name in ("report.csv",):
            reason = self.assert_refused(fx.csv_bytes(fx.pnl_rows()), "it's a CSV file", name)
            self.assertIn("choose Export to Excel", reason)
        with self.assertRaisesRegex(ji.IntakeError, "it's a CSV file"):
            ji.read_csv(fx.csv_bytes(fx.pnl_rows()))

    def test_every_problem_is_listed_at_once(self):
        found = recognise(fx.xlsx(fx.pnl_rows(period="All Dates", row4=["Class: Design"],
                                              footer="Cash Basis Monday, October 26, 2026 07:04 PM GMTZ")))
        self.assertEqual(3, len(found.problems), found.problems)
        reason = refusal(fx.xlsx(fx.pnl_rows(company=None, period="All Dates", row4=["Class: Design"],
                                             footer="Cash Basis Monday, October 26, 2026 07:04 PM GMTZ")))
        self.assertIn("(and 1 more)", reason)

    def test_a_workbook_with_two_sheets_is_refused_even_when_both_are_the_report(self):
        reason = refusal(fx.xlsx(fx.pnl_rows(), sheets=2))
        self.assertIn("more than one sheet", reason)


class SingleColumnSignTests(unittest.TestCase):
    """#129 review follow-up: a QuickBooks-only column name alone in its row is still a sign."""

    PLAIN = [["Invoice", "Date", "Customer", "Job", "Amount"], ["INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "405.00"]]

    def test_each_quickbooks_only_column_alone_in_a_row_refuses_the_file(self):
        for column in sorted(qr.QUICKBOOKS_COLUMNS):
            rows = [[column], *self.PLAIN]
            for name in ("file.csv", "file.xlsx"):
                data = fx.xlsx(rows) if name.endswith(".xlsx") else fx.csv_bytes(rows)
                with self.subTest(column, name=name):
                    self.assertIn(f"it has the column '{column}'", refusal(data, name))
            with self.subTest(column, name="read_csv"), self.assertRaisesRegex(ji.IntakeError, f"the column '{column}'"):
                ji.read_csv(fx.csv_bytes(rows))

    def test_the_example_from_the_review_is_refused(self):
        rows = [["Memo/Description", "", "", "", ""], *self.PLAIN]
        for name in ("file.csv", "file.xlsx"):
            data = fx.xlsx(rows) if name.endswith(".xlsx") else fx.csv_bytes(rows)
            with self.subTest(name):
                self.assertIn("it has the column 'Memo/Description'", refusal(data, name))

    def test_transaction_type_or_num_alone_is_not_a_sign(self):
        for word in ("Transaction type", "Num"):
            with self.subTest(word):
                rows = [[word], *self.PLAIN]
                self.assertEqual([], qr.quickbooks_signs(list(enumerate(rows, 1)), ji.MAX_TITLE_LINES))
                headers, records, _ = ji.read_file("file.csv", fx.csv_bytes(rows))
                self.assertEqual(self.PLAIN[0], headers)


class RefusalWordingTests(unittest.TestCase):
    """#129 review follow-up: the refusal says what made the file look like QuickBooks, and what to do."""

    PLAIN = [["Invoice", "Date", "Customer", "Job", "Amount"], ["INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "40.00"]]

    def test_each_trigger_gets_its_own_advice(self):
        cases = {
            "rename or remove that column": [["Invoice", "Date", "Customer", "Split", "Amount"], self.PLAIN[1]],
            "rename or remove those columns": [["Num", "Date", "Customer", "Transaction type", "Amount"], self.PLAIN[1]],
            "rename or remove that row": [*self.PLAIN, ["Total for Bakery (fictional)", "", "", "", "40.00"]],
        }
        for advice, rows in cases.items():
            with self.subTest(advice):
                reason = refusal(fx.csv_bytes(rows), "file.csv")
                self.assertIn(f"If this file didn't come from QuickBooks, {advice} and upload it again", reason)
                self.assertIn("upload a plain list with one row per sale or cost", reason)

    def test_a_title_says_what_to_upload_instead_without_rename_advice(self):
        reason = refusal(fx.csv_bytes([["Sales by Customer Detail"], *self.PLAIN]), "file.csv")
        self.assertIn("it has the title 'Sales by Customer Detail'", reason)
        self.assertIn("MargenX can't read this QuickBooks report yet", reason)
        self.assertIn("upload a plain list with one row per sale or cost", reason)
        self.assertNotIn("rename", reason)

    def test_plain_files_still_read(self):
        samples = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"
        for path in sorted(samples.glob("*.csv")):
            with self.subTest(path.name):
                ji.read_file(path.name, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
