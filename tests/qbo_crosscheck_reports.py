"""Made-up pairs of QuickBooks reports with known answers, for step 5b's cross-check.

Independent of MargenX on purpose: no product code is imported (only the test helpers that write the two
layouts). One list of made-up sales transactions is written into both a Profit and Loss Detail and a Sales by
Customer Detail. Then, in about half the pairs, a few transactions are changed in one report only: left
out, a cent off, another invoice number, or listed under another job. The right answers come from the
written rules (plan v7, S1, S3, S4, S8), not from MargenX's code:
- every transaction whose type, number, date, amount, customer and job agree in both reports matches;
- a job's sales are Complete only when every transaction of that job matched and counts as a sale (an
  Invoice or a Sales Receipt that isn't negative), and the second report has no line without a partner
  (that one could be anyone's);
- with no costs in these reports, a job's profit is Complete exactly when its sales are.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal

import quickbooks_fixtures as fx

CUSTOMERS = {"Coral Cafe (fictional)": ["Patio", "Kitchen"], "Palm Gym (fictional)": ["Lobby", "Pool", "Roof"],
             "Bay Clinic (fictional)": ["North wing"]}
TYPES = ["Invoice"] * 6 + ["Sales Receipt"] * 3 + ["Credit Memo"]


@dataclass
class Pair:
    pnl_rows: list
    sbcd_rows: list
    jobs: dict = field(default_factory=dict)  # (customer, job) -> (sales in cents, sales Complete?)
    unmatched_pnl: int = 0
    unmatched_sbcd: int = 0


def make_pair(seed: int) -> Pair:
    rng = random.Random(seed)
    transactions = []
    for number in range(rng.randint(2, 12)):
        customer = rng.choice(sorted(CUSTOMERS))
        job = rng.choice(CUSTOMERS[customer])
        kind = rng.choice(TYPES)
        cents = rng.randint(100, 500_000) * (-1 if kind == "Credit Memo" else 1)
        transactions.append({"customer": customer, "job": job, "kind": kind, "num": str(2000 + number),
                             "day": rng.randint(1, 26), "cents": cents})
    pnl_side = [dict(t) for t in transactions]
    sbcd_side = [dict(t) for t in transactions]
    pnl_bad: set[int] = set()  # transactions whose Profit and Loss line has no partner
    sbcd_bad: set[int] = set()  # transactions whose Sales by Customer line has no partner
    if rng.random() < 0.5:
        for index in rng.sample(range(len(transactions)), rng.randint(1, min(3, len(transactions)))):
            change = rng.choice(["drop from P&L", "drop from SBCD", "cent", "number", "job"])
            if change == "drop from P&L":
                pnl_side[index] = None
                sbcd_bad.add(index)
            elif change == "drop from SBCD":
                sbcd_side[index] = None
                pnl_bad.add(index)
            elif change == "cent":
                sbcd_side[index]["cents"] += 1
                pnl_bad.add(index), sbcd_bad.add(index)
            elif change == "number":
                sbcd_side[index]["num"] += "9"
                pnl_bad.add(index), sbcd_bad.add(index)
            else:
                others = [j for j in CUSTOMERS[transactions[index]["customer"]] if j != transactions[index]["job"]]
                if not others:
                    continue
                sbcd_side[index]["job"] = rng.choice(others)
                pnl_bad.add(index), sbcd_bad.add(index)

    # Amounts are built exactly, in whole cents, never through a float.
    pnl_lines = [fx.line(t["day"], t["kind"], t["num"], f"{t['customer']}:{t['job']}", Decimal(t["cents"]) / 100, None)
                 for t in pnl_side if t]
    groups: dict[str, dict[str, list]] = {}
    for t in sbcd_side:
        if t:
            sign = -1 if t["cents"] < 0 else 1
            groups.setdefault(t["customer"], {}).setdefault(t["job"], []).append(
                fx.sale(t["day"], t["kind"], t["num"], "Made-up", sign, Decimal(abs(t["cents"])) / 100))
    customers = [(name, [], sorted(jobs.items())) for name, jobs in sorted(groups.items())]
    pair = Pair(fx.report_rows({"Income": [("Design income", pnl_lines)]}) if pnl_lines else None,
                fx.sbcd_rows(customers), unmatched_pnl=len(pnl_bad), unmatched_sbcd=len(sbcd_bad))

    # Expected: every job named in Profit and Loss Detail, its sales and whether they can be Complete.
    any_sbcd_orphan = bool(sbcd_bad)
    for index, t in enumerate(pnl_side):
        if not t:
            continue
        key = (t["customer"], t["job"])
        cents, ok = pair.jobs.get(key, (0, True))
        counts = t["kind"] in ("Invoice", "Sales Receipt") and t["cents"] >= 0
        pair.jobs[key] = (cents + (t["cents"] if counts else 0), ok and counts and index not in pnl_bad)
    pair.jobs = {key: (cents, ok and not any_sbcd_orphan) for key, (cents, ok) in pair.jobs.items()}
    return pair
