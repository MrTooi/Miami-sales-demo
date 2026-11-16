"""MargenX: the owner's questions about a QuickBooks report, step 6a of the plan in issue #128.

Plan v7, step 6 ("Simpler questions"): group questions where S7 allows, show progress ("Question 2 of
5"), let the owner skip, go back, change an answer and review what's left, show the original row and
dollar amount, give no default answers, and use plain words with the codes in small print.

This module is the list behind those screens; it has no screen of its own (step 6b shows it, and
nothing is wired to an upload yet: job_intake still refuses every QuickBooks report).

- open_questions(...) works out every question still open from the checked report(s) and the answers
  so far, in a fixed order: whether sub-customers are jobs; the no-filter confirmation (only when a
  usable cross-check exists); each cost account's usual use (S7, one question per account, grouped);
  then each line that still needs the owner's word (S9; mixed-account entries one by one).
- Every question carries its own progress ("2 of 5"), plain words, the line's original row, date,
  Name and amount where it has one, and exactly the choices the rules allow: no choice is
  pre-selected, and "not sure" is always allowed (the question just stays open).
- answer(...) returns new OwnerAnswers with one answer applied (never changing the old ones), bound
  to the report. Skipping is not answering; going back or changing an answer is answering again; the
  list is recomputed after every answer, so it always shows what's left.
- A line MargenX can never count (money received or moved, AGENTS.md rule 4) isn't a question: it is
  listed in held_lines with the reason, so the owner sees it without being asked to do the impossible.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal

import quickbooks_figures as qf
import quickbooks_pnl as qp
import quickbooks_rules as qr

JOBS = "jobs"  # "Do you use sub-customers in QuickBooks for jobs?"
NO_FILTER = "no filter"  # "Were both reports exported with no filter?"
ACCOUNT = "account"  # S7: how a cost account is usually used
LINE = "line"  # S9: what one line is, or which job it is for

NOT_SURE = "not sure"  # always a choice; it leaves the question open
SEPARATOR = "\x1f"  # between a customer and a job in a "job:" choice value


@dataclass(frozen=True)
class Choice:
    value: str
    label: str  # plain words


NOT_SURE_CHOICE = Choice(NOT_SURE, "Not sure yet: leave it on \"Needs a check\"")


@dataclass(frozen=True)
class Question:
    key: str  # stable: the same question keeps the same key between answers
    kind: str  # JOBS, NO_FILTER, ACCOUNT or LINE
    number: int  # 1-based position among the open questions
    total: int
    title: str  # plain words
    details: tuple[str, ...]  # what the owner needs to see to answer (row, date, Name, amount; entries)
    small_print: str  # codes: rows, account paths, types
    choices: tuple[Choice, ...]
    row: int | None = None  # for LINE
    account: tuple[str, ...] | None = None  # for ACCOUNT
    amount: Decimal | None = None
    entries: tuple = ()  # for ACCOUNT: the exact entries shown (what an "overhead" answer confirms)
    report: str = ""  # the report it was asked about (its fingerprint): an answer for any other report changes nothing
    pair: str = ""  # for NO_FILTER: the exact pair of reports it was asked about (CrossCheck.pair)
    line_kind: str = ""  # for "which job": what the line is, as the question shows it (a job answer keeps exactly this)

    @property
    def progress(self) -> str:
        return f"Question {self.number} of {self.total}"


@dataclass(frozen=True)
class HeldLine:
    """A line MargenX never counts and can't ask about (money received or moved): shown, never asked."""
    row: int
    amount: Decimal | None
    reason: str


@dataclass(frozen=True)
class QuestionList:
    questions: tuple[Question, ...]
    held_lines: tuple[HeldLine, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    # The report's own problems (totals that don't match its lines...): shown first, because the figures they
    # touch stay on "Needs a check" whatever the answers.
    report_problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def done(self) -> bool:
        return not self.questions


def _money(amount: Decimal | None) -> str:
    if amount is None:
        return "amount unknown"
    return f"-${-amount:,.2f}" if amount < 0 else f"${amount:,.2f}"


def _type_and_number(line: qp.LedgerLine) -> str:
    return " ".join(part for part in (line.transaction_type.strip(), line.num.strip()) if part)


def _account_summary(entries: list[qp.LedgerLine], total: Decimal) -> str:
    """How many entries and their total. A total is never shown as complete when an amount can't be read (the
    automated review of b3921fe)."""
    count = f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
    unknown = sum(1 for l in entries if l.amount is None)
    if unknown:
        return (f"{count}: {_money(total)} that MargenX can read, and {unknown} with an amount it can't read, so "
                "the account's total isn't known:")
    return f"{count}, {_money(total)} in all:"


def _line_details(line: qp.LedgerLine) -> tuple[str, ...]:
    return (f"{line.date.strip() or '(no date)'} · {line.transaction_type.strip() or '(no type)'} "
            f"{line.num.strip()}".rstrip(),
            f"{line.name.strip() or '(no name)'} · {_money(line.amount)}",
            " › ".join(line.account_path))


KIND_LABELS = {
    qf.REVENUE: "A sale (money a customer owes or paid for work)",
    qf.REDUCTION: "A reduction of a sale (a credit, refund or discount)",
    qf.JOB_COST: "A cost of a job",
    qf.OVERHEAD: "Overhead (a cost of running the business, not of one job)",
    qf.OTHER_INCOME: "Other income (not from work for customers, like interest)",
    qf.OTHER_EXPENSE: "Other expense (not a cost of the work, like a penalty)",
    qf.OUTSIDE_PERIOD: "It belongs to another period, so leave it out",
}
ACCOUNT_LABELS = {
    qf.JOB_COSTS_ACCOUNT: "Job costs: what's in it is spent on specific jobs",
    qf.OVERHEAD_ACCOUNT: "Overhead: what's in it is a cost of running the business (I've checked every entry below)",
    qf.MIXED_ACCOUNT: "Mixed: some entries are for jobs, some are overhead (I'll answer them one by one)",
}


def open_questions(report: qp.ProfitAndLossDetail, answers: qf.OwnerAnswers | None = None,
                   cross_check=None) -> QuestionList:
    """Every question still open, in order, with its progress, and the lines MargenX holds without asking."""
    answers = answers or qf.OwnerAnswers()
    result = qf.figures(report, answers, cross_check=cross_check)
    bound = answers.report == qf.report_fingerprint(report)
    resolutions = {r.row: r for r in result.resolutions}
    lines = {l.row: l for l in report.lines}
    pending: list[dict] = []
    held: list[HeldLine] = []

    if (not bound or answers.sub_customers_are_jobs is None) and any(qf.names_of(l)[1] for l in report.lines):
        examples = sorted({l.name.strip() for l in report.lines if qf.names_of(l)[1]})[:3]
        pending.append(dict(key="jobs", kind=JOBS,
                            title="Do you use sub-customers in QuickBooks for jobs?",
                            details=("Some names look like \"Customer:Job\", for example: " + "; ".join(examples) + ".",
                                     "If you say yes, MargenX shows profit by job; if no, by customer."),
                            small_print="Plan rule S5", choices=(Choice("yes", "Yes, each sub-customer is a job"),
                                                                 Choice("no", "No, show profit by customer"))))

    if cross_check is not None and getattr(cross_check, "usable", False) and (
            not bound or answers.unfiltered_pair != cross_check.pair):
        pending.append(dict(key="no-filter", kind=NO_FILTER, pair=cross_check.pair,
                            title="Did you export both reports for the whole business, with no filter?",
                            details=("No filter means all customers and all accounts, for the same dates.",
                                     "MargenX can't see a filter QuickBooks doesn't print in the file, so it needs "
                                     "your word before a job's profit can be Complete."),
                            small_print="Plan rule S4",
                            choices=(Choice("yes", "Yes, both have no filter"),)))

    accounts: dict[tuple[str, ...], list[qp.LedgerLine]] = {}
    for line in report.lines:
        if line.section in qf.COST_SECTIONS and line.outcome == qp.INCLUDED:
            accounts.setdefault(line.account_path, []).append(line)
    mixed = set()
    for path, entries in accounts.items():
        given = answers.accounts.get(path) if bound else None
        if given is not None and given.use == qf.MIXED_ACCOUNT:
            mixed.add(path)
        settled = given is not None and given.use in (qf.JOB_COSTS_ACCOUNT, qf.MIXED_ACCOUNT) or (
            given is not None and given.use == qf.OVERHEAD_ACCOUNT
            and tuple(given.entries) == qf.entry_keys(report, path))
        if settled:
            continue
        everything = [l for l in report.lines if l.account_path == path]
        total = sum((l.amount for l in everything if l.amount is not None), Decimal("0"))
        pending.append(dict(key="account:" + " › ".join(path), kind=ACCOUNT, account=path, amount=total,
                            entries=qf.entry_keys(report, path),
                            title=f"How do you usually use the account \"{path[-1]}\"?",
                            details=(_account_summary(everything, total),
                                     *(f"Row {l.row} · {l.date.strip()} · {_type_and_number(l)} · {l.name.strip()} · "
                                       f"{_money(l.amount)}" for l in everything)),
                            small_print=" › ".join(path) + " · plan rule S7",
                            choices=tuple(Choice(k, v) for k, v in ACCOUNT_LABELS.items())))

    for row in sorted(resolutions):
        resolution, line = resolutions[row], lines[row]
        when = qp._date(line.date)
        if resolution.kind == qf.NOT_RESOLVED and when is None:
            held.append(HeldLine(row, line.amount, f"Row {row} ({_money(line.amount)}): its date "
                                                   f"'{line.date.strip()}' can't be read, so no answer can count it. "
                                                   "It stays held, with its amount shown."))
            continue
        if _type(line) in qr.PAYMENT_TYPES and resolution.kind == qf.NOT_RESOLVED and report.layout.in_period(when):
            held.append(HeldLine(row, line.amount, f"Row {row} ({_money(line.amount)}) is money received or "
                                                   "moved, so MargenX never counts it (AGENTS.md rule 4). It "
                                                   "stays held, with its amount shown."))
            continue
        question = _line_question(report, answers if bound else qf.OwnerAnswers(), result, resolution, line, mixed)
        if question:
            pending.append(question)

    total = len(pending)
    fingerprint = qf.report_fingerprint(report)
    questions = tuple(Question(number=index + 1, total=total, report=fingerprint,
                               **{**item, "choices": (*item["choices"], NOT_SURE_CHOICE)})
                      for index, item in enumerate(pending))
    problems = tuple(f"Row {p.row}: {p.text}" for p in report.problems)
    return QuestionList(questions, tuple(held), result.warnings, problems)


def _type(line: qp.LedgerLine) -> str:
    return " ".join(line.transaction_type.split()).casefold()


def _line_question(report, answers, result, resolution, line, mixed) -> dict | None:
    """The question for one line, or None when it needs nothing from the owner."""
    row = line.row
    common = dict(key=f"line:{row}", kind=LINE, row=row, amount=line.amount, details=_line_details(line),
                  small_print=f"Row {row} · {line.transaction_type.strip()} · " + " › ".join(line.account_path))
    if line.amount is None or line.section is None:
        return None  # nothing an answer could do: it stays held, with the report's problem shown
    allowed = [k for k in qf.ALLOWED.get(line.section, ()) if k in KIND_LABELS]
    when = qp._date(line.date)
    outside = when is not None and not report.layout.in_period(when)
    if outside:
        allowed = [qf.OUTSIDE_PERIOD]  # a line outside the period can only be left out: nothing can count it
    else:
        allowed = [k for k in allowed if k != qf.OUTSIDE_PERIOD]
    if _type(line) in qr.PAYMENT_TYPES:
        allowed = [k for k in allowed if k == qf.OUTSIDE_PERIOD]  # money moved is never counted (AGENTS.md rule 4)
    if line.amount < 0:
        allowed = [k for k in allowed if k != qf.REVENUE]
    elif line.amount > 0:
        allowed = [k for k in allowed if k != qf.REDUCTION]
    if resolution.kind == qf.NOT_RESOLVED:
        reason = line.reason.split(" It stays")[0]
        return {**common, "title": f"What is this {_money(line.amount)} line?",
                "details": (*common["details"], f"Why MargenX asks: {reason}"),
                "choices": tuple(Choice(k, KIND_LABELS[k]) for k in allowed)}
    if resolution.kind == qf.COST_KIND_UNKNOWN and line.account_path in mixed:
        return {**common, "title": f"Is this {_money(line.amount)} entry a job cost or overhead?",
                "choices": tuple(Choice(k, KIND_LABELS[k]) for k in (qf.JOB_COST, qf.OVERHEAD) if k in allowed)}
    if result.jobs_on and resolution.kind in (qf.REVENUE, qf.REDUCTION, qf.JOB_COST) and resolution.job is None:
        customer = resolution.customer
        settled = row in answers.lines and (answers.lines[row].no_job or answers.lines[row].outside_job)
        if settled:
            return None
        # Its customer's jobs when its customer is known; otherwise every job in the report, with its customer.
        pairs = sorted(pair for pair in result.jobs if customer is None or pair[0] == customer)
        if not pairs:
            # A customer with no jobs in the report: the line can hold no job back (S8), so there is nothing to ask.
            return None
        whose = f"{customer}'s" if customer else "nobody's that MargenX can tell (the name is a payee, not a customer)"
        choices = [Choice(f"job:{c}{SEPARATOR}{job}", f"Job \"{job}\"" + ("" if customer else f" ({c})"))
                   for c, job in pairs]
        if resolution.kind in (qf.REVENUE, qf.REDUCTION):
            choices.append(Choice("no job", "It isn't for any job"))
        if customer is not None:
            choices.append(Choice("outside job", "A job that isn't in this report (I'll name it)"))
        if resolution.kind == qf.JOB_COST and customer is None:
            choices.append(Choice(qf.OVERHEAD, KIND_LABELS[qf.OVERHEAD]))
        return {**common, "key": f"job:{row}", "line_kind": resolution.kind,
                "title": f"Which job is this {_money(line.amount)} for?",
                "details": (*common["details"], f"It's {whose}, but which job it belongs to isn't known."),
                "choices": tuple(choices)}
    return None


def answer(report: qp.ProfitAndLossDetail, answers: qf.OwnerAnswers | None, question: Question, choice: str, *,
           outside_job: str | None = None, cross_check=None, answered_at: str = "") -> qf.OwnerAnswers:
    """New answers with one question answered (the old answers are never changed), bound to this report.

    - A question asked about another report changes nothing (the automated review of 8370349).
    - NOT_SURE clears any earlier answer to this question, so it is open again and its figures go back to
      "Needs a check" (going back and saying "not sure"). Skipping is simply not calling this.
    - A choice the question doesn't offer changes nothing."""
    answers = answers or qf.OwnerAnswers()
    fingerprint = qf.report_fingerprint(report)
    if question.report != fingerprint:
        return answers
    if answers.report != fingerprint:
        answers = qf.OwnerAnswers()  # answers for another report are never carried over
    answers = dataclasses.replace(answers, report=fingerprint)
    if choice == NOT_SURE:
        return _reopen(report, answers, question)
    if choice not in {c.value for c in question.choices}:
        return answers
    if question.kind == JOBS:
        return dataclasses.replace(answers, sub_customers_are_jobs=choice == "yes")
    if question.kind == NO_FILTER:
        if cross_check is None or not getattr(cross_check, "usable", False) or cross_check.pair != question.pair:
            return answers  # only the pair of reports the question was asked about can be confirmed
        return dataclasses.replace(answers, unfiltered_pair=cross_check.pair)
    if question.kind == ACCOUNT:
        entries = tuple(question.entries) if choice == qf.OVERHEAD_ACCOUNT else ()  # exactly the entries shown
        accounts = {**answers.accounts, question.account: qf.AccountAnswer(choice, entries, answered_at)}
        return dataclasses.replace(answers, accounts=accounts)
    lines = dict(answers.lines)
    previous = lines.get(question.row)
    if question.key.startswith("job:"):
        # Every choice of a "which job" question, overhead included (the automated reviews of 872a31a, bbee1be).
        # What the line is comes from the question, never from the earlier answer: after "overhead", a job makes
        # it a job cost again.
        if not _still_current(report, answers, question):
            return answers  # the line has been answered (or reopened) as something else since this question was asked
        kind = question.line_kind
        if choice == qf.OVERHEAD:
            lines[question.row] = qf.LineAnswer(qf.OVERHEAD, answered_at=answered_at)
        elif choice.startswith("job:"):
            customer, job = choice[4:].split(SEPARATOR, 1)
            named = qf.names_of(next(l for l in report.lines if l.row == question.row))[0]
            lines[question.row] = qf.LineAnswer(kind, customer=None if named else customer, job=job,
                                                answered_at=answered_at)
        elif choice == "no job":
            lines[question.row] = qf.LineAnswer(kind, no_job=True, answered_at=answered_at)
        else:
            if not (outside_job or "").strip():
                return answers  # an outside job must be named; the question stays open
            lines[question.row] = qf.LineAnswer(kind, outside_job=outside_job.strip(), answered_at=answered_at)
    else:
        lines[question.row] = qf.LineAnswer(choice, answered_at=answered_at)
    return dataclasses.replace(answers, lines=lines)


def _own_kinds(question: Question) -> set[str]:
    """What a "which job" question's line can be while the question still applies: the kind it showed, or the
    overhead the question itself offers."""
    return {question.line_kind} | ({qf.OVERHEAD} if qf.OVERHEAD in {c.value for c in question.choices} else set())


def _still_current(report: qp.ProfitAndLossDetail, answers: qf.OwnerAnswers, question: Question) -> bool:
    previous = answers.lines.get(question.row)
    if previous is not None:
        now = previous.kind
    else:
        now = next(r for r in qf.figures(report, answers).resolutions if r.row == question.row).kind
    return now in _own_kinds(question)


def _reopen(report: qp.ProfitAndLossDetail, answers: qf.OwnerAnswers, question: Question) -> qf.OwnerAnswers:
    """"Not sure yet": the earlier answer to this question no longer counts."""
    if question.kind == JOBS:
        return dataclasses.replace(answers, sub_customers_are_jobs=None)
    if question.kind == NO_FILTER:
        return dataclasses.replace(answers, unfiltered_pair="")
    if question.kind == ACCOUNT:
        return dataclasses.replace(answers, accounts={k: v for k, v in answers.accounts.items() if k != question.account})
    lines = dict(answers.lines)
    if question.key.startswith("job:"):
        if question.row not in lines or not _still_current(report, answers, question):
            return answers  # nothing of this question's to reopen
        previous = lines.pop(question.row)
        # Only this question's own answer (the job, or its overhead) is reopened. What the line is, as the
        # question showed it, stays when MargenX can't work it out by itself (the owner said it).
        automatic = next(r for r in qf.figures(report, dataclasses.replace(answers, lines=lines)).resolutions
                         if r.row == question.row)
        if question.line_kind != automatic.kind:
            lines[question.row] = qf.LineAnswer(question.line_kind, answered_at=previous.answered_at)
        return dataclasses.replace(answers, lines=lines)
    lines.pop(question.row, None)
    return dataclasses.replace(answers, lines=lines)
