"""Made-up QuickBooks Sales by Customer Detail reports with known answers, for step 5a's accuracy check.

Independent of MargenX on purpose: this file imports nothing from the product. A report is generated
from a seed in the layout seen on 2026-10-26: customer headings, sub-customer headings closed by
"Total for X with sub-customers", lines with Quantity × Sales price = Amount, totals of Amount and
Quantity stored with Excel's float noise, and the grand TOTAL. The right answers are worked out here
in whole cents, from the written rules (issue #128, plan v7, S1 and S6), not from MargenX's code:
- a line is a sale only when it's an Invoice or a Sales Receipt, its amount isn't negative, and its
  customer's whole group adds up to its own totals (and the grand TOTAL to every line);
- everything else is "not resolved", and never dropped;
- a customer's lines are all counted only when its group matched and every line in it was counted.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SALE_TYPES = {"Invoice", "Sales Receipt"}
TYPES = ["Invoice"] * 6 + ["Sales Receipt"] * 3 + ["Credit Memo", "Refund", "Payment", "Journal Entry", "Estimate"]
CUSTOMERS = ["Coral Cafe (fictional)", "Palm Gym (fictional)", "Bay Clinic (fictional)", "Doral Realty (fictional)",
             "Kendall School (fictional)", "Brickell Law (fictional)", "Wynwood Bakery (fictional)"]
SUBS = ["Patio", "Lobby", "Kitchen", "North wing", "Pool", "Roof"]


@dataclass
class Expected:
    lines: int = 0
    line_sum: int = 0
    included: int = 0
    included_lines: int = 0
    not_resolved: int = 0
    not_resolved_lines: int = 0
    broken: bool = False

    @property
    def complete(self) -> bool:
        return not self.broken and self.not_resolved_lines == 0


@dataclass
class Report:
    rows: list
    stored: dict
    expected: dict
    totals: int
    line_rows: list = field(default_factory=list)


def _text(cents: int) -> str:
    return f"{'-' if cents < 0 else ''}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _excel(values: list[float]) -> str:
    total = 0.0
    for value in values:
        total += value
    return format(total, ".17g").upper()


def make_report(seed: int) -> Report:
    rng = random.Random(seed)
    tidy = rng.random() < 0.35  # plain sales only, so Complete customers come up too
    body, stored, expected, line_rows = [], {}, {}, []
    totals = 0
    all_amounts: list[float] = []
    all_quantities: list[float] = []
    closings: list[tuple[int, str]] = []  # (body index, customer) of totals that may be broken

    def row_number() -> int:
        return 6 + len(body)

    def line(customer: str, amounts: list[float], quantities: list[float]) -> None:
        kind = rng.choice(sorted(SALE_TYPES) if tidy else TYPES)
        quantity_halves = rng.randint(1, 20)  # 0.5 to 10, in halves
        price_cents = rng.randint(1, 50_000)
        if not tidy and kind in ("Credit Memo", "Refund") or (not tidy and rng.random() < 0.05):
            quantity_halves = -quantity_halves
        # Amount = Quantity × Sales price, rounded half up to the cent, in integers.
        product = quantity_halves * price_cents  # in half-cents
        cents = (abs(product) + 1) // 2 * (1 if product >= 0 else -1)
        counts = kind in SALE_TYPES and cents >= 0
        e = expected.setdefault(customer, Expected())
        e.lines += 1
        e.line_sum += cents
        if counts:
            e.included += cents
            e.included_lines += 1
        else:
            e.not_resolved += cents
            e.not_resolved_lines += 1
        line_rows.append(row_number())
        stored[f"I{row_number()}"] = _text(cents)
        stored[f"H{row_number()}"] = _text(price_cents)
        quantity = quantity_halves / 2
        body.append([None, f"{rng.randint(1, 10):02d}/{rng.randint(1, 28):02d}/2026", kind,
                     str(rng.randint(1000, 9999)), "Plants", "Made-up line", quantity, price_cents / 100, cents / 100])
        amounts.append(cents / 100)
        quantities.append(quantity)

    def total(label: str, customer: str | None, amounts: list[float], quantities: list[float]) -> None:
        nonlocal totals
        stored[f"I{row_number()}"] = _excel(amounts)
        stored[f"G{row_number()}"] = _excel(quantities)
        if customer is not None:
            closings.append((len(body), customer))
        body.append([label, None, None, None, None, None, 0, None, 0])
        totals += 1

    for customer in rng.sample(CUSTOMERS, rng.randint(1, 5)):
        body.append([customer])
        subs = rng.sample(SUBS, rng.randint(1, 3)) if rng.random() < 0.35 else []
        mine_a: list[float] = []
        mine_q: list[float] = []
        own = rng.randint(0, 2) if subs else rng.randint(1, 5)
        for _ in range(own):
            line(customer, mine_a, mine_q)
        if own or not subs:
            total(f"Total for {customer}", customer, list(mine_a), list(mine_q))
        for sub in subs:
            body.append([sub])
            sub_a: list[float] = []
            sub_q: list[float] = []
            for _ in range(rng.randint(1, 4)):
                line(customer, sub_a, sub_q)
            total(f"Total for {sub}", customer, sub_a, sub_q)
            mine_a += sub_a
            mine_q += sub_q
        if subs:
            total(f"Total for {customer} with sub-customers", customer, mine_a, mine_q)
        all_amounts += mine_a
        all_quantities += mine_q
    grand_index = len(body)
    total("TOTAL", None, all_amounts, all_quantities)

    # One report in four has a broken total: a customer's (that customer is held) or the grand TOTAL (all are).
    if rng.random() < 0.25:
        index, customer = rng.choice(closings + [(grand_index, None)])
        cell = f"I{6 + index}"
        stored[cell] = format(float(stored[cell]) + rng.choice([0.01, -0.01, 0.004]), ".17g").upper()
        for name, e in expected.items():
            if customer is None or name == customer:
                e.broken = True
                e.included, e.included_lines = 0, 0
                e.not_resolved, e.not_resolved_lines = e.line_sum, e.lines

    rows = [["Biscayne Landscaping (fictional)"], ["Sales by Customer Detail"], ["January 1-October 31, 2026"], [],
            [None, "Transaction date", "Transaction type", "Num", "Product/Service full name", "Description",
             "Quantity", "Sales price", "Amount", "Balance"],
            *body, [], [], [], ["Accrual Basis Saturday, October 31, 2026 05:00 PM GMTZ"]]
    return Report(rows, stored, expected, totals, line_rows)
