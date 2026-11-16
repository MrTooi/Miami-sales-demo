"""Issue #128, the switch-on: QuickBooks reports on the upload page (plan v7).

A file goes to the QuickBooks flow only when it is exactly a layout MargenX knows (quickbooks_layouts): QuickBooks
Online's Profit and Loss Detail, or its Sales by Customer Detail, exported to Excel on the accrual basis. Every
other file, QuickBooks look-alikes included, goes to the reader for plain lists (job_intake), which refuses any
QuickBooks look-alike with a plain reason (S2). The reader for plain lists never sees a QuickBooks report.

The flow, once a recognised QuickBooks report is uploaded:
- Exactly one Profit and Loss Detail is the sales and cost source (Alex's decision of 2026-10-26). Sales by
  Customer Detail, if added, only cross-checks its sales (S4); its amounts are never added.
- No other file is used alongside them: a plain sales or cost list could hold the same money again. Until it is
  removed, no figure is shown.
- The owner's questions (quickbooks_screens, step 6b), then the results in layers (quickbooks_results, step 7).

Files are read in memory for this browser session only and never saved; nothing is cached across sessions.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import streamlit as st

import job_intake as ji
import marginx_ui as ui
import quickbooks_crosscheck as qc
import quickbooks_layouts as qlayouts
import quickbooks_pnl as qp
import quickbooks_questions as qq
import quickbooks_results as qresults
import quickbooks_rules as qr
import quickbooks_sbcd as qs
import quickbooks_screens as qscreens

PNL = qlayouts.PROFIT_AND_LOSS_DETAIL
SBCD = qlayouts.SALES_BY_CUSTOMER_DETAIL


def recognised_report(name: str, data: bytes) -> str | None:
    """Which supported QuickBooks report a file is, only when it passes every layout check; None otherwise (the
    file then goes to the reader for plain lists, which refuses a QuickBooks look-alike with its reason)."""
    if not name.lower().endswith(".xlsx") or not data.startswith(b"PK\x03\x04"):
        return None
    try:
        _, table = ji._xlsx_sheet(data)
    except ji.IntakeError:
        return None  # read again by job_intake, which gives the reason
    claimed = qlayouts.claimed_report(qr.quickbooks_signs(table, ji.MAX_TITLE_LINES))
    if claimed and qlayouts.recognise(table, is_xlsx=True, report=claimed).layout is not None:
        return claimed
    return None


@dataclass(eq=False)  # each upload is itself: two copies of one file are still two uploads
class Upload:
    position: int
    name: str
    data: bytes

    @property
    def digest(self) -> bytes:
        return hashlib.sha256(self.data).digest()


@dataclass
class Sorted:
    """The uploaded files, sorted by what they are."""
    pnl: list[Upload] = field(default_factory=list)
    sbcd: list[Upload] = field(default_factory=list)
    other: list[Upload] = field(default_factory=list)

    @property
    def quickbooks(self) -> bool:
        """True when any file is a recognised QuickBooks report: the page then uses the QuickBooks flow."""
        return bool(self.pnl or self.sbcd)


def sort_files(files: list[tuple[str, bytes]]) -> Sorted:
    found = Sorted()
    for position, (name, data) in enumerate(files):
        upload = Upload(position, name, data)
        report = recognised_report(name, data)
        (found.pnl if report == PNL else found.sbcd if report == SBCD else found.other).append(upload)
    return found


def _distinct(uploads: list[Upload]) -> list[Upload]:
    """One of each exact file: the same file uploaded twice is the same rows, not new ones."""
    seen, out = set(), []
    for upload in uploads:
        if upload.digest not in seen:
            seen.add(upload.digest)
            out.append(upload)
    return out


ONE_PNL = ("MargenX reads one Profit and Loss Detail at a time, and {count} different ones were uploaded. Keep the "
           "one you want to look at and remove the others.")
ONE_SBCD = ("MargenX uses one Sales by Customer Detail at a time, to check the sales in the Profit and Loss Detail, "
            "and {count} different ones were uploaded. Keep the one for the same dates and remove the others.")
NOT_WITH_OTHERS = ("A QuickBooks Profit and Loss Detail already has your sales and your costs, so MargenX doesn't use "
                   "other sales or cost files with it: the same money could be counted twice. Remove {names} to see "
                   "your results, or remove the QuickBooks report to use the other files instead.")
NOT_WITH_SBCD = ("MargenX also doesn't mix QuickBooks reports with other sales or cost files. Remove {names}, or "
                 "remove the QuickBooks report to use the other files instead.")
SBCD_ALONE = ("MargenX uses QuickBooks' Sales by Customer Detail only to check the sales in a Profit and Loss Detail "
              "for the same dates. Add your Profit and Loss Detail (Excel, accrual basis) to see your results.")


def show(found: Sorted, results_area, *, key: str) -> tuple[bool, set[str]]:
    """The QuickBooks flow: each file under "Your files", then the questions and results in results_area.

    Returns (no question left, the kinds of report read for the "Sales report / Cost report" slots)."""
    _md = qscreens._md
    pnls, sbcds = _distinct(found.pnl), _distinct(found.sbcd)
    report, sales = None, None
    blocked: list[str] = []
    first: dict[bytes, str] = {}
    for upload in sorted([*found.pnl, *found.sbcd, *found.other], key=lambda u: u.position):
        ui.file_title(upload.name)
        if upload.digest in first and upload in (*found.pnl, *found.sbcd):
            st.warning(f"{_md(upload.name)} is identical to {_md(first[upload.digest])}. Its rows are the same rows, "
                       "not new ones; it's used once.")
            continue
        first.setdefault(upload.digest, upload.name)
        if upload in found.other:
            st.info("Not used: MargenX doesn't combine this file with a QuickBooks report (see the message above).")
            continue
        is_pnl = upload in found.pnl
        try:
            if is_pnl:
                read = qp.read_profit_and_loss_detail(upload.name, upload.data)
            else:
                read = qs.read_sales_by_customer_detail(upload.name, upload.data)
        except ji.IntakeError as exc:
            st.error(f"This file can't be read: {_md(exc)}")
            blocked.append(upload.name)
            continue
        layout = read.layout
        what = ("your sales and costs come from it" if is_pnl
                else "used only to check the sales in the Profit and Loss Detail; its amounts are never added")
        st.caption(_md(f"Read as QuickBooks' {layout.report} for {layout.company} ({layout.period}, "
                       f"{layout.basis.lower()} basis): {what}."))
        if is_pnl and upload is pnls[0]:
            report = read
        elif not is_pnl and upload is sbcds[0]:
            sales = read

    with results_area:
        if len(pnls) > 1:
            st.error(ONE_PNL.format(count=len(pnls)))
            return False, set()
        if len(sbcds) > 1:
            st.error(ONE_SBCD.format(count=len(sbcds)))
            return False, set()
        if found.other:
            names = ", ".join(_md(u.name) for u in found.other)
            st.error(NOT_WITH_OTHERS.format(names=names) if pnls else f"{SBCD_ALONE} {NOT_WITH_SBCD.format(names=names)}")
            return False, set()
        if not pnls:
            st.info(SBCD_ALONE)
            return False, set()
        if blocked or report is None:
            st.info("Your results appear here once every file below can be read (the reason is under each file).")
            return False, set()
        check = qc.cross_check(report, sales) if sales is not None else None
        answers = qscreens.question_screen(report, check, key=key)
        st.divider()
        qresults.results_screen(report, answers, check)
    # The steps column says "See your money" once no question is left (the figures may still need a check).
    done = not qq.open_questions(report, answers, check).questions
    return done, {"invoices", "costs"}
