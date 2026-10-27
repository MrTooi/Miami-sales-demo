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

    def test_row_numbers_are_spreadsheet_records_even_with_multiline_cells(self):
        headers, rows = ji.read_csv(b'Date,Payee,Amount\n10/01/2026,"two\nlines",1.00\n10/02/2026,,2.00\n')
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual(2, result.accepted[0]["row"])
        self.assertEqual(3, result.rejected[0]["row"])  # spreadsheet row 3, though text line 4

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

    def test_file_type_is_detected_from_headers(self):
        self.assertEqual("invoices", ji.detect_kind(load("fictional_invoices.csv", "invoices")[0]))
        self.assertEqual("costs", ji.detect_kind(load("fictional_costs.csv", "costs")[0]))
        self.assertEqual("invoices", ji.detect_kind(["Invoice", "Date", "Customer", "Amount"]))
        self.assertEqual("invoices", ji.detect_kind(["Num", "Date", "Bill To", "Amount", "Customer"]))  # "bill to" isn't a cost word
        self.assertEqual("costs", ji.detect_kind(["Date", "Vendor", "Amount"]))
        self.assertEqual("costs", ji.detect_kind(["Bill No", "Date", "Supplier", "Total"]))

    def test_undecidable_file_type_returns_none(self):
        self.assertIsNone(ji.detect_kind(["Num", "Date", "Name", "Amount"]))  # reads as either
        self.assertIsNone(ji.detect_kind(["Invoice", "Date", "Customer", "Vendor", "Amount"]))  # complete for both
        self.assertIsNone(ji.detect_kind(["A", "B"]))

    def test_balance_columns_are_refused_as_the_amount_even_when_chosen_by_hand(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Open Balance\nINV-1,10/31/2026,Acme,40.00\n")
        mapping = {"invoice_id": "Invoice", "date": "Date", "customer": "Customer", "amount": "Open Balance"}
        problems = ji.validate_mapping(mapping, headers, "invoices")
        self.assertTrue(any("balance still owed" in p for p in problems))
        with self.assertRaises(ji.IntakeError):  # zero accepted lines: intake refuses the mapping
            ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")
        for header in ("Open Balance", "Amount Due", "Balance", "Outstanding", "Unpaid Amount", "Remaining"):
            self.assertTrue(ji.is_balance_column(header), header)
        for header in ("Amount", "Total", "Invoice Total", "Line Amount"):
            self.assertFalse(ji.is_balance_column(header), header)
        cost_map = {"date": "Date", "vendor": "Vendor", "amount": "Balance Due"}
        self.assertTrue(ji.validate_mapping(cost_map, ["Date", "Vendor", "Balance Due"], "costs"))

    def test_bank_style_exports_are_never_auto_classified_as_costs(self):
        for headers in (["Date", "Payee", "Amount"], ["Date", "Description", "Payee", "Amount"],
                        ["Date", "Vendor", "Amount", "Balance"], ["Posted Date", "Payee", "Debit", "Amount"]):
            with self.subTest(headers=headers):
                self.assertIsNone(ji.detect_kind(headers))
        # Real bill/expense evidence still auto-detects.
        self.assertEqual("costs", ji.detect_kind(load("fictional_costs.csv", "costs")[0]))
        self.assertEqual("costs", ji.detect_kind(["Date", "Payee", "Bill No", "Amount"]))
        self.assertEqual("costs", ji.detect_kind(["Date", "Vendor", "Amount"]))

    def test_invoice_shaped_payment_exports_are_asked_about(self):
        for headers in (["Invoice", "Date", "Customer", "Amount", "Deposit"],
                        ["Invoice", "Date", "Customer", "Payment Amount", "Amount"],
                        ["Invoice", "Date", "Customer", "Amount", "Payout ID"],
                        ["Invoice", "Date", "Customer", "Amount", "Received"]):
            with self.subTest(headers=headers):
                self.assertIsNone(ji.detect_kind(headers))
        # Ordinary invoice files stay automatic, including a "Payment Terms" field.
        self.assertEqual("invoices", ji.detect_kind(load("fictional_invoices.csv", "invoices")[0]))
        self.assertEqual("invoices", ji.detect_kind(["Invoice", "Date", "Customer", "Payment Terms", "Amount"]))
        self.assertEqual("invoices", ji.detect_kind(["Num", "Date", "Customer", "Amount", "Open Balance"]))  # QuickBooks list

    def test_cost_shaped_payout_and_settlement_exports_are_asked_about(self):
        for headers in (["Date", "Vendor", "Amount", "Payout ID"], ["Date", "Vendor", "Amount", "Settlement Date"],
                        ["Bill No", "Date", "Vendor", "Payment Amount", "Amount"], ["Date", "Supplier", "Transfer", "Amount"]):
            with self.subTest(headers=headers):
                self.assertIsNone(ji.detect_kind(headers))
        # Real bills stay automatic, including a QuickBooks bill list with Open Balance.
        self.assertEqual("costs", ji.detect_kind(load("fictional_costs.csv", "costs")[0]))
        self.assertEqual("costs", ji.detect_kind(["Num", "Date", "Vendor", "Amount", "Open Balance"]))

    def test_line_amount_and_invoice_total_are_never_picked_silently(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Line Amount,Invoice Total\n"
                                    b"INV-1,10/31/2026,Acme,40.00,100.00\nINV-1,10/31/2026,Acme,60.00,100.00\n")
        self.assertIsNone(ji.suggest_mapping(headers, "invoices")["amount"])  # the owner is asked
        mapping = {"invoice_id": "Invoice", "date": "Date", "customer": "Customer", "amount": "Line Amount"}
        result = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")
        self.assertEqual([Decimal("40.00"), Decimal("60.00")], [r["amount"] for r in result.accepted])
        # A single clear amount column still needs no question.
        self.assertEqual("Line Amount", ji.suggest_mapping(["Invoice", "Date", "Customer", "Line Amount"], "invoices")["amount"])
        self.assertEqual("Total", ji.suggest_mapping(["Invoice", "Date", "Customer", "Total"], "invoices")["amount"])

    def test_money_paid_or_received_is_refused_as_the_amount_even_when_chosen_by_hand(self):
        for kind, base in (("invoices", {"invoice_id": "Invoice", "date": "Date", "customer": "Customer"}),
                           ("costs", {"date": "Date", "vendor": "Vendor"})):
            for header in ("Payment Amount", "Payout Amount", "Amount Paid", "Amount Received", "Deposit",
                           "Settlement Amount", "Transfer Amount"):
                with self.subTest(kind=kind, header=header):
                    headers = [*base.values(), header]
                    problems = ji.validate_mapping({**base, "amount": header}, headers, kind)
                    self.assertTrue(any("money paid or received" in p for p in problems), problems)
                    _, rows = ji.read_csv((",".join(headers) + "\nA,10/31/2026,X,40.00\n").encode()
                                          if kind == "invoices" else (",".join(headers) + "\n10/31/2026,X,40.00\n").encode())
                    with self.assertRaises(ji.IntakeError):  # nothing is imported
                        ji.intake(headers, rows, {**base, "amount": header}, kind, "MM/DD/YYYY")
        # Ordinary amount columns are unaffected.
        for header in ("Amount", "Total", "Line Amount", "Invoice Total"):
            self.assertFalse(ji.is_paid_column(header), header)

    def test_bank_credit_columns_are_cash_movements(self):
        # A file with a Credit column is asked about, never auto-read as costs or sales.
        for headers in (["Date", "Vendor", "Amount", "Credit"], ["Date", "Vendor", "Debit", "Credit", "Amount"],
                        ["Invoice", "Date", "Customer", "Amount", "Credit"]):
            with self.subTest(headers=headers):
                self.assertIsNone(ji.detect_kind(headers))
        # A credit column is refused as the amount, even when chosen by hand.
        for kind, base in (("costs", {"date": "Date", "vendor": "Vendor"}),
                           ("invoices", {"invoice_id": "Invoice", "date": "Date", "customer": "Customer"})):
            for header in ("Credit", "Credit Amount", "Credits"):
                with self.subTest(kind=kind, header=header):
                    problems = ji.validate_mapping({**base, "amount": header}, [*base.values(), header], kind)
                    self.assertTrue(any("money paid or received" in p for p in problems), problems)
        # Invoice credit lines stay ordinary negative amounts (the sample's reprint credit).
        headers, rows, mapping = load("fictional_invoices.csv", "invoices")
        self.assertEqual("invoices", ji.detect_kind(headers))
        self.assertIn(Decimal("-45.00"), [r["amount"] for r in ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line").accepted])

    def test_a_sales_file_with_payment_rows_is_refused_whole(self):
        # Before issue #128 the payment row was left out and the rest counted. A payment's type alone
        # never proves it can be left out (S9), and a file mixing sales with payments adds the same
        # money twice, so the whole file is refused as a sales file (S1, step 1).
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Type,Amount\n"
                                    b"INV-1,10/31/2026,Acme,Invoice,100.00\nINV-1,10/31/2026,Acme,Payment,100.00\n"
                                    b"INV-2,10/31/2026,Acme,Credit Memo,-20.00\n")
        self.assertEqual("invoices", ji.detect_kind(headers))
        reason = ji.sales_file_refusal(headers, rows)
        self.assertIn("mixes sales with payments or deposits (row 3 is 'Payment')", reason)
        self.assertIn("nothing from it was used", reason)
        with self.assertRaisesRegex(ji.IntakeError, "mixes sales with payments"):
            ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        # The same rule in every type column, and for deposits, transfers and bank credits too.
        for header, value in (("Transaction Type", "Deposit"), ("Txn Type", "Receive Payment"), ("Type", "Bank Credit"),
                              ("Type", "Transfer"), ("Type", "Bill Payment (Check)")):
            headers, rows = ji.read_csv(f"Invoice,Date,Customer,{header},Amount\nI-1,10/31/2026,Acme,Invoice,1.00\n"
                                        f"I-2,10/31/2026,Acme,{value},1.00\n".encode())
            with self.subTest(value), self.assertRaisesRegex(ji.IntakeError, "mixes sales with payments"):
                ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        # A costs file keeps its own rule: a transfer row is listed, never counted (as before).
        headers, rows = ji.read_csv(b"Date,Vendor,Type,Amount\n10/31/2026,Bank,Transfer,500.00\n")
        self.assertEqual([], ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY").accepted)
        # A sales file with no payment rows is read as before.
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Type,Amount\nI-1,10/31/2026,Acme,Invoice,1.00\n")
        self.assertIsNone(ji.sales_file_refusal(headers, rows))

    def test_transfer_rows_in_a_cost_file_are_rejected_not_imported_as_expenses(self):
        headers, rows = ji.read_csv(b"Date,Vendor,Type,Amount\n10/31/2026,Paper Co,Transfer,500.00\n"
                                    b"10/31/2026,Paper Co,Materials,80.00\n11/01/2026,Ink Co,Bill Payment (Check),80.00\n"
                                    b"11/02/2026,Sign Co,Check,45.00\n")
        self.assertEqual("costs", ji.detect_kind(headers))
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual([3, 5], [r["row"] for r in result.accepted])  # materials and an expense paid by check
        self.assertEqual([2, 4], [r["row"] for r in result.rejected])
        self.assertTrue(all("not a cost" in " ".join(r["reasons"]) for r in result.rejected))
        # A fee for moving money is a cost, not the money moving.
        headers, rows = ji.read_csv(b"Date,Vendor,Type,Amount\n10/31/2026,Square,Payment processing fees,2.90\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual(([2], []), ([r["row"] for r in result.accepted], result.rejected))

    def test_bank_credit_rows_are_rejected_but_credit_memos_and_card_charges_stay(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Type,Amount\n"
                                    b"INV-1,10/31/2026,Demo,Invoice,100.00\n"
                                    b"INV-3,10/31/2026,Demo,Credit,50.00\nINV-4,10/31/2026,Demo,Credit Memo,-20.00\n"
                                    b"INV-5,10/31/2026,Demo,Credit Note,-5.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertEqual([2, 4, 5], [r["row"] for r in result.accepted])
        # A bare "Credit" is unclear (money may be missing). (A bank credit in a sales file refuses the
        # whole file: test_a_sales_file_with_payment_rows_is_refused_whole.)
        self.assertEqual([(3, True)], [(r["row"], r["money_missing"]) for r in result.rejected])
        headers, rows = ji.read_csv(b"Date,Vendor,Type,Amount\n10/31/2026,Paper Co,Credit Card Charge,80.00\n"
                                    b"10/31/2026,Bank,Credit,500.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual([2], [r["row"] for r in result.accepted])
        self.assertEqual([3], [r["row"] for r in result.rejected])

    def test_unnumbered_cost_days_group_across_leading_zero_spellings(self):
        headers, rows = ji.read_csv(b"Date,Vendor,Memo,Amount\n"
                                    b"10/1/2026,Paper Co,Vinyl,300.00\n10/01/2026,Paper Co,Ink,300.00\n")
        self.assertEqual({"label": "Paper Co on 10/1/2026 (no bill number)", "lines": 2},
                         ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "costs"), "costs"))

    def test_row_types_that_mention_money_moving_are_matched_whole_or_refused(self):
        headers, rows = ji.read_csv(b"Date,Vendor,Type,Amount\n10/31/2026,Square,Payment processing fees,2.90\n"
                                    b"10/31/2026,Bank,Transfer,500.00\n10/31/2026,Square,Payout net of fees,40.00\n"
                                    b"10/31/2026,Bank,Transfer less fees,40.00\n10/31/2026,Bank,Wire fee,15.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY", "line")
        self.assertEqual([2, 6], [r["row"] for r in result.accepted])  # the two fees are costs
        self.assertEqual([(3, False), (4, True), (5, True)], [(r["row"], r["money_missing"]) for r in result.rejected])
        self.assertIn("isn't a recognized posted cost", " ".join(result.rejected[1]["reasons"]))
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Type,Amount\nI-1,10/31/2026,Demo,Invoice,100.00\n"
                                    b"I-2,10/31/2026,Square,Payout net of fees,40.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertEqual(([2], [3]), ([r["row"] for r in result.accepted], [r["row"] for r in result.rejected]))
        self.assertTrue(result.rejected[0]["money_missing"])

    def test_labeled_subtotal_rows_are_never_counted_even_under_a_line_amount_header(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Line Amount\n"
                                    b"INV-1,10/31/2026,Acme,Sign,40.00\nINV-1,10/31/2026,Acme,Install,60.00\n"
                                    b"INV-1,10/31/2026,Acme,Subtotal,100.00\nINV-2,10/31/2026,Acme,Total,75.00\n")
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertIsNone(ji.amount_scope_question(headers, rows, mapping, "invoices"))
        self.assertEqual([], ji.subtotal_questions(headers, rows, mapping, "invoices"))  # labeled: no question needed
        result = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")
        # INV-2 has one line described "Total": that is its own amount.
        self.assertEqual([Decimal("40.00"), Decimal("60.00"), Decimal("75.00")], [r["amount"] for r in result.accepted])
        self.assertEqual([4], [r["row"] for r in result.rejected])
        self.assertIn("labeled 'Subtotal'", " ".join(result.rejected[0]["reasons"]))

    def test_invoice_with_only_summary_rows_is_never_counted_twice(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Amount\n"
                                    b"A,10/31/2026,Acme,Subtotal,100.00\nA,10/31/2026,Acme,Total,100.00\n"
                                    b"B,10/31/2026,Acme,Total,75.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertEqual([Decimal("75.00")], [r["amount"] for r in result.accepted])  # one "Total" row stays
        self.assertEqual([2, 3], [r["row"] for r in result.rejected])
        self.assertTrue(all("only summary rows" in " ".join(r["reasons"]) for r in result.rejected))

    def test_unlabeled_sum_lines_are_asked_about_under_a_line_amount_header_too(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Line Amount\n"
                                    b"INV-1,10/31/2026,Acme,Sign,40.00\nINV-1,10/31/2026,Acme,Install,60.00\n"
                                    b"INV-1,10/31/2026,Acme,Stand,100.00\n")
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertEqual([4], [q["row"] for q in ji.subtotal_questions(headers, rows, mapping, "invoices")])
        with self.assertRaises(ji.IntakeError):
            ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")
        kept = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", None, {4: False})
        self.assertEqual([Decimal("40.00"), Decimal("60.00"), Decimal("100.00")], [r["amount"] for r in kept.accepted])
        # A clean line-amount file is not asked anything.
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Line Amount\nA,10/31/2026,X,40.00\n"
                                    b"A,10/31/2026,X,60.00\nA,10/31/2026,X,70.00\n")
        self.assertEqual([], ji.subtotal_questions(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices"))

    def test_repeated_invoice_total_is_never_counted_on_each_line(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Invoice Total\n"
                                    b"INV-1,10/31/2026,Acme,Banner,100.00\nINV-1,10/31/2026,Acme,Install,100.00\n"
                                    b"INV-2,10/31/2026,Acme,Decal,25.00\n")
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertEqual("Invoice Total", mapping["amount"])
        result = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")
        self.assertEqual([Decimal("25.00")], [r["amount"] for r in result.accepted])  # one-line invoice is fine
        self.assertEqual([2, 3], [r["row"] for r in result.rejected])
        self.assertTrue(all("whole invoice's total" in " ".join(r["reasons"]) for r in result.rejected))
        self.assertIn("2 rows of 3 couldn't be imported", texts(ji.missing_report(result)))
        # Choosing a line amount column instead imports every line.
        lines = ji.read_csv(b"Invoice,Date,Customer,Line Amount,Invoice Total\n"
                            b"INV-1,10/31/2026,Acme,40.00,100.00\nINV-1,10/31/2026,Acme,60.00,100.00\n")
        result = ji.intake(*lines, {"invoice_id": "Invoice", "date": "Date", "customer": "Customer",
                                    "amount": "Line Amount"}, "invoices", "MM/DD/YYYY")
        self.assertEqual([Decimal("40.00"), Decimal("60.00")], [r["amount"] for r in result.accepted])

    def test_repeated_bill_total_is_never_counted_on_each_line(self):
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Memo,Bill Total\n"
                                    b"B-1,10/31/2026,Paper Co,Vinyl,300.00\nB-1,10/31/2026,Paper Co,Ink,300.00\n"
                                    b"B-2,10/31/2026,Paper Co,Tape,12.00\n")
        mapping = ji.suggest_mapping(headers, "costs")
        result = ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY")
        self.assertEqual([Decimal("12.00")], [r["amount"] for r in result.accepted])
        self.assertEqual([2, 3], [r["row"] for r in result.rejected])
        self.assertTrue(all("whole bill's total" in " ".join(r["reasons"]) for r in result.rejected))
        # Without bill numbers, repeats can't be caught, so a bill total isn't accepted at all.
        problems = ji.validate_mapping({"date": "Date", "vendor": "Vendor", "amount": "Bill Total"},
                                       ["Date", "Vendor", "Bill Total"], "costs")
        self.assertTrue(any("bill number column" in p for p in problems), problems)

    def test_generic_total_repeated_on_every_line_is_asked_about(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Total\n"
                                    b"INV-1,10/31/2026,Acme,Banner,100.00\nINV-1,10/31/2026,Acme,Install,100.00\n"
                                    b"INV-2,10/31/2026,Acme,Decal,25.00\n")
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertEqual({"label": "invoice INV-1", "lines": 2}, ji.amount_scope_question(headers, rows, mapping, "invoices"))
        with self.assertRaises(ji.IntakeError):  # never imported until the owner answers
            ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY")
        per_line = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line")
        self.assertEqual([Decimal("100.00"), Decimal("100.00"), Decimal("25.00")], [r["amount"] for r in per_line.accepted])
        per_invoice = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "document")
        self.assertEqual([Decimal("25.00")], [r["amount"] for r in per_invoice.accepted])
        self.assertEqual([2, 3], [r["row"] for r in per_invoice.rejected])
        self.assertTrue(all("whole invoice's total" in " ".join(r["reasons"]) for r in per_invoice.rejected))

    def test_different_amounts_on_an_invoice_still_ask(self):
        # Different amounts don't prove per-line meaning: 40 + 60 may sit beside a 100 summary line.
        headers, rows, mapping = load("fictional_invoices.csv", "invoices")
        self.assertEqual({"label": "invoice FIC-1002", "lines": 2}, ji.amount_scope_question(headers, rows, mapping, "invoices"))

    def test_possible_subtotal_lines_are_asked_about_not_decided(self):
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Total\n"
                                    b"INV-1,10/31/2026,Acme,Banner,40.00\nINV-1,10/31/2026,Acme,Install,60.00\n"
                                    b"INV-1,10/31/2026,Acme,Stand,100.00\n")
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertEqual([{"row": 4, "label": "invoice INV-1", "amount": "100.00"}],
                         ji.subtotal_questions(headers, rows, mapping, "invoices"))
        with self.assertRaises(ji.IntakeError):  # never decided without the owner
            ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line")
        real = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line", {4: False})
        self.assertEqual([Decimal("40.00"), Decimal("60.00"), Decimal("100.00")], [r["amount"] for r in real.accepted])
        summary = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line", {4: True})
        self.assertEqual([Decimal("40.00"), Decimal("60.00")], [r["amount"] for r in summary.accepted])
        self.assertEqual([4], [r["row"] for r in summary.rejected])
        self.assertIn("Subtotal of invoice INV-1", " ".join(summary.rejected[0]["reasons"]))

    def test_zero_negative_and_non_adding_lines(self):
        def questions(body):
            headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Total\n" + body)
            return ji.subtotal_questions(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices")
        # Zero lines never count as subtotals; amounts that don't add up need no question.
        self.assertEqual([], questions(b"A,10/31/2026,X,Free proof,0.00\nA,10/31/2026,X,Setup,0.00\nA,10/31/2026,X,Note,0.00\n"))
        self.assertEqual([], questions(b"A,10/31/2026,X,Sign,40.00\nA,10/31/2026,X,Stand,60.00\nA,10/31/2026,X,Vinyl,70.00\n"))
        # A discount line can make a real line equal the others' sum: asked, never decided.
        self.assertEqual([4], [q["row"] for q in questions(
            b"A,10/31/2026,X,Sign,100.00\nA,10/31/2026,X,Discount,-20.00\nA,10/31/2026,X,Install,80.00\n")])
        # Two lines are covered by the amount question, not this one.
        self.assertEqual([], questions(b"A,10/31/2026,X,Sign,100.00\nA,10/31/2026,X,Stand,100.00\n"))

    def test_no_amount_question_when_the_file_shows_what_the_amount_means(self):
        # One line per invoice, or a column named per line or per invoice.
        for csv_text in (b"Invoice,Date,Customer,Total\nA,10/31/2026,X,100.00\nB,10/31/2026,X,100.00\n",
                         b"Invoice,Date,Customer,Line Amount\nA,10/31/2026,X,100.00\nA,10/31/2026,X,100.00\n",
                         b"Invoice,Date,Customer,Invoice Total\nA,10/31/2026,X,100.00\nA,10/31/2026,X,100.00\n"):
            with self.subTest(csv=csv_text):
                headers, rows = ji.read_csv(csv_text)
                self.assertIsNone(ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices"))
        with self.assertRaises(ji.IntakeError):
            ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY", "sometimes")

    def test_bill_numbers_are_grouped_per_vendor(self):
        # Two vendors can each issue bill B-1; those are two one-line bills, not one two-line bill.
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Bill Total\n"
                                    b"B-1,10/31/2026,Paper Co,300.00\nB-1,10/31/2026,Ink Co,300.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual([Decimal("300.00"), Decimal("300.00")], [r["amount"] for r in result.accepted])
        self.assertEqual([], result.rejected)
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Amount\n"
                                    b"B-1,10/31/2026,Paper Co,50.00\nB-1,10/31/2026,Ink Co,50.00\n")
        self.assertIsNone(ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "costs"), "costs"))
        # The report counts them as two bills too.
        result = ji.intake(*ji.read_csv(b"Bill No,Date,Vendor,Amount\n"
                                        b"B-1,10/31/2026,Paper Co,50.00\nB-1,10/31/2026,Ink Co,50.00\n"),
                           {"date": "Date", "vendor": "Vendor", "amount": "Amount", "cost_id": "Bill No"},
                           "costs", "MM/DD/YYYY")
        report = texts(ji.missing_report(result))
        self.assertIn("2 cost lines imported (2 bills)", report)
        self.assertNotIn("more than one line", report)
        # The same vendor's bill on two lines with one repeated amount is asked about.
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Memo,Amount\n"
                                    b"B-1,10/31/2026,Paper Co,Vinyl,50.00\nB-1,10/31/2026,Paper Co,Ink,50.00\n")
        self.assertEqual({"label": "bill B-1 from Paper Co", "lines": 2},
                         ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "costs"), "costs"))

    def test_each_document_is_judged_on_its_own_lines(self):
        # Invoice A's different amounts don't settle what invoice B's repeated 100s mean.
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Total\n"
                                    b"A,10/31/2026,X,Sign,40.00\nA,10/31/2026,X,Stand,60.00\n"
                                    b"B,10/31/2026,Y,Banner,100.00\nB,10/31/2026,Y,Install,100.00\n")
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertEqual({"label": "invoice B", "lines": 2}, ji.amount_scope_question(headers, rows, mapping, "invoices"))
        # An unreadable amount isn't evidence that the lines differ.
        headers, rows = ji.read_csv(b"Invoice,Date,Customer,Description,Total\n"
                                    b"B,10/31/2026,Y,Banner,100.00\nB,10/31/2026,Y,Install,100.00\n"
                                    b"B,10/31/2026,Y,Note,n/a\n")
        self.assertEqual({"label": "invoice B", "lines": 3},
                         ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices"))

    def test_cost_lines_without_bill_numbers_are_asked_about_when_amounts_repeat(self):
        headers, rows = ji.read_csv(b"Date,Vendor,Memo,Amount\n"
                                    b"10/31/2026,Paper Co,Vinyl,300.00\n10/31/2026,Paper Co,Ink,300.00\n"
                                    b"11/01/2026,Paper Co,Tape,300.00\n10/31/2026,Ink Co,Toner,300.00\n")
        mapping = ji.suggest_mapping(headers, "costs")
        self.assertEqual({"label": "Paper Co on 10/31/2026 (no bill number)", "lines": 2},
                         ji.amount_scope_question(headers, rows, mapping, "costs"))
        with self.assertRaises(ji.IntakeError):
            ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY")
        self.assertEqual(4, len(ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY", "line").accepted))
        whole = ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY", "document")
        self.assertEqual([4, 5], [r["row"] for r in whole.accepted])  # other day, other vendor: one line each
        self.assertEqual([2, 3], [r["row"] for r in whole.rejected])
        # One line per vendor per day needs no question.
        headers, rows = ji.read_csv(b"Date,Vendor,Memo,Amount\n"
                                    b"10/31/2026,Paper Co,Vinyl,300.00\n11/01/2026,Paper Co,Ink,45.00\n")
        self.assertIsNone(ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "costs"), "costs"))

    def test_partly_numbered_bills_from_one_vendor_and_day_are_asked_about(self):
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Memo,Amount\n"
                                    b"B-1,10/31/2026,Paper Co,Vinyl,100.00\n,10/31/2026,Paper Co,Ink,100.00\n"
                                    b"B-2,11/01/2026,Ink Co,Toner,40.00\n")
        mapping = ji.suggest_mapping(headers, "costs")
        self.assertEqual({"label": "Paper Co on 10/31/2026 (some lines have no bill number)", "lines": 2},
                         ji.amount_scope_question(headers, rows, mapping, "costs"))
        with self.assertRaises(ji.IntakeError):
            ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY")
        self.assertEqual(3, len(ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY", "line").accepted))
        whole = ji.intake(headers, rows, mapping, "costs", "MM/DD/YYYY", "document")
        self.assertEqual([2, 4], [r["row"] for r in whole.accepted])  # numbered bills, one line each
        self.assertEqual([3], [r["row"] for r in whole.rejected])
        self.assertIn("No bill number", " ".join(whole.rejected[0]["reasons"]))
        # Every line numbered, one line per bill: no question.
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Amount\nB-1,10/31/2026,Paper Co,100.00\n"
                                    b"B-2,10/31/2026,Paper Co,100.00\n")
        self.assertIsNone(ji.amount_scope_question(headers, rows, ji.suggest_mapping(headers, "costs"), "costs"))

    def test_bill_total_rows_without_a_bill_number_are_not_imported(self):
        headers, rows = ji.read_csv(b"Bill No,Date,Vendor,Memo,Bill Total\n"
                                    b",10/31/2026,Paper Co,Vinyl,300.00\n,10/31/2026,Paper Co,Ink,300.00\n"
                                    b"B-2,10/31/2026,Paper Co,Tape,12.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual([Decimal("12.00")], [r["amount"] for r in result.accepted])
        self.assertEqual([2, 3], [r["row"] for r in result.rejected])
        self.assertTrue(all("No bill number" in " ".join(r["reasons"]) for r in result.rejected))

    def test_competing_customer_and_job_columns_are_never_picked_silently(self):
        headers = ["Invoice", "Date", "Customer", "Client", "Amount", "Job", "Project"]
        mapping = ji.suggest_mapping(headers, "invoices")
        self.assertIsNone(mapping["customer"])  # required: the owner is asked
        self.assertIsNone(mapping["job_id"])  # optional, but still never guessed
        self.assertEqual({"customer": ["Customer", "Client"], "job_id": ["Job", "Project"]},
                         ji.ambiguous_columns(headers, "invoices"))
        self.assertEqual(("Invoice", "Date", "Amount"), (mapping["invoice_id"], mapping["date"], mapping["amount"]))
        # Every field, not only money and dates: vendor, bill number, cost type and memo too.
        cost_headers = ["Date", "Vendor", "Name", "Bill", "Ref", "Amount", "Type", "Category", "Memo", "Notes"]
        self.assertEqual({"vendor": ["Vendor", "Name"], "cost_id": ["Bill", "Ref"], "cost_type": ["Type", "Category"],
                          "memo": ["Memo", "Notes"]}, ji.ambiguous_columns(cost_headers, "costs"))
        self.assertTrue(all(ji.suggest_mapping(cost_headers, "costs")[f] is None
                            for f in ("vendor", "cost_id", "cost_type", "memo")))

    def test_one_clear_column_per_field_needs_no_question(self):
        headers, _, _ = load("fictional_invoices.csv", "invoices")
        self.assertEqual({}, ji.ambiguous_columns(headers, "invoices"))
        headers, _, _ = load("fictional_costs.csv", "costs")
        self.assertEqual({}, ji.ambiguous_columns(headers, "costs"))

    def test_two_possible_date_columns_are_never_picked_silently(self):
        self.assertIsNone(ji.suggest_mapping(["Invoice", "Date", "Invoice Date", "Customer", "Amount"], "invoices")["date"])
        self.assertEqual("Invoice Date", ji.suggest_mapping(["Invoice", "Invoice Date", "Customer", "Amount"], "invoices")["date"])

    def test_two_possible_amount_columns_are_never_picked_silently(self):
        for headers in (["Invoice", "Date", "Customer", "Amount", "Total"], ["Invoice", "Date", "Customer", "Amt", "Total Amount"]):
            with self.subTest(headers=headers):
                self.assertIsNone(ji.suggest_mapping(headers, "invoices")["amount"])
        self.assertEqual("Total", ji.suggest_mapping(["Invoice", "Date", "Customer", "Total"], "invoices")["amount"])

    def test_open_balance_is_never_suggested_as_the_amount(self):
        mapping = ji.suggest_mapping(["Num", "Date", "Customer", "Open Balance"], "invoices")
        self.assertIsNone(mapping["amount"])
        mapping = ji.suggest_mapping(["Num", "Date", "Customer", "Open Balance", "Amount"], "invoices")
        self.assertEqual("Amount", mapping["amount"])

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

    def test_date_format_is_chosen_only_when_one_format_reads_the_most_dates(self):
        self.assertEqual("MM/DD/YYYY", ji.suggest_date_format(["10/01/2026", "12/31/2026"]))
        # One date only ISO can read signals a second convention, so MargenX asks instead.
        self.assertIsNone(ji.suggest_date_format(["10/01/2026", "10/31/2026", "2026-10-06"]))
        self.assertIsNone(ji.suggest_date_format(["10/31/2026", "31/10/2026", "10/01/2026"]))  # month-first and day-first mixed
        self.assertEqual("YYYY-MM-DD", ji.suggest_date_format(["2026-10-01", "2026-10-02"]))
        self.assertIsNone(ji.suggest_date_format(["10/01/2026", "01/02/2026"]))  # fits MM/DD and DD/MM equally
        self.assertIsNone(ji.suggest_date_format(["10/01/2026", "2026-10-06"]))  # three-way tie
        self.assertIsNone(ji.suggest_date_format(["not a date"]))
        self.assertIsNone(ji.suggest_date_format([]))

    def test_date_question_shows_what_each_reading_means(self):
        q = ji.date_question(["10/01/2026", "10/02/2026"])
        self.assertEqual("10/01/2026", q["example"])
        self.assertEqual({"MM/DD/YYYY": "October 1, 2026", "DD/MM/YYYY": "January 10, 2026"}, q["options"])
        self.assertIsNone(ji.date_question(["10/31/2026"]))  # not ambiguous
        self.assertIsNone(ji.date_question(["nope"]))

    def test_three_way_tie_offers_no_partial_question(self):
        values = ["2026-10-06", "10/01/2026"]  # ISO, month-first and day-first each read one date
        self.assertIsNone(ji.suggest_date_format(values))
        self.assertIsNone(ji.date_question(values))  # no single date shows all three; the page asks for the main format

    def test_formats_that_agree_on_every_date_need_no_question(self):
        self.assertEqual("MM/DD/YYYY", ji.suggest_date_format(["01/01/2026", "02/02/2026"]))
        self.assertIsNone(ji.date_question(["01/01/2026", "02/02/2026"]))

    def test_mixed_styles_are_asked_about_even_when_the_tie_reads_the_same(self):
        # Month-first and day-first agree on 01/01 and 02/02, but the ISO date shows a second style.
        self.assertIsNone(ji.suggest_date_format(["01/01/2026", "02/02/2026", "2026-10-06"]))
        with self.assertRaises(ji.IntakeError):
            ji.intake(["Date"], [], {}, "costs", "guess")


class InvoiceIntakeTests(unittest.TestCase):
    def setUp(self):
        headers, rows, mapping = load("fictional_invoices.csv", "invoices")
        self.result = ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line")

    def test_every_row_is_accepted_or_rejected_with_a_reason(self):
        r = self.result
        self.assertEqual(r.total_rows, len(r.accepted) + len(r.rejected))
        reasons = {item["row"]: " ".join(item["reasons"]) for item in r.rejected}
        self.assertIn("Identical to row 6, so it is counted once", reasons[7])
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
        self.assertIn("1 of 6 imported invoice lines have no job number", report)
        self.assertIn("1 credit or refund line were imported", report)
        self.assertIn("1 invoice spans more than one line (for example FIC-1002)", report)
        self.assertIn("6 invoice lines imported (5 invoices), dated 2026-10-01 to 2026-10-07", report)
        self.assertNotIn("profit is", report.lower())

    def test_no_job_column_is_a_gap(self):
        headers, rows, mapping = load("fictional_invoices.csv", "invoices")
        mapping["job_id"] = None
        report = texts(ji.missing_report(ji.intake(headers, rows, mapping, "invoices", "MM/DD/YYYY", "line")))
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
        self.assertIn("3 of 8 imported cost lines aren't linked to a job", report)
        self.assertIn("1 of 8 imported cost lines have no cost type", report)
        self.assertIn("No labor costs were found", report)

    def test_labor_detection_needs_a_whole_recognized_labor_type(self):
        for value in ("Labor", "Direct labour", "Wages", "Payroll", "LABOR", "Cost of Goods Sold:Job Labor"):
            self.assertTrue(ji.is_labor(value), value)
        for value in ("Non-labor", "nonlabor", "Non labor", "No labor", "Labor fees", "Laboratory supplies",
                      "payroll - shop", "Materials", "", None):
            self.assertFalse(ji.is_labor(value), value)
        headers, rows = ji.read_csv(b"Date,Payee,Type,Amount\n10/01/2026,A,Non-labor,1.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertIn("No labor costs were found", texts(ji.missing_report(result)))

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
        # Same vendor, date and amount: answered as separate lines, so duplicates are what is tested.
        return ji.intake(headers, rows, self.MAP, "costs", "MM/DD/YYYY", "line")

    def test_rows_differing_only_in_unmapped_columns_are_both_kept(self):
        result = self.run_costs(b"Date,Payee,Amount,Note\n10/01/2026,A,1.00,first\n10/01/2026,A,1.00,second\n")
        self.assertEqual(2, len(result.accepted))

    def test_rows_differing_only_in_whitespace_are_both_kept_with_original_text(self):
        result = self.run_costs(b"Date,Payee,Amount\n10/01/2026,A,1.00\n10/01/2026,A ,1.00\n")
        self.assertEqual(2, len(result.accepted))
        self.assertEqual(["A", "A "], [r["original"]["vendor"] for r in result.accepted])
        self.assertEqual(("10/01/2026", "A ", "1.00"), result.accepted[1]["cells"])

    def test_original_identifiers_and_text_are_preserved(self):
        headers, rows = ji.read_csv(b"Num,Date,Customer,Amount,Job No\n  FIC-1 ,10/01/2026, Acme  Co ,1.00, J-5 \n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        record = result.accepted[0]
        self.assertEqual({"invoice_id": "  FIC-1 ", "date": "10/01/2026", "customer": " Acme  Co ",
                          "amount": "1.00", "job_id": " J-5 "}, record["original"])
        self.assertEqual(("FIC-1", "J-5"), (record["invoice_id"], record["job_id"]))  # trimmed working values
        # ...and the trimming is reported, never silent.
        self.assertIn("3 values had extra spaces at the start or end, which MargenX ignores (for example row 2: '  FIC-1 ')",
                      texts(ji.missing_report(result)))

    def test_identical_rows_are_rejected_once(self):
        result = self.run_costs(b"Date,Payee,Amount\n10/01/2026,A,1.00\n10/01/2026,A,1.00\n")
        self.assertEqual(1, len(result.accepted))
        self.assertIn("Identical to row 2, so it is counted once", result.rejected[0]["reasons"][0])


class UploadGateTests(unittest.TestCase):
    def test_own_file_needs_made_up_confirmation(self):
        self.assertTrue(ji.upload_allowed(True, False, False))
        self.assertFalse(ji.upload_allowed(False, True, False))
        self.assertFalse(ji.upload_allowed(False, False, True))
        self.assertTrue(ji.upload_allowed(False, True, True))



class FormulaSafetyTests(unittest.TestCase):
    def test_safe_cell_policy_covers_control_and_whitespace_prefixes(self):
        for risky in ("=1+1", "+1", "-1", "@SUM(A1)", "\t=1", "\r=1", "\n=1+1", " =1+1", "\x00=1", "  \n @x"):
            with self.subTest(risky=risky):
                self.assertEqual("'" + risky, ji.safe_cell(risky))
        for plain in ("Menu boards", "1.00", " plain", "a=b", "", None):
            with self.subTest(plain=plain):
                self.assertEqual("" if plain is None else plain, ji.safe_cell(plain))

    def test_rejected_rows_keep_formula_text_as_data(self):
        headers, rows = ji.read_csv(b'Date,Payee,Amount\n10/01/2026,"=cmd|\' /C calc\'!A0",-5\n')
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual("=cmd|' /C calc'!A0", result.rejected[0]["cells"][1])  # stored as text, never run
        self.assertTrue(result.rejected[0]["reasons"][0].startswith("Cost is negative"))

    def test_there_is_no_repair_file_export(self):
        # Removed on purpose: re-importing an edited repair file could turn unresolved
        # rows into accepted ones. Owners fix data at the source and export again.
        self.assertFalse(hasattr(ji, "rejected_rows_csv"))

    def test_empty_import_reports_nothing_imported(self):
        headers, rows = ji.read_csv(b"Date,Payee,Amount\n,,\n")
        report = texts(ji.missing_report(ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")))
        self.assertIn("1 row of 1 couldn't be imported", report)
        self.assertIn("No cost lines were imported", report)




class AmountTooLargeIntakeTests(unittest.TestCase):
    def test_an_oversized_cost_keeps_its_job_from_being_complete(self):
        import job_profit as jp
        sales_headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        sales = ji.intake(sales_headers, [ji.Record(2, ("INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "2400.00"))],
                          ji.suggest_mapping(sales_headers, "invoices"), "invoices", "MM/DD/YYYY")
        cost_headers = ["Bill", "Date", "Vendor", "Job", "Type", "Amount"]
        rows = [("B-1", "10/01/2026", "Supply (fictional)", "J-1", "Materials", "600.00"),
                ("B-2", "10/02/2026", "Crew (fictional)", "J-1", "Labor", "480.00")]
        def report(extra):
            records = [ji.Record(n, r) for n, r in enumerate(rows + extra, start=2)]
            costs = ji.intake(cost_headers, records, ji.suggest_mapping(cost_headers, "costs"), "costs", "MM/DD/YYYY")
            return jp.job_profit(sales, costs)
        # Control: with every cost readable, J-1 is Complete.
        self.assertEqual("complete", next(j for j in report([]).jobs if j.job_id == "J-1").status)
        # With a cost over the cap, J-1 isn't Complete, and the rejected cost line is counted.
        oversized = report([("B-3", "10/03/2026", "Supply (fictional)", "J-1", "Materials", "9" * 30)])
        j1 = next(j for j in oversized.jobs if j.job_id == "J-1")
        self.assertNotEqual("complete", j1.status)
        self.assertEqual(1, oversized.rejected_cost_lines)

    def test_an_amount_over_the_cap_is_rejected_with_its_own_reason_and_counts_as_missing_money(self):
        import job_intake as ji
        headers = ["Invoice", "Date", "Customer", "Job", "Amount"]
        rows = [("INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "100.00"),
                ("INV-2", "10/03/2026", "Bakery (fictional)", "J-1", "1" * 60),
                ("INV-3", "10/04/2026", "Bakery (fictional)", "J-1", "999,999,999,999.99")]
        records = [ji.Record(n, r) for n, r in enumerate(rows, start=2)]
        result = ji.intake(headers, records, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY")
        self.assertEqual(["INV-1", "INV-3"], [r["invoice_id"] for r in result.accepted])
        self.assertEqual([3], [r["row"] for r in result.rejected])
        self.assertTrue(result.rejected[0]["money_missing"])
        self.assertIn("is larger than $999,999,999,999.99, more than MargenX can add up exactly",
                      result.rejected[0]["reasons"][0])
        # The original cell is kept in full for provenance, even though the reason shortens it.
        self.assertEqual("1" * 60, result.rejected[0]["cells"][4])
        self.assertIn("'" + "1" * 40 + "'", result.rejected[0]["reasons"][0])  # only the reason shortens it


if __name__ == "__main__":
    unittest.main()
