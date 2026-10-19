from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_MarginX_Import.py")
INVOICE_DATE_QUESTION = "In fictional_invoices.csv, what date is 10/01/2026?"
SAMPLE_AMOUNT_QUESTION = "In fictional_invoices.csv, invoice FIC-1002 has 2 lines. What is 'Total' on each line?"


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
        self.assertIn("3 of 8 imported cost lines aren't linked to a job", text)
        self.assertIn("No labor costs were found", text)
        self.assertIn("Read as costs / bills, dates as MM/DD/YYYY.", [c.value for c in at.caption])
        self.assertEqual([], [c for c in at.checkbox])  # no confirmation boxes in sample mode

    def test_sample_invoices_ask_what_the_total_means_first(self):
        at = self.run_page()
        question = radio(at, SAMPLE_AMOUNT_QUESTION)
        self.assertEqual(["That line's own amount (count every line)",
                          "The whole invoice's total, repeated on each line"], question.options)
        self.assertEqual([], [r for r in at.radio if r.label == INVOICE_DATE_QUESTION])  # one question at a time
        self.assertNotIn("imported invoice lines", page_text(at))

    def test_ambiguous_dates_ask_one_plain_question(self):
        at = self.run_page()
        radio(at, SAMPLE_AMOUNT_QUESTION).set_value("line").run()
        question = radio(at, INVOICE_DATE_QUESTION)
        self.assertEqual(["October 1, 2026", "January 10, 2026"], question.options)
        self.assertNotIn("of 10 couldn't be imported", page_text(at))  # no invoice report until answered
        self.assertNotIn("imported invoice lines", page_text(at))

    def test_invoice_report_after_answering_the_date_question(self):
        at = self.run_page()
        radio(at, SAMPLE_AMOUNT_QUESTION).set_value("line").run()
        radio(at, INVOICE_DATE_QUESTION).set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        text = page_text(at)
        self.assertIn("4 rows of 10 couldn't be imported", text)
        self.assertIn("1 of 6 imported invoice lines have no job number", text)
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
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        radio(at, "What kind of file is fictional_invoices.csv?").set_value("invoices").run()
        # A header literally named like the "no column" choice can still be picked.
        ask = next(s for s in at.selectbox if s.label == "Which column has the customer?")
        ask.select_index(ask.options.index("(not in this file)", 1)).run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("1 invoice line imported (1 invoice)", page_text(at))

    def test_mixed_date_styles_fall_back_to_picking_the_main_format(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,2026-10-06,X,1.00\nB,10/31/2026,Y,2.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        pick = radio(at, "Which date format does fictional_invoices.csv mainly use?")
        pick.set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        text = page_text(at)
        self.assertIn("1 row of 2 couldn't be imported", text)
        self.assertIn("1 invoice line imported (1 invoice)", text)

    def test_unreadable_dates_are_still_accounted_for(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,someday,X,1.00\nB,,Y,2.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        radio(at, "Which date format does fictional_invoices.csv mainly use?").set_value("MM/DD/YYYY").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 rows of 2 couldn't be imported", page_text(at))
        self.assertIn("No invoice lines were imported", page_text(at))
        self.assertEqual([2, 3], list(at.dataframe[0].value["Row in file"]))  # every row listed with its reason
        self.assertEqual(0, len(at.get("download_button")))  # no repair-file download (removed on purpose)

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
        self.assertNotIn("imported cost lines", page_text(at))

    def test_two_amount_columns_ask_which_one_before_importing(self):
        at = self.with_files("Invoice,Date,Customer,Amount,Total\nA,10/31/2026,X,40.00,100.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertNotIn("imported invoice lines", page_text(at))
        ask = next(s for s in at.selectbox if s.label == "Which column has the amount?")
        ask.set_value("Total").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("1 invoice line imported (1 invoice)", page_text(at))

    def test_two_date_columns_ask_which_one_before_importing(self):
        at = self.with_files("Invoice,Date,Invoice Date,Customer,Amount\nA,10/31/2026,09/30/2026,X,1.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertNotIn("imported invoice lines", page_text(at))
        next(s for s in at.selectbox if s.label == "Which column has the invoice date?").set_value("Invoice Date").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("dated 2026-09-30 to 2026-09-30", page_text(at))

    def test_file_that_fits_both_kinds_asks_before_importing(self):
        at = self.with_files("Invoice,Date,Customer,Vendor,Amount\nA,10/31/2026,X,Y,1.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        question = radio(at, "What kind of file is fictional_invoices.csv?")
        self.assertIsNone(question.value)
        self.assertEqual(1, page_text(at).count("imported"))  # only the costs file has a report so far

    def test_open_balance_chosen_by_hand_imports_nothing(self):
        at = self.with_files("Invoice,Date,Customer,Open Balance\nINV-1,10/31/2026,Acme (fictional),40.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        next(s for s in at.selectbox if s.label == "Which column has the amount?").set_value("Open Balance").run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("balance still owed" in i.value for i in at.info))
        self.assertNotIn("imported invoice lines", page_text(at))
        self.assertNotIn("invoice line imported", page_text(at))

    def test_bank_style_export_is_asked_about_and_never_imported_as_costs(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,10/31/2026,X,1.00\n",
                             "Date,Payee,Amount\n10/31/2026,Transfer to savings,500.00\n")
        question = radio(at, "What kind of file is fictional_costs.csv?")
        self.assertIn("bank", question.options[2].lower())
        self.assertNotIn("cost line", page_text(at))
        question.set_value("bank").run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("can't read bank, card or payment statements" in i.value for i in at.info))
        self.assertNotIn("cost line", page_text(at))

    def test_invoice_shaped_deposit_export_is_asked_about_and_bank_imports_nothing(self):
        at = self.with_files("Invoice,Date,Customer,Amount,Deposit\nA,10/31/2026,X (fictional),40.00,40.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        question = radio(at, "What kind of file is fictional_invoices.csv?")  # (a) asked, not auto-imported
        self.assertNotIn("invoice line", page_text(at))
        question.set_value("bank").run()  # (b) bank/payment choice imports no sales
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("payment statements" in i.value for i in at.info))
        self.assertNotIn("invoice line", page_text(at))

    def test_ordinary_invoice_file_still_imports_with_no_questions(self):  # (c)
        at = self.with_files("Invoice,Date,Customer,Payment Terms,Amount\nA,10/31/2026,X (fictional),Net 30,100.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertEqual([], [r.label for r in at.radio if r.label.startswith("What kind of file")])
        self.assertIn("1 invoice line imported (1 invoice)", page_text(at))

    def test_wrong_auto_classification_can_be_rejected_as_a_bank_statement(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,10/31/2026,X (fictional),40.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertIn("1 invoice line imported (1 invoice)", page_text(at))
        override = next(r for r in at.radio if r.label == "File type" and r.value == "invoices")
        override.set_value("bank").run()
        self.assertFalse(at.exception, at.exception)
        self.assertNotIn("invoice line", page_text(at))
        self.assertTrue(any("payment statements" in i.value for i in at.info))

    def test_payout_shaped_cost_file_is_asked_about_and_bank_imports_nothing(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,10/31/2026,X (fictional),1.00\n",
                             "Date,Vendor,Amount,Payout ID\n10/31/2026,Processor (fictional),250.00,PO-1\n")
        question = radio(at, "What kind of file is fictional_costs.csv?")
        self.assertNotIn("cost line", page_text(at))
        question.set_value("bank").run()
        self.assertFalse(at.exception, at.exception)
        self.assertNotIn("cost line", page_text(at))
        self.assertTrue(any("payment statements" in i.value for i in at.info))

    def test_itemized_invoice_asks_which_amount_and_keeps_line_values(self):
        at = self.with_files("Invoice,Date,Customer,Line Amount,Invoice Total\n"
                             "INV-1,10/31/2026,X (fictional),40.00,100.00\nINV-1,10/31/2026,X (fictional),60.00,100.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertNotIn("invoice line", page_text(at))  # no silent choice of the repeated total
        next(s for s in at.selectbox if s.label == "Which column has the amount?").set_value("Line Amount").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 invoice lines imported (1 invoice)", page_text(at))

    def test_identical_files_both_get_reported_and_the_repeat_is_flagged(self):
        same = "Date,Vendor,Amount\n10/31/2026,A,1.00\n"
        at = self.with_files(same, same)
        self.assertEqual(2, page_text(at).count("1 cost line imported"))
        self.assertEqual(["fictional_costs.csv is identical to fictional_invoices.csv. Its rows are the same rows, "
                          "not new ones; upload it only once."], [w.value for w in at.warning[1:]])

    def test_different_files_are_not_flagged_as_identical(self):
        self.assertEqual(1, len(self.run_page().warning))  # only the pilot warning

    def test_competing_customer_columns_ask_before_importing(self):
        at = self.with_files("Invoice,Date,Customer,Client,Amount\nA,10/31/2026,Shop (fictional),Agency (fictional),1.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertNotIn("invoice line", page_text(at))
        next(s for s in at.selectbox if s.label == "Which column has the customer?").set_value("Client").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("1 invoice line imported (1 invoice)", page_text(at))
        self.assertIn("Client", [s.value for s in at.selectbox if s.label == "Customer *"])

    def test_competing_optional_job_columns_ask_and_neither_is_an_answer(self):
        csv_text = "Invoice,Date,Customer,Amount,Job,Project\nA,10/31/2026,X (fictional),1.00,J-1,P-9\n"
        at = self.with_files(csv_text, "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        question = radio(at, "Which column has the job number?")
        self.assertEqual(["Job", "Project", "Neither of these"], question.options)
        self.assertNotIn("invoice line", page_text(at))  # no report until answered
        question.set_value(1).run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("Project", [s.value for s in at.selectbox if s.label == "Job number"])
        self.assertIn("1 invoice line imported (1 invoice)", page_text(at))
        radio(at, "Which column has the job number?").set_value(2).run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("No job number column was chosen", page_text(at))

    def test_payment_amount_chosen_by_hand_imports_nothing(self):
        at = self.with_files("Invoice,Date,Customer,Payment Amount\nA,10/31/2026,X (fictional),40.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        radio(at, "What kind of file is fictional_invoices.csv?").set_value("invoices").run()
        next(s for s in at.selectbox if s.label == "Which column has the amount?").set_value("Payment Amount").run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("money paid or received" in i.value for i in at.info))
        self.assertNotIn("invoice line", page_text(at))

    def test_repeated_invoice_total_lines_are_listed_not_imported(self):
        at = self.with_files("Invoice,Date,Customer,Description,Invoice Total\n"
                             "INV-1,10/31/2026,X (fictional),Banner,100.00\nINV-1,10/31/2026,X (fictional),Install,100.00\n",
                             "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        text = page_text(at)
        self.assertIn("2 rows of 2 couldn't be imported", text)
        self.assertIn("No invoice lines were imported", text)
        self.assertEqual([2, 3], list(at.dataframe[0].value["Row in file"]))

    def test_repeated_generic_total_asks_what_the_number_is(self):
        csv_text = ("Invoice,Date,Customer,Description,Total\n"
                    "INV-1,10/31/2026,X (fictional),Banner,100.00\nINV-1,10/31/2026,X (fictional),Install,100.00\n")
        label = "In fictional_invoices.csv, invoice INV-1 has 2 lines. What is 'Total' on each line?"
        at = self.with_files(csv_text, "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        question = radio(at, label)
        self.assertEqual(["That line's own amount (count every line)", "The whole invoice's total, repeated on each line"],
                         question.options)
        self.assertNotIn("invoice line", page_text(at))  # nothing imported until answered
        question.set_value("line").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 invoice lines imported (1 invoice)", page_text(at))
        radio(at, label).set_value("document").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 rows of 2 couldn't be imported", page_text(at))
        self.assertIn("No invoice lines were imported", page_text(at))

    def test_changing_how_lines_are_grouped_asks_the_amount_question_again(self):
        csv_text = ("Invoice,Order,Date,Customer,Description,Total\n"
                    "INV-1,O-7,10/31/2026,X (fictional),Banner,100.00\nINV-1,O-7,10/31/2026,X (fictional),Install,100.00\n")
        at = self.with_files(csv_text, "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        first = next(r for r in at.radio if "on each line?" in r.label)
        first.set_value("line").run()
        self.assertIn("2 invoice lines imported (1 invoice)", page_text(at))
        # The owner says the order column is the invoice number: the question is now about
        # order O-7, and nothing is imported until it is answered again.
        next(s for s in at.selectbox if s.label == "Invoice number *").set_value("Order").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIsNone(next(r for r in at.radio if "invoice O-7 has 2 lines" in r.label).value)
        self.assertNotIn("invoice lines imported", page_text(at))
        self.assertNotIn("invoice line imported", page_text(at))

    def test_costs_without_bill_numbers_ask_about_a_repeated_amount(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,10/31/2026,X (fictional),1.00\n",
                             "Date,Vendor,Memo,Amount\n10/31/2026,Paper Co (fictional),Vinyl,300.00\n"
                             "10/31/2026,Paper Co (fictional),Ink,300.00\n")
        question = radio(at, "In fictional_costs.csv, Paper Co (fictional) on 10/31/2026 (no bill number) has 2 lines. "
                             "What is 'Amount' on each line?")
        self.assertNotIn("cost line", page_text(at))
        question.set_value("document").run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("2 rows of 2 couldn't be imported", page_text(at))

    def test_bank_credit_file_is_asked_about_and_bank_imports_nothing(self):
        at = self.with_files("Invoice,Date,Customer,Amount\nA,10/31/2026,X (fictional),1.00\n",
                             "Date,Vendor,Amount,Credit\n10/31/2026,Customer deposit (fictional),500.00,500.00\n")
        question = radio(at, "What kind of file is fictional_costs.csv?")
        self.assertNotIn("cost line", page_text(at))
        question.set_value("bank").run()
        self.assertFalse(at.exception, at.exception)
        self.assertNotIn("cost line", page_text(at))
        self.assertTrue(any("payment statements" in i.value for i in at.info))

    def test_possible_subtotal_is_asked_about_line_by_line(self):
        at = self.with_files("Invoice,Date,Customer,Description,Total\n"
                             "INV-1,10/31/2026,X (fictional),Banner,40.00\nINV-1,10/31/2026,X (fictional),Install,60.00\n"
                             "INV-1,10/31/2026,X (fictional),Stand,100.00\n", "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        next(r for r in at.radio if "on each line?" in r.label).set_value("line").run()
        label = ("In fictional_invoices.csv, row 4 of invoice INV-1 shows 100.00, which equals its other lines "
                 "added together. Is it a subtotal?")
        self.assertNotIn("invoice line", page_text(at))  # nothing imported until answered
        radio(at, label).set_value(False).run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("3 invoice lines imported (1 invoice)", page_text(at))
        radio(at, label).set_value(True).run()
        self.assertFalse(at.exception, at.exception)
        self.assertIn("1 row of 3 couldn't be imported", page_text(at))

    def test_header_only_file_needs_no_questions(self):
        at = self.with_files("Invoice,Date,Customer,Amount\n", "Date,Vendor,Amount\n10/31/2026,A,1.00\n")
        self.assertTrue(any("no rows" in i.value for i in at.info))
        self.assertEqual([], [r.label for r in at.radio if "fictional_invoices.csv" in r.label])
        self.assertEqual(1, page_text(at).count("imported"))


if __name__ == "__main__":
    unittest.main()
