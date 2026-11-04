"""Issue #128, step 3: reading a recognised Profit and Loss Detail, checking every total to the cent,
and the coverage ledger (S6).

End to end on made-up files in the layout seen (tests/quickbooks_fixtures.py): Excel bytes -> rows
-> recognised layout -> headings, lines and totals -> checks -> one ledger outcome per line ->
each section's status. Uploads still refuse every QuickBooks report (checked below).
"""
from decimal import Decimal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_fixtures as fx  # noqa: E402
import job_intake as ji  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_rules as qr  # noqa: E402

D = Decimal
GOOD_BYTES = fx.xlsx(fx.pnl_rows(), formulas=fx.FORMULAS, stored=fx.STORED)
# Excel rows of the fixture's lines, worked out by hand from fx.BODY (row 6 = BODY[0]).
LINE_ROWS = [9, 10, 15, 22, 23, 32]


def body_row(row: int) -> int:
    return row - fx.FIRST_BODY_ROW


def read(rows=None, *, formulas=None, stored=None) -> qp.ProfitAndLossDetail:
    data = GOOD_BYTES if rows is None else fx.xlsx(rows, formulas=formulas, stored=stored)
    return qp.read_profit_and_loss_detail("report.xlsx", data)


def with_body(changes: dict[int, list | None], inserts: dict[int, list] | None = None) -> list[list]:
    """The fixture with some body rows (by Excel row) replaced, removed (None) or inserted before."""
    body = []
    for offset, row in enumerate(fx.BODY):
        excel = fx.FIRST_BODY_ROW + offset
        for extra in (inserts or {}).get(excel, []):
            body.append(extra)
        replacement = changes.get(excel, row)
        if replacement is not None:
            body.append(replacement)
    return fx.pnl_rows(body=body)


class GoodReportTests(unittest.TestCase):
    """The made-up report, with every figure worked out by hand."""

    @classmethod
    def setUpClass(cls):
        cls.report = read()

    def test_every_total_matches_its_lines_to_the_cent(self):
        self.assertEqual((), self.report.problems)
        self.assertTrue(self.report.reconciled)
        checks = {(c.row, c.label): c.expected for c in self.report.checks}
        self.assertEqual({
            (11, "Total for Design income"): D("1200"), (12, "Total Income"): D("1200"),
            (16, "Total Cost of Goods Sold"): D("150"), (17, "Total Cost of Goods Sold"): D("150"),
            (24, "Total for Fuel"): D("349.41"), (25, "Total for Automobile with sub-accounts"): D("349.41"),
            (26, "Total Expenses"): D("349.41"), (33, "Total for Miscellaneous"): D("80"),
            (34, "Total Other Expense"): D("80"),
            # Summary rows, each with its own signs: 1,200 - 150; 1,050 - 349.41; 0 - 80; 700.59 - 80.
            (18, "Gross Profit"): D("1050"), (27, "Net Ordinary Income"): D("700.59"),
            (35, "Net Other Income"): D("-80"), (36, "Net Income"): D("620.59")}, checks)
        self.assertTrue(all(c.matches for c in self.report.checks))

    def test_the_float_rule_reads_the_noisy_stored_total_as_whole_cents(self):
        fuel = next(c for c in self.report.checks if c.label == "Total for Fuel")
        self.assertEqual(("349.40999999999997", D("349.41")), (fuel.stored, fuel.stored_cents))

    def test_every_line_is_in_the_ledger_once_with_its_outcome(self):
        lines = {line.row: line for line in self.report.lines}
        self.assertEqual(LINE_ROWS, sorted(lines))
        self.assertEqual((qp.INCLUDED, qr.SALE, D("900.0")), (lines[9].outcome, lines[9].counts_as, lines[9].amount))
        self.assertEqual((qp.INCLUDED, qr.SALE), (lines[10].outcome, lines[10].counts_as))
        # The $405 kind of line: an Invoice under Cost of Goods Sold is never a sale.
        self.assertEqual((qp.NOT_RESOLVED, None), (lines[15].outcome, lines[15].counts_as))
        self.assertIn("'Invoice' under Cost of Goods Sold is never a sale", lines[15].reason)
        self.assertEqual(("Cost of Goods Sold", "Cost of Goods Sold"), lines[15].account_path)
        self.assertEqual([qp.INCLUDED, qp.INCLUDED], [lines[22].outcome, lines[23].outcome])
        self.assertEqual(("Expenses", "Automobile", "Fuel"), lines[22].account_path)
        self.assertEqual(qp.NOT_RESOLVED, lines[32].outcome)
        self.assertEqual("Other Expenses", lines[32].section)
        self.assertIn("counted only once you say what each one is", lines[32].reason)
        # S5: the Name is kept whole; customer and job are step 4.
        self.assertEqual(("Coral Cafe (fictional):Patio", None, None), (lines[9].name, lines[9].customer, lines[9].job))
        self.assertEqual(("report.xlsx", "10/02/2026", "1001"), (lines[9].source, lines[9].date, lines[9].num))

    def test_each_section_adds_up_and_has_its_status(self):
        sections = self.report.sections
        expected = {  # section: (lines, included, not resolved, status)
            "Income": (2, D("1200"), D("0"), qp.COMPLETE),
            "Cost of Goods Sold": (1, D("0"), D("150"), qp.NEEDS_A_CHECK),
            "Expenses": (2, D("349.41"), D("0"), qp.COMPLETE),
            "Other Income": (0, D("0"), D("0"), qp.COMPLETE),  # the empty heading in column B
            "Other Expenses": (1, D("0"), D("80"), qp.NEEDS_A_CHECK),
        }
        for name, (count, included, held, status) in expected.items():
            with self.subTest(name):
                section = sections[name]
                self.assertEqual((count, included, held, status),
                                 (section.lines, section.included, section.not_resolved, section.status))
                self.assertTrue(section.adds_up)
                self.assertEqual(section.stored_total, section.included + section.excluded + section.not_resolved)

    def test_the_upload_page_still_refuses_the_report(self):
        with self.assertRaisesRegex(ji.IntakeError, "MargenX can't use QuickBooks reports yet"):
            ji.read_file("report.xlsx", GOOD_BYTES)


class FloatRuleTests(unittest.TestCase):
    def test_only_totals_within_a_millionth_of_a_cent_count(self):
        for stored, cents in (("349.40999999999997", D("349.41")), ("349.409999", D("349.41")),
                              ("349.410001", D("349.41")), ("1200", D("1200.00")), ("-89.5", D("-89.50")),
                              ("5.5511151231257827E-17", D("0.00")), ("-1.1368683772161603e-13", D("0.00")),
                              ("1E+3", D("1000.00")), ("1E+999", None), ("5E-3", None),
                              ("349.4099989", None), ("349.405", None), ("1.001", None), ("", None),
                              ("1,200.00", None), ("1000000000000.00", None)):
            with self.subTest(stored):
                self.assertEqual(cents, qp.total_cents(stored))

    def test_lines_must_be_exact_cents_never_the_float_rule(self):
        for stored, amount in (("750.0", D("750.0")), ("337.5", D("337.5")), ("-89.5", D("-89.5")),
                               ("349.40999999999997", None), ("1.001", None), ("", None), ("1,200.00", None)):
            with self.subTest(stored):
                self.assertEqual(amount, qp.line_amount(stored))

    def test_the_line_rules_hold_an_amount_that_isnt_exact_cents(self):
        # The #129 review (W2): the S1 rules never count a line amount with fractions of a cent.
        for classify in (lambda a: qr.classify_profit_and_loss_line(("Income", "Design income"), "Invoice", a,
                                                                    section_verified=True),
                         lambda a: qr.classify_sales_by_customer_line("Invoice", a, group_verified=True)):
            outcome = classify(D("100.005"))
            self.assertEqual(qr.NOT_RESOLVED, outcome.counts_as)
            self.assertIn("isn't an exact number of cents", outcome.reason)
            self.assertEqual(qr.SALE, classify(D("100.50")).counts_as)


class StaleAndBrokenTotalTests(unittest.TestCase):
    """A total that doesn't match its lines holds every line of its section (S6)."""

    def assert_section_held(self, report, section, says):
        self.assertFalse(report.reconciled)
        self.assertTrue(any(says in p.text for p in report.problems), report.problems)
        coverage = report.sections[section]
        self.assertEqual(qp.NEEDS_A_CHECK, coverage.status)
        self.assertEqual(0, coverage.included_lines)
        held = [line for line in report.lines if line.section == section]
        self.assertTrue(held)
        for line in held:
            self.assertEqual(qp.NOT_RESOLVED, line.outcome)
            self.assertIn("hasn't been checked against the report's own totals", line.reason)

    def test_a_stale_saved_formula_result_is_used_as_saved_and_caught(self):
        # J11 is "=J9+J10" (1,200), but its saved result says 1,300: MargenX reads the saved value and never
        # recalculates, so the mismatch shows (the PR #134 review, W3; plan follow-up W7).
        stale = dict(fx.STORED, J11="1300")
        report = read(fx.pnl_rows(), formulas=fx.FORMULAS, stored=stale)
        check = next(c for c in report.checks if c.row == 11)
        self.assertEqual((D("1300.00"), D("1200"), False), (check.stored_cents, check.expected, check.matches))
        self.assert_section_held(report, "Income", "it says 1,300.00, but its lines add up to 1,200.00")
        # The other sections don't depend on it.
        self.assertEqual(qp.COMPLETE, report.sections["Expenses"].status)

    def test_a_total_off_by_one_cent_holds_its_section(self):
        report = read(with_body({24: fx.total("Total for Fuel", 349.40)}), stored={})
        self.assert_section_held(report, "Expenses", "'Total for Fuel': it says 349.40, but its lines add up to 349.41")

    def test_a_total_outside_the_float_rule_holds_its_section(self):
        report = read(fx.pnl_rows(), stored=dict(fx.STORED, J24="349.4099"))
        self.assert_section_held(report, "Expenses", "isn't a whole number of cents")

    def test_a_missing_account_total_holds_its_section(self):
        report = read(with_body({11: None}))
        self.assert_section_held(report, "Income", "'Design income' has no closing total")

    def test_a_missing_section_total_holds_its_section(self):
        report = read(with_body({26: None}), stored={"J24": "349.40999999999997", "J25": "349.40999999999997"})
        self.assert_section_held(report, "Expenses", "'Expenses' has no closing total")

    def test_a_total_naming_another_account_holds_its_section(self):
        report = read(with_body({24: fx.total("Total for Gas", 349.41)}))
        self.assert_section_held(report, "Expenses", "'Total for Gas' doesn't close the account above it")

    def test_a_summary_row_that_doesnt_match_holds_the_sections_it_is_built_from(self):
        report = read(with_body({18: fx.total("Gross Profit", 1150.0)}), stored=fx.STORED)
        for section in ("Income", "Cost of Goods Sold"):
            self.assertEqual(qp.NEEDS_A_CHECK, report.sections[section].status)
        self.assertFalse(report.sections["Income"].verified)
        self.assertTrue(report.sections["Expenses"].verified)  # Gross Profit isn't built from it
        net = read(with_body({36: fx.total("Net Income", 600.0)}), stored=fx.STORED)
        self.assertFalse(any(s.verified for s in net.sections.values()))

    def test_no_net_income_row_holds_the_whole_report(self):
        report = read(with_body({36: None}), stored=fx.STORED)
        self.assertIn("the report has no 'Net Income' row", [p.text for p in report.problems])
        self.assertFalse(any(s.verified for s in report.sections.values()))


class LineProblemTests(unittest.TestCase):
    """A blank or uneven amount, an odd date or an odd row never makes a line disappear (S6)."""

    def test_an_amount_with_fractions_of_a_cent_is_held_and_holds_its_section(self):
        # The PR #134 review: "1.001" passed recognition. It is never counted, never rounded.
        line = fx.line(4, "Expense", "", "Bayside Fuel (fictional)", 200.11, 200.11, "Truck fuel", "Mastercard")
        line[9] = "200.111"
        report = read(with_body({22: line}), stored=fx.STORED)
        held = next(l for l in report.lines if l.row == 22)
        self.assertEqual((qp.NOT_RESOLVED, None, "200.111"), (held.outcome, held.amount, held.amount_text))
        self.assertIn("isn't an exact number of cents", held.reason)
        expenses = report.sections["Expenses"]
        self.assertEqual((qp.NEEDS_A_CHECK, False, 1), (expenses.status, expenses.adds_up,
                                                       expenses.not_resolved_unknown_amounts))

    def test_a_blank_amount_is_held(self):
        line = fx.line(4, "Expense", "", "Bayside Fuel (fictional)", None, None, "Truck fuel", "Mastercard")
        report = read(with_body({22: line}), stored=fx.STORED)
        held = next(l for l in report.lines if l.row == 22)
        self.assertEqual(qp.NOT_RESOLVED, held.outcome)
        self.assertIn("Its amount is blank", held.reason)
        self.assertEqual(qp.NEEDS_A_CHECK, report.sections["Expenses"].status)

    def test_a_line_dated_outside_the_period_is_held_not_excluded(self):
        line = fx.line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 900.0, 900.0, "Patio design")
        line[1] = "11/02/2026"
        report = read(with_body({9: line}), stored=fx.STORED)
        held = next(l for l in report.lines if l.row == 9)
        self.assertEqual(qp.NOT_RESOLVED, held.outcome)
        self.assertIn("outside the report's period (January 1-October 26, 2026). Only you can confirm", held.reason)
        self.assertEqual((D("300.0"), D("900.0"), qp.NEEDS_A_CHECK, 0),
                         (report.sections["Income"].included, report.sections["Income"].not_resolved,
                          report.sections["Income"].status, report.sections["Income"].excluded_lines))

    def test_a_date_not_written_as_quickbooks_writes_it_is_held(self):
        for written in ("2026-10-02", "10/2/2026", "13/02/2026", ""):
            with self.subTest(written):
                line = fx.line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 900.0, 900.0)
                line[1] = written
                report = read(with_body({9: line}), stored=fx.STORED)
                held = next(l for l in report.lines if l.row == 9)
                self.assertEqual(qp.NOT_RESOLVED, held.outcome)

    def test_a_row_of_an_unknown_shape_holds_the_whole_report_and_is_kept_in_the_ledger(self):
        report = read(with_body({}, inserts={22: [["Memo", "", "", "", "Fuel note", "", "", "", "", 5.0]]}), stored={})
        self.assertTrue(any("isn't a heading, a line or a total" in p.text for p in report.problems))
        self.assertTrue(all(line.outcome == qp.NOT_RESOLVED for line in report.lines))
        self.assertFalse(any(s.verified for s in report.sections.values()))
        # The automated review of fe569fa: the row itself, with its amount, is in the ledger.
        kept = next(line for line in report.lines if line.row == 22)
        self.assertEqual((D("5"), "Fuel note", qp.NOT_RESOLVED, "Expenses"),
                         (kept.amount, kept.name, kept.outcome, kept.section))
        self.assertIn("Row 22 isn't a heading, a line or a total MargenX knows", kept.reason)

    def test_a_label_with_an_amount_that_isnt_a_total_is_kept_in_the_ledger(self):
        report = read(with_body({}, inserts={22: [fx.total("Adjustment (fictional)", 5.0)]}), stored={})
        kept = next(line for line in report.lines if line.row == 22)
        self.assertEqual((D("5"), qp.NOT_RESOLVED), (kept.amount, kept.outcome))
        self.assertIn("('Adjustment (fictional)') isn't a heading, a line or a total", kept.reason)
        self.assertFalse(any(s.verified for s in report.sections.values()))
        # A row shaped like a total that can't be placed is only a check, never money.
        unplaced = read(with_body({}, inserts={22: [fx.total("Total for Gas", 5.0)]}), stored={})
        self.assertNotIn(22, [line.row for line in unplaced.lines])
        self.assertFalse(unplaced.sections["Expenses"].verified)

    def test_names_and_amounts_are_kept_exactly_as_written(self):
        line = fx.line(2, "Invoice", "1001", "  Coral Cafe (fictional):Patio ", 900.0, 900.0)
        report = read(with_body({9: line}), stored={"J9": "900.0"})
        kept = next(l for l in report.lines if l.row == 9)
        self.assertEqual(("  Coral Cafe (fictional):Patio ", "900.0", D("900.0")), (kept.name, kept.amount_text, kept.amount))

    def test_a_line_directly_under_a_section_is_held(self):
        stray = fx.line(3, "Invoice", "1009", "Bay Clinic (fictional)", 50.0, 50.0)
        report = read(with_body({12: fx.total("Total Income", 1250.0)}, inserts={8: [stray]}), stored=fx.STORED)
        held = next(l for l in report.lines if l.row == 8)
        self.assertEqual(qp.NOT_RESOLVED, held.outcome)
        self.assertTrue(any("directly under the section 'Income'" in p.text for p in report.problems))
        self.assertEqual(qp.NEEDS_A_CHECK, report.sections["Income"].status)

    def test_lines_under_the_column_b_heading_are_held(self):
        interest = fx.line(25, "Deposit", "", "Bank (fictional)", 5.0, 5.0, "Interest", "Checking")
        report = read(with_body({}, inserts={30: [interest]}), stored=fx.STORED)
        self.assertTrue(any("row 30 is a line" in p.text for p in report.problems), report.problems)
        self.assertEqual(qp.NEEDS_A_CHECK, report.sections["Other Income"].status)

    def test_no_line_ever_disappears(self):
        variants = {
            "good": fx.pnl_rows(),
            "missing total": with_body({11: None}),
            "unknown row": with_body({}, inserts={22: [["Memo", "", "", "", "x", "", "", "", "", 5.0]]}),
            "unapplied cash": with_body({8: ["Unapplied Cash Payment Income"]}),
            "label with amount": with_body({}, inserts={22: [fx.total("Adjustment (fictional)", 5.0)]}),
            "uneven amount": with_body({22: [None, "10/04/2026", "Expense", "", "B", "", "", "", "", "1.001", ""]}),
            "section out of order": with_body({13: ["Expenses"]}),
            "no wrapper": with_body({6: None}),
            "account outside a section": with_body({7: None}),
        }
        for name, rows in variants.items():
            with self.subTest(name):
                report = read(rows, stored={})
                # Every line, and every row of unknown shape: a label beside anything but an amount, or beside
                # an amount when the label isn't a total or summary row.
                def is_total(label):
                    return str(label).startswith("Total ") or label in qp.SUMMARIES
                line_rows = [row for row, cells in enumerate(rows, 1)
                             if row > 5 and len(cells) > 2 and any(c not in (None, "") for c in cells[1:])
                             and cells[1] != "Other Income" and (not cells[0] or not is_total(cells[0]) or any(
                                 c not in (None, "") for i, c in enumerate(cells[1:], 1) if i != 9))]
                self.assertEqual(sorted(line_rows), sorted(line.row for line in report.lines))
                for coverage in report.sections.values():
                    known = sum((l.amount for l in report.lines if l.section == coverage.section and l.amount is not None),
                                D("0"))
                    self.assertEqual(known, coverage.included + coverage.excluded + coverage.not_resolved)


class StructureTests(unittest.TestCase):
    """The nested accounts seen: parents with their own lines, sub-accounts, and "with sub-accounts" totals."""

    BODY = [
        ["Ordinary Income/Expenses"], ["Income"],
        ["Landscaping Services"],                                                              # parent, own lines
        fx.line(3, "Invoice", "1101", "Palm Gym (fictional):Lobby", 500.0, 500.0),
        fx.total("Total for Landscaping Services", 500.0),
        ["Job Materials"],                                                                     # parent, no own lines
        ["Plants and Soil"],
        fx.line(4, "Invoice", "1102", "Palm Gym (fictional):Lobby", 120.0, 120.0),
        fx.total("Total for Plants and Soil", 120.0),
        ["Sprinklers"],
        fx.line(5, "Invoice", "1103", "Bay Clinic (fictional)", 80.0, 80.0),
        fx.total("Total for Sprinklers", 80.0),
        fx.total("Total for Job Materials with sub-accounts", 200.0),
        fx.total("Total for Landscaping Services with sub-accounts", 700.0),
        ["Discounts given"],
        fx.line(6, "Invoice", "1104", "Bay Clinic (fictional)", -20.0, -20.0),
        fx.total("Total for Discounts given", -20.0),
        fx.total("Total Income", 680.0),
        fx.total("Gross Profit", 680.0),
        ["Expenses"], ["Job Expenses"],
        fx.line(7, "Bill", "B-1", "Garden Supply (fictional)", 60.0, 60.0, "", "Accounts Payable (A/P)"),
        fx.total("Total for Job Expenses", 60.0),
        ["Job Materials"],                                                                     # same name as above
        ["Plants and Soil"],
        fx.line(8, "Check", "301", "Garden Supply (fictional)", 40.0, 40.0, "", "Checking"),
        fx.total("Total for Plants and Soil", 40.0),
        fx.total("Total for Job Materials with sub-accounts", 40.0),
        fx.total("Total for Job Expenses with sub-accounts", 100.0),
        ["Rent or Lease"],
        fx.line(1, "Expense", "", "Landlord (fictional)", 300.0, 300.0, "", "Checking"),
        fx.total("Total for Rent or Lease", 300.0),
        fx.total("Total Expenses", 400.0),
        fx.total("Net Ordinary Income", 280.0),
        ["Other Income/Expense"], ["Other Income"],
        ["Interest Earned"],
        fx.line(30, "Deposit", "", "Bank (fictional)", 2.5, 2.5, "Interest", "Checking"),
        fx.total("Total for Interest Earned", 2.5),
        fx.total("Total Other Income", 2.5),
        fx.total("Net Other Income", 2.5),
        fx.total("Net Income", 282.5),
    ]

    def test_nested_accounts_are_read_and_checked(self):
        report = read(fx.pnl_rows(body=self.BODY))
        self.assertEqual((), report.problems)
        paths = {line.amount: line.account_path for line in report.lines}
        self.assertEqual(("Income", "Landscaping Services"), paths[D("500.0")])
        self.assertEqual(("Income", "Landscaping Services", "Job Materials", "Plants and Soil"), paths[D("120.0")])
        self.assertEqual(("Income", "Discounts given"), paths[D("-20.0")])
        self.assertEqual(("Expenses", "Job Expenses"), paths[D("60.0")])
        self.assertEqual(("Expenses", "Job Expenses", "Job Materials", "Plants and Soil"), paths[D("40.0")])
        self.assertEqual(("Expenses", "Rent or Lease"), paths[D("300.0")])
        self.assertEqual(("Other Income", "Interest Earned"), paths[D("2.5")])
        income = report.sections["Income"]
        # The -$20 discount line is held (negative amounts aren't tested yet), never dropped: 700 + (-20) = 680.
        self.assertEqual((D("700.0"), D("-20.0"), D("680.00"), qp.NEEDS_A_CHECK),
                         (income.included, income.not_resolved, income.stored_total, income.status))
        self.assertEqual((D("400.0"), qp.COMPLETE), (report.sections["Expenses"].included,
                                                    report.sections["Expenses"].status))
        # A deposit under Other Income is never counted automatically (S9).
        self.assertEqual((D("2.5"), qp.NEEDS_A_CHECK), (report.sections["Other Income"].not_resolved,
                                                       report.sections["Other Income"].status))

    def test_a_with_sub_accounts_total_that_doesnt_match_holds_the_section(self):
        body = [row if row[0] != "Total for Job Materials with sub-accounts" or row[9] != 200.0
                else fx.total("Total for Job Materials with sub-accounts", 210.0) for row in self.BODY]
        report = read(fx.pnl_rows(body=body))
        self.assertFalse(report.sections["Income"].verified)
        self.assertTrue(report.sections["Expenses"].verified)

    def test_a_parent_without_own_lines_missing_its_total_holds_the_section(self):
        body = [row for row in self.BODY if row[0] != "Total for Job Materials with sub-accounts" or row[9] != 200.0]
        report = read(fx.pnl_rows(body=body))
        self.assertFalse(report.sections["Income"].verified, report.problems)
        self.assertTrue(report.sections["Expenses"].verified)

    def test_a_missing_sub_account_total_never_changes_an_amount(self):
        # Without "Total for Landscaping Services with sub-accounts", the file reads just as well as Landscaping
        # Services being an account of its own followed by a parent "Job Materials": every total still matches
        # its lines, and no outcome depends on which account sits above which (see the Unapplied Cash test).
        body = [row for row in self.BODY if row[0] != "Total for Landscaping Services with sub-accounts"]
        report = read(fx.pnl_rows(body=body))
        self.assertEqual(read(fx.pnl_rows(body=self.BODY)).sections["Income"].included,
                         report.sections["Income"].included)

    def test_a_line_after_a_parents_sub_accounts_holds_the_section(self):
        stray = fx.line(9, "Invoice", "1105", "Bay Clinic (fictional)", 10.0, 10.0)
        index = self.BODY.index(fx.total("Total for Job Materials with sub-accounts", 200.0))
        body = [*self.BODY[:index], stray, *self.BODY[index:]]  # after Sprinklers' total
        report = read(fx.pnl_rows(body=body))
        self.assertTrue(any("after the sub-accounts of 'Job Materials'" in p.text for p in report.problems),
                        report.problems)
        self.assertFalse(report.sections["Income"].verified)
        self.assertIn(10, [int(line.amount) for line in report.lines])  # kept in the ledger

    def test_an_unapplied_cash_parent_missing_its_total_never_lets_its_lines_count(self):
        # The automated review of fe569fa: an "Unapplied Cash" parent with its own lines and total, whose
        # "with sub-accounts" total is missing, could be read as a sibling of its sub-account, so the
        # sub-account's Invoice lines would no longer sit under "Unapplied Cash". Such an account (cash-basis
        # only) now holds its whole section, whatever the nesting.
        body = [["Ordinary Income/Expenses"], ["Income"],
                ["Unapplied Cash Payment Income"],
                fx.line(3, "Invoice", "1201", "Bay Clinic (fictional)", 100.0, 100.0),
                fx.total("Total for Unapplied Cash Payment Income", 100.0),
                ["Design income"],
                fx.line(4, "Invoice", "1202", "Bay Clinic (fictional)", 250.0, 250.0),
                fx.total("Total for Design income", 250.0),
                fx.total("Total Income", 350.0),
                fx.total("Net Ordinary Income", 350.0), fx.total("Net Income", 350.0)]
        report = read(fx.pnl_rows(body=body))
        self.assertTrue(any("appears in an accrual-basis report" in p.text for p in report.problems), report.problems)
        income = report.sections["Income"]
        self.assertEqual((0, D("0"), D("350.0"), qp.NEEDS_A_CHECK),
                         (income.included_lines, income.included, income.not_resolved, income.status))
        self.assertEqual([qp.NOT_RESOLVED] * 2, [line.outcome for line in report.lines])

    def test_a_with_sub_accounts_total_on_an_account_without_any_holds_the_section(self):
        body = [*self.BODY[:31], fx.total("Total for Rent or Lease with sub-accounts", 300.0), *self.BODY[32:]]
        report = read(fx.pnl_rows(body=body))
        self.assertTrue(any("has no sub-accounts" in p.text for p in report.problems), report.problems)
        self.assertFalse(report.sections["Expenses"].verified)


class EndToEndRealShapeTests(unittest.TestCase):
    """The #129 review (W5): from the uploaded bytes to each line's outcome and each section's status."""

    def test_csv_and_unrecognised_files_are_refused_with_the_page_reason(self):
        with self.assertRaisesRegex(ji.IntakeError, "Excel"):
            qp.read_profit_and_loss_detail("report.csv", fx.csv_bytes(fx.pnl_rows()))
        with self.assertRaisesRegex(ji.IntakeError, "cash-basis"):
            qp.read_profit_and_loss_detail("report.xlsx", fx.xlsx(fx.pnl_rows(
                footer="Cash Basis Monday, October 26, 2026 07:04 PM GMTZ")))

    def test_the_405_regression_end_to_end(self):
        cogs = [fx.line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 80.0, 80.0),
                fx.line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 70.0, 150.0),
                fx.line(5, "Invoice", "1002", "Palm Gym (fictional):Lobby", 65.0, 215.0),
                fx.line(5, "Invoice", "1002", "Palm Gym (fictional):Lobby", 65.0, 280.0),
                fx.line(9, "Invoice", "1003", "Bay Clinic (fictional)", 62.5, 342.5),
                fx.line(9, "Invoice", "1003", "Bay Clinic (fictional)", 62.5, 405.0)]
        body = [*fx.BODY[:9], *cogs, fx.total("Total Cost of Goods Sold", 405.0), fx.total("Total Cost of Goods Sold", 405.0),
                fx.total("Gross Profit", 795.0), *fx.BODY[13:21], fx.total("Net Ordinary Income", 445.59),
                *fx.BODY[22:29], fx.total("Net Other Income", -80.0), fx.total("Net Income", 365.59)]
        report = read(fx.pnl_rows(body=body), stored={})
        self.assertEqual((), report.problems)
        sales = [line for line in report.lines if line.counts_as == qr.SALE]
        self.assertEqual(D("1200"), sum(line.amount for line in sales))  # never $1,605
        cogs_section = report.sections["Cost of Goods Sold"]
        self.assertEqual((6, D("405.0"), 0, qp.NEEDS_A_CHECK),
                         (cogs_section.not_resolved_lines, cogs_section.not_resolved, cogs_section.included_lines,
                          cogs_section.status))


if __name__ == "__main__":
    unittest.main()
