from decimal import Decimal
from pathlib import Path
import csv
import io
import unittest

import job_intake as ji

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data" / "marginx"


def load(name, kind):
    headers, rows = ji.read_csv((SAMPLES / name).read_bytes())
    mapping = ji.suggest_mapping(headers, kind)
    return headers, rows, mapping


def texts(report):
    return " | ".join(item["text"] for item in report)


class ReadCsvTests(unittest.TestCase):
    def test_reads_utf8_with_bom_and_keeps_text_as_text(self):
        headers, rows = ji.read_csv("﻿A,B\n=1+1,0012\n".encode("utf-8"))
        self.assertEqual(["A", "B"], headers)
        self.assertEqual("=1+1", rows[0].cells[0])  # never evaluated
        self.assertEqual("0012", rows[0].cells[1])  # no type coercion

    def test_refuses_unreadable_files_with_plain_reasons(self):
        cases = {
            b"": "empty",
            "Café,Amount\n1,2\n".encode("cp1252"): "UTF-8",
            b"OnlyOne\n1\n": "separator",
            b"A,\n1,2\n": "no header",
            b"A,a\n1,2\n": "same header",
            b'A,B\n"unclosed,2\n': "valid CSV",
            b"x" * (ji.MAX_FILE_BYTES + 1): "larger",
        }
        for data, phrase in cases.items():
            with self.subTest(phrase):
                with self.assertRaises(ji.IntakeError) as ctx:
                    ji.read_csv(data)
                self.assertIn(phrase, str(ctx.exception))

    def test_row_numbers_match_the_file_and_separator_only_lines_are_reported(self):
        headers, rows = ji.read_csv(b'Date,Payee,Amount\n\n10/01/2026,A,1.00\n,,\n   \n""\n10/02/2026,,2.00\n')
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual(3, result.accepted[0]["row"])
        # Only the truly empty line 2 is skipped. ",,", a spaces-only line and a quoted
        # empty "" are records: counted and rejected, never silently skipped.
        self.assertEqual([4, 5, 6, 7], [r["row"] for r in result.rejected])
        self.assertEqual(5, result.total_rows)
        self.assertIn("Date is blank", " ".join(result.rejected[0]["reasons"]))
        self.assertIn("1 cells", " ".join(result.rejected[1]["reasons"]))
        self.assertIn("1 cells", " ".join(result.rejected[2]["reasons"]))

    def test_wrong_cell_count_is_reported_per_row_not_dropped(self):
        headers, rows = ji.read_csv(b"Date,Payee,Amount\n10/01/2026,A,1.00\n10/02/2026,B\n")
        result = ji.intake(headers, rows, {"date": "Date", "vendor": "Payee", "amount": "Amount"}, "costs", "MM/DD/YYYY")
        self.assertEqual(1, len(result.accepted))
        self.assertEqual(3, result.rejected[0]["row"])
        self.assertIn("2 cells", result.rejected[0]["reasons"][0])

    def test_reserved_looking_headers_are_ordinary_columns(self):
        headers, rows = ji.read_csv(b"__row__,__shape_error__,Date,Payee,Amount\nx,y,10/01/2026,A,1.00\n")
        result = ji.intake(headers, rows, {"date": "Date", "vendor": "Payee", "amount": "Amount"}, "costs", "MM/DD/YYYY")
        self.assertEqual(1, len(result.accepted))
        self.assertEqual(2, result.accepted[0]["row"])
        self.assertEqual([], result.rejected)


class MappingTests(unittest.TestCase):
    def test_suggestions_match_common_export_headers(self):
        headers, _, mapping = load("fictional_invoices.csv", "invoices")
        self.assertEqual({"invoice_id": "Invoice #", "date": "Date", "customer": "Customer Name", "amount": "Total",
                          "job_id": "Job No", "description": "Description"}, mapping)
        self.assertEqual([], ji.validate_mapping(mapping, headers, "invoices"))
        _, _, cost_map = load("fictional_costs.csv", "costs")
        self.assertEqual(("Payee", "Bill No", "Job", "Type"),
                         (cost_map["vendor"], cost_map["cost_id"], cost_map["job_id"], cost_map["cost_type"]))

    def test_unrecognised_headers_are_left_for_the_owner(self):
        mapping = ji.suggest_mapping(["Cust Nm", "Amt (USD)", "When"], "invoices")
        self.assertIsNone(mapping["customer"])
        self.assertEqual("Amt (USD)", mapping["amount"])
        self.assertIsNone(mapping["date"])

    def test_invalid_mappings_are_refused(self):
        headers = ["Date", "Payee", "Amount"]
        problems = ji.validate_mapping({"date": "Date", "vendor": "Date", "amount": None}, headers, "costs")
        self.assertTrue(any("Amount" in p for p in problems))
        self.assertTrue(any("more than one field" in p for p in problems))
        self.assertTrue(ji.validate_mapping({"date": "Nope", "vendor": "Payee", "amount": "Amount"}, headers, "costs"))
        with self.assertRaises(ji.IntakeError):
            ji.intake(headers, [], {"date": "Date"}, "costs", "MM/DD/YYYY")

    def test_date_format_is_suggested_only_when_unambiguous(self):
        self.assertEqual("MM/DD/YYYY", ji.suggest_date_format(["10/01/2026", "12/31/2026"]))
        self.assertIsNone(ji.suggest_date_format(["10/01/2026", "01/02/2026"]))  # fits MM/DD and DD/MM
        self.assertIsNone(ji.suggest_date_format(["10/01/2026", "2026-10-06"]))  # mixed
        self.assertIsNone(ji.suggest_date_format([]))
        with self.assertRaises(ji.IntakeError):
            ji.intake(["Date"], [], {}, "costs", "guess")


class InvoiceIntakeTests(unittest.TestCase):
    def setUp(self):
        headers, rows, mapping = load("fictional_invoices.csv", "invoices")
        self.result = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")

    def test_every_row_is_accepted_or_rejected_with_a_reason(self):
        r = self.result
        self.assertEqual(r.total_rows, len(r.accepted) + len(r.rejected))
        reasons = {item["row"]: " ".join(item["reasons"]) for item in r.rejected}
        self.assertIn("Exact duplicate of row 6", reasons[7])
        self.assertIn("doesn't match MM/DD/YYYY", reasons[8])
        self.assertIn("Customer is blank", reasons[10])
        self.assertIn("max 2 decimals", reasons[11])
        self.assertEqual({7, 8, 10, 11}, set(reasons))

    def test_money_is_exact_and_multi_line_invoices_are_kept(self):
        amounts = [r["amount"] for r in self.result.accepted]
        self.assertTrue(all(isinstance(a, Decimal) for a in amounts))
        self.assertIn(Decimal("1250.00"), amounts)
        self.assertEqual(2, sum(1 for r in self.result.accepted if r["invoice_id"] == "FIC-1002"))
        self.assertEqual("2026-10-01", self.result.accepted[0]["date"])

    def test_whats_missing_report(self):
        report = texts(ji.missing_report(self.result))
        self.assertIn("4 rows of 10 couldn't be imported", report)
        self.assertIn("1 of 6 imported invoices have no job number", report)
        self.assertIn("1 credit or refund line were imported", report)
        self.assertIn("span more than one line (for example FIC-1002)", report)
        self.assertIn("6 invoices imported, dated 2026-10-01 to 2026-10-07", report)
        self.assertNotIn("profit is", report.lower())

    def test_no_job_column_is_a_gap(self):
        headers, rows, mapping = load("fictional_invoices.csv", "invoices")
        mapping["job_id"] = None
        report = texts(ji.missing_report(ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")))
        self.assertIn("No job number column was chosen", report)


class CostIntakeTests(unittest.TestCase):
    def setUp(self):
        headers, rows, mapping = load("fictional_costs.csv", "costs")
        self.result = ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY")

    def test_negative_cost_is_rejected_and_formula_text_is_kept_as_text(self):
        reasons = {item["row"]: " ".join(item["reasons"]) for item in self.result.rejected}
        self.assertEqual({9}, set(reasons))
        self.assertIn("negative", reasons[9])
        memo = next(r["memo"] for r in self.result.accepted if r["cost_id"] == "B-82")
        self.assertEqual('=HYPERLINK("http://example.invalid")', memo)

    def test_whats_missing_report(self):
        report = texts(ji.missing_report(self.result))
        self.assertIn("3 of 8 imported costs aren't linked to a job", report)
        self.assertIn("1 of 8 imported costs have no cost type", report)
        self.assertIn("No labor costs were found", report)

    def test_labor_present_removes_the_labor_gap(self):
        headers, rows = ji.read_csv(b"Date,Payee,Type,Amount\n10/01/2026,Crew,Labor,100.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertNotIn("No labor costs", texts(ji.missing_report(result)))

    def test_no_cost_type_column_is_a_gap(self):
        headers, rows = ji.read_csv(b"Date,Payee,Amount\n10/01/2026,A,1.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertIn("No cost type column was chosen", texts(ji.missing_report(result)))


class DuplicateTests(unittest.TestCase):
    MAP = {"date": "Date", "vendor": "Payee", "amount": "Amount"}

    def run_costs(self, data):
        headers, rows = ji.read_csv(data)
        return ji.intake(headers, rows, self.MAP, "costs", "MM/DD/YYYY")

    def test_rows_differing_only_in_unmapped_columns_are_both_kept(self):
        result = self.run_costs(b"Date,Payee,Amount,Note\n10/01/2026,A,1.00,first\n10/01/2026,A,1.00,second\n")
        self.assertEqual(2, len(result.accepted))

    def test_rows_differing_only_in_whitespace_are_both_kept(self):
        result = self.run_costs(b"Date,Payee,Amount\n10/01/2026,A,1.00\n10/01/2026,A ,1.00\n")
        self.assertEqual(2, len(result.accepted))

    def test_identical_rows_are_rejected_once(self):
        result = self.run_costs(b"Date,Payee,Amount\n10/01/2026,A,1.00\n10/01/2026,A,1.00\n")
        self.assertEqual(1, len(result.accepted))
        self.assertIn("Exact duplicate of row 2", result.rejected[0]["reasons"][0])


class UploadGateTests(unittest.TestCase):
    def test_own_file_needs_made_up_confirmation(self):
        self.assertTrue(ji.upload_allowed(True, False, False))
        self.assertFalse(ji.upload_allowed(False, True, False))
        self.assertFalse(ji.upload_allowed(False, False, True))
        self.assertTrue(ji.upload_allowed(False, True, True))


class ExportSafetyTests(unittest.TestCase):
    MAP = {"date": "Date", "vendor": "Payee", "amount": "Amount"}

    def export(self, data):
        headers, rows = ji.read_csv(data)
        result = ji.intake(headers, rows, self.MAP, "costs", "MM/DD/YYYY")
        return list(csv.reader(io.StringIO(ji.rejected_rows_csv(result))))

    def test_formula_headers_are_neutralized_in_the_export(self):
        exported = self.export(b'Date,Payee,Amount,"=HYPERLINK(""http://x.invalid"")"\n10/01/2026,A,-5,n\n')
        self.assertEqual("'=HYPERLINK(\"http://x.invalid\")", exported[0][-1])

    def test_original_headers_round_trip_and_export_names_never_collide(self):
        data = b"Date,Payee,Amount,marginx_row,marginx_reasons, Note \n10/01/2026,A,-5,a,b,c\n"
        exported = self.export(data)
        self.assertEqual(["marginx_row_2", "marginx_reasons_2", "Date", "Payee", "Amount", "marginx_row",
                          "marginx_reasons", " Note "], exported[0])
        # Re-uploading the fix file works: headers are unique and readable.
        fixed = io.StringIO()
        csv.writer(fixed).writerows(exported)
        headers, rows = ji.read_csv(fixed.getvalue().encode("utf-8"))
        self.assertIn(" Note ", headers)
        self.assertEqual(1, len(rows))

    def test_extra_cell_names_avoid_collisions(self):
        exported = self.export(b"Date,Payee,Amount,extra_cell_1\n10/01/2026,A,1.00,x,OVER\n")
        self.assertEqual("extra_cell_1_2", exported[0][-1])

    def test_rows_to_fix_export_is_lossless(self):
        headers, rows = ji.read_csv(
            b"Date,Payee,Note,Amount\n10/01/2026,A,keep me,-5\n10/02/2026,B\n10/03/2026,C,x,1.00,EXTRA\n")
        result = ji.intake(headers, rows, {"date": "Date", "vendor": "Payee", "amount": "Amount"}, "costs", "MM/DD/YYYY")
        exported = list(csv.reader(io.StringIO(ji.rejected_rows_csv(result))))
        self.assertEqual(["marginx_row", "marginx_reasons", "Date", "Payee", "Note", "Amount", "extra_cell_1"], exported[0])
        self.assertEqual(["2", "10/01/2026", "A", "keep me", "'-5", ""], [exported[1][0], *exported[1][2:]])
        self.assertEqual(["3", "10/02/2026", "B", "", "", ""], [exported[2][0], *exported[2][2:]])
        self.assertEqual(["4", "10/03/2026", "C", "x", "1.00", "EXTRA"], [exported[3][0], *exported[3][2:]])

    def test_rejected_rows_export_neutralizes_formulas(self):
        headers, rows = ji.read_csv(b'Date,Payee,Amount\n10/01/2026,"=cmd|\' /C calc\'!A0",-5\n')
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        exported = list(csv.reader(io.StringIO(ji.rejected_rows_csv(result))))
        self.assertEqual("'=cmd|' /C calc'!A0", exported[1][3])
        self.assertTrue(exported[1][1].startswith("Cost is negative"))
        for prefix in ("=", "+", "-", "@"):
            self.assertTrue(ji.safe_cell(prefix + "x").startswith("'"))
        self.assertEqual("plain", ji.safe_cell("plain"))

    def test_empty_import_reports_nothing_imported(self):
        headers, rows = ji.read_csv(b"Date,Payee,Amount\n,,\n")
        report = texts(ji.missing_report(ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")))
        self.assertIn("1 row of 1 couldn't be imported", report)
        self.assertIn("No costs were imported", report)


if __name__ == "__main__":
    unittest.main()
