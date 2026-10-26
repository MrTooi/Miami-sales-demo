"""Issue #128, step 1: QuickBooks money rules S1 and S2, and the audit of the reader for plain lists.

Every row here is made up. The layouts copy only the column names and the row shapes seen in QuickBooks
Online exports on 2026-10-26 (issue #128, "Layouts seen"); no Intuit file is used or kept.
"""
from datetime import date
from decimal import Decimal
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

import job_intake as ji
import job_profit as jp
import quickbooks_rules as qr

D = Decimal
PNL = qr.PROFIT_AND_LOSS_DETAIL


def xlsx(rows) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def csv_bytes(rows) -> bytes:
    def cell(value):
        text = "" if value is None else (value.strftime("%m/%d/%Y") if isinstance(value, date) else str(value))
        return f'"{text}"' if "," in text else text
    return "\n".join(",".join(cell(v) for v in row) for row in rows).encode()


# --- Made-up reports in the layouts seen ---------------------------------------------------------

PNL_COLUMNS = [None, "Transaction date", "Transaction type", "Num", "Name", "Location", "Class full name",
               "Description", "Item split account", "Amount", "Balance"]


def pnl_line(day, kind, num, name, amount, balance, description="", split="Accounts Receivable (A/R)"):
    return [None, date(2026, 10, day), kind, num, name, None, None, description, split, amount, balance]


# The $405 case: six Cost of Goods Sold lines whose transaction type is "Invoice" (QuickBooks posts an
# item's cost on the invoice), beside real Income invoices and an expense Bill.
COGS_LINES = [pnl_line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 80.0, 80.0),
              pnl_line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 70.0, 150.0),
              pnl_line(5, "Invoice", "1002", "Palm Gym (fictional):Lobby", 65.0, 215.0),
              pnl_line(5, "Invoice", "1002", "Palm Gym (fictional):Lobby", 65.0, 280.0),
              pnl_line(9, "Invoice", "1003", "Bay Clinic (fictional)", 62.5, 342.5),
              pnl_line(9, "Invoice", "1003", "Bay Clinic (fictional)", 62.5, 405.0)]
PNL_REPORT = [
    ["Biscayne Landscaping (fictional)"], ["Profit and Loss Detail"], ["January 1-October 26, 2026"], [],
    PNL_COLUMNS,
    ["Income"], ["Design income"],
    pnl_line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 900.0, 900.0, "Patio design"),
    pnl_line(5, "Invoice", "1002", "Palm Gym (fictional):Lobby", 600.0, 1500.0, "Lobby plants"),
    pnl_line(9, "Sales Receipt", "1003", "Bay Clinic (fictional)", 300.0, 1800.0, "Planters"),
    ["Total for Design income", None, None, None, None, None, None, None, None, 1800.0],
    ["Total for Income", None, None, None, None, None, None, None, None, 1800.0],
    ["Cost of Goods Sold"], *COGS_LINES,
    ["Total for Cost of Goods Sold", None, None, None, None, None, None, None, None, 405.0],
    ["Gross Profit", None, None, None, None, None, None, None, None, 1395.0],
    ["Expenses"], ["Job Expenses"], ["Job Materials"],
    pnl_line(3, "Bill", "B-7", "Garden Supply (fictional)", 210.0, 210.0, "Soil", "Accounts Payable (A/P)"),
    ["Total for Job Materials", None, None, None, None, None, None, None, None, 210.0],
    ["Total for Job Expenses", None, None, None, None, None, None, None, None, 210.0],
    ["Total for Expenses", None, None, None, None, None, None, None, None, 210.0],
    ["Net Income", None, None, None, None, None, None, None, None, 1185.0],
    [], ["Accrual Basis Monday, October 26, 2026 07:04 PM GMTZ"],
]

SBCD_COLUMNS = [None, "Transaction date", "Transaction type", "Num", "Product/Service full name", "Description",
                "Quantity", "Sales price", "Amount", "Balance"]
SBCD_REPORT = [
    ["Biscayne Landscaping (fictional)"], ["Sales by Customer Detail"], ["All Dates"], [],
    SBCD_COLUMNS,
    ["Coral Cafe (fictional)"], ["Patio"],
    [None, date(2026, 10, 2), "Invoice", "1001", "Design:Patio", "Patio design", 2, 450.0, 900.0, 900.0],
    ["Total for Patio", None, None, None, None, None, 2, None, 900.0],
    ["Total for Coral Cafe (fictional) with sub-customers", None, None, None, None, None, 2, None, 900.0],
    ["TOTAL", None, None, None, None, None, 2, None, 900.0],
    [], ["Accrual Basis Monday, October 26, 2026 07:04 PM GMTZ"],
]

# "Transaction List by Customer": invoices and customer payments in one list, totals adding both.
TLBC_REPORT = [
    ["Biscayne Landscaping (fictional)"], ["Transaction List by Customer"], ["All Dates"], [],
    [None, "Transaction date", "Transaction type", "Num", "Amount"],
    ["Coral Cafe (fictional)"],
    [None, date(2026, 10, 2), "Invoice", "1001", 900.0],
    [None, date(2026, 10, 20), "Payment", "", 900.0],
    ["Total for Coral Cafe (fictional)", None, None, None, 1800.0],
]


class CogsInvoiceRegressionTests(unittest.TestCase):
    """The observed mistake: $405 of Cost of Goods Sold lines typed "Invoice" counted as SALES."""

    def test_the_405_dollars_under_cost_of_goods_sold_are_never_a_sale(self):
        for line in COGS_LINES:
            outcome = qr.classify_profit_and_loss_line(("Cost of Goods Sold",), line[2], D(str(line[9])),
                                                       section_verified=True)
            self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
            self.assertIn("'Invoice' under Cost of Goods Sold is never a sale", outcome.reason)
            self.assertIn("never left out", outcome.reason)
        self.assertEqual(D("405.0"), sum(D(str(line[9])) for line in COGS_LINES))
        # The real invoices in Income are sales: $1,800 of sales, never $2,205.
        sales = [row for row in PNL_REPORT[7:10]
                 if qr.classify_profit_and_loss_line(("Income", "Design income"), row[2], D(str(row[9])),
                                                     section_verified=True).counts_as == qr.SALE]
        self.assertEqual(D("1800.0"), sum(D(str(row[9])) for row in sales))

    def test_the_report_itself_is_refused_before_the_old_reader_sees_it(self):
        for name, data in (("pnl.xlsx", xlsx(PNL_REPORT)), ("pnl.csv", csv_bytes(PNL_REPORT))):
            with self.subTest(name), self.assertRaises(ji.IntakeError) as caught:
                ji.read_file(name, data)
            self.assertIn("This looks like a QuickBooks report (it has the title 'Profit and Loss Detail')",
                          str(caught.exception))
            self.assertIn("nothing from this file was used", str(caught.exception))

    def test_without_the_refusal_the_old_reader_would_count_the_405_as_sales(self):
        # Shows what the refusal prevents (the mistake seen on main eab330d): the reader for plain lists
        # can't see account sections, so it takes every "Invoice" line for a sale.
        with mock.patch.object(qr, "quickbooks_refusal", return_value=None):
            headers, records, _ = ji.read_file("pnl.xlsx", xlsx(PNL_REPORT))
        mapping = ji.suggest_mapping(headers, "invoices")
        result = ji.intake(headers, records, mapping, "invoices", "YYYY-MM-DD", "line")
        cogs_rows = set(range(14, 20))  # Excel rows of the six Cost of Goods Sold lines
        self.assertEqual(cogs_rows, {r["row"] for r in result.accepted} & cogs_rows)
        self.assertEqual(D("2205.0"), sum(r["amount"] for r in result.accepted))

    def test_the_page_refuses_the_report_and_shows_no_sales(self):
        from streamlit.testing.v1 import AppTest

        page = Path(__file__).resolve().parents[1] / "pages" / "1_MargenX_Import.py"
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pnl.xlsx").write_bytes(xlsx(PNL_REPORT))
            Path(tmp, "costs.csv").write_bytes(b"Bill,Date,Vendor,Job,Type,Amount\n"
                                               b"B-1,10/01/2026,Supply (fictional),J-1,Materials,600.00\n")
            source = page.read_text(encoding="utf-8").replace(
                'SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"', f"SAMPLES = Path({tmp!r})").replace(
                'DEFAULT_SAMPLE_SET = "demo"', 'DEFAULT_SAMPLE_SET = "test"').replace(
                'SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")', 'SAMPLE_FILES = ("pnl.xlsx", "costs.csv")')
            at = AppTest.from_string(source, default_timeout=60)
            at.run()
        self.assertFalse(at.exception, at.exception)
        errors = " ".join(e.value for e in at.error)
        self.assertIn("This file can't be read: This looks like a QuickBooks report", errors)
        markdown = " ".join(m.value for m in at.markdown)
        self.assertNotIn("Here's where your money was made", markdown)
        for amount in ("$405", "$2,205", "$1,800"):
            self.assertNotIn(amount, markdown + " ".join(t.value for t in at.text))


class ProfitAndLossRuleTests(unittest.TestCase):
    """S1 for Profit and Loss Detail: a sale needs a verified Income section and an Invoice or Sales
    Receipt; a cost needs a type on its section's tested allow-list. Everything else is not resolved."""

    def classify(self, path, kind, amount="100.00", verified=True):
        return qr.classify_profit_and_loss_line(path, kind, D(amount), section_verified=verified)

    def test_invoices_and_sales_receipts_in_income_are_sales(self):
        for kind in ("Invoice", "Sales Receipt", "  sales   receipt ", "INVOICE"):
            for path in (("Income",), ("Income", "Design income"), ("Income", "Design income", "Patios")):
                with self.subTest(kind=kind, path=path):
                    self.assertEqual(qr.SALE, self.classify(path, kind).counts_as)
        self.assertEqual(qr.SALE, self.classify(("Income",), "Invoice", "0.00").counts_as)

    def test_the_cost_allow_list_is_bill_expense_and_check_proved_by_these_rows(self):
        # Fictional lines in the observed layout: a Bill for soil, an Expense paid by card, a Check.
        lines = [("Bill", ("Expenses", "Job Expenses", "Job Materials", "Plants and Soil"), "210.00"),
                 ("Expense", ("Expenses", "Automobile", "Fuel"), "349.41"),
                 ("Check", ("Expenses", "Rent or Lease"), "900.00"),
                 ("Bill", ("Cost of Goods Sold",), "75.00"),
                 ("Expense", ("Cost of Goods Sold",), "12.50"),
                 ("Check", ("Cost of Goods Sold",), "40.00")]
        for kind, path, amount in lines:
            with self.subTest(kind=kind, path=path):
                self.assertEqual(qr.COST, self.classify(path, kind, amount).counts_as)
        self.assertEqual({(PNL, qr.COST_OF_GOODS_SOLD): {"bill", "expense", "check"},
                          (PNL, qr.EXPENSES): {"bill", "expense", "check"}}, qr.COST_TYPES)

    def test_a_sale_type_in_a_cost_section_is_checked_against_the_allow_list_never_a_sale(self):
        for section in (("Cost of Goods Sold",), ("Expenses", "Job Expenses", "Job Materials")):
            for kind in ("Invoice", "Sales Receipt"):
                with self.subTest(section=section, kind=kind):
                    outcome = self.classify(section, kind)
                    self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                    self.assertIn("is never a sale, and it isn't on the tested list of cost types", outcome.reason)

    def test_payments_and_deposits_are_never_counted_automatically_in_any_section(self):
        for kind in ("Deposit", "Payment", "Receive Payment", "Bank Deposit", "Transfer", "Bill Payment (Check)",
                     "Bill Payment (Credit Card)", "Credit Card Payment", "Sales Tax Payment"):
            for path in (("Income", "Design income"), ("Cost of Goods Sold",), ("Expenses", "Job Expenses")):
                with self.subTest(kind=kind, path=path):
                    outcome = self.classify(path, kind)
                    self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                    self.assertIn("never counted automatically", outcome.reason)

    def test_a_deposit_posted_to_income_is_held_not_dropped(self):
        # The plan's S9 case: a $700 Deposit in Design Income beside a $4,000 Invoice.
        self.assertEqual(qr.SALE, self.classify(("Income", "Design income"), "Invoice", "4000.00").counts_as)
        deposit = self.classify(("Income", "Design income"), "Deposit", "700.00")
        self.assertEqual(qr.NOT_RESOLVED, deposit.counts_as)
        self.assertIn("It stays not resolved and is shown with its amount; it is never left out.", deposit.reason)

    def test_unapplied_cash_accounts_are_never_counted_whatever_the_type(self):
        cases = [(("Income", "Unapplied Cash Payment Income"), "Payment"),
                 (("Income", "Unapplied Cash Payment Income"), "Invoice"),
                 (("Income", "4900 Unapplied Cash Payment Income"), "Deposit"),
                 (("Expenses", "Unapplied Cash Bill Payment Expense"), "Bill Payment (Check)"),
                 (("Expenses", "Unapplied Cash Bill Payment Expense"), "Bill"),
                 (("Expenses", "Unapplied cash bill payment expense"), "Check")]
        for path, kind in cases:
            with self.subTest(path=path, kind=kind):
                outcome = self.classify(path, kind)
                self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                self.assertIn("money QuickBooks hasn't matched to an invoice or a bill", outcome.reason)

    def test_other_income_and_other_expenses_wait_for_the_owner(self):
        for path in (("Other Income", "Interest earned"), ("Other Expenses", "Penalties")):
            for kind in ("Invoice", "Sales Receipt", "Bill", "Expense", "Check", "Deposit", "Journal Entry"):
                with self.subTest(path=path, kind=kind):
                    outcome = self.classify(path, kind, "50.00")
                    self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                    self.assertIn("counted only once you say what each one is", outcome.reason)

    def test_an_unknown_or_unverified_section_is_not_resolved(self):
        for path in ((), ("",), ("Expense",), ("Ordinary Income/Expenses",), ("Design income",), ("Gross Profit",)):
            with self.subTest(path=path):
                self.assertEqual(qr.NOT_RESOLVED, self.classify(path, "Invoice").counts_as)
        for path, kind in ((("Income",), "Invoice"), (("Expenses",), "Bill")):
            with self.subTest("unverified", path=path):
                outcome = self.classify(path, kind, verified=False)
                self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                self.assertIn("hasn't been checked against the report's own totals", outcome.reason)

    def test_negative_sales_and_costs_and_untested_reductions_are_not_resolved(self):
        for path, kind in ((("Income",), "Invoice"), (("Income",), "Sales Receipt"), (("Expenses",), "Bill"),
                           (("Cost of Goods Sold",), "Check")):
            with self.subTest(path=path, kind=kind):
                outcome = self.classify(path, kind, "-25.00")
                self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                self.assertIn("negative amount", outcome.reason)
        for kind, path in (("Credit Memo", ("Income",)), ("Refund", ("Income",)), ("Refund Receipt", ("Income",)),
                           ("Discount", ("Income",)), ("Vendor Credit", ("Expenses",))):
            with self.subTest(kind=kind):
                outcome = self.classify(path, kind, "-200.00")
                self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
                self.assertIn("hasn't tested how QuickBooks posts it yet", outcome.reason)

    def test_no_line_is_ever_dropped_because_of_its_type(self):
        # S9: every type, in every section, with any sign, is a sale, a cost or not resolved. A sale or a
        # cost only on exactly the tested combinations; there is no "left out" outcome at all.
        kinds = ["Invoice", "Sales Receipt", "Bill", "Expense", "Check", "Deposit", "Payment", "Credit Memo",
                 "Refund", "Journal Entry", "Transfer", "Estimate", "Time Charge", "Time Activity", "Charge",
                 "Delayed Charge", "Billable Expense Charge", "Customer Payment", "Vendor Credit",
                 "Credit Card Expense", "Credit Card Credit", "Cash Expense", "Inventory Qty Adjust", "Paycheck",
                 "Sales Tax Payment", "", None, "Invoice Payment", "Bill (fictional variant)"]
        paths = [(), ("Income",), ("Income", "Design income"), ("Cost of Goods Sold",), ("Expenses", "Job Expenses"),
                 ("Other Income",), ("Other Expenses",), ("Equity",), ("Income", "Unapplied Cash Payment Income")]
        for kind in kinds:
            for path in paths:
                for amount in ("120.00", "0.00", "-120.00"):
                    for verified in (True, False):
                        outcome = qr.classify_profit_and_loss_line(path, kind, D(amount), section_verified=verified)
                        self.assertIn(outcome.counts_as, (qr.SALE, qr.COST, qr.NOT_RESOLVED))
                        self.assertTrue(outcome.reason)
                        text = " ".join((kind or "").split()).casefold()
                        sale = (verified and path[:1] == ("Income",) and "Unapplied" not in " ".join(path)
                                and text in ("invoice", "sales receipt") and D(amount) >= 0)
                        cost = (verified and path[:1] in (("Cost of Goods Sold",), ("Expenses",))
                                and text in ("bill", "expense", "check") and D(amount) >= 0)
                        self.assertEqual(sale, outcome.counts_as == qr.SALE, (kind, path, amount, verified))
                        self.assertEqual(cost, outcome.counts_as == qr.COST, (kind, path, amount, verified))
        self.assertFalse(hasattr(qr, "EXCLUDED"))

    def test_the_q6_types_are_never_sales_in_income(self):
        for kind in ("Estimate", "Time Charge", "Time Activity", "Charge", "Delayed Charge", "Billable Expense Charge",
                     "Customer Payment", "Deposit"):
            with self.subTest(kind):
                self.assertEqual(qr.NOT_RESOLVED, self.classify(("Income", "Design income"), kind).counts_as)

    def test_allow_lists_never_hold_payments_or_sales(self):
        for types in qr.COST_TYPES.values():
            self.assertFalse(types & qr.PAYMENT_TYPES)
            self.assertFalse(types & qr.SALE_TYPES)
        self.assertEqual({"invoice", "sales receipt"}, qr.SALE_TYPES)

    def test_amounts_must_be_exact_decimals(self):
        for amount in (100.0, 100, "100.00", D("NaN"), D("Infinity")):
            with self.subTest(amount=amount), self.assertRaises(TypeError):
                qr.classify_profit_and_loss_line(("Income",), "Invoice", amount, section_verified=True)
            with self.subTest("sales by customer", amount=amount), self.assertRaises(TypeError):
                qr.classify_sales_by_customer_line("Invoice", amount, group_verified=True)


class SalesByCustomerRuleTests(unittest.TestCase):
    """S1 for Sales by Customer Detail: no account sections, so a sale needs a verified customer group."""

    def classify(self, kind, amount="900.00", verified=True):
        return qr.classify_sales_by_customer_line(kind, D(amount), group_verified=verified)

    def test_invoices_and_sales_receipts_in_a_verified_group_are_sales(self):
        for kind in ("Invoice", "Sales Receipt"):
            self.assertEqual(qr.SALE, self.classify(kind).counts_as)
            outcome = self.classify(kind, verified=False)
            self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
            self.assertIn("customer group hasn't been checked", outcome.reason)

    def test_everything_else_is_not_resolved_and_never_a_cost(self):
        for kind in ("Credit Memo", "Payment", "Deposit", "Refund Receipt", "Estimate", "Bill", "Expense", "", None):
            for amount in ("900.00", "-900.00"):
                with self.subTest(kind=kind, amount=amount):
                    self.assertEqual(qr.NOT_RESOLVED, self.classify(kind, amount).counts_as)
        self.assertEqual(qr.NOT_RESOLVED, self.classify("Invoice", "-45.00").counts_as)


class QuickBooksLookAlikeTests(unittest.TestCase):
    """S2: a file that looks like a QuickBooks report never reaches the reader for plain lists."""

    def refusal(self, rows, name="file.csv"):
        data = xlsx(rows) if name.endswith(".xlsx") else csv_bytes(rows)
        with self.assertRaises(ji.IntakeError) as caught:
            ji.read_file(name, data)
        return str(caught.exception)

    def test_every_layout_seen_is_refused_with_a_plain_reason(self):
        for rows in (PNL_REPORT, SBCD_REPORT):
            for name in ("report.xlsx", "report.csv"):
                with self.subTest(title=rows[1][0], name=name):
                    reason = self.refusal(rows, name)
                    self.assertIn(f"it has the title '{rows[1][0]}'", reason)
                    self.assertIn("MargenX can't read QuickBooks reports yet", reason)

    def test_transaction_list_by_customer_is_refused_as_a_sales_file(self):
        for name in ("list.xlsx", "list.csv"):
            with self.subTest(name):
                reason = self.refusal(TLBC_REPORT, name)
                self.assertIn('"Transaction List by Customer"', reason)
                self.assertIn("mixes invoices with customer payments", reason)
                self.assertIn("can't be used as a sales file", reason)

    def test_each_quickbooks_sign_alone_refuses_the_file(self):
        plain = [["Invoice", "Date", "Customer", "Job", "Amount"], ["INV-1", "10/02/2026", "Bakery (fictional)", "J-1", "40.00"]]
        cases = {
            "the title 'General Ledger'": [["General Ledger"], *plain],
            "the title 'Profit and Loss by Customer'": [["Biscayne (fictional)"], ["Profit and Loss by Customer"], *plain],
            "the title 'Transaction Detail by Account'": [["Transaction Detail by Account"], *plain],
            "the column 'Memo/Description'": [["Invoice", "Date", "Customer", "Memo/Description", "Amount"], plain[1]],
            "the column 'Item split account'": [["Invoice", "Date", "Customer", "Item split account", "Amount"], plain[1]],
            "the column 'Customer full name'": [["Invoice", "Date", "Customer full name", "Job", "Amount"], plain[1]],
            "the column 'Split'": [["Invoice", "Date", "Customer", "Split", "Amount"], plain[1]],
            "the columns 'Transaction type' and 'Num'": [["Num", "Date", "Customer", "Transaction type", "Amount"],
                                                         ["INV-1", "10/02/2026", "Bakery (fictional)", "Invoice", "40.00"]],
            "the row 'Total for Bakery (fictional)'": [*plain, ["Total for Bakery (fictional)", "", "", "", "40.00"]],
            "the row 'Total for Job Materials with sub-accounts'": [*plain, ["Total for Job Materials with sub-accounts"]],
            "the line 'Accrual Basis Monday, October 26, 2026 07:04 PM GMTZ'": [
                *plain, ["Accrual Basis Monday, October 26, 2026 07:04 PM GMTZ"]],
            "the line 'Cash Basis Tuesday, October 20, 2026'": [*plain, ["Cash Basis Tuesday, October 20, 2026"]],
            "the row 'Gross Profit'": [*plain, ["Gross Profit", "", "", "", "40.00"]],
            "the row 'Net Income'": [*plain, ["Net Income", "", "", "", "40.00"]],
        }
        for sign, rows in cases.items():
            for name in ("file.csv", "file.xlsx"):
                with self.subTest(sign, name=name):
                    self.assertIn(f"it has {sign}", self.refusal(rows, name))
        # The older entry point refuses too.
        with self.assertRaisesRegex(ji.IntakeError, "looks like a QuickBooks report"):
            ji.read_csv(csv_bytes(cases["the row 'Gross Profit'"]))

    def test_an_unrecognised_quickbooks_layout_is_refused(self):
        # A QuickBooks look-alike whose title and columns match nothing MargenX knows.
        rows = [["Biscayne Landscaping (fictional)"], ["Customer Income Overview (fictional variant)"], ["All Dates"], [],
                [None, "Transaction date", "Transaction type", "Num", "Customer full name", "Amount"],
                [None, date(2026, 10, 2), "Invoice", "1001", "Coral Cafe (fictional)", 900.0],
                ["Total for Coral Cafe (fictional)", None, None, None, None, 900.0]]
        for name in ("variant.xlsx", "variant.csv"):
            with self.subTest(name):
                self.assertIn("This looks like a QuickBooks report", self.refusal(rows, name))

    def test_plain_files_are_not_mistaken_for_quickbooks(self):
        samples = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"
        for path in sorted(samples.glob("*.csv")):
            with self.subTest(path.name):
                ji.read_file(path.name, path.read_bytes())
        for rows in ([["Num", "Date", "Customer", "Amount"], ["INV-1", "10/02/2026", "A", "1.00"]],
                     [["Bill", "Date", "Vendor", "Job", "Transaction Type", "Category", "Amount"],
                      ["B-1", "10/01/2026", "Crew", "J-1", "Bill", "Labor", "20.00"]],
                     [["Sales by job"], ["Invoice", "Date", "Customer", "Amount"], ["INV-1", "10/02/2026", "A", "1.00"],
                      ["TOTAL", "", "", "1.00"]],
                     [["Invoice", "Date", "Customer", "Description", "Amount"],
                      ["INV-1", "10/02/2026", "A", "Total for the whole job", "1.00"]]):
            with self.subTest(rows[0]):
                self.assertEqual([], qr.quickbooks_signs([(n, r) for n, r in enumerate(rows, 1)], ji.MAX_TITLE_LINES))


class PlainListReaderAuditTests(unittest.TestCase):
    """The reader for plain lists, audited against S1, S5 and S6 (issue #128, step 1)."""

    def read(self, data: bytes, kind: str):
        headers, records, _ = ji.read_file("file.csv", data)
        return ji.intake(headers, records, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY")

    def test_s1_a_sales_line_posted_to_a_cost_account_is_never_a_sale(self):
        rows = [("Design income", True), ("Income:Design income", True), ("Sales of Product Income", True),
                ("Cost of Goods Sold", False), ("Job Expenses:Job Materials", False), ("Other Income:Interest", False),
                ("Unapplied Cash Payment Income", False), ("Accounts Receivable (A/R)", False), ("Services", False),
                ("", False), ("Sales tax payable", False)]
        data = b"Invoice,Date,Customer,Account,Amount\n" + b"".join(
            f"I-{n},10/02/2026,Bakery (fictional),{account},100.00\n".encode() for n, (account, _) in enumerate(rows))
        result = self.read(data, "invoices")
        self.assertEqual([f"I-{n}" for n, (_, ok) in enumerate(rows) if ok], [r["invoice_id"] for r in result.accepted])
        self.assertEqual(len(rows) - 3, len(result.rejected))
        self.assertTrue(all(r["money_missing"] for r in result.rejected))
        reasons = " ".join(" ".join(r["reasons"]) for r in result.rejected)
        self.assertIn("Account 'Cost of Goods Sold' isn't an income account, so this line isn't counted as a sale", reasons)
        self.assertIn("This line's account is blank", reasons)
        # A file with no account column reads as before.
        plain = self.read(b"Invoice,Date,Customer,Amount\nI-1,10/02/2026,Bakery (fictional),100.00\n", "invoices")
        self.assertEqual(1, len(plain.accepted))

    def test_s1_sale_types_in_a_costs_file_and_other_types_in_a_sales_file_are_never_counted(self):
        costs = self.read(b"Bill,Date,Vendor,Transaction Type,Amount\nB-1,10/02/2026,Supply (fictional),Invoice,80.00\n"
                          b"B-2,10/02/2026,Supply (fictional),Sales Receipt,70.00\nB-3,10/02/2026,Supply (fictional),Bill,60.00\n",
                          "costs")
        self.assertEqual(["B-3"], [r["cost_id"] for r in costs.accepted])
        self.assertTrue(all(r["money_missing"] for r in costs.rejected))
        sales = self.read(b"Invoice,Date,Customer,Type,Amount\nI-1,10/02/2026,A,Invoice,10.00\nI-2,10/02/2026,A,Estimate,10.00\n"
                          b"I-3,10/02/2026,A,Charge,10.00\nI-4,10/02/2026,A,Bill,10.00\n", "invoices")
        self.assertEqual(["I-1"], [r["invoice_id"] for r in sales.accepted])
        self.assertTrue(all(r["money_missing"] for r in sales.rejected))

    def test_s5_names_are_kept_whole_and_a_vendor_never_becomes_a_customer(self):
        invoices = self.read(b"Invoice,Date,Customer,Job,Amount\n"
                             b"I-1,10/02/2026,Freeman Sports (fictional):Ocean View Road,,500.00\n"
                             b"I-2,10/02/2026,Bay Clinic (fictional),J-2,300.00\n", "invoices")
        self.assertEqual(["Freeman Sports (fictional):Ocean View Road", "Bay Clinic (fictional)"],
                         [r["customer"] for r in invoices.accepted])
        self.assertEqual(["", "J-2"], [r["job_id"] for r in invoices.accepted])  # the job never comes from the name
        costs = self.read(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/02/2026,Garden Supply (fictional),J-2,Materials,100.00\n"
                          b"B-2,10/02/2026,Garden Supply (fictional),J-2,Labor,50.00\n", "costs")
        report = jp.job_profit(invoices, costs)
        self.assertEqual({"Freeman Sports (fictional):Ocean View Road", "Bay Clinic (fictional)"},
                         {c.customer for c in report.customers})
        self.assertNotIn("Garden Supply (fictional)", {c.customer for c in report.customers})

    def test_s6_every_row_gets_exactly_one_outcome_and_none_disappears(self):
        files = {
            "invoices": b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/02/2026,A,J-1,Invoice,100.00\n"
                        b"I-2,10/02/2026,A,J-1,Credit Memo,-20.00\nI-3,10/02/2026,A,J-1,Mystery,30.00\n"
                        b"I-4,10/02/2026,A,J-1,,30.00\nI-5,,A,J-1,Invoice,30.00\nI-6,10/02/2026,A,J-1,Invoice,thirty\n"
                        b"I-1,10/02/2026,A,J-1,Invoice,100.00\nI-7,10/02/2026,A,J-1,Credit Memo,25.00\n"
                        b"TOTAL,,,,,265.00\n",
            "costs": b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/02/2026,V,J-1,Materials,10.00\n"
                     b"B-2,10/02/2026,V,J-1,Materials,-5.00\nB-3,10/02/2026,V,J-1,Transfer,500.00\n"
                     b"B-4,10/02/2026,V,J-1,Vendor Credit,5.00\nB-5,10/02/2026,V,,,7.00\n,,,,,\n",
        }
        for kind, data in files.items():
            with self.subTest(kind):
                headers, records, _ = ji.read_file("file.csv", data)
                result = ji.intake(headers, records, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY", "line",
                                   {})
                outcomes = [r["row"] for r in (*result.accepted, *result.rejected, *result.skipped)]
                self.assertEqual(sorted(r.row for r in records), sorted(outcomes))  # each row exactly once
                self.assertTrue(all(r["reasons"] for r in result.rejected))
                self.assertTrue(all(r["reason"] for r in result.skipped))


if __name__ == "__main__":
    unittest.main()
