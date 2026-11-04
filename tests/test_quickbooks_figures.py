"""Issue #128, step 4: customers, jobs, accounts and costs for Profit and Loss Detail (S5, S7, S8, S9).

The plan's own tests (issue #128, "Tests"), written for one Profit and Loss Detail, plus the v7 review
follow-ups W1-W4. Every company, customer and job is made up; every report is built in the layout
seen (tests/quickbooks_fixtures.py) and read end to end from Excel bytes.

One report never makes a job's profit Complete by itself (S3): every job keeps that one hold until a
second report cross-checks it (step 5). So "ready" below means "no hold except that one".
"""
import dataclasses
from decimal import Decimal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402

D = Decimal
L = fx.line
X, Y = "Customer X (fictional)", "Customer Y (fictional)"
A, B = (X, "Job A"), (X, "Job B")
JOBS_ON = {"sub_customers_are_jobs": True}
MATERIALS = ("Expenses", "Job Materials")
OFFICE = ("Expenses", "Office Supplies")


def read(sections) -> qp.ProfitAndLossDetail:
    report = qp.read_profit_and_loss_detail("test.xlsx", fx.xlsx(fx.report_rows(sections)))
    assert report.reconciled, report.problems
    return report


def rows_of(report, **match) -> list[int]:
    return [l.row for l in report.lines if all(getattr(l, k) == v for k, v in match.items())]


def holds(figure: qf.Figure) -> set:
    """The lines holding a figure, leaving out the one-report hold every job has in step 4."""
    return {h.row for h in figure.holds if h.reason != qf.ONE_REPORT}


def ready(figure: qf.Figure) -> bool:
    return not holds(figure) and all(h.reason == qf.ONE_REPORT for h in figure.holds)


def answers(accounts=None, lines=None, **kw) -> qf.OwnerAnswers:
    return qf.OwnerAnswers(**{**JOBS_ON, **kw}, accounts=accounts or {}, lines=lines or {})


def figures(report, owner_answers: qf.OwnerAnswers) -> qf.Figures:
    """The figures, with the answers bound to this report (as the question screens will bind them)."""
    return qf.figures(report, dataclasses.replace(owner_answers, report=qf.report_fingerprint(report)))


def two_jobs(*extra_income, extra_expenses=(), extra_cogs=(), office=()):
    """Job A ($4,000 sales, $1,000 costs) and Job B ($2,000 sales, $500 costs), both Customer X's."""
    sections = {
        "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0),
                                      L(3, "Invoice", "1002", f"{X}:Job B", 2000.0, 6000.0), *extra_income])],
        "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0, "", "Accounts Payable (A/P)"),
                                        L(6, "Bill", "B-2", f"{X}:Job B", 500.0, 1500.0, "", "Accounts Payable (A/P)"),
                                        *extra_expenses])],
    }
    if office:
        sections["Expenses"].append(("Office Supplies", list(office)))
    if extra_cogs:
        sections["Cost of Goods Sold"] = [("Cost of Goods Sold", list(extra_cogs))]
    return read(sections)


JOB_COSTS = {MATERIALS: qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)}


class S8UnknownJobCostTests(unittest.TestCase):
    """The S8 test: a $900 Job Materials cost with only a vendor name."""

    def setUp(self):
        self.report = two_jobs(extra_expenses=[L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 2400.0)])
        self.row = rows_of(self.report, amount=D("900.0"))[0]

    def test_both_margins_are_held_until_the_900_is_assigned(self):
        result = figures(self.report, answers(JOB_COSTS))
        for job in (A, B):
            self.assertEqual({self.row}, holds(result.jobs[job]["profit_after_job_costs"]), job)
        # A vendor is never a customer (S5): every customer's figures are held too.
        self.assertEqual({self.row}, holds(result.customers[X]["profit_after_job_costs"]))
        self.assertEqual(D("2400"), result.company["job_costs"].amount)  # counted as a job cost of the company
        self.assertEqual(qp.COMPLETE, result.company["job_costs"].status)

    def test_assigned_to_job_a(self):
        result = figures(self.report, answers(JOB_COSTS, {self.row: qf.LineAnswer(qf.JOB_COST, X, "Job A")}))
        self.assertEqual(D("2100"), result.jobs[A]["profit_after_job_costs"].amount)  # 4,000 - 1,000 - 900
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))
        self.assertTrue(ready(result.jobs[B]["profit_after_job_costs"]))
        self.assertEqual(D("1500"), result.jobs[B]["profit_after_job_costs"].amount)

    def test_proven_overhead(self):
        result = figures(self.report, answers(JOB_COSTS, {self.row: qf.LineAnswer(qf.OVERHEAD)}))
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))
        self.assertEqual((D("1500"), D("900")), (result.company["job_costs"].amount, result.company["overhead"].amount))

    def test_the_vendor_in_cost_of_goods_sold(self):
        # The plan's COGS variant: the $900 is a Bill under Cost of Goods Sold whose Name is only a vendor.
        report = two_jobs(extra_cogs=[L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 900.0)])
        row = rows_of(report, amount=D("900.0"))[0]
        result = figures(report, answers({**JOB_COSTS, ("Cost of Goods Sold", "Cost of Goods Sold"):
                                             qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)}))
        for job in (A, B):
            self.assertEqual({row}, holds(result.jobs[job]["profit_after_job_costs"]))
        self.assertEqual({row}, holds(result.customers[X]["profit_after_job_costs"]))

    def test_customer_known_job_unknown(self):
        # W4: the customer is verified by an Invoice line under Cost of Goods Sold (the cost of the items sold)
        # whose Name is the customer, never by a bare name on a Bill.
        report = two_jobs(
            L(4, "Invoice", "1003", f"{Y}:Job C", 300.0, 6300.0),
            extra_cogs=[L(7, "Invoice", "1004", X, 900.0, 900.0, "Pavers")])
        row = rows_of(report, amount=D("900.0"))[0]
        result = figures(report, answers({**JOB_COSTS, ("Cost of Goods Sold", "Cost of Goods Sold"):
                                             qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)}))
        for job in (A, B):
            self.assertEqual({row}, holds(result.jobs[job]["profit_after_job_costs"]))
        self.assertTrue(ready(result.jobs[(Y, "Job C")]["profit_after_job_costs"]))  # other customers' jobs unaffected
        self.assertEqual(set(), holds(result.customers[Y]["profit_after_job_costs"]))
        # W1: the cost counts in Customer X's profit although its job is unknown.
        self.assertEqual((D("2400"), D("3600"), qp.COMPLETE),
                         (result.customers[X]["job_costs"].amount,
                          result.customers[X]["profit_after_job_costs"].amount,
                          result.customers[X]["profit_after_job_costs"].status))


class S8UnknownJobSaleTests(unittest.TestCase):
    """The S8 sales test: a $700 Invoice in Design Income named only "Customer X"."""

    def setUp(self):
        self.report = two_jobs(L(4, "Invoice", "1003", X, 700.0, 6700.0))
        self.row = rows_of(self.report, amount=D("700.0"))[0]

    def test_both_jobs_held_and_customer_x_has_6700(self):
        result = figures(self.report, answers(JOB_COSTS))
        for job in (A, B):
            self.assertEqual({self.row}, holds(result.jobs[job]["profit_after_job_costs"]))
        self.assertEqual((D("6700"), qp.COMPLETE), (result.customers[X]["sales"].amount, result.customers[X]["sales"].status))

    def test_assigned_to_job_a(self):
        result = figures(self.report, answers(JOB_COSTS, {self.row: qf.LineAnswer(qf.REVENUE, X, "Job A")}))
        self.assertEqual(D("3700"), result.jobs[A]["profit_after_job_costs"].amount)
        self.assertTrue(ready(result.jobs[B]["profit_after_job_costs"]))
        self.assertEqual(D("1500"), result.jobs[B]["profit_after_job_costs"].amount)

    def test_confirmed_as_no_job(self):
        result = figures(self.report, answers(JOB_COSTS, {self.row: qf.LineAnswer(qf.REVENUE, no_job=True)}))
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))
        self.assertTrue(ready(result.jobs[B]["profit_after_job_costs"]))
        self.assertEqual(D("6700"), result.customers[X]["sales"].amount)


class S9DepositTests(unittest.TestCase):
    """A $4,000 Invoice and a $700 Deposit in Design Income for Job A, and a $1,000 Bill for Job A."""

    def setUp(self):
        self.report = read({
            "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0),
                                          L(9, "Deposit", "", f"{X}:Job A", 700.0, 4700.0, "", "Checking")])],
            "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0)])]})
        self.deposit = rows_of(self.report, transaction_type="Deposit")[0]
        self.invoice = rows_of(self.report, transaction_type="Invoice")[0]

    def test_3000_never_shows_as_complete(self):
        result = figures(self.report, answers(JOB_COSTS))
        job = result.jobs[A]["profit_after_job_costs"]
        self.assertEqual((D("3000"), {self.deposit}), (job.amount, holds(job)))
        sales = result.customers[X]["sales"]
        self.assertEqual((D("4000"), qp.NEEDS_A_CHECK, D("700.0")), (sales.amount, sales.status, sales.held_amount))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)

    def test_a_deposit_is_never_counted_even_on_the_owners_word(self):
        # Plan v7 lets the owner confirm this Deposit as revenue ($4,700 / $3,700). AGENTS.md rule 4 (binding,
        # it wins on a conflict) says deposits are cash movement, never new revenue, so the answer is refused
        # and the line stays held: $3,000 still never shows as Complete. Raised for Alex on PR #138.
        result = figures(self.report, answers(JOB_COSTS, {self.deposit: qf.LineAnswer(qf.REVENUE)}))
        self.assertIn("money received or moved, so MargenX leaves it unresolved", " ".join(result.warnings))
        self.assertEqual((D("4000"), qp.NEEDS_A_CHECK), (result.customers[X]["sales"].amount,
                                                        result.customers[X]["sales"].status))
        self.assertEqual({self.deposit}, holds(result.jobs[A]["profit_after_job_costs"]))

    def test_no_money_movement_type_can_be_counted_by_an_answer(self):
        for kind in ("Payment", "Receive Payment", "Bank Deposit", "Transfer", "Bill Payment (Check)"):
            for section, answer in (("Income", qf.LineAnswer(qf.REVENUE)), ("Expenses", qf.LineAnswer(qf.JOB_COST)),
                                    ("Expenses", qf.LineAnswer(qf.OVERHEAD))):
                with self.subTest(kind=kind, section=section, answer=answer.kind):
                    sections = {"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0)])]}
                    moved = L(9, kind, "", f"{X}:Job A", 700.0, 700.0)
                    if section == "Income":
                        sections["Income"][0][1].append(moved)
                    else:
                        sections["Expenses"] = [("Job Materials", [moved])]
                    report = read(sections)
                    row = rows_of(report, transaction_type=kind)[0]
                    result = figures(report, answers(JOB_COSTS, {row: answer}))
                    self.assertIn("money received or moved", " ".join(result.warnings))
                    self.assertEqual(NOT_RESOLVED_KIND, next(r for r in result.resolutions if r.row == row).kind)

    def test_a_700_deposit_cant_be_a_duplicate_of_a_4000_invoice(self):
        result = figures(self.report, answers(JOB_COSTS, {self.deposit: qf.LineAnswer(qf.DUPLICATE,
                                                                                         duplicate_of=self.invoice)}))
        self.assertIn("same amount", " ".join(result.warnings))
        self.assertEqual({self.deposit}, holds(result.jobs[A]["profit_after_job_costs"]))
        self.assertEqual(qp.NEEDS_A_CHECK, result.customers[X]["sales"].status)


NOT_RESOLVED_KIND = qf.NOT_RESOLVED


class S9DuplicateTests(unittest.TestCase):
    def test_a_deposit_pointing_to_the_same_sales_receipt_is_excluded(self):
        report = read({"Income": [("Design income", [
            L(2, "Sales Receipt", "1001", f"{X}:Job A", 700.0, 700.0, "", "Checking"),
            L(2, "Deposit", "", f"{X}:Job A", 700.0, 1400.0, "", "Checking")])]})  # the same day
        receipt, deposit = rows_of(report, transaction_type="Sales Receipt")[0], rows_of(report, transaction_type="Deposit")[0]
        result = figures(report, answers(lines={deposit: qf.LineAnswer(qf.DUPLICATE, duplicate_of=receipt)}))
        self.assertEqual((D("700"), qp.COMPLETE), (result.jobs[A]["sales"].amount, result.jobs[A]["sales"].status))
        excluded = next(r for r in result.resolutions if r.row == deposit)
        self.assertEqual((qf.DUPLICATE, receipt), (excluded.kind, excluded.duplicate_of))  # the ledger links both

    def test_a_duplicate_of_another_customer_isnt_accepted(self):
        report = read({"Income": [("Design income", [
            L(2, "Sales Receipt", "1001", f"{Y}:Job C", 700.0, 700.0, "", "Checking"),
            L(9, "Deposit", "", f"{X}:Job A", 700.0, 1400.0, "", "Checking")])]})
        receipt, deposit = rows_of(report, transaction_type="Sales Receipt")[0], rows_of(report, transaction_type="Deposit")[0]
        result = figures(report, answers(lines={deposit: qf.LineAnswer(qf.DUPLICATE, duplicate_of=receipt)}))
        self.assertIn("same customer", " ".join(result.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)


class S9CreditMemoTests(unittest.TestCase):
    """A $4,000 Invoice and a -$200 Credit Memo for Job A, and a $1,000 Bill for Job A."""

    def setUp(self):
        self.report = read({
            "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0),
                                          L(9, "Credit Memo", "1009", f"{X}:Job A", -200.0, 3800.0)])],
            "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0)])]})
        self.memo = rows_of(self.report, transaction_type="Credit Memo")[0]

    def test_before_classification_nothing_is_complete(self):
        result = figures(self.report, answers(JOB_COSTS))
        self.assertEqual(D("3000"), result.jobs[A]["profit_after_job_costs"].amount)
        self.assertEqual({self.memo}, holds(result.jobs[A]["profit_after_job_costs"]))
        sales = result.customers[X]["sales"]
        self.assertEqual((D("4000"), qp.NEEDS_A_CHECK, D("-200.0")), (sales.amount, sales.status, sales.held_amount))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)

    def test_isnt_revenue_is_not_an_answer(self):
        # "It isn't revenue" doesn't say what it is, so there is no such answer: the line stays not resolved.
        self.assertNotIn("not revenue", qf.ALLOWED["Income"])
        result = figures(self.report, answers(JOB_COSTS, {self.memo: qf.LineAnswer("not revenue")}))
        self.assertTrue(result.warnings)
        self.assertEqual(qp.NEEDS_A_CHECK, result.customers[X]["sales"].status)

    def test_classified_as_a_revenue_reduction(self):
        result = figures(self.report, answers(JOB_COSTS, {self.memo: qf.LineAnswer(qf.REDUCTION)}))
        self.assertEqual((D("3800"), qp.COMPLETE), (result.customers[X]["sales"].amount, result.customers[X]["sales"].status))
        self.assertEqual(D("2800"), result.jobs[A]["profit_after_job_costs"].amount)
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))

    def test_a_reduction_cant_be_positive_and_revenue_cant_be_negative(self):
        result = figures(self.report, answers(JOB_COSTS, {self.memo: qf.LineAnswer(qf.REVENUE)}))
        self.assertIn("revenue can't be negative", " ".join(result.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, result.customers[X]["sales"].status)


class S9OverheadAndOtherSectionTests(unittest.TestCase):
    """Job A: $4,000 sales, $1,000 job cost; a $500 Office Supplies expense with no job; then $50 interest
    under Other Income and an $80 penalty under Other Expense."""

    def setUp(self):
        office = L(8, "Expense", "", "Office Depot (fictional)", 500.0, 500.0, "", "Checking")
        self.report = read({
            "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0)])],
            "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0)]),
                         ("Office Supplies", [office])],
            # The plan doesn't name the interest line's type: a Journal Entry here. As a Deposit it would stay held
            # (AGENTS.md rule 4; see test_interest_posted_as_a_deposit_stays_held).
            "Other Income": [("Interest Earned", [L(20, "Journal Entry", "JE-4", "Bank (fictional)", 50.0, 50.0)])],
            "Other Expense": [("Penalties", [L(21, "Check", "310", "County (fictional)", 80.0, 80.0)])]})
        self.office = rows_of(self.report, amount=D("500.0"))[0]
        self.interest = rows_of(self.report, amount=D("50.0"))[0]
        self.penalty = rows_of(self.report, amount=D("80.0"))[0]
        self.entries = {OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, entries=qf.entry_keys(self.report, OFFICE))}

    def test_before_the_owner_answers(self):
        result = figures(self.report, answers(JOB_COSTS))
        self.assertIn(self.office, holds(result.jobs[A]["profit_after_job_costs"]))
        for name in ("profit_after_job_costs", "after_overhead"):
            self.assertEqual(qp.NEEDS_A_CHECK, result.company[name].status, name)

    def test_the_500_is_overhead(self):
        result = figures(self.report, answers({**JOB_COSTS, **self.entries}, {
            self.interest: qf.LineAnswer(qf.OTHER_INCOME), self.penalty: qf.LineAnswer(qf.OTHER_EXPENSE)}))
        job = result.jobs[A]["profit_after_job_costs"]
        self.assertEqual(D("3000"), job.amount)
        self.assertTrue(ready(job))
        self.assertEqual((D("3000"), qp.COMPLETE), (result.company["profit_after_job_costs"].amount,
                                                   result.company["profit_after_job_costs"].status))
        # 3,000 - 500 + 50 - 80
        self.assertEqual((D("2470"), qp.COMPLETE), (result.company["after_overhead"].amount,
                                                   result.company["after_overhead"].status))

    def test_other_sections_stay_not_resolved_until_classified(self):
        result = figures(self.report, answers({**JOB_COSTS, **self.entries}))
        self.assertEqual((D("2500"), {self.interest, self.penalty}),
                         (result.company["after_overhead"].amount, holds(result.company["after_overhead"])))
        self.assertEqual(D("3000"), result.jobs[A]["profit_after_job_costs"].amount)
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))  # other income and expenses never touch a job

    def test_interest_posted_as_a_deposit_stays_held(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0)])],
                       "Other Income": [("Interest Earned", [L(20, "Deposit", "", "Bank (fictional)", 50.0, 50.0)])]})
        row = rows_of(report, transaction_type="Deposit")[0]
        result = figures(report, answers(lines={row: qf.LineAnswer(qf.OTHER_INCOME)}))
        self.assertIn("money received or moved", " ".join(result.warnings))
        self.assertEqual({row}, holds(result.company["after_overhead"]))
        self.assertEqual(qp.COMPLETE, result.company["sales"].status)

    def test_other_income_never_becomes_job_revenue(self):
        # W3: a line is never moved into another section.
        result = figures(self.report, answers(JOB_COSTS, {self.interest: qf.LineAnswer(qf.REVENUE, X, "Job A")}))
        self.assertIn("can't be 'revenue'", " ".join(result.warnings))
        self.assertEqual(D("4000"), result.jobs[A]["sales"].amount)

    def test_overhead_counts_only_with_every_entry_confirmed(self):
        (row, date, num, name, _), = qf.entry_keys(self.report, OFFICE)
        stale = {OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, entries=((row, date, num, name, "450.0"),))}
        result = figures(self.report, answers({**JOB_COSTS, **stale}))
        self.assertIn("Confirm them again", " ".join(result.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["profit_after_job_costs"].status)
        self.assertIn(self.office, holds(result.jobs[A]["profit_after_job_costs"]))
        unconfirmed = {OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT)}
        self.assertEqual(qp.NEEDS_A_CHECK,
                         figures(self.report, answers({**JOB_COSTS, **unconfirmed})).company["overhead"].status)


class AutomatedReviewOf52b5809Tests(unittest.TestCase):
    def test_a_customer_named_like_an_internal_marker_is_still_held(self):
        report = read({"Income": [("Design income", [
            L(2, "Invoice", "1001", "jobs of:Job A", 4000.0, 4000.0),
            L(9, "Credit Memo", "1009", "jobs of:Job A", -200.0, 3800.0)])]})
        memo = rows_of(report, transaction_type="Credit Memo")[0]
        result = figures(report, answers())
        self.assertEqual({memo}, holds(result.jobs[("jobs of", "Job A")]["sales"]))
        self.assertEqual(qp.NEEDS_A_CHECK, result.jobs[("jobs of", "Job A")]["sales"].status)

    def test_an_overhead_confirmation_must_cover_every_entry_held_ones_too(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0)])],
                       "Expenses": [("Office Supplies", [
                           L(8, "Expense", "", "Office Depot (fictional)", 500.0, 500.0, "", "Checking"),
                           L(9, "Vendor Credit", "", "Office Depot (fictional)", -40.0, 460.0, "", "Checking")])]})
        credit = rows_of(report, transaction_type="Vendor Credit")[0]
        only_the_expense = {OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, entries=qf.entry_keys(report, OFFICE)[:1])}
        result = figures(report, answers(only_the_expense))
        self.assertIn("Confirm them again", " ".join(result.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["overhead"].status)
        both = {OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, entries=qf.entry_keys(report, OFFICE))}
        result = figures(report, answers(both))
        self.assertEqual(D("500"), result.company["overhead"].amount)  # only the expense S1 counts
        self.assertEqual({credit}, holds(result.company["overhead"]))  # the credit still needs its own answer
        result = figures(report, answers(both, {credit: qf.LineAnswer(qf.OVERHEAD)}))
        self.assertEqual((D("460"), qp.COMPLETE), (result.company["overhead"].amount, result.company["overhead"].status))

    def test_a_cost_is_never_a_duplicate_of_a_sale(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 700.0, 700.0)])],
                       "Cost of Goods Sold": [("Cost of Goods Sold", [
                           L(3, "Invoice", "1001", f"{X}:Job A", 700.0, 700.0, "Pavers")])]})
        sale, cost = rows_of(report, section="Income")[0], rows_of(report, section="Cost of Goods Sold")[0]
        result = figures(report, answers({("Cost of Goods Sold", "Cost of Goods Sold"):
                                             qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)},
                                            {cost: qf.LineAnswer(qf.DUPLICATE, duplicate_of=sale)}))
        self.assertIn("same section", " ".join(result.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, result.company["job_costs"].status)


class ManualReviewOf151a80aTests(unittest.TestCase):
    """The PR #138 manual review's blockers, each with the reviewer's own example."""

    def test_two_separate_700_invoices_are_never_duplicates(self):
        # Blocker 1: two $700 invoices for Customer X, one for Job A and one for Job B: $1,400, never $700 Complete.
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 700.0, 700.0),
                                                     L(3, "Invoice", "1002", f"{X}:Job B", 700.0, 1400.0)])]})
        first, second = rows_of(report, num="1001")[0], rows_of(report, num="1002")[0]
        result = figures(report, answers(lines={second: qf.LineAnswer(qf.DUPLICATE, duplicate_of=first)}))
        self.assertIn("counts this line by itself", " ".join(result.warnings))
        self.assertEqual((D("1400"), qp.NEEDS_A_CHECK), (result.company["sales"].amount, result.company["sales"].status))
        self.assertEqual(D("700"), result.jobs[B]["sales"].amount)
        self.assertEqual(qp.NEEDS_A_CHECK, result.customers[X]["sales"].status)

    def test_a_duplicate_needs_evidence_of_the_same_posting(self):
        def case(held_type, held_name, held_num, day=2, jobs_on=True):
            report = read({"Income": [("Design income", [
                L(2, "Sales Receipt", "1001", f"{X}:Job A", 700.0, 700.0, "", "Checking"),
                L(day, held_type, held_num, held_name, 700.0, 1400.0, "", "Checking")])]})
            receipt = rows_of(report, num="1001")[0]
            held = [l.row for l in report.lines if l.row != receipt][0]
            return figures(report, answers(lines={held: qf.LineAnswer(qf.DUPLICATE, duplicate_of=receipt)},
                                           sub_customers_are_jobs=jobs_on))
        self.assertEqual((), case("Deposit", f"{X}:Job A", "").warnings)  # the plan's own example, same day
        # The re-review's blocker 1: missing contradictions are never evidence. A Journal Entry, another day, or
        # another job by the Names even with job figures off: all stay held.
        for args, says in (((("Deposit", f"{X}:Job B", ""), {}), "aren't for the same job"),
                           ((("Deposit", f"{X}:Job B", ""), {"jobs_on": False}), "aren't for the same job"),
                           ((("Deposit", f"{X}:Job A", "77"), {}), "different numbers"),
                           ((("Deposit", f"{X}:Job A", ""), {"day": 9}), "aren't on the same date"),
                           ((("Journal Entry", f"{X}:Job A", ""), {"day": 9}), "only money received or moved"),
                           ((("Journal Entry", f"{X}:Job A", "1001"), {}), "only money received or moved")):
            with self.subTest(args=args):
                result = case(*args[0], **args[1])
                self.assertIn(says, " ".join(result.warnings))
                self.assertEqual(D("700"), result.customers[X]["sales"].amount)
                self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)

    def test_a_duplicate_is_checked_against_where_the_counted_line_ended_up(self):
        # The automated review of f63462b: a $700 Sales Receipt named only "Customer X", assigned by the owner to
        # Job B, and a $700 Deposit named "Customer X:Job A" pointing to it: not the same money.
        report = read({"Income": [("Design income", [
            L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0),
            L(3, "Invoice", "1002", f"{X}:Job B", 2000.0, 6000.0),
            L(4, "Sales Receipt", "1003", X, 700.0, 6700.0, "", "Checking"),
            L(4, "Deposit", "", f"{X}:Job A", 700.0, 7400.0, "", "Checking")])]})
        receipt, deposit = rows_of(report, num="1003")[0], rows_of(report, transaction_type="Deposit")[0]
        result = figures(report, answers(lines={receipt: qf.LineAnswer(qf.REVENUE, job="Job B"),
                                                deposit: qf.LineAnswer(qf.DUPLICATE, duplicate_of=receipt)}))
        self.assertIn("aren't for the same job", " ".join(result.warnings))
        self.assertIn(deposit, holds(result.jobs[A]["sales"]))
        same_job = figures(report, answers(lines={receipt: qf.LineAnswer(qf.REVENUE, job="Job A"),
                                                  deposit: qf.LineAnswer(qf.DUPLICATE, duplicate_of=receipt)}))
        self.assertEqual((), same_job.warnings)
        self.assertEqual(D("4700"), same_job.jobs[A]["sales"].amount)

    def test_the_fingerprint_covers_totals_too(self):
        rows = fx.report_rows({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 900.0, 900.0)])]})
        changed = [r if r[:1] != ["Total for Design income"] else fx.total("Total for Design income", 950.0)
                   for r in rows]
        first = qp.read_profit_and_loss_detail("t.xlsx", fx.xlsx(rows))
        second = qp.read_profit_and_loss_detail("t.xlsx", fx.xlsx(changed))
        self.assertEqual([l.amount_text for l in first.lines], [l.amount_text for l in second.lines])
        self.assertNotEqual(qf.report_fingerprint(first), qf.report_fingerprint(second))

    def test_a_duplicate_answer_that_names_a_customer_or_job_is_refused(self):
        # The automated review of adf24cb: a Deposit named "X:Job A" matching a Job A receipt, but answered as a
        # duplicate "for Job B", contradicts itself: it stays held instead of being excluded.
        report = read({"Income": [("Design income", [
            L(2, "Sales Receipt", "1001", f"{X}:Job A", 700.0, 700.0, "", "Checking"),
            L(2, "Deposit", "", f"{X}:Job A", 700.0, 1400.0, "", "Checking")])]})
        receipt, deposit = rows_of(report, transaction_type="Sales Receipt")[0], rows_of(report, transaction_type="Deposit")[0]
        for extra in ({"job": "Job B"}, {"customer": Y}, {"no_job": True}, {"outside_job": "Old patio (fictional)"}):
            with self.subTest(extra):
                result = figures(report, answers(lines={deposit: qf.LineAnswer(qf.DUPLICATE, duplicate_of=receipt,
                                                                                **extra)}))
                self.assertIn("never belongs to a customer or a job", " ".join(result.warnings))
                self.assertEqual(qp.NEEDS_A_CHECK, result.company["sales"].status)
                self.assertNotEqual(qf.DUPLICATE, next(r for r in result.resolutions if r.row == deposit).kind)

    def test_a_refused_move_holds_the_proposed_customer_too(self):
        # The re-review's blocker 2: a -$200 credit memo exported under X that the owner says is Y's. It stays held,
        # and Y (with its job) needs a check too: Y's sales could be $100, not $300.
        report = read({"Income": [("Design income", [
            L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0),
            L(3, "Invoice", "1002", f"{Y}:Job C", 300.0, 4300.0),
            L(9, "Credit Memo", "1009", f"{X}:Job A", -200.0, 4100.0)])]})
        memo = rows_of(report, transaction_type="Credit Memo")[0]
        result = figures(report, answers(lines={memo: qf.LineAnswer(qf.REDUCTION, customer=Y)}))
        self.assertIn("an answer can't change a customer the Name proves", " ".join(result.warnings))
        for figure in (result.customers[X]["sales"], result.customers[Y]["sales"], result.jobs[(Y, "Job C")]["sales"],
                       result.company["sales"]):
            self.assertIn(memo, holds(figure))
            self.assertEqual(qp.NEEDS_A_CHECK, figure.status)
        self.assertEqual(D("300"), result.customers[Y]["sales"].amount)  # no amount moved

    def test_a_counting_answer_needs_a_readable_date_inside_the_period(self):
        # The automated review of 2b6cb7c: an answer never counts a line the report's period can't vouch for.
        for written, says in (("11/02/2026", "outside January 1-October 26, 2026"), ("2026-10-02", "can't be read")):
            with self.subTest(written):
                deposit_like = L(9, "Journal Entry", "JE-1", f"{X}:Job A", 700.0, 4700.0)
                deposit_like[1] = written
                report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0),
                                                             deposit_like])]})
                row = rows_of(report, transaction_type="Journal Entry")[0]
                result = figures(report, answers(lines={row: qf.LineAnswer(qf.REVENUE)}))
                self.assertIn(says, " ".join(result.warnings))
                self.assertEqual((D("4000"), qp.NEEDS_A_CHECK), (result.company["sales"].amount,
                                                                result.company["sales"].status))

    def test_answers_for_rows_or_accounts_not_in_the_report_are_reported(self):
        report = two_jobs()
        result = figures(report, answers({("Expenses", "Nowhere (fictional)"): qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)},
                                         {999: qf.LineAnswer(qf.REVENUE)}))
        warnings = " ".join(result.warnings)
        self.assertIn("Row 999: there's no money line on that row", warnings)
        self.assertIn("There's no account 'Expenses › Nowhere (fictional)' in this report", warnings)

    def test_overhead_never_carries_over_to_a_swapped_entry(self):
        # Blocker 3: a $500 office expense confirmed as overhead; a corrected export puts a $500 project bill in its
        # place, same account, same count and total. The confirmation never applies to it.
        def office(name, kind):
            return read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0)])],
                         "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0)]),
                                      ("Office Supplies", [L(8, kind, "", name, 500.0, 500.0, "", "Checking")])]})
        first = office("Office Depot (fictional)", "Expense")
        corrected = office(f"{X}:Job A", "Bill")
        confirmed = answers({**JOB_COSTS, OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT,
                                                                    entries=qf.entry_keys(first, OFFICE))})
        self.assertEqual(qp.COMPLETE, figures(first, confirmed).company["overhead"].status)
        # The same answers on the corrected file: bound to the first file, so none is used ...
        stale = qf.figures(corrected, dataclasses.replace(confirmed, report=qf.report_fingerprint(first)))
        self.assertIn("given for a different report", " ".join(stale.warnings))
        self.assertEqual(qp.NEEDS_A_CHECK, stale.customers[X]["profit_after_job_costs"].status)
        # ... and even re-bound to it, the entries the owner saw aren't the account's entries now.
        rebound = figures(corrected, confirmed)
        self.assertIn("aren't exactly its entries now", " ".join(rebound.warnings))
        self.assertEqual(D("0"), rebound.company["overhead"].amount)
        self.assertEqual(qp.NEEDS_A_CHECK, rebound.customers[X]["profit_after_job_costs"].status)

    def test_a_line_whose_name_proves_a_customer_is_never_overhead(self):
        # The same class as blocker 2, found by Claude: "overhead" would take the cost away from Job A.
        report = two_jobs(office=[L(8, "Expense", "", f"{X}:Job A", 500.0, 500.0, "", "Checking")])
        row = rows_of(report, transaction_type="Expense")[0]  # not Job B's $500 Bill
        result = figures(report, answers(JOB_COSTS, {row: qf.LineAnswer(qf.OVERHEAD)}))
        self.assertIn("so it can't be overhead", " ".join(result.warnings))
        self.assertIn(row, holds(result.jobs[A]["job_costs"]))
        whole_account = {OFFICE: qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, entries=qf.entry_keys(report, OFFICE))}
        result = figures(report, answers({**JOB_COSTS, **whole_account}))
        self.assertEqual(D("0"), result.company["overhead"].amount)
        self.assertIn(row, holds(result.jobs[A]["job_costs"]))
        result = figures(report, answers({**JOB_COSTS, **whole_account}, {row: qf.LineAnswer(qf.JOB_COST)}))
        self.assertEqual((D("1500"), qp.COMPLETE), (result.jobs[A]["job_costs"].amount, result.jobs[A]["job_costs"].status))

    def test_answers_without_the_reports_fingerprint_are_never_used(self):
        report = two_jobs()
        for fingerprint in ("", "0" * 64):
            with self.subTest(fingerprint=fingerprint):
                result = qf.figures(report, dataclasses.replace(answers(JOB_COSTS), report=fingerprint))
                self.assertIn("given for a different report", " ".join(result.warnings))
                self.assertEqual({}, result.jobs)  # not even "sub-customers are jobs"
                self.assertEqual(qp.NEEDS_A_CHECK, result.company["job_costs"].status)

    def test_a_job_cost_clears_job_holds_only_for_a_named_job_outside_the_report(self):
        # Blocker 4: an unassigned $900 bill marked "no job" left Job A's costs at $500 Complete.
        report = two_jobs(extra_expenses=[L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 2400.0)])
        row = rows_of(report, amount=D("900.0"))[0]
        result = figures(report, answers(JOB_COSTS, {row: qf.LineAnswer(qf.JOB_COST, customer=X, no_job=True)}))
        self.assertIn("a job cost always belongs to a job", " ".join(result.warnings))
        for job in (A, B):
            self.assertIn(row, holds(result.jobs[job]["job_costs"]))
        result = figures(report, answers(JOB_COSTS, {row: qf.LineAnswer(qf.JOB_COST, customer=X,
                                                                        outside_job="Old patio, 2025 (fictional)")}))
        self.assertEqual((), result.warnings)
        self.assertEqual(D("2400"), result.customers[X]["job_costs"].amount)  # still in the customer's costs
        for job in (A, B):
            self.assertEqual(qp.COMPLETE, result.jobs[job]["job_costs"].status)
        # The re-review's blocker 3: a spelling variant of a job in the report is that job, never one outside it.
        for spelled in ("Job A", "job a", "JOB-A", " Job  A ", "jobA"):
            with self.subTest(spelled):
                result = figures(report, answers(JOB_COSTS, {row: qf.LineAnswer(qf.JOB_COST, customer=X,
                                                                                outside_job=spelled)}))
                self.assertIn("looks like the job 'Job A' in this report", " ".join(result.warnings))
                self.assertIn(row, holds(result.jobs[A]["job_costs"]))


class MixedAccountTests(unittest.TestCase):
    """W2: each entry of a mixed account is a job cost for a verified job, overhead, or not resolved."""

    def test_each_entry_on_its_own(self):
        report = two_jobs(extra_expenses=[L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 2400.0),
                                          L(8, "Bill", "B-4", "Garden Supply (fictional)", 60.0, 2460.0)])
        first, second = rows_of(report, amount=D("900.0"))[0], rows_of(report, amount=D("60.0"))[0]
        mixed = {MATERIALS: qf.AccountAnswer(qf.MIXED_ACCOUNT)}
        # Entries with a job in their Name still need the owner's word in a mixed account.
        result = figures(report, answers(mixed, {first: qf.LineAnswer(qf.JOB_COST, X, "Job B"),
                                                    second: qf.LineAnswer(qf.OVERHEAD)}))
        self.assertEqual(qp.NEEDS_A_CHECK, result.jobs[A]["profit_after_job_costs"].status)
        named = rows_of(report, name=f"{X}:Job A")
        answered = {r: qf.LineAnswer(qf.JOB_COST) for r in rows_of(report, transaction_type="Bill")
                    if r not in (first, second)}
        result = figures(report, answers(mixed, {**answered, first: qf.LineAnswer(qf.JOB_COST, X, "Job B"),
                                                    second: qf.LineAnswer(qf.OVERHEAD)}))
        self.assertTrue(named)
        self.assertEqual(D("600"), result.jobs[B]["profit_after_job_costs"].amount)  # 2,000 - 500 - 900
        self.assertTrue(ready(result.jobs[B]["profit_after_job_costs"]))
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))
        self.assertEqual(D("60"), result.company["overhead"].amount)
        # Never forced to pick a job: an entry left unanswered holds, it isn't guessed.
        result = figures(report, answers(mixed, {**answered, first: qf.LineAnswer(qf.JOB_COST, X, "Job B")}))
        self.assertEqual({second}, holds(result.jobs[A]["profit_after_job_costs"]))

    def test_an_answer_never_replaces_what_the_name_proves(self):
        # The PR #138 manual review, blocker 2: a $700 invoice for Customer X and a $300 one for Customer Y. An
        # answer moving X's line to Y is refused: the amounts stay where the Names put them, and every figure the
        # line could change needs a check (never "X $0 Complete, Y $1,000 Complete").
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", X, 700.0, 700.0),
                                                     L(3, "Invoice", "1002", Y, 300.0, 1000.0)])]})
        row = rows_of(report, amount=D("700.0"))[0]
        for jobs_on in (True, False):
            with self.subTest(jobs_on=jobs_on):
                result = figures(report, answers(lines={row: qf.LineAnswer(qf.REVENUE, customer=Y)},
                                                 sub_customers_are_jobs=jobs_on))
                self.assertIn("an answer can't change a customer the Name proves", " ".join(result.warnings))
                self.assertEqual((D("700"), D("300")), (result.customers[X]["sales"].amount,
                                                        result.customers[Y]["sales"].amount))
                for customer in (X, Y):
                    self.assertEqual({row}, holds(result.customers[customer]["sales"]))

    def test_the_final_customer_and_job_are_checked(self):
        report = two_jobs(L(4, "Invoice", "1003", f"{Y}:Job C", 300.0, 6300.0))
        row = rows_of(report, amount=D("4000.0"))[0]
        for bad in (qf.LineAnswer(qf.REVENUE, customer=Y),
                    qf.LineAnswer(qf.REVENUE, customer=Y, job="Job A"),
                    qf.LineAnswer(qf.REVENUE, job="Job B"),
                    qf.LineAnswer(qf.REVENUE, no_job=True),
                    qf.LineAnswer(qf.REVENUE, customer="Nobody (fictional)")):
            with self.subTest(bad):
                result = figures(report, answers(JOB_COSTS, {row: bad}))
                self.assertTrue(result.warnings)
                self.assertEqual(D("4000"), result.jobs[A]["sales"].amount)  # unchanged: the answer wasn't used
                self.assertIn(row, holds(result.jobs[A]["sales"]))  # ... and its figures need a check
        unnamed = rows_of(report, amount=D("1000.0"))  # the Job A bill names its job: fine to restate it
        result = figures(report, answers(JOB_COSTS, {unnamed[0]: qf.LineAnswer(qf.JOB_COST, X, "Job A")}))
        self.assertEqual((), result.warnings)

    def test_a_job_that_isnt_in_the_report_isnt_accepted(self):
        report = two_jobs(extra_expenses=[L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 2400.0)])
        row = rows_of(report, amount=D("900.0"))[0]
        result = figures(report, answers(JOB_COSTS, {row: qf.LineAnswer(qf.JOB_COST, X, "Job Z")}))
        self.assertIn("'Job Z' isn't a job", " ".join(result.warnings))
        self.assertEqual({row}, holds(result.jobs[A]["profit_after_job_costs"]))


class NamesTests(unittest.TestCase):
    """S5: names are kept whole; split only with exactly one ":" and text on both sides."""

    def test_two_colons_or_an_empty_part_verify_nothing(self):
        report = two_jobs(L(4, "Invoice", "1003", "Bay (fictional):North:Lobby", 300.0, 6300.0),
                          L(5, "Invoice", "1004", f"{Y}:", 50.0, 6350.0))
        result = figures(report, answers(JOB_COSTS))
        self.assertNotIn("Bay (fictional)", result.customers)
        self.assertNotIn(Y, result.customers)
        for row in rows_of(report, amount=D("300.0")) + rows_of(report, amount=D("50.0")):
            self.assertIn(row, holds(result.customers[X]["sales"]))
            self.assertIn(row, holds(result.jobs[A]["profit_after_job_costs"]))
        self.assertTrue(any(l.name == "Bay (fictional):North:Lobby" for l in report.lines))  # kept whole

    def test_without_the_owners_word_profit_is_by_customer(self):
        report = two_jobs()
        for said in (None, False):
            with self.subTest(said):
                result = figures(report, qf.OwnerAnswers(sub_customers_are_jobs=said, accounts=JOB_COSTS))
                self.assertEqual({}, result.jobs)
                self.assertEqual((D("4500"), qp.COMPLETE), (result.customers[X]["profit_after_job_costs"].amount,
                                                           result.customers[X]["profit_after_job_costs"].status))

    def test_a_vendor_is_never_a_customer(self):
        report = two_jobs(extra_expenses=[L(7, "Bill", "B-3", "Garden Supply (fictional)", 900.0, 2400.0)])
        self.assertNotIn("Garden Supply (fictional)", figures(report, answers(JOB_COSTS)).customers)


class StepRuleTests(unittest.TestCase):
    def test_one_report_never_makes_a_job_complete(self):
        result = figures(two_jobs(), answers(JOB_COSTS))
        for job in (A, B):
            figure = result.jobs[job]["profit_after_job_costs"]
            self.assertEqual(qp.NEEDS_A_CHECK, figure.status)
            self.assertEqual([qf.ONE_REPORT], [h.reason for h in figure.holds])
        self.assertEqual(qp.COMPLETE, result.customers[X]["profit_after_job_costs"].status)
        self.assertIn("isn't proof the report covers the whole business", result.scope)

    def test_cash_and_card_expenses_count_as_costs(self):
        report = two_jobs(extra_expenses=[
            L(7, "Cash Expense", "", f"{X}:Job A", 40.0, 1540.0, "", "Petty Cash"),
            L(8, "Credit Card Expense", "", f"{X}:Job B", 25.5, 1565.5, "", "Mastercard")])
        result = figures(report, answers(JOB_COSTS))
        self.assertEqual((D("1040"), D("525.5")), (result.jobs[A]["job_costs"].amount, result.jobs[B]["job_costs"].amount))
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))

    def test_the_cost_of_items_sold_counts_as_a_job_cost_never_a_sale(self):
        report = two_jobs(extra_cogs=[L(2, "Invoice", "1001", f"{X}:Job A", 150.0, 150.0, "Pavers"),
                                      L(3, "Sales Receipt", "1010", f"{X}:Job B", 30.0, 180.0, "Pots")])
        result = figures(report, answers({**JOB_COSTS, ("Cost of Goods Sold", "Cost of Goods Sold"):
                                             qf.AccountAnswer(qf.JOB_COSTS_ACCOUNT)}))
        self.assertEqual((D("6000"), D("1680")), (result.company["sales"].amount, result.company["job_costs"].amount))
        self.assertEqual(D("2850"), result.jobs[A]["profit_after_job_costs"].amount)  # 4,000 - 1,000 - 150
        self.assertTrue(ready(result.jobs[A]["profit_after_job_costs"]))

    def test_an_unsorted_account_holds_every_figure_it_could_change(self):
        result = figures(two_jobs(), answers())
        for job in (A, B):
            self.assertTrue(holds(result.jobs[job]["profit_after_job_costs"]))
        for name in ("job_costs", "overhead", "profit_after_job_costs", "after_overhead"):
            self.assertEqual(qp.NEEDS_A_CHECK, result.company[name].status, name)
        self.assertEqual(qp.COMPLETE, result.company["sales"].status)

    def test_a_section_whose_totals_dont_match_holds_everything_it_feeds_whatever_the_answers(self):
        rows = fx.report_rows({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", 4000.0, 4000.0)])],
                               "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", 1000.0, 1000.0)])]})
        rows = [r if r[:1] != ["Total for Design income"] else fx.total("Total for Design income", 4100.0) for r in rows]
        report = qp.read_profit_and_loss_detail("t.xlsx", fx.xlsx(rows))
        invoice = rows_of(report, transaction_type="Invoice")[0]
        result = figures(report, answers(JOB_COSTS, {invoice: qf.LineAnswer(qf.REVENUE)}))
        self.assertEqual(D("4000"), result.company["sales"].amount)  # the owner's answer counts it ...
        for figure in (result.company["sales"], result.customers[X]["sales"], result.jobs[A]["sales"]):
            self.assertEqual(qp.NEEDS_A_CHECK, figure.status)  # ... but the section's totals still hold it
            self.assertTrue(figure.unknown_amount)

    def test_an_answer_for_an_out_of_period_line_must_be_true(self):
        report = two_jobs()
        row = rows_of(report, amount=D("4000.0"))[0]
        result = figures(report, answers(JOB_COSTS, {row: qf.LineAnswer(qf.OUTSIDE_PERIOD)}))
        self.assertIn("isn't outside", " ".join(result.warnings))
        self.assertEqual(D("6000"), result.company["sales"].amount)


if __name__ == "__main__":
    unittest.main()
