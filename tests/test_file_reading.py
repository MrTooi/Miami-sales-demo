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
import struct
import unittest
import zipfile
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


def raw_xlsx(rows_xml: str) -> bytes:
    """An Excel file whose only sheet is exactly this raw sheet XML (the <row> elements), so the test
    controls the text stored in the file instead of going through openpyxl's floats."""
    package = io.BytesIO(xlsx([["placeholder"]]))
    out = io.BytesIO()
    with zipfile.ZipFile(package) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                content = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                           f"<sheetData>{rows_xml}</sheetData></worksheet>").encode()
            target.writestr(info.filename, content)
    return out.getvalue()


def text_cells(row: int, *values: str) -> str:
    """A row of text cells (inline strings), starting at column A."""
    cells = "".join(f'<c r="{chr(65 + i)}{row}" t="inlineStr"><is><t>{v}</t></is></c>'
                    for i, v in enumerate(values) if v)
    return f'<row r="{row}">{cells}</row>'


# Column names, then one sale whose amount cell (E2) is filled in by each test.
RAW_HEADER = text_cells(1, "Invoice", "Date", "Customer", "Job", "Amount")


def raw_sale(amount_cell_xml: str) -> bytes:
    line = text_cells(2, "INV-1", "2026-10-02", "Bakery (fictional)", "J-1").replace("</row>", amount_cell_xml + "</row>")
    return raw_xlsx(RAW_HEADER + line)


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

    def test_excel_numbers_are_read_from_the_exact_text_stored_in_the_file(self):
        # openpyxl alone would read 12.3400000000000001 as the float 12.34 and lose the extra
        # digits; MargenX reads the stored text, so the value is refused, never rounded.
        for stored in ("12.3400000000000001", "0.30000000000000004", "12.345"):
            result, _ = intake("sales.xlsx", raw_sale(f'<c r="E2"><v>{stored}</v></c>'), "invoices", "YYYY-MM-DD")
            self.assertEqual([], result.accepted, stored)
            self.assertTrue(result.rejected[0]["money_missing"])
            self.assertIn(f"Amount '{stored}' isn't a valid dollar amount", result.rejected[0]["reasons"][0])
        for stored, read in (("2400", "2400"), ("12.50", "12.50"), ("1.2345E3", "1234.5"), ("-45", "-45")):
            result, _ = intake("sales.xlsx", raw_sale(f'<c r="E2"><v>{stored}</v></c>'), "invoices", "YYYY-MM-DD")
            self.assertEqual([Decimal(read)], [r["amount"] for r in result.accepted], stored)
            self.assertEqual(read, result.accepted[0]["original"]["amount"])
        # A huge or tiny exponent is kept in its short stored form, never written out in full (1E1000000000
        # would be a billion characters), and no money check accepts it: the row is rejected with a reason.
        for stored, kept in (("1E1000000000", "1E+1000000000"), ("-1E1000000000", "-1E+1000000000"),
                             ("1E-1000000000", "1E-1000000000"), ("1.4210854715202004E-14", "1.4210854715202004E-14")):
            result, _ = intake("sales.xlsx", raw_sale(f'<c r="E2"><v>{stored}</v></c>'), "invoices", "YYYY-MM-DD")
            self.assertEqual([], result.accepted, stored)
            self.assertIn(f"Amount '{kept}' isn't a valid dollar amount", result.rejected[0]["reasons"][0])
            self.assertTrue(result.rejected[0]["money_missing"])
        self.assertEqual("123456789012345678901", ji._cell_text(Decimal("1.23456789012345678901E20"), "E2"))
        # A float can never reach the money check.
        with self.assertRaisesRegex(ji.IntakeError, "couldn't be read exactly"):
            ji._cell_text(0.1 + 0.2, "E2")

    def test_formulas_without_a_saved_result_and_error_cells_refuse_the_file(self):
        # A formula Excel never calculated has no value in the file. It is never read as blank.
        with self.assertRaisesRegex(ji.IntakeError, "Cell E2 holds a formula with no saved result"):
            ji.read_file("sales.xlsx", raw_sale('<c r="E2"><f>C2*D2</f></c>'))
        # A whole row made by formulas would otherwise vanish as an empty row.
        formula_row = "".join(f'<c r="{c}3"><f>{c}2</f></c>' for c in "ABCDE")
        with self.assertRaisesRegex(ji.IntakeError, "Cell A3 holds a formula with no saved result"):
            ji.read_file("sales.xlsx", raw_xlsx(RAW_HEADER + text_cells(2, "INV-1", "2026-10-02", "A", "J-1", "1.00")
                                                + f'<row r="3">{formula_row}</row>'))
        # An empty saved value is no result for a number, so it refuses the file too, for one cell or a whole row.
        with self.assertRaisesRegex(ji.IntakeError, "Cell E2 holds a formula with no saved result"):
            ji.read_file("sales.xlsx", raw_sale('<c r="E2"><f>C2*D2</f><v/></c>'))
        empty_row = "".join(f'<c r="{c}3"><f>{c}2</f><v></v></c>' for c in "ABCDE")
        with self.assertRaisesRegex(ji.IntakeError, "Cell A3 holds a formula with no saved result"):
            ji.read_file("sales.xlsx", raw_xlsx(RAW_HEADER + text_cells(2, "INV-1", "2026-10-02", "A", "J-1", "1.00")
                                                + f'<row r="3">{empty_row}</row>'))
        with self.assertRaisesRegex(ji.IntakeError, r"Cell C2 holds an error \(#REF!\)"):
            ji.read_file("sales.xlsx", raw_xlsx(RAW_HEADER + '<row r="2"><c r="A2" t="inlineStr"><is><t>INV-1</t></is></c>'
                                                '<c r="C2" t="e"><v>#REF!</v></c><c r="E2"><v>5</v></c></row>'))
        # A formula with its saved result is read as that result, exactly.
        result, _ = intake("sales.xlsx", raw_sale('<c r="E2"><f>C2*D2</f><v>100.5</v></c>'), "invoices", "YYYY-MM-DD")
        self.assertEqual([Decimal("100.5")], [r["amount"] for r in result.accepted])
        # A saved result that is empty text (=IF(...,"")) is a real blank, so the line is rejected as missing money.
        result, _ = intake("sales.xlsx", raw_sale('<c r="E2" t="str"><f>IF(1,"","")</f><v></v></c>'), "invoices", "YYYY-MM-DD")
        self.assertEqual(["Amount is blank."], result.rejected[0]["reasons"])

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

    def test_repeated_or_reordered_rows_and_cells_refuse_the_file(self):
        sale = text_cells(2, "INV-1", "2026-10-02", "A", "J-1").replace("</row>", '<c r="E2"><v>100</v></c></row>')
        # A second row 2 that would total the first: both could otherwise be skipped as one row.
        total_again = '<row r="2"><c r="A2" t="inlineStr"><is><t>Total</t></is></c><c r="E2"><v>100</v></c></row>'
        with self.assertRaisesRegex(ji.IntakeError, "Row 2 appears twice or out of order"):
            ji.read_file("sales.xlsx", raw_xlsx(RAW_HEADER + sale + total_again))
        with self.assertRaisesRegex(ji.IntakeError, "Row 1 appears twice or out of order"):
            ji.read_file("sales.xlsx", raw_xlsx(sale + RAW_HEADER))
        # The same cell twice: the second would silently replace the first.
        twice = sale.replace("</row>", '<c r="E2"><v>1</v></c></row>')
        with self.assertRaisesRegex(ji.IntakeError, "A cell in row 2 appears twice, out of order or outside its row"):
            ji.read_file("sales.xlsx", raw_xlsx(RAW_HEADER + twice))
        outside = sale.replace('<c r="E2">', '<c r="E7">')
        with self.assertRaisesRegex(ji.IntakeError, "A cell in row 2 appears twice, out of order or outside its row"):
            ji.read_file("sales.xlsx", raw_xlsx(RAW_HEADER + outside))
        # intake itself also refuses two records with one row number.
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        records = [ji.Record(2, ("INV-1", "10/02/2026", "A", "J-1", "100.00")), ji.Record(2, ("Total", "", "", "", "100.00"))]
        with self.assertRaisesRegex(ji.IntakeError, "same row number"):
            ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")

    def test_size_and_shape_limits_refuse_the_file(self):
        table = [["Invoice", "Date", "Customer", "Amount"], ["INV-1", date(2026, 10, 2), "A", 1]]
        data = xlsx(table)
        with mock.patch.object(ji, "MAX_FILE_BYTES", len(data) - 1):
            with self.assertRaisesRegex(ji.IntakeError, "File is larger than"):
                ji.read_file("sales.xlsx", data)
        with mock.patch.object(ji, "MAX_COLUMNS", 3):
            with self.assertRaisesRegex(ji.IntakeError, "more than 3 columns"):
                ji.read_file("sales.xlsx", data)
        # Empty cells past the limit are fine; only a filled one is refused.
        with mock.patch.object(ji, "MAX_COLUMNS", 4):
            self.assertEqual(["Invoice", "Date", "Customer", "Amount"], ji.read_file("sales.xlsx", data)[0])

    def test_a_compressed_bomb_is_refused_before_it_is_unpacked(self):
        # A real crafted archive, no lowered limit: under 5 MB packed, over 50 MB unpacked.
        padding = "<!--" + " " * (ji.MAX_XLSX_UNPACKED_BYTES + 1) + "-->"
        bomb = raw_xlsx(padding + RAW_HEADER)
        self.assertLess(len(bomb), ji.MAX_FILE_BYTES)
        with self.assertRaisesRegex(ji.IntakeError, "unpacks to more than 50 MB"):
            ji.read_file("sales.xlsx", bomb)

    def test_an_archive_that_understates_its_unpacked_size_is_refused(self):
        # The sheet says it unpacks to 100 bytes but holds far more: reading stops at the stated
        # size, the check sum fails, and the file is refused rather than read in part.
        data = bytearray(raw_xlsx(RAW_HEADER + text_cells(2, "INV-1", "2026-10-02", "A", "J-1", "1.00")))
        name = b"xl/worksheets/sheet1.xml"
        for signature, size_at, name_at in ((b"PK\x03\x04", 22, 30), (b"PK\x01\x02", 24, 46)):
            at = data.index(signature)
            while data[at + name_at:at + name_at + len(name)] != name:
                at = data.index(signature, at + 1)
            struct.pack_into("<I", data, at + size_at, 100)
        with self.assertRaisesRegex(ji.IntakeError, "can't be opened"):
            ji.read_file("sales.xlsx", bytes(data))


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
        self.assertIn("A heading ('Palm Gym (fictional)'), closed by the total row on row 13", reasons[10])
        self.assertIn("The report's footer ('Accrual basis", reasons[16])
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
        # Only a proven total, heading or footer is skipped. Every row below is shaped a bit like
        # one but lacks the proof, so it goes through the usual checks: rejected, money possibly missing.
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        line = ("INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "100.00")
        cases = {
            "a date": ("Total", "10/02/2026", "Total Fitness (fictional)", "J-2", "100.00"),
            "a customer and job": ("Total", "", "Customer A (fictional)", "J-1", "100.00"),
            "a customer and job written as numbers": ("Total", "", "123", "456", "100.00"),
            "a job written as a number": ("Total", "", "", "456", "100.00"),
            "only an invoice number": ("INV-7", "", "", "", ""),
            "only an amount": ("", "", "", "", "50.00"),
            "a total that doesn't add up": ("Total", "", "", "", "99.00"),
            "a total with no amount": ("TOTAL", "", "", "", ""),
            "a lone name never closed by a total": ("Total Fitness (fictional)", "", "", "", ""),
            "a lone number in the wrong column": ("500.00", "", "", "", ""),
        }
        for what, row in cases.items():
            records = [ji.Record(2, line), ji.Record(3, row)]
            result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
            self.assertEqual([], result.skipped, what)
            if what == "a date":  # a complete line whose invoice number happens to be "Total"
                self.assertEqual(["INV-1", "Total"], [r["invoice_id"] for r in result.accepted])
                continue
            self.assertEqual([3], [r["row"] for r in result.rejected], what)
            self.assertTrue(result.rejected[0]["money_missing"], what)
        result = ji.intake(headers, [ji.Record(2, line), ji.Record(3, cases["a total that doesn't add up"])],
                           ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertIn("Looks like a total row ('Total'), but its amount doesn't equal the rows above it",
                      " ".join(result.rejected[0]["reasons"]))

    def test_a_group_total_must_match_the_rows_under_its_own_heading(self):
        headers = ["Group", "Date", "Invoice", "Customer", "Job", "Amount"]
        mapping = ji.suggest_mapping(headers, "invoices")
        rows = [("Bakery (fictional)", "", "", "", "", ""),
                ("", "10/02/2026", "INV-1", "Bakery (fictional)", "J-1", "40.00"),
                ("", "10/03/2026", "INV-2", "Bakery (fictional)", "J-1", "60.00"),
                ("Total for Bakery (fictional)", "", "", "", "", "100.00"),
                ("Gym (fictional)", "", "", "", "", ""),
                ("", "10/04/2026", "INV-3", "Gym (fictional)", "J-2", "25.00"),
                # Equals the run from the file's start (125.00), not the rows under "Gym": not proven.
                ("Total for Gym (fictional)", "", "", "", "", "125.00")]
        records = [ji.Record(n, r) for n, r in enumerate(rows, start=2)]
        result = ji.intake(headers, records, mapping, "invoices", "MM/DD/YYYY")
        self.assertEqual([2, 5], [r["row"] for r in result.skipped])
        self.assertEqual([6, 8], [r["row"] for r in result.rejected])  # the unclosed heading and the bad total
        self.assertTrue(all(r["money_missing"] for r in result.rejected))
        self.assertEqual(["INV-1", "INV-2", "INV-3"], [r["invoice_id"] for r in result.accepted])

    def test_a_named_total_needs_its_own_heading(self):
        headers = ["Group", "Date", "Invoice", "Customer", "Job", "Amount"]
        mapping = ji.suggest_mapping(headers, "invoices")
        sale = ("", "10/02/2026", "INV-1", "Bakery (fictional)", "J-1", "100.00")
        for above in ([], [("Gym (fictional)", "", "", "", "", "")]):  # no heading, or a different one
            rows = [*above, sale, ("Total for Bakery (fictional)", "", "", "", "", "100.00")]
            records = [ji.Record(n, r) for n, r in enumerate(rows, start=2)]
            result = ji.intake(headers, records, mapping, "invoices", "MM/DD/YYYY")
            self.assertEqual([], result.skipped)
            total = result.rejected[-1]
            self.assertEqual(len(rows) + 1, total["row"])
            self.assertTrue(total["money_missing"])
            self.assertIn("Looks like a total row", " ".join(total["reasons"]))

    def test_a_number_or_date_is_never_a_heading_even_when_a_total_closes_it(self):
        # "500.00" in the invoice column may be a misplaced amount; a zero "Total for 500.00" mustn't hide it.
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        for lone in ("500.00", "12.345", "10/02/2026"):
            records = [ji.Record(2, (lone, "", "", "", "")), ji.Record(3, (f"Total for {lone}", "", "", "", "0.00"))]
            result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
            self.assertEqual([], [r["row"] for r in result.skipped if r["row"] == 2], lone)
            self.assertIn(2, [r["row"] for r in result.rejected], lone)
            self.assertTrue(next(r for r in result.rejected if r["row"] == 2)["money_missing"], lone)

    def test_a_footer_is_skipped_only_on_the_last_row(self):
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        line = ("INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "100.00")
        footer = ("Cash basis Tuesday, October 20, 2026", "", "", "", "")
        mapping = ji.suggest_mapping(headers, "invoices")
        last = ji.intake(headers, [ji.Record(2, line), ji.Record(3, footer)], mapping, "invoices", "MM/DD/YYYY")
        self.assertEqual(([3], []), ([r["row"] for r in last.skipped], last.rejected))
        middle = ji.intake(headers, [ji.Record(2, footer), ji.Record(3, line)], mapping, "invoices", "MM/DD/YYYY")
        self.assertEqual(([], [2]), ([r["row"] for r in middle.skipped], [r["row"] for r in middle.rejected]))

    def test_a_row_whose_amount_cant_be_read_stops_totals_from_spanning_it(self):
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        rows = [("INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "40.00"),
                ("INV-2", "10/02/2026", "Bakery (fictional)", "J-1", "sixty"),
                ("Total", "", "", "", "40.00")]
        records = [ji.Record(n, r) for n, r in enumerate(rows, start=2)]
        result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertEqual([], result.skipped)
        self.assertEqual([3, 4], [r["row"] for r in result.rejected])

    def test_an_amount_or_date_above_the_column_names_is_never_skipped_as_a_title(self):
        header = ",Date,Invoice,Customer,Job,Amount"
        # Valid money or not (12.345 has too many decimals), anything written like a number or a date is refused.
        for above in ("100.00", "\"$1,250.00\"", "-45", "10/02/2026", "12.345", "(45.00)", "1.2E3", "15%"):
            data = "\n".join(["Sales report (fictional)", above, header,
                              ",10/02/2026,INV-1,Bakery (fictional),J-1,40.00"]).encode()
            with self.assertRaisesRegex(ji.IntakeError, "Row 2, above the column names, holds .* which looks like an "
                                                        "amount or a date, not a title"):
                ji.read_file("sales.csv", data)
        with self.assertRaisesRegex(ji.IntakeError, "Row 1, above the column names, holds '12.345'"):
            ji.read_file("sales.xlsx", raw_xlsx('<row r="1"><c r="A1"><v>12.345</v></c></row>'
                                                + RAW_HEADER.replace('r="1"', 'r="2"').replace('1"', '2"')))
        with self.assertRaisesRegex(ji.IntakeError, "Row 1, above the column names, holds '100'"):
            ji.read_file("sales.xlsx", raw_xlsx('<row r="1"><c r="A1"><v>100</v></c></row>'
                                                + RAW_HEADER.replace('r="1"', 'r="2"').replace('1"', '2"')))
        # Words are still titles.
        data = b"Sales report (fictional)\nOctober 2026\n" + header.encode() + b"\n,10/02/2026,INV-1,A,J-1,40.00\n"
        self.assertIn("Skipped 2 title lines", ji.read_file("sales.csv", data)[2][0])

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
