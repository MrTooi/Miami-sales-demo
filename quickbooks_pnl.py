"""MargenX: reading QuickBooks Online's Profit and Loss Detail, step 3 of the plan in issue #128.

Takes a report whose layout quickbooks_layouts recognised (step 2) and:

1. Reads every row below the column names as one of: a heading (a wrapper such as "Ordinary
   Income/Expenses", a section such as "Income", or an account), a line, a closing total ("Total
   for X", "Total for X with sub-accounts", "Total Income"...) or a summary row ("Gross Profit",
   "Net Ordinary Income", "Net Other Income", "Net Income"). Anything else is a problem.
2. Checks every closing total against the exact sum of the lines it closes, to the cent, and every
   summary row against the sections it is built from, each with its own sign. A stored total
   counts as a whole number of cents only within 0.000001 of one (the float rule: QuickBooks'
   Excel totals carry noise such as 349.40999999999997). The rule is for totals only: a line must
   be exact cents.
3. Writes the coverage ledger (S6): every money line, with its row, original amount, account path
   and outcome. A line is "included" only when its section passed every check and the S1 rules
   count it as a sale or a cost; otherwise it is "not resolved", with the reason, and is never
   dropped. Nothing is "excluded" automatically: only a proven duplicate or a line dated outside
   the report's period can be, and those are the owner's to confirm later (S9). A line dated
   outside the period is held as not resolved here.

Totals are only ever checks; every figure is a sum of lines. Customers, jobs and accounts (S5, S7,
S8, S9) are step 4, so the ledger keeps each line's Name whole and leaves customer and job unknown.
Nothing here is wired to an upload yet: job_intake still refuses every QuickBooks report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import job_intake as ji
import quickbooks_layouts as qlayouts
import quickbooks_rules as qr
from finance_engine import MAX_MONEY, money

INCLUDED = "included"
EXCLUDED = "excluded"
NOT_RESOLVED = "not resolved"
COMPLETE = "Complete"
NEEDS_A_CHECK = "Needs a check"

# Section headings exactly as seen, and the name the S1 rules know each by.
SECTION_NAMES = {"Income": "Income", "Cost of Goods Sold": "Cost of Goods Sold", "Expenses": "Expenses",
                 "Other Income": "Other Income", "Other Expense": "Other Expenses"}
ORDINARY_WRAPPER, OTHER_WRAPPER = "Ordinary Income/Expenses", "Other Income/Expense"
ORDINARY_SECTIONS = ("Income", "Cost of Goods Sold", "Expenses")
OTHER_SECTIONS = ("Other Income", "Other Expense")
# Summary rows, and how each is built from the sections' line sums (+1 adds, -1 subtracts).
SUMMARIES = {
    "Gross Profit": {"Income": 1, "Cost of Goods Sold": -1},
    "Net Ordinary Income": {"Income": 1, "Cost of Goods Sold": -1, "Expenses": -1},
    "Net Other Income": {"Other Income": 1, "Other Expense": -1},
    "Net Income": {"Income": 1, "Cost of Goods Sold": -1, "Expenses": -1, "Other Income": 1, "Other Expense": -1},
}
TOTAL_FOR = re.compile(r"Total for (.+?)( with sub-accounts)?")
TOTAL_PLAIN = re.compile(r"Total (.+)")
NUMBER = re.compile(r"-?\d+(\.\d+)?")
# A stored total may also be in Excel's short form for tiny float noise ("5.5511151231257827E-17" where
# lines cancel out). Lines never may.
TOTAL_NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d{1,3})?")
LINE_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
CENT = Decimal("0.01")
FLOAT_TOLERANCE = Decimal("0.000001")


def total_cents(text: str) -> Decimal | None:
    """A stored total as whole cents under the float rule, or None when it isn't within 0.000001 of a
    whole cent (or isn't a plain number). For totals only, never for lines."""
    text = text.strip()
    if not TOTAL_NUMBER.fullmatch(text):
        return None
    try:
        stored = Decimal(text)
        if stored.copy_abs() > MAX_MONEY + 1:
            return None
        cents = stored.quantize(CENT, rounding=ROUND_HALF_EVEN)
    except InvalidOperation:
        return None
    return cents if (stored - cents).copy_abs() <= FLOAT_TOLERANCE and cents.copy_abs() <= MAX_MONEY else None


def line_amount(text: str) -> Decimal | None:
    """A line's amount, exactly as stored, only when it is a plain number of whole cents."""
    text = text.strip()
    if not NUMBER.fullmatch(text):
        return None
    try:
        return money(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class LedgerLine:
    """One money line of the report and its outcome (S6)."""
    source: str  # the file it came from
    row: int  # its Excel row number
    date: str  # as written
    transaction_type: str
    num: str
    name: str  # kept whole, exactly as written (S5)
    description: str
    amount_text: str  # the amount exactly as stored
    amount: Decimal | None  # None when it isn't exact cents
    section: str | None  # "Income", "Cost of Goods Sold", "Expenses", "Other Income", "Other Expenses"
    account_path: tuple[str, ...]  # the headings above it, section first, as written
    outcome: str  # INCLUDED, EXCLUDED or NOT_RESOLVED
    counts_as: str | None  # qr.SALE or qr.COST when included
    reason: str
    customer: str | None = None  # step 4 (S5)
    job: str | None = None  # step 4 (S5)


@dataclass(frozen=True)
class TotalCheck:
    """One stored total or summary row, checked against the lines it is built from."""
    row: int
    label: str
    section: str | None
    stored: str  # as stored
    stored_cents: Decimal | None  # under the float rule
    expected: Decimal | None  # the exact sum of its lines
    matches: bool
    reason: str


@dataclass(frozen=True)
class Problem:
    row: int
    section: str | None  # None: the problem touches the whole report
    text: str


@dataclass(frozen=True)
class SectionCoverage:
    """Every line of one section, by outcome. included + excluded + not resolved = the section's total."""
    section: str
    verified: bool  # every total in it matched, and nothing in the report is unexplained
    lines: int
    line_sum: Decimal | None  # None when a line amount isn't exact cents
    stored_total: Decimal | None  # its closing total under the float rule (0 for an empty section)
    included: Decimal
    included_lines: int
    excluded: Decimal
    excluded_lines: int
    not_resolved: Decimal
    not_resolved_lines: int
    not_resolved_unknown_amounts: int  # lines whose amount couldn't be read at all

    @property
    def adds_up(self) -> bool:
        """S6: included + excluded + not resolved add up to the report's own total for the section."""
        return (self.stored_total is not None and self.not_resolved_unknown_amounts == 0
                and self.included + self.excluded + self.not_resolved == self.stored_total)

    @property
    def status(self) -> str:
        """Complete only when the section passed every check and every line in it is included."""
        return COMPLETE if self.verified and self.adds_up and self.not_resolved_lines == 0 else NEEDS_A_CHECK


@dataclass(frozen=True)
class ProfitAndLossDetail:
    layout: qlayouts.ProfitAndLossDetailLayout
    source: str
    lines: tuple[LedgerLine, ...]
    checks: tuple[TotalCheck, ...]
    problems: tuple[Problem, ...]
    sections: dict[str, SectionCoverage]

    @property
    def reconciled(self) -> bool:
        """Every row was understood and every total matched its lines."""
        return not self.problems


# --- reading the rows ---------------------------------------------------------------------------

@dataclass
class _Group:
    name: str  # as written
    section: str | None  # canonical section key (SECTION_NAMES key), None outside any section
    is_section: bool
    row: int
    column_b: bool = False  # a section heading written in column B (seen once, for an empty "Other Income")
    lines: list = field(default_factory=list)  # (row, cells) of its own lines
    children: list = field(default_factory=list)
    direct_closed: bool = False  # its own "Total for X" was read

    def all_lines(self) -> list:
        found = list(self.lines)
        for child in self.children:
            found += child.all_lines()
        return found


def _clean(text: str) -> str:
    return " ".join((text or "").split())


class _Reader:
    def __init__(self, layout: qlayouts.ProfitAndLossDetailLayout):
        self.layout = layout
        self.columns = layout.columns
        self.amount = layout.columns["Amount"]
        self.rows = list(layout.body)
        self.problems: list[Problem] = []
        self.checks: list[TotalCheck] = []
        self.stack: list[_Group] = []
        self.sections: dict[str, _Group] = {}
        self.orphans: list[tuple[int, tuple[str, ...], str | None, tuple[str, ...]]] = []  # lines under no account
        self.placed: list[tuple[int, tuple[str, ...], str | None, tuple[str, ...]]] = []  # (row, cells, section, path)
        self.summaries: list[tuple[int, str, str]] = []
        self.section_totals: dict[str, Decimal | None] = {}  # each section's own closing total (float rule)
        self.wrapper: str | None = None

    # -- helpers --
    def problem(self, row: int, text: str, section: str | None = "current") -> None:
        if section == "current":
            section = self.stack[0].section if self.stack else None
        self.problems.append(Problem(row, section, text))

    def kind(self, cells: tuple[str, ...]) -> tuple[str, str]:
        """(kind, text) of a row: heading, heading_b, line, labelled (a label with an amount), other."""
        first = _clean(cells[0])
        filled = [i for i, c in enumerate(cells) if i > 0 and c.strip()]
        if not first:
            if filled == [1] and _clean(cells[1]) in SECTION_NAMES:
                return "heading_b", _clean(cells[1])
            return ("line", "") if filled else ("other", "")
        if not filled:
            return "heading", first
        if filled == [self.amount]:
            return "labelled", first
        return "other", first

    def lookahead_is_child(self, index: int, group: _Group) -> bool:
        """After group's own "Total for X", is the next heading its sub-account (True) or a sibling (False)?
        A sub-account follows only when the next closing row that names group or any group above it
        is "Total for <group> with sub-accounts"."""
        above = {g.name for g in self.stack[:-1]}
        for _, cells in self.rows[index:]:
            kind, text = self.kind(cells)
            if kind == "labelled":
                match = TOTAL_FOR.fullmatch(text)
                if match and match.group(1) == group.name and match.group(2):
                    return True
                if match and match.group(1) in above:
                    return False
                if not match and (text in SUMMARIES or TOTAL_PLAIN.fullmatch(text)):
                    return False
            elif kind in ("heading", "heading_b") and (text in SECTION_NAMES or text in (ORDINARY_WRAPPER, OTHER_WRAPPER)):
                return False
        return False

    def close_finished_leaves(self, index: int | None = None, upto: str | None = None) -> None:
        """Pop accounts whose own total was read and that have no sub-accounts still to come."""
        while self.stack and not self.stack[-1].is_section and self.stack[-1].direct_closed:
            top = self.stack[-1]
            if upto is not None and top.name == upto:
                return
            if index is not None and self.lookahead_is_child(index, top):
                return
            if top.children:
                # A parent closes only with "Total for X with sub-accounts"; never silently. (A parent with its
                # own lines that is missing that total reads as an account followed by a separate parent: every
                # amount is the same either way, and every total is still checked against its lines.)
                self.problem(top.row, f"'{top.name}' has sub-accounts but no 'Total for {top.name} with "
                             "sub-accounts'", top.section)
            self.stack.pop()

    def close_section_if_open(self, row: int) -> None:
        self.close_finished_leaves()
        if not self.stack:
            return
        section = self.stack[0]
        if section.column_b and not section.all_lines() and not section.children and len(self.stack) == 1:
            self.stack.clear()  # the empty section seen in column B: nothing in it, total 0
            return
        for group in reversed(self.stack):
            label = f"'{group.name}'"
            self.problem(row, f"{label} has no closing total before row {row}", group.section)
        self.stack.clear()

    def check(self, row: int, label: str, section: str | None, stored: str, expected: Decimal | None) -> bool:
        cents = total_cents(stored)
        if cents is None:
            reason = (f"the stored total '{stored}' isn't a whole number of cents (MargenX allows only Excel's "
                      "tiny rounding noise, within 0.000001)")
        elif expected is None:
            reason = "a line it closes has an amount that isn't exact cents, so it can't be added up exactly"
        elif cents != expected:
            reason = f"it says {cents:,.2f}, but its lines add up to {expected:,.2f}"
        else:
            reason = "it matches its lines to the cent"
        matches = cents is not None and expected is not None and cents == expected
        self.checks.append(TotalCheck(row, label, section, stored, cents, expected, matches, reason))
        if not matches:
            self.problem(row, f"'{label}': {reason}", section)
        return matches

    def line_sum(self, lines: list) -> Decimal | None:
        amounts = [line_amount(cells[self.amount]) for _, cells in lines]
        return None if any(a is None for a in amounts) else sum(amounts, Decimal("0"))

    def path_of(self) -> tuple[str, ...]:
        return tuple(g.name for g in self.stack)

    # -- the walk --
    def read(self) -> None:
        if not self.rows or self.kind(self.rows[0][1]) != ("heading", ORDINARY_WRAPPER):
            self.problem(self.rows[0][0] if self.rows else self.layout.header_row,
                         f"the report doesn't start with '{ORDINARY_WRAPPER}', as in the layout MargenX knows", None)
        for index, (row, cells) in enumerate(self.rows):
            kind, text = self.kind(cells)
            nxt = index + 1
            if kind == "heading" and text in (ORDINARY_WRAPPER, OTHER_WRAPPER):
                self.close_section_if_open(row)
                if (text == ORDINARY_WRAPPER and self.wrapper is not None) or (
                        text == OTHER_WRAPPER and self.wrapper == OTHER_WRAPPER):
                    self.problem(row, f"'{text}' appears out of order", None)
                self.wrapper = text
            elif kind == "heading" and self.stack and self.stack[0].name == text and len(self.stack) == 1 \
                    and not self.stack[0].children and not self.stack[0].lines:
                # Seen: the section "Cost of Goods Sold" holds an account of the same name, as its first heading.
                self.account_heading(nxt, row, text)
            elif kind in ("heading", "heading_b") and text in SECTION_NAMES:
                self.close_section_if_open(row)
                allowed = ORDINARY_SECTIONS if self.wrapper == ORDINARY_WRAPPER else (
                    OTHER_SECTIONS if self.wrapper == OTHER_WRAPPER else ())
                if text not in allowed or text in self.sections:
                    self.problem(row, f"the section '{text}' isn't where the layout MargenX knows puts it", text)
                group = _Group(text, text, True, row, column_b=kind == "heading_b")
                self.sections.setdefault(text, group)
                self.stack = [group]
            elif kind == "heading_b":
                self.problem(row, f"row {row} has '{text}' alone in column B, which the layout MargenX knows "
                             "doesn't have")
            elif kind == "heading" and (text in SUMMARIES or TOTAL_PLAIN.fullmatch(text)):
                self.problem(row, f"'{text}' has no amount")
            elif kind == "heading":
                self.account_heading(nxt, row, text)
            elif kind == "line":
                self.line(row, cells)
            elif kind == "labelled":
                self.labelled(nxt, row, text, cells)
            else:
                # What it belongs to can't be told, so it holds the whole report.
                self.problem(row, f"row {row} isn't a heading, a line or a total MargenX knows", None)
        self.close_section_if_open(self.layout.footer_row)
        if not any(label == "Net Income" for _, label, _ in self.summaries):
            self.problem(self.layout.footer_row, "the report has no 'Net Income' row", None)

    def account_heading(self, nxt: int, row: int, text: str) -> None:
        if self.stack and self.stack[0].column_b:
            self.problem(row, f"the section '{self.stack[0].name}' in column B has accounts under it, which the "
                         "layout MargenX knows doesn't have", self.stack[0].section)
        self.close_finished_leaves(index=nxt - 1)
        if not self.stack:
            self.problem(row, f"the account '{text}' isn't under any section", None)
            self.stack = [_Group(text, None, False, row)]
            return
        top = self.stack[-1]
        if not top.is_section and top.lines and not top.direct_closed:
            self.problem(row, f"'{top.name}' has lines but no 'Total for {top.name}' before its sub-account "
                         f"'{text}'", top.section)
        group = _Group(text, top.section, False, row)
        top.children.append(group)
        self.stack.append(group)

    def line(self, row: int, cells: tuple[str, ...]) -> None:
        self.close_finished_leaves(upto=None)
        top = self.stack[-1] if self.stack else None
        section = top.section if top else None
        if top is None or top.is_section or top.direct_closed or top.children:
            where = ("outside any section" if top is None else
                     f"directly under the section '{top.name}', not under an account" if top.is_section else
                     f"after the total for '{top.name}'" if top.direct_closed else
                     f"after the sub-accounts of '{top.name}'")
            self.problem(row, f"row {row} is a line {where}", section)
            if top is not None and not top.column_b:
                top.lines.append((row, cells))  # still in its section's total check
            self.placed.append((row, cells, section, self.path_of()))
            return
        top.lines.append((row, cells))
        self.placed.append((row, cells, section, self.path_of()))

    def labelled(self, nxt: int, row: int, text: str, cells: tuple[str, ...]) -> None:
        stored = cells[self.amount]
        match = TOTAL_FOR.fullmatch(text)
        if text in SUMMARIES:
            self.close_section_if_open(row)
            self.summaries.append((row, text, stored))
            return
        if match:
            name, with_sub = match.group(1), bool(match.group(2))
            self.close_finished_leaves(upto=name)
            top = self.stack[-1] if self.stack else None
            section = top.section if top else None
            if top is None or top.is_section or top.name != name:
                self.problem(row, f"'{text}' doesn't close the account above it", section)
                return
            if with_sub:
                if not top.children:
                    self.problem(row, f"'{text}', but '{name}' has no sub-accounts", section)
                self.check(row, text, section, stored, self.line_sum(top.all_lines()))
                self.stack.pop()
            else:
                if top.direct_closed:
                    self.problem(row, f"'{text}' appears twice", section)
                self.check(row, text, section, stored, self.line_sum(top.lines))
                top.direct_closed = True
            return
        plain = TOTAL_PLAIN.fullmatch(text)
        if plain:
            name = plain.group(1)
            top = self.stack[-1] if self.stack else None
            # Seen: the account "Cost of Goods Sold" is closed by "Total Cost of Goods Sold", and so is its section.
            if top is not None and not top.is_section and top.name == name and not top.direct_closed and not top.children:
                self.check(row, text, top.section, stored, self.line_sum(top.lines))
                top.direct_closed = True
                return
            self.close_finished_leaves()
            if self.stack and self.stack[0].is_section and self.stack[0].name == name and not self.stack[0].column_b:
                section = self.stack[0]
                for group in reversed(self.stack[1:]):
                    self.problem(row, f"'{group.name}' has no closing total before '{text}'", section.section)
                self.check(row, text, section.section, stored, self.line_sum(section.all_lines()))
                self.section_totals[section.section] = total_cents(stored)
                self.stack.clear()
                return
        self.problem(row, f"'{text}' isn't a total MargenX can place")

    def summary_checks(self) -> None:
        sums = {name: self.line_sum(group.all_lines()) for name, group in self.sections.items()}
        for row, label, stored in self.summaries:
            parts = SUMMARIES[label]
            values = [sums.get(name, Decimal("0")) for name in parts]
            expected = None if any(v is None for v in values) else sum(
                (v * sign for v, sign in zip(values, parts.values())), Decimal("0"))
            if not self.check(row, label, None, stored, expected):
                # A summary row is only a check, but when it doesn't match, every section it is built from
                # needs a check (S6).
                self.problems.pop()
                for name in parts:
                    self.problems.append(Problem(row, name, f"'{label}' doesn't match the sections it is built from"))


def _date(text: str) -> date | None:
    found = LINE_DATE.fullmatch(text.strip())
    if not found:
        return None
    month, day, year = (int(part) for part in found.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def reconcile(layout: qlayouts.ProfitAndLossDetailLayout, source: str) -> ProfitAndLossDetail:
    """Read, check and account for every line of a recognised Profit and Loss Detail (step 3)."""
    reader = _Reader(layout)
    reader.read()
    reader.summary_checks()
    report_wide = any(p.section is None for p in reader.problems)
    troubled = {p.section for p in reader.problems}
    verified = {name: not report_wide and name not in troubled for name in SECTION_NAMES}

    def cell(cells: tuple[str, ...], column: str) -> str:
        position = layout.columns.get(column)
        return cells[position].strip() if position is not None and position < len(cells) else ""

    lines = []
    for row, cells, section, path in reader.placed:
        amount_text = cell(cells, "Amount")
        amount = line_amount(amount_text)
        when = _date(cell(cells, "Transaction date"))
        kind = cell(cells, "Transaction type")
        canonical = SECTION_NAMES.get(section) if section else None
        counts_as, reason = None, ""
        if amount is None:
            reason = (f"Its amount '{amount_text}' isn't an exact number of cents, so it can't be counted." if amount_text
                      else "Its amount is blank, so it can't be counted.")
        elif when is None:
            reason = (f"Its date '{cell(cells, 'Transaction date')}' isn't written the way QuickBooks writes dates "
                      "(MM/DD/YYYY), so whether it's in the report's period can't be told.")
        elif not layout.period_start <= when <= layout.period_end:
            reason = (f"It's dated {when:%m/%d/%Y}, outside the report's period ({layout.period}). Only you can "
                      "confirm whether it should be left out.")
        elif canonical is None:
            reason = "It isn't under any section of the report, so what it is can't be told."
        else:
            outcome = qr.classify_profit_and_loss_line((canonical, *path[1:]), kind, amount,
                                                       section_verified=verified[section])
            reason = outcome.reason
            if outcome.counts_as in (qr.SALE, qr.COST):
                counts_as = outcome.counts_as
        lines.append(LedgerLine(
            source=source, row=row, date=cell(cells, "Transaction date"), transaction_type=kind,
            num=cell(cells, "Num"), name=cell(cells, "Name"), description=cell(cells, "Description"),
            amount_text=amount_text, amount=amount, section=canonical, account_path=path,
            outcome=INCLUDED if counts_as else NOT_RESOLVED, counts_as=counts_as,
            reason=reason if counts_as else reason + ("" if "never left out" in reason else
                                                      " It stays not resolved and is shown with its amount; it is "
                                                      "never left out.")))

    stored = reader.section_totals
    coverage = {}
    for name, group in reader.sections.items():
        mine = [line for line in lines if line.section == SECTION_NAMES[name]]
        known = [line for line in mine if line.amount is not None]
        empty = group.column_b and not mine
        coverage[SECTION_NAMES[name]] = SectionCoverage(
            section=SECTION_NAMES[name], verified=verified[name], lines=len(mine),
            line_sum=reader.line_sum(group.all_lines()) if not empty else Decimal("0"),
            stored_total=Decimal("0") if empty else stored.get(name),
            included=sum((l.amount for l in known if l.outcome == INCLUDED), Decimal("0")),
            included_lines=sum(1 for l in mine if l.outcome == INCLUDED),
            excluded=sum((l.amount for l in known if l.outcome == EXCLUDED), Decimal("0")),
            excluded_lines=sum(1 for l in mine if l.outcome == EXCLUDED),
            not_resolved=sum((l.amount for l in known if l.outcome == NOT_RESOLVED), Decimal("0")),
            not_resolved_lines=sum(1 for l in mine if l.outcome == NOT_RESOLVED),
            not_resolved_unknown_amounts=sum(1 for l in mine if l.amount is None))
    return ProfitAndLossDetail(layout, source, tuple(lines), tuple(reader.checks), tuple(reader.problems), coverage)


def read_profit_and_loss_detail(name: str, data: bytes) -> ProfitAndLossDetail:
    """Read an uploaded file as Profit and Loss Detail, end to end. Raises ji.IntakeError, with the same
    plain reason the upload page gives, when the file isn't exactly the layout MargenX knows.

    Not called by the upload page yet: until steps 4 and later are built, uploads still refuse every
    QuickBooks report (job_intake)."""
    is_xlsx = name.lower().endswith(".xlsx")
    if not is_xlsx or not data.startswith(b"PK\x03\x04"):
        raise ji.IntakeError("MargenX reads QuickBooks' Profit and Loss Detail only as an Excel (.xlsx) file.")
    table = ji._xlsx_rows(data)
    found = qlayouts.recognise_profit_and_loss_detail(table, is_xlsx=True)
    if found.layout is None:
        raise ji.IntakeError(qlayouts.quickbooks_refusal(table, ji.MAX_TITLE_LINES, is_xlsx=True)
                             or "This isn't QuickBooks' Profit and Loss Detail report.")
    return reconcile(found.layout, name)
