"""Reading CSV and Excel (.xlsx) files, including report-style exports with title, heading and total rows.

Every file here is made up and built in memory. The report layout follows what QuickBooks Online's
help pages describe for exported reports (title lines on top, rows grouped under a heading, "Total
for ..." rows and a grand total). The exact column names of real exports are not assumed: the
tests check that MargenX finds the column-name row, skips only rows that can't be a sale or cost,
and counts every real line once.
"""
from datetime import date, datetime
from decimal import Decimal
import io
import unittest
from unittest import mock

from openpyxl import Workbook

import job_intake as ji
import job_profit as jp


def xlsx(*sheets) -> bytes:
    """An Excel file with one sheet per list of rows."""
    book = Workbook()
    book.remove(book.active)
    for number, rows in enumerate(sheets, start=1):
        sheet = book.create_sheet(f"Sheet{number}")
        for row in rows:
            sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def intake(name, data, kind, date_format):
    headers, records, notes = ji.read_file(name, data)
    return ji.intake(headers, records, ji.suggest_mapping(headers, kind), kind, date_format), notes


# A sales report laid out like an accounting export: title lines, a blank first column name,
# customer headings, lines, "Total for" rows, a grand total and a footer.
REPORT = [
    ["Biscayne Signs (fictional)"],
    ["Sales by Customer Detail"],
    ["October 2026"],
    [],
    [None, "Date", "Invoice", "Customer", "Job", "Description", "Amount"],
    ["Coastal Bakery (fictional)"],
    [None, date(2026, 10, 2), "INV-1", "Coastal Bakery (fictional)", "J-1", "Storefront sign", 2400.0],
    [None, date(2026, 10, 9), "INV-2", "Coastal Bakery (fictional)", "J-2", "Menu board", 312.5],
    ["Total for Coastal Bakery (fictional)", None, None, None, None, None, 2712.5],
    ["Palm Gym (fictional)"],
    [None, date(2026, 10, 12), "INV-3", "Palm Gym (fictional)", "J-3", "Window vinyl", 950.0],
    [None, date(2026, 10, 14), "INV-4", "Palm Gym (fictional)", "J-3", "Refund for a scratched panel", -45.0],
    ["Total for Palm Gym (fictional)", None, None, None, None, None, 905.0],
    ["TOTAL", None, None, None, None, None, 3617.5],
    [],
    ["Accrual basis Tuesday, October 20, 2026 10:00 AM GMT-04:00"],
]


class ExcelReadingTests(unittest.TestCase):
    def test_plain_excel_table_reads_like_the_same_csv(self):
        data = xlsx([["Invoice", "Date", "Customer", "Job", "Amount"],
                     ["INV-1", date(2026, 10, 2), "Bakery (fictional)", "J-1", 2400],
                     ["INV-2", date(2026, 10, 3), "Bakery (fictional)", "J-2", 12.5]])
        result, notes = intake("sales.xlsx", data, "invoices", "YYYY-MM-DD")
        self.assertEqual([], notes)
        self.assertEqual([], result.rejected)
        self.assertEqual([(Decimal("2400"), "2026-10-02"), (Decimal("12.5"), "2026-10-03")],
                         [(r["amount"], r["date"]) for r in result.accepted])
        self.assertTrue(all(isinstance(r["amount"], Decimal) for r in result.accepted))

    def test_money_from_excel_is_never_rounded(self):
        # A value with more than two decimals is refused, not rounded.
        data = xlsx([["Invoice", "Date", "Customer", "Job", "Amount"],
                     ["INV-1", date(2026, 10, 2), "Bakery (fictional)", "J-1", 12.345],
                     ["INV-2", date(2026, 10, 2), "Bakery (fictional)", "J-2", 0.3]])
        result, _ = intake("sales.xlsx", data, "invoices", "YYYY-MM-DD")
        self.assertEqual(["INV-2"], [r["invoice_id"] for r in result.accepted])
        self.assertEqual(Decimal("0.3"), result.accepted[0]["amount"])
        self.assertEqual([2], [r["row"] for r in result.rejected])
        self.assertTrue(result.rejected[0]["money_missing"])
        # A stored value carrying binary noise (Excel saves a formula's result to 17 digits, e.g.
        # 0.1 + 0.2) keeps every digit as text, so the money check refuses it instead of rounding.
        noisy = ji._cell_text(0.1 + 0.2)
        self.assertEqual("0.30000000000000004", noisy)
        with self.assertRaises(ValueError):
            ji.money(noisy)
        self.assertEqual(("1234.56", "2400", "-45"), (ji._cell_text(1234.56), ji._cell_text(2400.0), ji._cell_text(-45.0)))

    def test_dates_become_unambiguous_and_a_time_of_day_is_refused(self):
        self.assertEqual("2026-10-02", ji._cell_text(date(2026, 10, 2)))
        self.assertEqual("2026-10-02", ji._cell_text(datetime(2026, 10, 2)))
        data = xlsx([["Invoice", "Date", "Customer", "Job", "Amount"],
                     ["INV-1", datetime(2026, 10, 2, 14, 30), "Bakery (fictional)", "J-1", 10]])
        result, _ = intake("sales.xlsx", data, "invoices", "YYYY-MM-DD")
        self.assertEqual([], result.accepted)
        self.assertIn("doesn't match", " ".join(result.rejected[0]["reasons"]))

    def test_unsafe_or_unclear_excel_files_are_refused(self):
        table = [["Invoice", "Date", "Customer", "Amount"], ["INV-1", date(2026, 10, 2), "A", 1]]
        with self.assertRaisesRegex(ji.IntakeError, "more than one sheet"):
            ji.read_file("sales.xlsx", xlsx(table, table))
        with self.assertRaisesRegex(ji.IntakeError, "name and contents don't match"):
            ji.read_file("sales.xlsx", b"Invoice,Date,Customer,Amount\nINV-1,10/02/2026,A,1.00\n")
        with self.assertRaisesRegex(ji.IntakeError, "name and contents don't match"):
            ji.read_file("sales.csv", xlsx(table))
        with self.assertRaisesRegex(ji.IntakeError, "can't be opened"):
            ji.read_file("sales.xlsx", b"PK\x03\x04 not really a zip")
        with mock.patch.object(ji, "MAX_XLSX_UNPACKED_BYTES", 100):
            with self.assertRaisesRegex(ji.IntakeError, "unpacks to more than"):
                ji.read_file("sales.xlsx", xlsx(table))
        with mock.patch.object(ji, "MAX_ROWS", 1):
            with self.assertRaisesRegex(ji.IntakeError, "more than 1 rows"):
                ji.read_file("sales.xlsx", xlsx(table))


class ReportLayoutTests(unittest.TestCase):
    def test_report_title_lines_headings_and_totals_are_handled(self):
        result, notes = intake("sales.xlsx", xlsx(REPORT), "invoices", "YYYY-MM-DD")
        self.assertIn("Skipped 3 title lines above the column names: Biscayne Signs (fictional) / "
                      "Sales by Customer Detail / October 2026.", notes)
        self.assertIn("(no name, column A)", " ".join(notes))
        # Every real line is imported once; nothing is rejected.
        self.assertEqual([], result.rejected)
        self.assertEqual(["INV-1", "INV-2", "INV-3", "INV-4"], [r["invoice_id"] for r in result.accepted])
        self.assertEqual(Decimal("3617.5"), sum(r["amount"] for r in result.accepted))
        # Headings, totals and the footer are listed as skipped, with their reason.
        reasons = {r["row"]: r["reason"] for r in result.skipped}
        self.assertEqual({6, 9, 10, 13, 14, 16}, set(reasons))
        self.assertIn("A total row ('Total for Coastal Bakery (fictional)')", reasons[9])
        self.assertIn("A total row ('TOTAL')", reasons[14])
        self.assertIn("A heading or note ('Palm Gym (fictional)')", reasons[10])
        self.assertIn("A heading or note ('Accrual basis", reasons[16])
        self.assertTrue(any("total or heading row" in i["text"] for i in ji.missing_report(result)))

    def test_totals_are_never_counted_again_in_profit(self):
        sales, _ = intake("sales.xlsx", xlsx(REPORT), "invoices", "YYYY-MM-DD")
        costs, _ = intake("costs.xlsx", xlsx([
            ["Biscayne Signs (fictional)"], ["Expenses by job"], [],
            ["Bill", "Date", "Vendor", "Job", "Type", "Amount"],
            ["B-1", date(2026, 10, 1), "Supply (fictional)", "J-1", "Materials", 600],
            ["B-2", date(2026, 10, 2), "Crew (fictional)", "J-1", "Labor", 480.25],
            ["Total", None, None, None, None, 1080.25]]), "costs", "YYYY-MM-DD")
        self.assertEqual([], costs.rejected)
        report = jp.job_profit(sales, costs)
        j1 = next(j for j in report.jobs if j.job_id == "J-1")
        self.assertEqual((Decimal("2400"), Decimal("1080.25"), Decimal("1319.75"), "complete"),
                         (j1.sales, j1.total_costs, j1.contribution, j1.status))
        # The skipped total rows don't count as missing money anywhere.
        self.assertEqual((0, 0), (report.rejected_sales_lines, report.rejected_cost_lines))

    def test_the_same_report_as_csv_is_read_the_same_way(self):
        lines = ["Biscayne Signs (fictional)", "Sales by Customer Detail", "",
                 ",Date,Invoice,Customer,Job,Description,Amount",
                 "Coastal Bakery (fictional),,,,,,",
                 ",10/02/2026,INV-1,Coastal Bakery (fictional),J-1,Storefront sign,\"2,400.00\"",
                 "Total for Coastal Bakery (fictional),,,,,,\"2,400.00\"", "TOTAL,,,,,,\"2,400.00\""]
        headers, records, notes = ji.read_file("sales.csv", "\n".join(lines).encode())
        result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertIn("Skipped 2 title lines", " ".join(notes))
        self.assertEqual([Decimal("2400.00")], [r["amount"] for r in result.accepted])
        self.assertEqual([], result.rejected)
        self.assertEqual(3, len(result.skipped))

    def test_rows_that_could_hold_money_are_never_skipped(self):
        # A row with a date isn't a total row, even if its first cell says "Total"; a single
        # filled cell that is the amount isn't a heading. Both go through the usual checks.
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        records = [ji.Record(2, ("Total", "10/02/2026", "Total Fitness (fictional)", "J-1", "100.00")),
                   ji.Record(3, ("", "", "", "", "50.00")),
                   ji.Record(4, ("Total Fitness (fictional)", "", "", "", ""))]
        result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertEqual(["Total"], [r["invoice_id"] for r in result.accepted])
        self.assertEqual([3], [r["row"] for r in result.rejected])
        self.assertTrue(result.rejected[0]["money_missing"])
        self.assertEqual([4], [r["row"] for r in result.skipped])  # a lone name with no amount: a heading

    def test_plain_csv_files_read_exactly_as_before(self):
        data = b"Invoice,Date,Customer,Job,Amount\nINV-1,10/02/2026,Bakery (fictional),J-1,100.00\n"
        self.assertEqual(ji.read_csv(data), ji.read_file("sales.csv", data)[:2])
        self.assertEqual([], ji.read_file("sales.csv", data)[2])
        # A plain file whose first line has a blank column name is still refused.
        with self.assertRaisesRegex(ji.IntakeError, "no header name"):
            ji.read_file("sales.csv", b"Invoice,,Amount\nINV-1,x,1.00\n")


class PageTests(unittest.TestCase):
    def test_excel_report_files_go_all_the_way_to_results_on_the_page(self):
        import tempfile
        from pathlib import Path
        from streamlit.testing.v1 import AppTest

        page = Path(__file__).resolve().parents[1] / "pages" / "1_MargenX_Import.py"
        costs = [["Biscayne Signs (fictional)"], ["Expenses by job"], [],
                 ["Bill", "Date", "Vendor", "Job", "Type", "Amount"],
                 ["B-1", date(2026, 10, 1), "Supply (fictional)", "J-1", "Materials", 600],
                 ["B-2", date(2026, 10, 2), "Crew (fictional)", "J-1", "Labor", 480.25],
                 ["Total", None, None, None, None, 1080.25]]
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sales.xlsx").write_bytes(xlsx(REPORT))
            Path(tmp, "costs.xlsx").write_bytes(xlsx(costs))
            source = page.read_text(encoding="utf-8").replace(
                'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({tmp!r})").replace(
                'DEFAULT_SAMPLE_SET = "demo"', 'DEFAULT_SAMPLE_SET = "test"').replace(
                'SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")', 'SAMPLE_FILES = ("sales.xlsx", "costs.xlsx")')
            at = AppTest.from_string(source, default_timeout=60)
            at.run()
        self.assertFalse(at.exception, at.exception)
        page_html = " ".join(m.value for m in at.markdown)
        self.assertIn("Here's where your money was made", page_html)
        self.assertIn("$3,617.50", page_html)  # every real sales line once; no total counted again
        captions = " ".join(c.value for c in at.caption)
        self.assertIn("Skipped 3 title lines above the column names", captions)
        self.assertTrue(any(e.label.startswith("Report lines skipped: totals and headings (6)") for e in at.expander))
        self.assertFalse(any(e.label.startswith("Rows that couldn't be used") for e in at.expander))


if __name__ == "__main__":
    unittest.main()
