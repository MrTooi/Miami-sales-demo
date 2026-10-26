"""MargenX: QuickBooks Online money rules, step 1 of the plan in issue #128.

Two rules from the reviewed plan (v7), and nothing else:

- S1: which QuickBooks report lines may be *counted automatically* as a sale or a cost. A line
  is a sale only when the report's structure and its transaction type both say so, and a cost
  only through a tested allow-list of cost types per section. Every other line is "not
  resolved": it is never guessed and never dropped, whatever its type (S9).
- S2: what makes a file *look like* a QuickBooks report. job_intake.read_file refuses every such
  file with a plain reason, so it never reaches the older reader for plain lists.

No QuickBooks layout is verified yet (that is step 2), so no upload reaches the S1 rules today.
Later steps call them only for lines of a verified layout, inside a section or customer group
closed by its own matching total (steps 2 and 3). The rules only say what a line may count as;
they never add anything up.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# What a line may count as. There is deliberately no "left out": type rules never prove that a
# line can leave the figures (S9). Only a proven duplicate or a line dated outside the report's
# period can be excluded, and those are decided later, by the owner and the ledger (step 3).
SALE = "sale"
COST = "cost"
NOT_RESOLVED = "not resolved"

# The two reports the plan supports. Each has its own rule.
PROFIT_AND_LOSS_DETAIL = "Profit and Loss Detail"
SALES_BY_CUSTOMER_DETAIL = "Sales by Customer Detail"

# The top-level account sections of Profit and Loss Detail, exactly as QuickBooks heads them.
INCOME = "income"
COST_OF_GOODS_SOLD = "cost of goods sold"
EXPENSES = "expenses"
OTHER_INCOME = "other income"
OTHER_EXPENSES = "other expenses"
SECTIONS = (INCOME, COST_OF_GOODS_SOLD, EXPENSES, OTHER_INCOME, OTHER_EXPENSES)

# The transaction types that are a sale, and only in a verified Income section (Profit and Loss
# Detail) or a verified customer group (Sales by Customer Detail).
SALE_TYPES = frozenset({"invoice", "sales receipt"})

# The tested cost allow-list, per report and section. A type is added only together with a
# fictional-file test that proves it (tests/test_quickbooks_rules.py). Being in a cost section
# never bypasses this list: an Invoice or Sales Receipt under Cost of Goods Sold is on neither
# list, so it is not resolved. Other Income and Other Expenses have no list: the owner says what
# each of their lines is (S9).
COST_TYPES = {
    (PROFIT_AND_LOSS_DETAIL, COST_OF_GOODS_SOLD): frozenset({"bill", "expense", "check"}),
    (PROFIT_AND_LOSS_DETAIL, EXPENSES): frozenset({"bill", "expense", "check"}),
}

# Money received or moved: never counted automatically as a sale or a cost, in any section.
# Listed so their reason can say so, and so no allow-list can ever hold one (checked below).
PAYMENT_TYPES = frozenset({
    "payment", "receive payment", "customer payment", "deposit", "bank deposit", "transfer",
    "bill payment", "bill payment (check)", "bill payment (credit card)", "credit card payment",
    "sales tax payment",
})

# Types the plan lets count only after their sign and posting are tested (Q6): not resolved for now.
NOT_YET_TESTED_TYPES = frozenset({"credit memo", "discount", "refund", "refund receipt", "vendor credit"})

for _types in COST_TYPES.values():
    assert not _types & (PAYMENT_TYPES | SALE_TYPES), "payments and sales are never on a cost allow-list"
assert not SALE_TYPES & PAYMENT_TYPES


@dataclass(frozen=True)
class Outcome:
    """What one line may count as, and why, in plain words."""
    counts_as: str  # SALE, COST or NOT_RESOLVED
    reason: str


def _text(value: str | None) -> str:
    """Compared exactly, ignoring only letter case and repeated spaces ("Sales  Receipt")."""
    return " ".join((value or "").split()).casefold()


def _amount(amount: Decimal) -> Decimal:
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise TypeError("Amounts must be exact, finite Decimal values.")
    return amount


def _not_resolved(reason: str) -> Outcome:
    return Outcome(NOT_RESOLVED, reason + " It stays not resolved and is shown with its amount; it is never "
                                          "left out.")


def _negative(shown: str) -> Outcome:
    """A sale or cost type with a negative amount: a discount, refund or credit line, not tested yet."""
    return _not_resolved(f"This '{shown}' line has a negative amount, which can be a discount, a refund or a "
                         "credit. MargenX hasn't tested those yet.")


def _type_reason(kind: str, shown: str) -> str:
    """Why a type isn't counted automatically."""
    if kind in PAYMENT_TYPES:
        return f"'{shown}' is money received or moved, which is never counted automatically as a sale or a cost."
    if kind in NOT_YET_TESTED_TYPES:
        return f"'{shown}' can lower sales or costs, but MargenX hasn't tested how QuickBooks posts it yet."
    if not kind:
        return "The transaction type is blank."
    return f"'{shown}' isn't a type MargenX counts automatically here."


def _unapplied_cash(account_path: tuple[str, ...]) -> str | None:
    """The heading of an unapplied-cash account ("Unapplied Cash Payment Income", "Unapplied Cash
    Bill Payment Expense"). QuickBooks puts them in cash-basis reports; any account named
    "unapplied" is held the same way, account number or not."""
    return next((h.strip() for h in account_path if "unapplied" in _text(h)), None)


def classify_profit_and_loss_line(account_path: tuple[str, ...] | list[str], transaction_type: str | None,
                                  amount: Decimal, *, section_verified: bool) -> Outcome:
    """What one Profit and Loss Detail line may count as (S1).

    account_path: the account headings above the line, outermost first, exactly as written
    (("Income", "Design income"), ("Expenses", "Job Expenses", "Job Materials")).
    section_verified: True only when the line's layout is verified and its section is closed by
    its own matching total. Steps 2 and 3 decide that; until then the line is not resolved.

    - A sale: Income section, Invoice or Sales Receipt, amount not negative.
    - A cost: Cost of Goods Sold or Expenses section, a type on that section's tested allow-list,
      amount not negative.
    - Everything else is not resolved, including payments, deposits, unapplied cash, a negative
      amount, an unknown section and any type nobody has tested.
    """
    amount = _amount(amount)
    path = tuple(account_path)
    kind, shown = _text(transaction_type), (transaction_type or "").strip()
    unapplied = _unapplied_cash(path)
    if unapplied:
        return _not_resolved(f"It's in '{unapplied}', money QuickBooks hasn't matched to an invoice or a bill.")
    section = _text(path[0]) if path else ""
    if section not in SECTIONS:
        where = f"'{path[0].strip()}'" if path else "no account section"
        return _not_resolved(f"It's under {where}, which isn't a Profit and Loss section MargenX knows.")
    if not section_verified:
        return _not_resolved("Its section hasn't been checked against the report's own totals yet.")
    if section == INCOME:
        if kind in SALE_TYPES:
            return _negative(shown) if amount < 0 else Outcome(SALE, f"'{shown}' in the Income section.")
        return _not_resolved(_type_reason(kind, shown))
    if section in (COST_OF_GOODS_SOLD, EXPENSES):
        if kind in COST_TYPES[(PROFIT_AND_LOSS_DETAIL, section)]:
            return _negative(shown) if amount < 0 else Outcome(COST, f"'{shown}' in {path[0].strip()}.")
        if kind in SALE_TYPES:
            # The observed $405 case: QuickBooks posts an item's cost on the invoice, so the line says
            # "Invoice" but sits under Cost of Goods Sold. It is never a sale (issue #128).
            return _not_resolved(f"'{shown}' under {path[0].strip()} is never a sale, and it isn't on the tested "
                                 "list of cost types.")
        return _not_resolved(_type_reason(kind, shown))
    # Other Income and Other Expenses never count automatically: the owner says what each line is (S9).
    return _not_resolved(f"Lines under {path[0].strip()} are counted only once you say what each one is.")


def classify_sales_by_customer_line(transaction_type: str | None, amount: Decimal, *, group_verified: bool) -> Outcome:
    """What one Sales by Customer Detail line may count as (S1). The report has no account sections,
    so a line is a sale only when the report is verified, its type is an Invoice or a Sales
    Receipt, its amount isn't negative, and its customer group adds up to the group's own total
    (group_verified, decided by steps 2 and 3). It never holds a cost."""
    amount = _amount(amount)
    kind, shown = _text(transaction_type), (transaction_type or "").strip()
    if not group_verified:
        return _not_resolved("Its customer group hasn't been checked against the group's own total yet.")
    if kind in SALE_TYPES:
        if amount < 0:
            return _negative(shown)
        return Outcome(SALE, f"'{shown}' in a customer group that adds up to its total.")
    return _not_resolved(_type_reason(kind, shown))


# --- S2: what makes a file look like a QuickBooks report -----------------------------------------

# Report titles QuickBooks Online prints above the column names, matched from the start of any cell
# in the top rows (a title can share its row with the company name or the period). Generous on
# purpose: a false match only refuses a file, it never counts anything.
QUICKBOOKS_TITLE = re.compile(
    r"(?i)^(profit and loss|balance sheet|statement of cash flows|general ledger|journal( report)?$|trial balance|"
    r"transaction (detail|list|report)|sales by (customer|product|class|location|rep)|income by customer|"
    r"customer balance|vendor balance|a/?r aging|a/?p aging|invoice list|invoices and received payments|"
    r"open invoices|collections report|deposit detail|check detail|expenses by vendor|purchases by|"
    r"bill payment list|unpaid bills|project profitability|time activities by|estimates by|unbilled (charges|time)|"
    r"sales tax liability|recent transactions|inventory valuation|physical inventory)")
TRANSACTION_LIST = re.compile(r"(?i)^transaction list by customer\b")
# Column names QuickBooks uses (compared in lower case, spaces collapsed). A heuristic, not proof: other
# programs may use some of them too, and a false match only refuses the file, never counts anything.
QUICKBOOKS_COLUMNS = frozenset({
    "memo/description", "product/service", "product/service full name", "item split account", "split",
    "split account", "class full name", "location full name", "account full name", "customer full name",
    "vendor full name", "payee full name", "employee full name",
})
# A "Total for X" or "Total for X with sub-accounts" row, a basis footer ("Accrual Basis Monday,
# October 26, 2026 07:04 PM GMTZ") and Profit and Loss summary rows, in a row's first filled cell.
TOTAL_FOR = re.compile(r"(?i)^total for\s+\S")
BASIS_FOOTER = re.compile(r"(?i)^(accrual|cash) basis\b")
# A cell that is only a number or a date ("40.00", "10/02/2026", "(12.50)"). The first row holding two
# or more (a line always has a date and an amount) is where the lines start, so titles are looked for
# only above it: a line's description ("Balance sheet cleanup") is never taken for a title. A single
# number (a date beside a title) doesn't stop it.
DATA_CELL = re.compile(r"^[\s$+\-(]*\d[\d,.\s/:-]*\)?$")
SUMMARY_ROWS = frozenset({"gross profit", "net ordinary income", "net operating income", "net other income",
                          "net income"})


def _shown(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:57] + "..."


def quickbooks_signs(table: list[tuple[int, list[str]]], title_lines: int) -> list[str]:
    """What makes a file look like a QuickBooks report, in plain words; empty when nothing does.

    table: every non-empty row of the file, with its row number. title_lines: how many rows to look
    at for a title block and the column names (the reader's own limit). Looked for:
    - in any cell of the first title_lines + 1 rows, whatever else the row holds: QuickBooks column
      names (an exact cell match), or "Transaction type" together with "Num";
    - in any cell above the first row holding two numbers or dates: a QuickBooks report title;
    - in any row's first filled cell: a "Total for ..." row, a basis footer or a Profit and Loss
      summary row (S2).
    """
    signs = []
    above_lines = True
    for position, (_, cells) in enumerate(table):
        filled = [c.strip() for c in cells if c and c.strip()]
        if not filled:
            continue
        first = filled[0]
        top = position <= title_lines
        above_lines = above_lines and top and sum(1 for c in filled if DATA_CELL.match(c)) < 2
        if above_lines:
            signs += [f"the title '{_shown(c)}'" for c in filled if QUICKBOOKS_TITLE.match(c)]
        if top and len(filled) >= 2:
            signs += [f"the column '{_shown(c)}'" for c in filled if _text(c) in QUICKBOOKS_COLUMNS]
            names = {_text(c) for c in filled}
            if {"transaction type", "num"} <= names:
                signs.append("the columns 'Transaction type' and 'Num'")
        if TOTAL_FOR.match(first):
            signs.append(f"the row '{_shown(first)}'")
        elif BASIS_FOOTER.match(first):
            signs.append(f"the line '{_shown(first)}'")
        elif _text(first) in SUMMARY_ROWS:
            signs.append(f"the row '{_shown(first)}'")
    return list(dict.fromkeys(signs))


def quickbooks_refusal(table: list[tuple[int, list[str]]], title_lines: int) -> str | None:
    """The plain reason a QuickBooks look-alike is refused, or None for any other file (S2).

    No QuickBooks layout is verified yet, so every look-alike is refused. "Transaction List by
    Customer" gets its own reason: it mixes invoices with customer payments, and its totals add
    both, so it can never be a sales file.
    """
    signs = quickbooks_signs(table, title_lines)
    if not signs:
        return None
    if any(TRANSACTION_LIST.match(sign.removeprefix("the title '")) for sign in signs if sign.startswith("the title")):
        return ("This looks like QuickBooks' \"Transaction List by Customer\" report. It mixes invoices with "
                "customer payments, and its totals add both together, so it can't be used as a sales file "
                "(and it has no costs). Nothing from this file was used.")
    return (f"This looks like a QuickBooks report (it has {signs[0]}), and MargenX can't read QuickBooks reports "
            "yet, so nothing from this file was used. For now, upload a plain list with one row per sale or cost, "
            "with columns such as Date, Customer, Job and Amount.")
