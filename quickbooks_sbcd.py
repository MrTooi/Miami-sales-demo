"""MargenX: reading QuickBooks Online's Sales by Customer Detail, step 5a of the plan in issue #128.

Takes a report whose layout quickbooks_layouts recognised and, like step 3 does for Profit and Loss
Detail:

1. Reads every row below the column names as one of: a customer heading, a sub-customer heading
   (a second heading level, nested in its customer), a line, a closing total ("Total for X" for a
   group's own lines, "Total for X with sub-customers" for a customer and its sub-customers), the
   grand "TOTAL" (the last row), or something else, which holds the whole report.
2. Checks every closing total against the exact sum of the lines it closes: the Amount to the cent
   (with the float rule for stored totals, never for lines) and the Quantity too, when the total shows
   one. A line's Amount must be exact cents, and must equal its Quantity × Sales price, rounded to the
   cent, when it shows both (seen on every line of the export), and a readable date inside the period;
   a line that fails these holds its whole customer. The grand TOTAL must equal every line.
3. Writes the ledger: every line with its row, the customer and sub-customer headings above it
   exactly as written, its amount as stored, and its outcome. A line is "included" only when its
   customer's whole group passed every check, the grand TOTAL matched, nothing in the report is
   unexplained, and S1 counts it (an Invoice or a Sales Receipt that isn't negative). Anything else is
   "not resolved", with the reason, and is never dropped.

The customer is the heading; a sub-customer is the nested heading inside it. Here nothing but the
nesting says whose a line is, and the nesting can't be proven from this report alone: if a "Total for
X with sub-customers" row were missing, a sub-customer would read exactly like a customer of its own,
and every remaining total would still match (the automated review of 4ef0f9d). So this report never
proves who a line belongs to (ownership_proven is always False), and no customer figure is ever built
from it alone. A customer's totals matching (totals_match) and all its lines being counted
(all_counted) say only that its lines and totals agree. Who a line belongs to comes from Profit and
Loss Detail's "Customer:Job" Names, which step 5b cross-checks line by line (S4, S5). Customers and
sub-customers nested more than two levels deep aren't the layout seen: they are held.

Plan rule S4: when both reports are uploaded, sales come from Profit and Loss Detail; this report is a
cross-check only, and its sales are never added (step 5b). Nothing here is wired to an upload yet: job_intake
still refuses every QuickBooks report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

import job_intake as ji
import quickbooks_layouts as qlayouts
import quickbooks_pnl as qp
import quickbooks_rules as qr

TOTAL_FOR = re.compile(r"Total for (.+?)( with sub-customers)?")
GRAND_TOTAL = "TOTAL"
MAX_DEPTH = 2  # a customer, and one level of sub-customer (the layout seen)
QUANTITY_TOLERANCE = Decimal("0.000001")
ZERO = Decimal("0")
NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d{1,3})?")


@dataclass(frozen=True)
class SalesLine:
    """One money line of Sales by Customer Detail and its outcome (S6)."""
    source: str
    sheet: str
    row: int
    date: str  # every text field exactly as written
    transaction_type: str
    num: str
    product: str
    description: str
    quantity_text: str
    price_text: str
    amount_text: str
    amount: Decimal | None  # None when it isn't exact cents
    customer_path: tuple[str, ...]  # the customer and sub-customer headings above it, exactly as written
    outcome: str  # qp.INCLUDED or qp.NOT_RESOLVED
    counts_as: str | None  # qr.SALE when included
    reason: str

    @property
    def customer(self) -> str | None:
        return " ".join(self.customer_path[0].split()) if self.customer_path else None

    @property
    def sub_customer(self) -> str | None:
        return " ".join(self.customer_path[1].split()) if len(self.customer_path) == 2 else None


@dataclass(frozen=True)
class CustomerCoverage:
    """Every line of one customer's group (sub-customers included), by outcome."""
    customer: str  # the heading, as read: who the lines belong to isn't proven by this report (see above)
    totals_match: bool  # every total in its group matched its lines, and nothing in the report is unexplained
    lines: int
    line_sum: Decimal | None
    stored_total: Decimal | None  # the group's own closing total, under the float rule
    included: Decimal
    included_lines: int
    not_resolved: Decimal
    not_resolved_lines: int
    unknown_amounts: int

    @property
    def adds_up(self) -> bool:
        return self.stored_total is not None and self.unknown_amounts == 0 and \
            self.included + self.not_resolved == self.stored_total

    @property
    def all_counted(self) -> bool:
        """Its totals matched and every line in its group counts as a sale. This is about the lines and totals
        agreeing, never a customer figure: this report alone doesn't prove who the lines belong to."""
        return self.totals_match and self.adds_up and self.not_resolved_lines == 0


@dataclass(frozen=True)
class SalesByCustomerDetail:
    layout: qlayouts.ReportLayout
    source: str
    lines: tuple[SalesLine, ...]
    checks: tuple[qp.TotalCheck, ...]
    problems: tuple[qp.Problem, ...]  # Problem.section holds the customer it touches, or None for the report
    customers: dict[str, CustomerCoverage]
    grand_total: Decimal | None  # the stored TOTAL under the float rule

    @property
    def reconciled(self) -> bool:
        return not self.problems

    @property
    def ownership_proven(self) -> bool:
        """Never, from this report alone (see the module docstring): a missing "with sub-customers" total turns a
        sub-customer into a customer of its own with every other total still matching."""
        return False


@dataclass
class _Group:
    name: str  # spaces collapsed, for matching its totals
    raw: str  # as written
    row: int
    depth: int
    lines: list = field(default_factory=list)
    children: list = field(default_factory=list)
    direct_closed: bool = False
    full_total: Decimal | None = None  # its own closing total of everything in it

    def all_lines(self) -> list:
        found, waiting = [], [self]
        while waiting:
            group = waiting.pop()
            found += group.lines
            waiting += group.children
        return found


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _decimal(text: str) -> Decimal | None:
    text = text.strip()
    if not NUMBER.fullmatch(text):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() and value.copy_abs() < Decimal("1E+15") else None


class _Reader:
    def __init__(self, layout: qlayouts.ReportLayout):
        self.layout = layout
        self.amount = layout.columns["Amount"]
        self.quantity = layout.columns.get("Quantity")
        self.rows = list(layout.body)
        self.stack: list[_Group] = []
        self.customers: dict[str, _Group] = {}
        self.problems: list[qp.Problem] = []
        self.checks: list[qp.TotalCheck] = []
        self.placed: list[tuple[int, tuple[str, ...], tuple[str, ...], str | None]] = []  # row, cells, path, note
        self.grand_total: Decimal | None = None
        self.grand_seen = False

    # -- helpers --
    def problem(self, row: int, text: str, customer: str | None | object = "current") -> None:
        if customer == "current":
            customer = self.stack[0].name if self.stack else None
        self.problems.append(qp.Problem(row, customer, text))

    def kind(self, cells: tuple[str, ...]) -> tuple[str, str]:
        first = _clean(cells[0])
        filled = [i for i, c in enumerate(cells) if i > 0 and c.strip()]
        if not first:
            return ("line", "") if filled else ("other", "")
        if not filled:
            return "heading", first
        if self.amount in filled and set(filled) <= {self.amount, self.quantity}:
            return "labelled", first
        return "other", first

    def path(self) -> tuple[str, ...]:
        return tuple(g.raw for g in self.stack)

    def lookahead_is_child(self, index: int, group: _Group) -> bool:
        """After a customer's own "Total for X", is the next heading its sub-customer? Only when the next
        closing row naming it or a group above it is "Total for X with sub-customers"."""
        above = {g.name for g in self.stack[:-1]}
        for _, cells in self.rows[index:]:
            kind, text = self.kind(cells)
            if kind == "labelled":
                match = TOTAL_FOR.fullmatch(text)
                if match and match.group(1) == group.name and match.group(2):
                    return True
                if (match and match.group(1) in above) or text == GRAND_TOTAL:
                    return False
        return False

    def close_finished(self, index: int | None = None, upto: str | None = None) -> None:
        while self.stack and self.stack[-1].direct_closed:
            top = self.stack[-1]
            if upto is not None and top.name == upto:
                return
            if index is not None and self.lookahead_is_child(index, top):
                return
            if top.children:
                self.problem(top.row, f"'{top.name}' has sub-customers but no 'Total for {top.name} with "
                             "sub-customers'")
            self.stack.pop()

    def sums(self, lines: list) -> tuple[Decimal | None, Decimal | None]:
        """The exact sum of the lines' amounts (None if one isn't exact cents) and of their quantities (None if
        one isn't a number)."""
        amounts = [qp.line_amount(cells[self.amount] if self.amount < len(cells) else "") for _, cells in lines]
        amount = None if any(a is None for a in amounts) else sum(amounts, ZERO)
        if self.quantity is None:
            return amount, ZERO
        quantities = []
        for _, cells in lines:
            text = cells[self.quantity].strip() if self.quantity < len(cells) else ""
            if text:
                quantities.append(_decimal(text))
        quantity = None if any(q is None for q in quantities) else sum(quantities, ZERO)
        return amount, quantity

    def check(self, row: int, label: str, cells: tuple[str, ...], lines: list) -> Decimal | None:
        """Checks a total row's Amount (and Quantity, when shown) against its lines; returns the stored Amount
        as cents when it matched."""
        amount, quantity = self.sums(lines)
        stored = cells[self.amount] if self.amount < len(cells) else ""
        cents = qp.total_cents(stored)
        if cents is None:
            reason = (f"the stored total '{stored}' isn't a whole number of cents (MargenX allows only Excel's "
                      "tiny rounding noise, within 0.000001)")
        elif amount is None:
            reason = "a line it closes has an amount that isn't exact cents, so it can't be added up exactly"
        elif cents != amount:
            reason = f"it says {cents:,.2f}, but its lines add up to {amount:,.2f}"
        else:
            reason = "it matches its lines to the cent"
        matches = cents is not None and amount is not None and cents == amount
        if matches and self.quantity is not None and self.quantity < len(cells) and cells[self.quantity].strip():
            shown = _decimal(cells[self.quantity])
            if shown is None or quantity is None or (shown - quantity).copy_abs() > QUANTITY_TOLERANCE:
                matches = False
                reason = (f"its Quantity says {cells[self.quantity].strip()}, but its lines' quantities add up to "
                          f"{quantity if quantity is not None else 'something that can’t be read'}")
        self.checks.append(qp.TotalCheck(row, label, self.stack[0].name if self.stack else None, stored, cents,
                                         amount, matches, reason))
        if not matches:
            self.problem(row, f"'{label}': {reason}")
        return cents if matches else None

    # -- the walk --
    def read(self) -> None:
        for index, (row, cells) in enumerate(self.rows):
            kind, text = self.kind(cells)
            if self.grand_seen:
                self.problem(row, f"row {row} comes after the grand TOTAL", None)
                if kind in ("line", "other", "labelled"):
                    self.placed.append((row, cells, (), f"Row {row} comes after the report's grand TOTAL, so what "
                                                         "it is can't be told."))
                continue
            if kind == "heading":
                if text == GRAND_TOTAL or TOTAL_FOR.fullmatch(text):
                    self.problem(row, f"'{text}' has no amount")
                else:
                    self.heading(index, row, cells, text)
            elif kind == "line":
                self.line(row, cells)
            elif kind == "labelled":
                self.labelled(row, text, cells)
            else:
                self.problem(row, f"row {row} isn't a heading, a line or a total MargenX knows", None)
                self.placed.append((row, cells, self.path(), f"Row {row} isn't a heading, a line or a total MargenX "
                                                             "knows, so what it is can't be told."))
        if not self.grand_seen:
            self.close_finished()
            for group in reversed(self.stack):
                self.problem(self.layout.footer_row, f"'{group.name}' has no closing total")
            self.stack.clear()
            self.problem(self.layout.footer_row, "the report has no grand TOTAL row", None)

    def heading(self, index: int, row: int, cells: tuple[str, ...], text: str) -> None:
        self.close_finished(index=index)
        raw = next(c for c in cells if c.strip())
        if not self.stack:
            group = _Group(text, raw, row, 1)
            if text in self.customers:
                self.problem(row, f"the customer '{text}' appears twice", None)
            self.customers.setdefault(text, group)
            self.stack = [group]
            return
        top = self.stack[-1]
        if top.lines and not top.direct_closed:
            self.problem(row, f"'{top.name}' has lines but no 'Total for {top.name}' before its sub-customer '{text}'")
        group = _Group(text, raw, row, top.depth + 1)
        if group.depth > MAX_DEPTH:
            self.problem(row, f"'{text}' is nested {group.depth} levels deep; the layout MargenX knows has customers "
                         "and one level of sub-customers")
        top.children.append(group)
        self.stack.append(group)

    def line(self, row: int, cells: tuple[str, ...]) -> None:
        self.close_finished()
        top = self.stack[-1] if self.stack else None
        if top is None or top.direct_closed or top.children:
            where = ("outside any customer" if top is None else
                     f"after the total for '{top.name}'" if top.direct_closed else
                     f"after the sub-customers of '{top.name}'")
            self.problem(row, f"row {row} is a line {where}", self.stack[0].name if self.stack else None)
            if top is not None:
                top.lines.append((row, cells))  # still in its customer's total check
        else:
            top.lines.append((row, cells))
        self.placed.append((row, cells, self.path(), None))

    def labelled(self, row: int, text: str, cells: tuple[str, ...]) -> None:
        if text == GRAND_TOTAL:
            self.close_finished()
            for group in reversed(self.stack):
                self.problem(row, f"'{group.name}' has no closing total before the grand TOTAL")
            self.stack.clear()
            every_line = [(r, c) for r, c, _, note in self.placed if note is None]
            self.grand_total = self.check(row, GRAND_TOTAL, cells, every_line)  # a problem here touches every customer
            self.grand_seen = True
            return
        match = TOTAL_FOR.fullmatch(text)
        if not match:
            self.problem(row, f"row {row} isn't a heading, a line or a total MargenX knows", None)
            self.placed.append((row, cells, self.path(), f"Row {row} ('{qr._shown(text)}') isn't a heading, a line "
                                                         "or a total MargenX knows, so what it is can't be told."))
            return
        name, with_sub = match.group(1), bool(match.group(2))
        self.close_finished(upto=name)
        top = self.stack[-1] if self.stack else None
        if top is None or top.name != name:
            # What it was meant to close can't be told, so it holds the whole report (the automated review of
            # 4ef0f9d).
            self.problem(row, f"'{text}' doesn't close the customer above it", None)
            return
        if with_sub:
            if not top.children:
                self.problem(row, f"'{text}', but '{name}' has no sub-customers")
            top.full_total = self.check(row, text, cells, top.all_lines())
            self.stack.pop()
        else:
            if top.direct_closed:
                self.problem(row, f"'{text}' appears twice")
            stored = self.check(row, text, cells, top.lines)
            top.direct_closed = True
            if not top.children:
                top.full_total = stored  # until sub-customers follow, its own total is its whole total


def _times(quantity: Decimal, price: Decimal) -> Decimal | None:
    """Quantity × Sales price rounded half up to the cent, or None when it's too large to be money (never a crash:
    the automated review of 5f45bbd)."""
    digits = len(quantity.as_tuple().digits) + len(price.as_tuple().digits)
    if digits > 60:
        return None  # more digits than any real price or quantity: held, never repaired
    try:
        with localcontext() as exact:
            # Enough precision that the product is exact, so it is rounded once, to the cent (the automated review
            # of 658ae53: default precision rounded it first).
            exact.prec = digits + 5
            product = quantity * price
            if product.copy_abs() > qp.MAX_MONEY:
                return None
            return product.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def reconcile(layout: qlayouts.ReportLayout, source: str, sheet: str = "") -> SalesByCustomerDetail:
    """Read, check and account for every line of a recognised Sales by Customer Detail (step 5a)."""
    reader = _Reader(layout)
    reader.read()

    def raw(cells, column):
        position = layout.columns.get(column)
        return cells[position] if position is not None and position < len(cells) else ""

    # First, every line's own checks. A line whose date or Quantity × Sales price can't be trusted holds its whole
    # customer, not just itself: nothing but the group's headings and totals says whose its neighbours are (the
    # automated review of 5f45bbd).
    own_problem: dict[int, str] = {}
    for row, cells, path, note in reader.placed:
        amount_text = raw(cells, "Amount")
        amount = qp.line_amount(amount_text)
        when = qp._date(raw(cells, "Transaction date"))
        customer = _clean(path[0]) if path else None
        quantity_text, price_text = raw(cells, "Quantity").strip(), raw(cells, "Sales price").strip()
        if note:
            reason = note
        elif amount is None:
            reason = (f"Its amount '{amount_text.strip()}' isn't an exact number of cents, so it can't be counted."
                      if amount_text.strip() else "Its amount is blank, so it can't be counted.")
        elif when is None:
            reason = (f"Its date '{raw(cells, 'Transaction date').strip()}' isn't written the way QuickBooks writes "
                      "dates (MM/DD/YYYY), so whether it's in the report's period can't be told.")
        elif not layout.in_period(when):
            reason = f"It's dated {when:%m/%d/%Y}, outside the report's period ({layout.period})."
        elif customer is None:
            reason = "It isn't under any customer, so whose it is can't be told."
        elif quantity_text and price_text:
            quantity, price = _decimal(quantity_text), _decimal(price_text)
            product = _times(quantity, price) if quantity is not None and price is not None else None
            reason = "" if product == amount else (
                f"Its Quantity × Sales price ({quantity_text} × {price_text}) doesn't give its Amount ({amount_text.strip()}).")
        else:
            reason = ""
        if reason:
            own_problem[row] = reason
            if customer is not None and not note:
                reader.problems.append(qp.Problem(row, customer, f"row {row}: {reason}"))

    report_wide = any(p.section is None for p in reader.problems)
    troubled = {p.section for p in reader.problems}
    verified = {name: not report_wide and name not in troubled for name in reader.customers}

    lines = []
    for row, cells, path, note in reader.placed:
        amount_text = raw(cells, "Amount")
        amount = qp.line_amount(amount_text)
        customer = _clean(path[0]) if path else None
        counts_as = None
        reason = own_problem.get(row, "")
        if not reason:
            outcome = qr.classify_sales_by_customer_line(raw(cells, "Transaction type"), amount,
                                                         group_verified=verified.get(customer, False))
            reason = outcome.reason
            if outcome.counts_as == qr.SALE:
                counts_as = qr.SALE
        if not counts_as and "never left out" not in reason:
            reason += " It stays not resolved and is shown with its amount; it is never left out."
        lines.append(SalesLine(
            source=source, sheet=sheet, row=row, date=raw(cells, "Transaction date"),
            transaction_type=raw(cells, "Transaction type"), num=raw(cells, "Num"),
            product=raw(cells, "Product/Service full name"), description=raw(cells, "Description"),
            quantity_text=raw(cells, "Quantity"), price_text=raw(cells, "Sales price"), amount_text=amount_text,
            amount=amount, customer_path=path, outcome=qp.INCLUDED if counts_as else qp.NOT_RESOLVED,
            counts_as=counts_as, reason=reason))

    coverage = {}
    for name, group in reader.customers.items():
        mine = [l for l in lines if l.customer == name]
        known = [l for l in mine if l.amount is not None]
        line_sum, _ = reader.sums(group.all_lines())
        coverage[name] = CustomerCoverage(
            customer=name, totals_match=verified[name], lines=len(mine), line_sum=line_sum, stored_total=group.full_total,
            included=sum((l.amount for l in known if l.outcome == qp.INCLUDED), ZERO),
            included_lines=sum(1 for l in mine if l.outcome == qp.INCLUDED),
            not_resolved=sum((l.amount for l in known if l.outcome == qp.NOT_RESOLVED), ZERO),
            not_resolved_lines=sum(1 for l in mine if l.outcome == qp.NOT_RESOLVED),
            unknown_amounts=sum(1 for l in mine if l.amount is None))
    return SalesByCustomerDetail(layout, source, tuple(lines), tuple(reader.checks), tuple(reader.problems), coverage,
                                 reader.grand_total)


def read_sales_by_customer_detail(name: str, data: bytes) -> SalesByCustomerDetail:
    """Read an uploaded file as Sales by Customer Detail, end to end. Raises ji.IntakeError, with the same plain
    reason the upload page gives, when the file isn't exactly the layout MargenX knows. Not called by the upload
    page yet."""
    if not name.lower().endswith(".xlsx") or not data.startswith(b"PK\x03\x04"):
        raise ji.IntakeError("MargenX reads QuickBooks' Sales by Customer Detail only as an Excel (.xlsx) file.")
    sheet, table = ji._xlsx_sheet(data)
    found = qlayouts.recognise_sales_by_customer_detail(table, is_xlsx=True)
    if found.layout is None:
        raise ji.IntakeError(qlayouts.quickbooks_refusal(table, ji.MAX_TITLE_LINES, is_xlsx=True)
                             or "This isn't QuickBooks' Sales by Customer Detail report.")
    return reconcile(found.layout, name, sheet)
