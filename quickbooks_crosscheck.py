"""MargenX: cross-checking Profit and Loss Detail with Sales by Customer Detail, step 5b of issue #128.

Plan rules S3 and S4 (v7), and the step 5a review's guidance:
- Sales come from exactly one report, Profit and Loss Detail (Alex's decision of 2026-10-26). Sales by
  Customer Detail is a cross-check only: its amounts are never added to any figure.
- The two reports are combined only when they show the same company, the same dates (a real range on
  both: "All Dates" can't be shown to cover the same period), the same basis, and the same currency and
  filters. Both layouts show no currency and no filter line (row 4 must be empty), so those agree.
- The cross-check uses the second report only when it reconciles completely: every one of its totals
  matched. Otherwise it proves nothing, and the one-report rule (S3) stays.
- It matches transactions, never totals: every Income line of Profit and Loss Detail whose type is a sales
  form Sales by Customer Detail lists (an Invoice, a Sales Receipt, a Credit Memo or a Refund, the types
  seen in its export) against every line of Sales by Customer Detail, by transaction type, number, date and exact amount, counted (two identical
  $100 lines need two matches, never one). Customer and job are used where they're reliable: a pair whose
  Profit and Loss Name proves a customer or job that the other report's headings contradict isn't a
  match. Sales by Customer Detail's headings never prove ownership by themselves (step 5a).
- A line that doesn't match, in either report, holds the figures it could change (quickbooks_figures).
  Other Income lines (a Deposit, an Expense adjustment, a Journal Entry...) aren't in the sales report at
  all, so they aren't matched; they stay governed by S1 and S9 (never counted by themselves).

Seen on the practice-company exports of 2026-10-26: every one of the 70 lines of Sales by Customer Detail
matches one Income line of Profit and Loss Detail by type, number and amount, with the same customer and
job; the two that don't are "Expense" adjustments posted to income. (Their dates differ by two days in
those two files only because Intuit's practice company moves its dates in every session.)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

import quickbooks_figures as qf
import quickbooks_pnl as qp
import quickbooks_sbcd as qs


@dataclass(frozen=True)
class CrossCheck:
    """What the second report says about the first. usable: the reports cover the same scope and the second
    one reconciles completely, so its matches count; otherwise reasons says why not, in plain words."""
    pnl_fingerprint: str  # the Profit and Loss Detail it was made for (quickbooks_figures.report_fingerprint)
    usable: bool
    reasons: tuple[str, ...]
    matched: tuple[tuple[int, int], ...]  # (Profit and Loss row, Sales by Customer row)
    pnl_unmatched: tuple[int, ...]  # Income rows of Profit and Loss Detail of a sales-form type, with no match
    sbcd_unmatched: tuple[int, ...]  # rows of Sales by Customer Detail with no match
    sbcd_unmatched_amounts: tuple[tuple[int, Decimal | None], ...]  # those rows with their amounts
    sbcd_jobs: dict  # Profit and Loss row -> (customer heading, sub-customer heading or None) of its match


# The sales forms Sales by Customer Detail lists (seen in its export): only these are expected in both reports.
SALES_FORMS = frozenset({"invoice", "sales receipt", "credit memo", "refund"})


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _key(transaction_type: str, num: str, date: str, amount: Decimal | None):
    return (_clean(transaction_type).casefold(), _clean(num), _clean(date), amount)


def scope_problems(pnl: qp.ProfitAndLossDetail, sbcd: qs.SalesByCustomerDetail) -> list[str]:
    """Why the two reports can't be combined; empty when they cover the same scope (S4)."""
    a, b = pnl.layout, sbcd.layout
    problems = []
    if _clean(a.company) != _clean(b.company):
        problems.append(f"they're for different companies ('{a.company}' and '{b.company}')")
    if b.period_start is None or a.period_start is None:
        problems.append(f"Sales by Customer Detail says '{b.period}', which can't be shown to cover the same dates as "
                        f"'{a.period}': export both for the same date range")
    elif (a.period_start, a.period_end) != (b.period_start, b.period_end):
        problems.append(f"they cover different dates ('{a.period}' and '{b.period}')")
    if a.basis != b.basis:
        problems.append(f"they're on different bases ({a.basis} and {b.basis})")
    return problems


def cross_check(pnl: qp.ProfitAndLossDetail, sbcd: qs.SalesByCustomerDetail) -> CrossCheck:
    """Match every Income line of Profit and Loss Detail with the lines of Sales by Customer Detail (S4)."""
    reasons = scope_problems(pnl, sbcd)
    if not sbcd.reconciled:
        reasons.append("Sales by Customer Detail's own totals don't all match its lines, so it can't vouch for "
                       "anything")
    income = [l for l in pnl.lines if l.section == "Income" and _clean(l.transaction_type).casefold() in SALES_FORMS]
    waiting: dict[tuple, list[qs.SalesLine]] = defaultdict(list)
    for line in sbcd.lines:
        waiting[_key(line.transaction_type, line.num, line.date, line.amount)].append(line)

    def agrees(pnl_line: qp.LedgerLine, sales_line: qs.SalesLine) -> bool:
        """No contradiction between what the Profit and Loss Name proves and the other report's headings."""
        customer, job = qf.names_of(pnl_line)
        if customer is not None and customer != sales_line.customer:
            return False
        if job is not None and job != sales_line.sub_customer:
            return False
        return True

    matched, pnl_unmatched, jobs = [], [], {}
    # The lines whose Name proves the most (a customer and a job, then a customer) are matched first, so a vaguer
    # line never takes the partner a more specific one needs.
    income.sort(key=lambda l: -sum(part is not None for part in qf.names_of(l)))
    for line in income:
        candidates = waiting.get(_key(line.transaction_type, line.num, line.date, line.amount), [])
        partner = next((c for c in candidates if line.amount is not None and agrees(line, c)), None)
        if partner is None:
            pnl_unmatched.append(line.row)
            continue
        candidates.remove(partner)
        matched.append((line.row, partner.row))
        jobs[line.row] = (partner.customer, partner.sub_customer)
    left = sorted(((l.row, l.amount) for group in waiting.values() for l in group), key=lambda pair: pair[0])
    return CrossCheck(qf.report_fingerprint(pnl), not reasons, tuple(reasons), tuple(sorted(matched)),
                      tuple(sorted(pnl_unmatched)),
                      tuple(row for row, _ in left), tuple(left), jobs)
