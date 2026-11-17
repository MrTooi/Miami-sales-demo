"""Issue #128, step 7: a QuickBooks report's results, in layers (plan v7, step 7).

1. One sentence first: what the business made after job costs, and whether that's final.
2. Then the figures, for the business, each job (when sub-customers are jobs) and each customer. Every figure
   that isn't final carries its status and the dollar amount being held right next to it, in the same cell,
   never in a separate box.
3. What's missing, in plain words, with the amounts.
4. Details folded away: the scope, and how each line was counted.

Every number comes from quickbooks_figures (exact Decimal, holds included); nothing is added up here except
the count of lines held. The upload page (pages/1_MargenX_Import.py) shows it below the questions.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pandas as pd
import streamlit as st

import job_intake as ji
import marginx_ui as ui
import quickbooks_figures as qf
import quickbooks_pnl as qp

FINAL = "Complete"
CHECKS_DONE = "The required checks and confirmations are complete for this report."
NOT_FINAL = "Needs a check"
_CODES = re.compile(r"\s*\((?:issue #\d+|plan|AGENTS\.md|the PR #|S\d)[^)]*\)")
_BARE_AMOUNT = re.compile(r"\((-?)(\d[\d,]*\.\d\d)\)")  # "(1,000.00)" in a hold's reason


def _md(value) -> str:
    """Text for any Streamlit call that reads Markdown: ui.md_text, and every "$" escaped. Streamlit reads the text
    between two "$" as a math formula, so "$5,500.00 so far ... $3,600.00" would show garbled (found in the browser
    in step 7)."""
    return ui.md_text(value).replace("$", "\\$")


def money(amount: Decimal | None) -> str:
    if amount is None:
        return "amount unknown"
    return f"-${-amount:,.2f}" if amount < 0 else f"${amount:,.2f}"


def plain(reason: str) -> str:
    """A hold's reason without the rule codes, which go in small print elsewhere."""
    text = _CODES.sub("", reason).strip()
    return _BARE_AMOUNT.sub(lambda m: f"({m.group(1)}${m.group(2)})", text)


def _held(figure: qf.Figure) -> tuple[int, int]:
    """(lines held with a known amount, lines held whose amount can't be read), each line once."""
    known, unknown = set(), set()
    for hold in figure.holds:
        if hold.row is not None:
            (known if hold.amount is not None else unknown).add((hold.report, hold.row))
    return len(known), len(unknown - known)


def _offsetting(figure: qf.Figure) -> bool:
    """True when the known held amounts go both ways (a +$50 and a -$50 line, say), so their sum is a net, not the
    money at stake."""
    amounts = {(hold.report, hold.row): hold.amount for hold in figure.holds
               if hold.row is not None and hold.amount is not None}
    return any(a > 0 for a in amounts.values()) and any(a < 0 for a in amounts.values())


def _held_text(figure: qf.Figure) -> str:
    """The amount held, never understated: an amount that can't be read is said, not left out (the automated
    review of 8a41156). Lines that add and lines that take away are labelled a net, so +$50 and -$50 never read as
    "$0.00 held" (the PR #144 manual review, warning 1)."""
    known, unknown = _held(figure)
    parts = []
    if known:
        parts.append(("net " if _offsetting(figure) else "") + money(figure.held_amount))
    if unknown:
        parts.append(f"{unknown} line{'' if unknown == 1 else 's'} of unknown amount")
    return " plus ".join(parts)


def cell(figure: qf.Figure) -> str:
    """A figure with its status beside it: "$4,000.00 · Complete" or "$3,800.00 · Needs a check ($50.00 held)".
    While the file's coverage isn't confirmed it also says "missing amount unknown": never an amount, never $0, and
    the known held amount is never presented as the size of what may be missing."""
    if figure.status == qp.COMPLETE:
        return f"{money(figure.amount)} · {FINAL}"
    amounts = _held_text(figure)
    unknown = [qf.MISSING_UNKNOWN] if figure.coverage_open else []
    if not amounts:
        return f"{money(figure.amount)} · {NOT_FINAL} ({'; '.join(unknown) or 'see why below'})"
    lines = sum(_held(figure))
    across = f" across {lines} lines" if lines > 1 else ""
    return f"{money(figure.amount)} · {NOT_FINAL} ({'; '.join([f'{amounts} held{across}', *unknown])})"


def _holds(figures: qf.Figures):
    for group in (figures.company, *figures.customers.values(), *figures.jobs.values()):
        for figure in group.values():
            yield from figure.holds


def held_lines(figures: qf.Figures) -> dict[tuple[str, int | None], list[str]]:
    """Every line (or the report itself) holding any figure back, each once, with its reasons in plain words."""
    found: dict[tuple[str, int | None], list[str]] = {}
    for hold in _holds(figures):
        reasons = found.setdefault((hold.report, hold.row), [])
        if plain(hold.reason) not in reasons:
            reasons.append(plain(hold.reason))
    return found


def held_amounts(figures: qf.Figures) -> dict[tuple[str, int], list[Decimal | None]]:
    """Each held line's amount as the holds carry it (None when it can't be read), each distinct amount once."""
    found: dict[tuple[str, int], list[Decimal | None]] = {}
    for hold in _holds(figures):
        if hold.row is not None:
            amounts = found.setdefault((hold.report, hold.row), [])
            if hold.amount not in amounts:
                amounts.append(hold.amount)
    return found


def headline(report: qp.ProfitAndLossDetail, figures: qf.Figures) -> str:
    """The one-sentence answer. It says "final" only when the figure is Complete."""
    layout = report.layout
    profit = figures.company["profit_after_job_costs"]
    made = "made" if profit.amount >= 0 else "lost"
    shown = money(abs(profit.amount))
    where = f"{layout.company}, {layout.period}"
    if profit.status == qp.COMPLETE:
        return f"After job costs, {where}: the business {made} {shown}. This figure is final for this report."
    # The count and the amount both come from this figure's own holds, each line once (the automated review of
    # 9234135: lines holding only a job or a customer aren't the business's).
    known, unknown = _held(profit)
    lines = known + unknown
    whys = []
    if lines:
        whys.append(f"{lines} line{'' if lines == 1 else 's'} {'is' if lines == 1 else 'are'} still held back "
                    f"({_held_text(profit)})")
    if profit.coverage_open:
        whys.append({qf.SAID_MISSING: "you said something is missing from this file",
                     qf.CONTRADICTED: "Sales by Customer Detail has sales this file doesn't, so it may not include "
                                      "your whole business"}.get(figures.coverage,
                                                                 "you haven't confirmed yet that this file includes "
                                                                 "your whole business"))
        whys[-1] += f" ({qf.MISSING_UNKNOWN})"
    if any(hold.row is None and hold.kind != qf.COVERAGE_HOLD for hold in profit.holds) or not whys:
        whys.append("something else that applies to the whole report is still open" if whys
                    else "something that applies to the whole report is still open")
    why = ", and ".join(whys)
    return (f"After job costs, {where}: the business {made} {shown} so far, but this isn't final yet: {why}. "
            "See what's missing below.")


_COMPANY = (("sales", "Sales"), ("job_costs", "Job costs"), ("profit_after_job_costs", "Profit after job costs"),
            ("overhead", "Overhead"), ("other", "Other income and expenses"),
            ("after_overhead", "Profit after overhead and other items"))


def company_rows(figures: qf.Figures) -> list[dict[str, str]]:
    return [{"Figure": label, "Amount and status": cell(figures.company[key])} for key, label in _COMPANY]


def group_rows(groups: dict, label: str) -> list[dict[str, str]]:
    """Jobs or customers, the ones losing money first. Names from the report are spreadsheet-safe (the table can
    be exported as CSV)."""
    def name(key):
        return " › ".join(key) if isinstance(key, tuple) else key

    ordered = sorted(groups.items(), key=lambda item: (item[1]["profit_after_job_costs"].amount, name(item[0])))
    return [{label: ji.safe_cell(name(key)), "Sales": cell(f["sales"]), "Job costs": cell(f["job_costs"]),
             "Profit after job costs": cell(f["profit_after_job_costs"])} for key, f in ordered]


def missing(figures: qf.Figures) -> list[str]:
    """What's missing, in plain words: one line per held line (by row), then the report-wide reasons."""
    out = []
    held = held_lines(figures)
    amounts = held_amounts(figures)
    for (report, row), reasons in sorted(held.items(), key=lambda item: (item[0][1] is None, item[0][0],
                                                                         item[0][1] or 0)):
        prefix = "" if row is None or report == "Profit and Loss Detail" else f"{report}: "
        if row is None:
            out.extend(reasons)  # each reason that applies to the whole report on its own line
            continue
        text = " ".join(reasons)
        if row is not None:
            # The amount comes from the hold itself, beside its reason, so it's shown even when a reason's words
            # don't carry it (the PR #144 manual review, warning 2). The same amount isn't repeated in the words.
            held = amounts[(report, row)]
            if len(held) == 1:
                text = text.replace(f" ({money(held[0])})", "")
            prefix = " / ".join(money(a) for a in held) + " held · " + prefix
        out.append(prefix + text)
    return out


def results_screen(report: qp.ProfitAndLossDetail, answers: qf.OwnerAnswers | None = None, cross_check=None) -> None:
    """The results, in layers."""
    figures = qf.figures(report, answers, cross_check=cross_check)
    st.subheader(_md(headline(report, figures)))
    for warning in figures.warnings:
        st.warning(_md(warning))
    if figures.coverage == qf.CONFIRMED:
        st.success(qf.COVERAGE_CONFIRMED)
    elif figures.coverage == qf.SAID_MISSING:
        st.warning(_md(qf.COVERAGE_SAID_MISSING))
    elif figures.coverage == qf.CONTRADICTED:
        st.warning(_md(qf.COVERAGE_CONTRADICTED))
    else:
        st.info(_md(qf.COVERAGE_NOT_YET))
    st.caption(_md(qf.RELIANCE))

    st.markdown("**Your business**")
    st.dataframe(pd.DataFrame(company_rows(figures)), hide_index=True, width="stretch")
    if figures.jobs_on and figures.jobs:
        st.markdown("**By job** (losing money first)")
        st.dataframe(pd.DataFrame(group_rows(figures.jobs, "Customer › Job")), hide_index=True, width="stretch")
    if figures.customers:
        st.markdown("**By customer** (losing money first)")
        st.dataframe(pd.DataFrame(group_rows(figures.customers, "Customer")), hide_index=True, width="stretch")
    if not figures.jobs_on:
        st.caption("Profit is shown by customer: you haven't said that sub-customers are jobs.")

    reasons = missing(figures)
    if reasons:
        st.markdown(f"**What's missing** ({len(reasons)})")
        st.caption("Each figure marked \"Needs a check\" waits on one of these. Answer the questions, or fix the "
                   "report in QuickBooks and export it again.")
        for reason in reasons:
            st.markdown(f"- {_md(reason)}")
    else:
        # Never "nothing is missing": MargenX can't know that, and Complete relies on the owner's answers (the PR #148
        # manual review, blocker 3).
        st.success(CHECKS_DONE)

    with st.expander("Details: what these figures cover and how each line was counted"):
        st.caption(_md(figures.scope))
        st.dataframe(pd.DataFrame([{
            "Row": r.row, "Amount": money(r.amount), "Counted as": r.kind,
            "Customer": ji.safe_cell(r.customer or ""), "Job": ji.safe_cell(r.job or ""),
            "Why": ji.safe_cell(plain(r.reason)),
        } for r in figures.resolutions]), hide_index=True, width="stretch")
