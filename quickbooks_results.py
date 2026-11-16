"""Issue #128, step 7: a QuickBooks report's results, in layers (plan v7, step 7).

1. One sentence first: what the business made after job costs, and whether that's final.
2. Then the figures, for the business, each job (when sub-customers are jobs) and each customer. Every figure
   that isn't final carries its status and the dollar amount being held right next to it, in the same cell,
   never in a separate box.
3. What's missing, in plain words, with the amounts.
4. Details folded away: the scope, and how each line was counted.

Every number comes from quickbooks_figures (exact Decimal, holds included); nothing is added up here except
the count of lines held. Not switched on yet: QuickBooks uploads are still refused, so no page calls this.
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


def cell(figure: qf.Figure) -> str:
    """A figure with its status beside it: "$4,000.00 · Complete" or "$3,800.00 · Needs a check ($50.00 held)"."""
    if figure.status == qp.COMPLETE:
        return f"{money(figure.amount)} · {FINAL}"
    held = figure.held_amount
    known = any(h.amount is not None and h.row is not None for h in figure.holds)
    detail = f"{money(held)} held" if known else "see why below"
    return f"{money(figure.amount)} · {NOT_FINAL} ({detail})"


def held_lines(figures: qf.Figures) -> dict[tuple[str, int | None], list[str]]:
    """Every line (or the report itself) holding any figure back, each once, with its reasons in plain words."""
    found: dict[tuple[str, int | None], list[str]] = {}
    groups = [figures.company, *figures.customers.values(), *figures.jobs.values()]
    for group in groups:
        for figure in group.values():
            for hold in figure.holds:
                reasons = found.setdefault((hold.report, hold.row), [])
                if plain(hold.reason) not in reasons:
                    reasons.append(plain(hold.reason))
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
    lines = sum(1 for (_, row) in held_lines(figures) if row is not None)
    held = profit.held_amount
    why = (f"{money(held)} on {lines} line{'' if lines == 1 else 's'} is still held back"
           if lines else "the report itself has a problem")
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
    for (report, row), reasons in sorted(held.items(), key=lambda item: (item[0][1] is None, item[0][0],
                                                                         item[0][1] or 0)):
        prefix = "" if row is None or report == "Profit and Loss Detail" else f"{report}: "
        out.append(prefix + " ".join(reasons))
    return out


def results_screen(report: qp.ProfitAndLossDetail, answers: qf.OwnerAnswers | None = None, cross_check=None) -> None:
    """The results, in layers."""
    figures = qf.figures(report, answers, cross_check=cross_check)
    st.subheader(_md(headline(report, figures)))
    for warning in figures.warnings:
        st.warning(_md(warning))

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
        st.success("Nothing is missing: every figure above is final for this report.")

    with st.expander("Details: what these figures cover and how each line was counted"):
        st.caption(_md(figures.scope))
        st.dataframe(pd.DataFrame([{
            "Row": r.row, "Amount": money(r.amount), "Counted as": r.kind,
            "Customer": ji.safe_cell(r.customer or ""), "Job": ji.safe_cell(r.job or ""),
            "Why": ji.safe_cell(plain(r.reason)),
        } for r in figures.resolutions]), hide_index=True, width="stretch")
