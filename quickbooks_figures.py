"""MargenX: figures from a QuickBooks Profit and Loss Detail, step 4 of the plan in issue #128.

Takes the checked ledger of step 3 (quickbooks_pnl) and the owner's answers, and works out the
company's, each customer's and each job's figures. Every figure is a sum of lines, never of totals,
and carries every "hold" that stops it being Complete, with the dollar amount being held.

The rules, from plan v7:
- S5, names. The Name is kept whole. "Customer:Job" is split only with exactly one ":" and text on
  both sides. With no ":", the Name is the customer only on an Invoice or Sales Receipt line (in
  Income, or in Cost of Goods Sold where it's the cost of the items sold); on any other line it is a
  payee, never a customer. Sub-customers count as jobs only once the owner says so; until then,
  profit is by customer.
- S7, accounts. The owner sorts each cost account once: job costs, overhead, mixed or not sure.
  "Overhead" counts only once the owner has confirmed every entry of that account at once (their
  number and total, which must still match). In a mixed account each entry is answered on its own:
  a job cost, overhead, or left not resolved. Overhead is never spread across jobs.
- S8, holds. A line counted with no known job holds every job it could belong to. A line not
  resolved holds every figure it could change. A hold never changes an amount.
- S9, resolving a line means saying what it is. What a line can be depends on its section (a line
  is never moved into another section: Other Income stays out of sales and jobs):

    | Section             | It can be                                                |
    |---------------------|----------------------------------------------------------|
    | Income              | revenue, a revenue reduction                             |
    | Cost of Goods Sold  | a job cost, overhead                                     |
    | Expenses            | a job cost, overhead                                     |
    | Other Income        | other income                                             |
    | Other Expense       | other expense                                            |
    | any                 | a duplicate of a counted line, or dated outside the period |

  Only the last row leaves the figures ("excluded").
  Money received or moved (a Payment, Deposit, Transfer...: quickbooks_rules.PAYMENT_TYPES) is never
  counted, even on the owner's word: AGENTS.md rule 4 says it is cash movement, never new revenue. It
  can only be shown to be a duplicate or outside the period; otherwise it stays held. (Plan v7's
  deposit example lets the owner confirm a Deposit as revenue; AGENTS.md wins, and the mismatch is
  raised for the owner on PR #138.)
- S3. One report never makes a job's profit Complete by itself: every job's profit keeps that hold
  until a second report cross-checks it (step 5). Complete always means complete within this
  report: its company, dates and accrual basis. A filter that QuickBooks doesn't print in the file
  can't be detected, so this is not proof that the report covers the whole business.

Nothing here is wired to an upload yet: job_intake still refuses every QuickBooks report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

import quickbooks_pnl as qp
import quickbooks_rules as qr

ZERO = Decimal("0")

# What a line is (S9).
REVENUE = "revenue"
REDUCTION = "revenue reduction"
JOB_COST = "job cost"
OVERHEAD = "overhead"
OTHER_INCOME = "other income"
OTHER_EXPENSE = "other expense"
DUPLICATE = "duplicate"
OUTSIDE_PERIOD = "outside the period"
COST_KIND_UNKNOWN = "cost, job cost or overhead not yet known"
NOT_RESOLVED = "not resolved"
EXCLUDED_KINDS = (DUPLICATE, OUTSIDE_PERIOD)

ALLOWED = {
    "Income": {REVENUE, REDUCTION, DUPLICATE, OUTSIDE_PERIOD},
    "Cost of Goods Sold": {JOB_COST, OVERHEAD, DUPLICATE, OUTSIDE_PERIOD},
    "Expenses": {JOB_COST, OVERHEAD, DUPLICATE, OUTSIDE_PERIOD},
    "Other Income": {OTHER_INCOME, DUPLICATE, OUTSIDE_PERIOD},
    "Other Expenses": {OTHER_EXPENSE, DUPLICATE, OUTSIDE_PERIOD},
}
COST_SECTIONS = ("Cost of Goods Sold", "Expenses")

# How an account is usually used (S7).
JOB_COSTS_ACCOUNT = "job costs"
OVERHEAD_ACCOUNT = "overhead"
MIXED_ACCOUNT = "mixed"
NOT_SURE_ACCOUNT = "not sure"
ACCOUNT_USES = (JOB_COSTS_ACCOUNT, OVERHEAD_ACCOUNT, MIXED_ACCOUNT, NOT_SURE_ACCOUNT)

ONE_REPORT = ("One report alone can't make a job's profit Complete: a second report has to cross-check its "
              "sales first (issue #128, S3).")


@dataclass(frozen=True)
class LineAnswer:
    """What the owner said one line is (S9), or which job a mixed-account entry belongs to (S7)."""
    kind: str  # REVENUE, REDUCTION, JOB_COST, OVERHEAD, OTHER_INCOME, OTHER_EXPENSE, DUPLICATE or OUTSIDE_PERIOD
    customer: str | None = None  # for revenue, a reduction or a job cost: the customer, when it isn't in the Name
    job: str | None = None  # ... and the job
    outside_jobs: bool = False  # it belongs to no job in this report (no job at all, or a job outside it)
    duplicate_of: int | None = None  # for DUPLICATE: the Excel row of the counted line it repeats
    answered_at: str = ""


@dataclass(frozen=True)
class AccountAnswer:
    """How the owner usually uses one cost account (S7). For OVERHEAD, the number and total of the
    entries the owner confirmed, all at once; if the account's entries change, the answer no longer
    applies."""
    use: str
    entries: int | None = None
    total: Decimal | None = None
    answered_at: str = ""


@dataclass(frozen=True)
class OwnerAnswers:
    sub_customers_are_jobs: bool | None = None  # "Do you use sub-customers in QuickBooks for jobs?"
    accounts: Mapping[tuple[str, ...], AccountAnswer] = field(default_factory=dict)  # by account path as written
    lines: Mapping[int, LineAnswer] = field(default_factory=dict)  # by Excel row


@dataclass(frozen=True)
class Hold:
    row: int | None  # the line that holds the figure, or None for the report itself
    amount: Decimal | None  # the amount being held (None when it isn't known)
    reason: str


@dataclass(frozen=True)
class Figure:
    amount: Decimal  # the sum of the lines counted in it
    holds: tuple[Hold, ...]

    @property
    def status(self) -> str:
        return qp.COMPLETE if not self.holds else qp.NEEDS_A_CHECK

    @property
    def held_amount(self) -> Decimal:
        """The known amounts being held, each line once."""
        seen = {}
        for hold in self.holds:
            if hold.row is not None and hold.amount is not None:
                seen[hold.row] = hold.amount
        return sum(seen.values(), ZERO)

    @property
    def unknown_amount(self) -> bool:
        """True when something held has no known amount (a whole section, or an unreadable line)."""
        return any(hold.amount is None for hold in self.holds)


@dataclass(frozen=True)
class Resolution:
    """What one ledger line was taken to be, and why: the ledger's record of the owner's answers (S8, S9)."""
    row: int
    amount: Decimal | None
    kind: str
    customer: str | None
    job: str | None
    reason: str
    answer: LineAnswer | AccountAnswer | None = None
    duplicate_of: int | None = None


@dataclass(frozen=True)
class Figures:
    scope: str
    jobs_on: bool
    company: dict[str, Figure]  # sales, job_costs, profit_after_job_costs, overhead, other, after_overhead
    customers: dict[str, dict[str, Figure]]  # customer -> sales, job_costs, profit_after_job_costs
    jobs: dict[tuple[str, str], dict[str, Figure]]  # (customer, job) -> sales, job_costs, profit_after_job_costs
    resolutions: tuple[Resolution, ...]
    warnings: tuple[str, ...]  # answers that couldn't be used, in plain words


# --- names (S5) -----------------------------------------------------------------------------------

def _type(line: qp.LedgerLine) -> str:
    return " ".join(line.transaction_type.split()).casefold()


def names_of(line: qp.LedgerLine) -> tuple[str | None, str | None]:
    """(customer, job) the line's Name proves (S5); None for what it doesn't."""
    name = line.name.strip()
    if name.count(":") == 1:
        customer, job = (part.strip() for part in name.split(":"))
        return (customer, job) if customer and job else (None, None)
    if ":" in name or not name:
        return None, None
    if _type(line) in qr.SALE_TYPES and line.section in ("Income", "Cost of Goods Sold"):
        return name, None  # the customer on a sales line, or on the cost of items sold
    return None, None  # a payee: never a customer


# --- the figures ----------------------------------------------------------------------------------

ALL = object()  # every customer, or every job


class _Builder:
    def __init__(self, report: qp.ProfitAndLossDetail, answers: OwnerAnswers):
        self.report = report
        self.answers = answers
        self.jobs_on = answers.sub_customers_are_jobs is True
        self.lines = {line.row: line for line in report.lines}
        self.customers: set[str] = set()
        self.jobs: set[tuple[str, str]] = set()
        for line in report.lines:
            customer, job = names_of(line)
            if customer:
                self.customers.add(customer)
                if job and self.jobs_on:
                    self.jobs.add((customer, job))
        self.amounts: dict[tuple, Decimal] = {}
        self.holds: dict[tuple, list[Hold]] = {}
        self.pending: list[tuple] = []  # (scope, field, hold) with ALL or "jobs of" scopes, resolved at the end
        self.resolutions: list[Resolution] = []
        self.warnings: list[str] = []

    # -- writing --
    def add(self, key: tuple, amount: Decimal) -> None:
        self.amounts[key] = self.amounts.get(key, ZERO) + amount

    def hold(self, where: str, who, figure: str, hold: Hold) -> None:
        """where: company, customer or job; who: a name, (customer, job), ALL, or ("jobs of", customer)."""
        self.pending.append((where, who, figure, hold))

    def hold_customer_and_jobs(self, customer, job, figure: str, hold: Hold, *, jobs_too: bool = True) -> None:
        """S8: a verified customer, else every customer; its job, else every job of the customer, else every job."""
        self.hold("customer", customer if customer else ALL, figure, hold)
        if self.jobs_on and jobs_too:
            if customer and job:
                self.hold("job", (customer, job), figure, hold)
            else:
                self.hold("job", ("jobs of", customer) if customer else ALL, figure, hold)

    # -- answers --
    def account_use(self, line: qp.LedgerLine) -> tuple[str | None, AccountAnswer | None, str]:
        answer = self.answers.accounts.get(line.account_path)
        if answer is None:
            return None, None, f"You haven't said yet how the account '{' › '.join(line.account_path)}' is used."
        if answer.use not in ACCOUNT_USES:
            self.warn(f"The answer '{answer.use}' for '{' › '.join(line.account_path)}' isn't one MargenX knows.")
            return None, None, "That account's answer couldn't be used."
        if answer.use == OVERHEAD_ACCOUNT:
            entries = [l for l in self.report.lines if l.account_path == line.account_path and l.outcome == qp.INCLUDED]
            total = sum((l.amount for l in entries), ZERO)
            if answer.entries != len(entries) or answer.total != total:
                self.warn(f"You confirmed {answer.entries} entries ({answer.total}) in "
                          f"'{' › '.join(line.account_path)}' as overhead, but it now has {len(entries)} ({total}). "
                          "Confirm them again.")
                return None, None, "The overhead confirmation no longer matches the account's entries."
        return answer.use, answer, ""

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)

    def usable(self, line: qp.LedgerLine, answer: LineAnswer) -> str:
        """Why an answer can't be used for this line; empty when it can."""
        section = line.section
        if section not in ALLOWED or answer.kind not in ALLOWED[section]:
            return (f"a line in {section or 'no section'} can't be '{answer.kind}'; it can be "
                    + ", ".join(sorted(ALLOWED.get(section, {DUPLICATE, OUTSIDE_PERIOD}))))
        if answer.outside_jobs and answer.job is not None:
            return "it can't both belong to a job and to no job in this report"
        if answer.kind not in EXCLUDED_KINDS and _type(line) in qr.PAYMENT_TYPES:
            return (f"'{line.transaction_type.strip()}' is money received or moved, never new revenue or a cost "
                    "(AGENTS.md rule 4); it can only be a duplicate or outside the period")
        if answer.kind in EXCLUDED_KINDS:
            if answer.kind == OUTSIDE_PERIOD:
                when = qp._date(line.date)
                layout = self.report.layout
                if when is None or layout.period_start <= when <= layout.period_end:
                    return f"it's dated {line.date.strip() or '(no date)'}, which isn't outside {layout.period}"
            return ""  # duplicates are checked once every other line is known
        if line.amount is None:
            return "its amount isn't known, so it can't be counted"
        if answer.kind == REVENUE and line.amount < 0:
            return "revenue can't be negative; a negative line is a revenue reduction"
        if answer.kind == REDUCTION and line.amount > 0:
            return "a revenue reduction lowers sales, so it can't be positive"
        if answer.kind in (REVENUE, REDUCTION, JOB_COST):
            if answer.job is not None and not self.jobs_on:
                return "you haven't said that sub-customers are jobs, so profit is by customer"
            customer, job = self.who(line, answer)
            # The final customer and job are checked, not just what the answer named (the automated review
            # of 7da2180): a job must be one of that customer's jobs in this report.
            if customer is not None and customer not in self.customers:
                return f"'{customer}' isn't a customer in this report"
            if job is not None and (customer, job) not in self.jobs:
                return f"'{job}' isn't a job of '{customer}' in this report"
            if job is not None and customer is None:
                return "a job needs its customer"
        return ""

    def who(self, line: qp.LedgerLine, answer: LineAnswer | None) -> tuple[str | None, str | None]:
        customer, job = names_of(line)
        if answer is not None:
            if answer.customer is not None and answer.customer != customer:
                # Another customer: the Name's job was the old customer's, so it never carries over.
                customer, job = answer.customer, None
            job = answer.job or job
            if answer.outside_jobs:
                job = None
        return customer, (job if self.jobs_on else None)

    # -- one line --
    def place(self, line: qp.LedgerLine) -> Resolution:
        answer = self.answers.lines.get(line.row)
        if answer is not None:
            problem = self.usable(line, answer)
            if problem:
                self.warn(f"Row {line.row}: your answer '{answer.kind}' can't be used: {problem}.")
                answer = None
        if answer is not None and answer.kind in EXCLUDED_KINDS:
            return Resolution(line.row, line.amount, answer.kind, None, None, f"You said it's {answer.kind}.", answer,
                              answer.duplicate_of)
        if answer is not None:
            customer, job = self.who(line, answer)
            return self.count(line, answer.kind, customer, job, f"You said it's {answer.kind}.", answer,
                              outside_jobs=answer.outside_jobs)
        if line.outcome == qp.INCLUDED and line.counts_as == qr.SALE:
            customer, job = self.who(line, None)
            return self.count(line, REVENUE, customer, job, line.reason, None)
        if line.outcome == qp.INCLUDED and line.counts_as == qr.COST:
            use, account_answer, why = self.account_use(line)
            customer, job = self.who(line, None)
            if use == JOB_COSTS_ACCOUNT:
                return self.count(line, JOB_COST, customer, job, "Its account holds job costs.", account_answer)
            if use == OVERHEAD_ACCOUNT:
                return self.count(line, OVERHEAD, None, None, "You confirmed every entry of its account as overhead.",
                                  account_answer)
            why = why or ("Its account is mixed: say whether this entry is a job cost or overhead." if use == MIXED_ACCOUNT
                          else "You said you're not sure how its account is used.")
            return self.count(line, COST_KIND_UNKNOWN, customer, job, why, account_answer)
        return self.unresolved(line)

    def count(self, line, kind, customer, job, reason, answer, *, outside_jobs: bool = False) -> Resolution:
        amount = line.amount
        row = line.row
        if kind in (REVENUE, REDUCTION, JOB_COST):
            figure = "sales" if kind in (REVENUE, REDUCTION) else "job_costs"
            self.add(("company", figure), amount)
            if customer:
                self.add(("customer", customer, figure), amount)
                if job:
                    self.add(("job", (customer, job), figure), amount)
                elif self.jobs_on and not outside_jobs:
                    self.hold("job", ("jobs of", customer), figure, Hold(
                        row, amount, f"Row {row} ({amount:,.2f}) is {customer}'s, but which job it belongs to isn't known."))
            else:
                hold = Hold(row, amount, f"Row {row} ({amount:,.2f}) is counted, but whose it is isn't known.")
                self.hold("customer", ALL, figure, hold)
                if self.jobs_on and not outside_jobs:
                    self.hold("job", ALL, figure, hold)
        elif kind == OVERHEAD:
            self.add(("company", "overhead"), amount)
        elif kind in (OTHER_INCOME, OTHER_EXPENSE):
            self.add(("company", "other"), amount if kind == OTHER_INCOME else -amount)
        elif kind == COST_KIND_UNKNOWN:
            hold = Hold(row, amount, f"Row {row} ({amount:,.2f}) is a cost, but whether it's a job cost or overhead "
                                     "isn't known yet.")
            self.hold("company", None, "job_costs", hold)
            self.hold("company", None, "overhead", hold)
            self.hold_customer_and_jobs(customer, job, "job_costs", hold)
        return Resolution(row, amount, kind, customer, job, reason, answer)

    def unresolved(self, line: qp.LedgerLine) -> Resolution:
        row, amount = line.row, line.amount
        shown = f"{amount:,.2f}" if amount is not None else "amount unknown"
        hold = Hold(row, amount, f"Row {row} ({shown}) isn't resolved yet: {line.reason.split(' It stays')[0]}")
        customer, job = self.who(line, None)
        if line.section == "Income":
            self.hold("company", None, "sales", hold)
            self.hold_customer_and_jobs(customer, job, "sales", hold)
        elif line.section in COST_SECTIONS:
            self.hold("company", None, "job_costs", hold)
            self.hold("company", None, "overhead", hold)
            self.hold_customer_and_jobs(customer, job, "job_costs", hold)
        elif line.section in ("Other Income", "Other Expenses"):
            self.hold("company", None, "other", hold)
        else:
            self.hold_everything(hold)
        return Resolution(row, amount, NOT_RESOLVED, customer, job, line.reason)

    def hold_everything(self, hold: Hold) -> None:
        for figure in ("sales", "job_costs", "overhead", "other"):
            self.hold("company", None, figure, hold)
        for figure in ("sales", "job_costs"):
            self.hold_customer_and_jobs(None, None, figure, hold)

    def check_duplicates(self, resolutions: list[Resolution]) -> list[Resolution]:
        """S9: a duplicate must point to a specific counted line with the same customer and amount."""
        counted = {r.row: r for r in resolutions if r.kind in (REVENUE, REDUCTION, JOB_COST, OVERHEAD, OTHER_INCOME,
                                                               OTHER_EXPENSE)}
        final = []
        for resolution in resolutions:
            if resolution.kind != DUPLICATE:
                final.append(resolution)
                continue
            line = self.lines[resolution.row]
            target = counted.get(resolution.duplicate_of)
            mine, _ = names_of(line)
            problem = ""
            if target is None:
                problem = f"row {resolution.duplicate_of} isn't a counted line"
            elif line.amount is None or target.amount != line.amount:
                problem = "a duplicate must have the same amount as the line it repeats"
            elif not mine or mine != target.customer:
                problem = "a duplicate must have the same customer as the line it repeats"
            if problem:
                self.warn(f"Row {resolution.row}: your answer '{DUPLICATE}' can't be used: {problem}.")
                final.append(self.unresolved(line))
            else:
                final.append(resolution)
        return final

    # -- the whole report --
    def build(self) -> Figures:
        resolutions = self.check_duplicates([self.place(line) for line in self.report.lines])
        for problem in self.report.problems:
            # A total that doesn't match, or a row that can't be placed: every figure its section feeds needs
            # a check, whatever the answers (S6). It isn't tied to one line, so its amount isn't known.
            hold = Hold(None, None, f"The report's own totals don't all match its lines (row {problem.row}: "
                                    f"{problem.text}).")
            section = qp.SECTION_NAMES.get(problem.section) if problem.section else None
            if section == "Income":
                self.hold("company", None, "sales", hold)
                self.hold_customer_and_jobs(None, None, "sales", hold)
            elif section in COST_SECTIONS:
                self.hold("company", None, "job_costs", hold)
                self.hold("company", None, "overhead", hold)
                self.hold_customer_and_jobs(None, None, "job_costs", hold)
            elif section in ("Other Income", "Other Expenses"):
                self.hold("company", None, "other", hold)
            else:
                self.hold_everything(hold)
        return Figures(self.scope(), self.jobs_on, *self.assemble(), tuple(resolutions), tuple(self.warnings))

    def scope(self) -> str:
        layout = self.report.layout
        return (f"Within QuickBooks' Profit and Loss Detail for {layout.company}, {layout.period}, "
                f"{layout.basis.lower()} basis. A filter QuickBooks doesn't print in the file can't be seen, so "
                "this isn't proof the report covers the whole business.")

    def assemble(self):
        holds: dict[tuple, list[Hold]] = {}

        def put(key, hold):
            bucket = holds.setdefault(key, [])
            if hold not in bucket:
                bucket.append(hold)

        for where, who, figure, hold in self.pending:
            if where == "company":
                put(("company", figure), hold)
            elif where == "customer":
                for customer in (self.customers if who is ALL else [who]):
                    put(("customer", customer, figure), hold)
            else:
                if who is ALL:
                    targets = self.jobs
                elif isinstance(who, tuple) and who[0] == "jobs of":
                    targets = [j for j in self.jobs if j[0] == who[1]]
                else:
                    targets = [who]
                for job in targets:
                    put(("job", job, figure), hold)

        def figure(key):
            return Figure(self.amounts.get(key, ZERO), tuple(holds.get(key, ())))

        def derived(amount, *parts, extra=()):
            seen = []
            for part in parts:
                for hold in part.holds:
                    if hold not in seen:
                        seen.append(hold)
            return Figure(amount, tuple(seen) + tuple(extra))

        sales, costs = figure(("company", "sales")), figure(("company", "job_costs"))
        overhead, other = figure(("company", "overhead")), figure(("company", "other"))
        profit = derived(sales.amount - costs.amount, sales, costs)
        company = {"sales": sales, "job_costs": costs, "profit_after_job_costs": profit, "overhead": overhead,
                   "other": other,
                   "after_overhead": derived(profit.amount - overhead.amount + other.amount, profit, overhead, other)}
        customers = {}
        for customer in sorted(self.customers):
            s, c = figure(("customer", customer, "sales")), figure(("customer", customer, "job_costs"))
            customers[customer] = {"sales": s, "job_costs": c, "profit_after_job_costs": derived(s.amount - c.amount, s, c)}
        jobs = {}
        for job in sorted(self.jobs):
            s, c = figure(("job", job, "sales")), figure(("job", job, "job_costs"))
            jobs[job] = {"sales": s, "job_costs": c,
                         "profit_after_job_costs": derived(s.amount - c.amount, s, c, extra=(Hold(None, None, ONE_REPORT),))}
        return company, customers, jobs


def figures(report: qp.ProfitAndLossDetail, answers: OwnerAnswers | None = None) -> Figures:
    """Company, customer and job figures from a checked Profit and Loss Detail and the owner's answers."""
    return _Builder(report, answers or OwnerAnswers()).build()
