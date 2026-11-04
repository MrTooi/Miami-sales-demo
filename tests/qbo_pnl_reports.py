"""Made-up QuickBooks Profit and Loss Detail reports with known answers, for step 3's accuracy check.

Independent of MargenX on purpose: this file imports nothing from the product. A report is generated
from a seed in the layout seen on 2026-10-26 (nested accounts, parents with and without their own
lines, "Total for X" and "Total for X with sub-accounts", the "Cost of Goods Sold" account inside its
section, the empty "Other Income" heading in column B, summary rows, totals stored with Excel's float
noise). Its right answers are worked out here in whole cents (integers, never floats), from the
report itself, and the report is written out as an Excel file.

The rules below are MargenX's written rules (issue #128, plan v7, S1 and S6), re-implemented from
the text, not copied from the code:
- A line is a sale only in the Income section, with the type Invoice or Sales Receipt, and an amount
  that isn't negative.
- A line is a cost only in Cost of Goods Sold or Expenses, with the type Bill, Expense or Check (the
  tested allow-list), and an amount that isn't negative.
- An account named "Unapplied Cash ..." is never counted. Other Income and Other Expense lines are
  never counted automatically.
- Everything else is "not resolved", and never dropped.
- If any total in a section doesn't match its lines to the cent, nothing in that section is
  counted: every line in it is not resolved.
- A section is Complete only when it matched and every line in it was counted.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SALE_TYPES = {"Invoice", "Sales Receipt"}
COST_TYPES = {"Bill", "Expense", "Check"}
INCOME_TYPES = ["Invoice"] * 6 + ["Sales Receipt"] * 3 + ["Credit Memo", "Deposit", "Payment", "Journal Entry",
                                                         "Refund"]
COSTS_TYPES = ["Bill"] * 4 + ["Expense"] * 3 + ["Check"] * 2 + ["Cash Expense", "Credit Card Expense", "Invoice",
                                                                "Vendor Credit", "Journal Entry", "Sales Receipt"]
OTHER_TYPES = ["Deposit", "Check", "Journal Entry", "Bill", "Invoice", "Expense"]
ACCOUNTS = {
    "Income": ["Design income", "Landscaping Services", "Pest Control Services", "Sales of Product Income",
               "Services", "Discounts given", "Unapplied Cash Payment Income"],
    "Cost of Goods Sold": ["Cost of Goods Sold", "Materials cost", "Subcontractors"],
    "Expenses": ["Advertising", "Automobile", "Job Expenses", "Insurance", "Rent or Lease", "Utilities",
                 "Unapplied Cash Bill Payment Expense"],
    "Other Income": ["Interest Earned", "Other Ordinary Income"],
    "Other Expense": ["Miscellaneous", "Penalties"],
}
SUB_ACCOUNTS = ["Job Materials", "Plants and Soil", "Fuel", "Labor", "Gas and Electric", "Telephone", "Decks"]
NAMES = ["Coral Cafe (fictional):Patio", "Palm Gym (fictional):Lobby", "Bay Clinic (fictional)",
         "Garden Supply (fictional)", "Bayside Fuel (fictional)", "Landlord (fictional)"]


@dataclass
class Expected:
    """One section's right answers, in whole cents."""
    lines: int = 0
    line_sum: int = 0
    included: int = 0
    included_lines: int = 0
    sales: int = 0
    costs: int = 0
    not_resolved: int = 0
    not_resolved_lines: int = 0
    broken: bool = False

    @property
    def complete(self) -> bool:
        return not self.broken and self.not_resolved_lines == 0


@dataclass
class Report:
    rows: list
    stored: dict  # Excel cell -> stored number text
    expected: dict  # section -> Expected
    total_rows: int  # closing totals plus summary rows
    line_rows: list = field(default_factory=list)


def _excel_total(cents_list: list[int]) -> str:
    """A total as Excel stores it: the lines added as binary floats, written with 17 significant digits."""
    total = 0.0
    for cents in cents_list:
        total += cents / 100
    return format(total, ".17g").upper()


def make_report(seed: int) -> Report:
    rng = random.Random(seed)
    body: list[list] = []
    stored: dict[str, str] = {}
    expected: dict[str, Expected] = {}
    totals = 0
    line_rows: list[int] = []
    breakable: list[tuple[int, str]] = []  # (body index, section) of totals that may be broken on purpose

    def excel_row(index: int) -> int:
        return 6 + index

    def add_line(section: str, account_path: list[str], cents_list: list[int]) -> None:
        day = rng.randint(1, 28)
        month = rng.randint(1, 10)
        pool = (INCOME_TYPES if section == "Income" else COSTS_TYPES
                if section in ("Cost of Goods Sold", "Expenses") else OTHER_TYPES)
        kind = rng.choice(pool)
        cents = rng.randint(1, 500_000) if rng.random() > 0.08 else -rng.randint(1, 50_000)
        if rng.random() < 0.03:
            cents = 0
        unapplied = any(a.startswith("Unapplied Cash") for a in account_path)
        if section == "Income" and kind in SALE_TYPES and cents >= 0 and not unapplied:
            counts = "sale"
        elif section in ("Cost of Goods Sold", "Expenses") and kind in COST_TYPES and cents >= 0 and not unapplied:
            counts = "cost"
        else:
            counts = None
        e = expected.setdefault(section, Expected())
        e.lines += 1
        e.line_sum += cents
        if counts:
            e.included += cents
            e.included_lines += 1
            e.sales += cents if counts == "sale" else 0
            e.costs += cents if counts == "cost" else 0
        else:
            e.not_resolved += cents
            e.not_resolved_lines += 1
        line_rows.append(excel_row(len(body)))
        # Stored exactly, as the real export stores line amounts ("750.0"); openpyxl alone would write some
        # as 16-digit approximations ("68.76000000000001"), which MargenX rightly refuses as not exact cents.
        stored[f"J{excel_row(len(body))}"] = f"{'-' if cents < 0 else ''}{abs(cents) // 100}.{abs(cents) % 100:02d}"
        body.append([None, f"{month:02d}/{day:02d}/2026", kind, str(rng.randint(1000, 9999)), rng.choice(NAMES), "", "",
                     "Made-up line", "Checking", cents / 100, None])
        cents_list.append(cents)

    def add_total(label: str, cents_list: list[int], section: str | None, breakable_total: bool = True) -> None:
        nonlocal totals
        index = len(body)
        body.append([label, None, None, None, None, None, None, None, None, 0])
        stored[f"J{excel_row(index)}"] = _excel_total(cents_list)
        totals += 1
        if section and breakable_total:
            breakable.append((index, section))

    def add_account(section: str, name: str, depth: int, above: list[str]) -> list[int]:
        body.append([name])
        path = [*above, name]  # every account heading above the line counts (an "Unapplied Cash" parent too)
        mine: list[int] = []
        parent = depth < 2 and rng.random() < 0.35
        own = rng.randint(1, 4) if not parent else rng.choice([0, 0, 1, 2])
        for _ in range(own):
            add_line(section, path, mine)
        if not parent:
            add_total(f"Total for {name}", mine, section)
            return mine
        if own:
            add_total(f"Total for {name}", list(mine), section)
        children = rng.sample([a for a in SUB_ACCOUNTS if a != name], rng.randint(1, 3))
        for child in children:
            mine += add_account(section, child, depth + 1, path)
        add_total(f"Total for {name} with sub-accounts", mine, section)
        return mine

    def add_section(section: str, empty_ok: bool = False) -> list[int]:
        if empty_ok and rng.random() < 0.5:
            body.append([None, section])  # the empty heading in column B, as seen for "Other Income"
            expected.setdefault(section, Expected())
            return []
        body.append([section])
        cents: list[int] = []
        if section == "Cost of Goods Sold" and rng.random() < 0.5:
            # As seen: an account named like its section, closed by "Total Cost of Goods Sold".
            body.append(["Cost of Goods Sold"])
            mine: list[int] = []
            for _ in range(rng.randint(1, 4)):
                add_line(section, ["Cost of Goods Sold"], mine)
            add_total("Total Cost of Goods Sold", mine, section)
            cents += mine
        names = [a for a in ACCOUNTS[section] if a != "Cost of Goods Sold"]
        for name in rng.sample(names, rng.randint(1, min(3, len(names)))):
            cents += add_account(section, name, 0, [])
        add_total(f"Total {section}", cents, section)
        return cents

    body.append(["Ordinary Income/Expenses"])
    income = add_section("Income")
    cogs = add_section("Cost of Goods Sold")
    add_total("Gross Profit", [*income, *(-c for c in cogs)], None)
    expenses = add_section("Expenses")
    add_total("Net Ordinary Income", [*income, *(-c for c in cogs), *(-c for c in expenses)], None)
    body.append(["Other Income/Expense"])
    other_income = add_section("Other Income", empty_ok=True)
    other_expense = add_section("Other Expense")
    add_total("Net Other Income", [*other_income, *(-c for c in other_expense)], None)
    add_total("Net Income", [*income, *(-c for c in cogs), *(-c for c in expenses), *other_income,
                             *(-c for c in other_expense)], None)

    # One report in four has a broken total: a cent off (as if a line were edited after export), or off by
    # a fraction of a cent, far more than Excel's float noise (the float rule must refuse it).
    if breakable and rng.random() < 0.25:
        index, section = rng.choice(breakable)
        cell = f"J{excel_row(index)}"
        stored[cell] = format(float(stored[cell]) + rng.choice([0.01, -0.01, 0.004]), ".17g").upper()
        e = expected[section]
        e.broken = True
        e.included, e.included_lines = 0, 0
        e.sales = e.costs = 0
        e.not_resolved, e.not_resolved_lines = e.line_sum, e.lines

    rows = [["Biscayne Landscaping (fictional)"], ["Profit and Loss Detail"], ["January 1-October 31, 2026"], [],
            [None, "Transaction date", "Transaction type", "Num", "Name", "Location", "Class full name", "Description",
             "Item split account", "Amount", "Balance"],
            *body, [], [], [], ["Accrual Basis Saturday, October 31, 2026 05:00 PM GMTZ"]]
    return Report(rows, stored, expected, totals, line_rows)
