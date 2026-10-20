"""MarginX step 1: drop in CSV files, see what's missing.

Designed so the owner does as little as possible: MarginX works out the file
type, the columns and the date format itself, and asks one plain question only
when it genuinely can't tell. Every automatic choice is shown and can be changed.
It never guesses money: anything it can't read is listed with a reason.

Made-up files only (D-003), except in pilot mode: on a team laptop, with pilot
mode switched on and the app reachable from that computer alone (pilot_safety),
a pilot shop's own files may be read with the owner's consent. Either way, files
are processed in memory for this session only and never saved; "End session"
forgets everything.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import job_intake as ji  # noqa: E402
import job_profit as jp  # noqa: E402
import pilot_safety as ps  # noqa: E402
from ui_theme import apply_theme  # noqa: E402

SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"
SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")
KIND_LABELS = {"invoices": "sales / invoices", "costs": "costs / bills"}
NOT_MAPPED = "(not in this file)"
# A file that is fully dealt with but adds nothing to profit (a bank statement, headers only).
EXCLUDED = "excluded"
LEVEL_LABELS = {"problem": "Problem", "gap": "Missing", "info": "Note"}
# Deposits, transfers and payments are cash movements, not sales or costs (MVP spec).
BANK_MESSAGE = ("MarginX can't read bank, card or payment statements yet: deposits, payments and transfers "
                "aren't sales or costs. Export your invoices and your bills from your accounting software instead.")

st.set_page_config(page_title="MarginX | Check your data", page_icon="▰", layout="wide")
apply_theme()

PILOT = ps.pilot_mode(os.environ, st.get_option("server.address"))

st.title("MarginX: check your data")
if PILOT:
    st.warning(
        "**Pilot session on this laptop.** A pilot shop's own files may be used only with the shop owner present "
        "and agreeing below. Files are read in memory only, never saved, and forgotten when you press "
        "**End session**."
    )
else:
    st.warning(
        "**Pilot preview: use the sample files or made-up data only.** Don't upload real customer, invoice or bank "
        "files yet. Files are checked in memory for this session and never saved."
    )

# "End session" forgets every file, answer and result: the session's state is cleared and the
# upload box gets a new key, so nothing from the visit stays in the app.
session = st.session_state.get("session_number", 0)
if st.button("End session and clear everything"):
    st.session_state.clear()
    st.session_state["session_number"] = session + 1
    st.session_state["just_ended"] = True
    st.rerun()
if st.session_state.pop("just_ended", False):
    st.success("Session ended. Nothing from it is kept in MarginX.")
st.session_state["session_number"] = session

use_samples = st.toggle("Try it with the made-up sample files", value=not PILOT, key=f"samples-{session}")
files: list[tuple[str, bytes]] = []
if use_samples:
    files = [(name, (SAMPLES / name).read_bytes()) for name in SAMPLE_FILES]
else:
    uploads = st.file_uploader("Drop your sales and cost CSV files here", type=["csv"], accept_multiple_files=True,
                               key=f"upload-{session}")
    confirmed = st.checkbox(ps.CONSENT_TEXT if PILOT else ps.MADE_UP_TEXT, key=f"confirm-{session}")
    if ps.upload_allowed(False, bool(uploads), confirmed):
        files = [(u.name, u.getvalue()) for u in uploads]
    elif uploads:
        st.info("Tick the box above to continue.")
if not files:
    st.stop()


def describe_format(name: str, example: str | None) -> str:
    """A format label with what the file's first date would mean in it."""
    if not example:
        return name
    parsed = ji._parse_date(example, ji.DATE_FORMATS[name])
    return f"{name}: {example} = {parsed:%B} {parsed.day}, {parsed.year}" if parsed else f"{name} (doesn't fit {example})"


def show_file(position: int, name: str, data: bytes, same_as: str | None = None) -> ji.IntakeResult | str | None:
    """Read one file and show its results, asking only what MarginX can't work out.

    Returns what was imported; EXCLUDED for a file that adds nothing (a bank statement, headers
    only); or None while a question is unanswered or the file can't be read.
    """
    st.header(name)
    if same_as:
        # Each file is checked on its own and nothing is added up across files yet,
        # but a repeated upload is pointed out rather than reported as if it were new.
        st.warning(f"{name} is identical to {same_as}. Its rows are the same rows, not new ones; "
                   "upload it only once.")
    # Each file in the list gets its own widget namespace, even if two files are identical.
    key = f"f{position}-{hashlib.sha256(name.encode('utf-8') + data).hexdigest()[:12]}"
    try:
        headers, records = ji.read_csv(data)
    except ji.IntakeError as exc:
        st.error(f"This file can't be read: {exc}")
        return
    if not records:
        st.info("This file has column headers but no rows, so there is nothing to import.")
        return EXCLUDED

    detected = ji.detect_kind(headers)
    if detected is None:
        kind = st.radio(f"What kind of file is {name}?", [*KIND_LABELS, "bank"],
                        format_func=lambda k: KIND_LABELS.get(k, "a bank, card or payment statement"),
                        index=None, key=f"{key}-kind-ask")
        if kind is None:
            return
        if kind == "bank":
            st.info(BANK_MESSAGE)
            return EXCLUDED
    else:
        kind = detected
    settings = st.expander("How MarginX read this file (change anything that's wrong)")
    with settings:
        kind = st.radio("File type", [*KIND_LABELS, "bank"], index=list(KIND_LABELS).index(kind),
                        format_func=lambda k: KIND_LABELS.get(k, "a bank, card or payment statement"), horizontal=True,
                        key=f"{key}-kind-{kind}")
    if kind == "bank":
        st.info(BANK_MESSAGE)
        return EXCLUDED

    # Columns: suggested automatically; the owner is asked for required ones MarginX can't
    # find, and for optional ones where two columns could fit (e.g. "Job" and "Project").
    mapping = ji.suggest_mapping(headers, kind)
    ambiguous = ji.ambiguous_columns(headers, kind)
    options: list[str | None] = [None, *headers]
    for fld, (label, required) in ji.FIELDS[kind].items():
        if required and not mapping[fld]:
            mapping[fld] = st.selectbox(f"Which column has the {label.lower()}?", options, index=None,
                                        format_func=lambda h: NOT_MAPPED if h is None else h,
                                        key=f"{key}-{kind}-ask-{fld}")
        elif fld in ambiguous:
            # Answers are positions, so "neither" can't be confused with "not answered yet".
            candidates = ambiguous[fld]
            pick = st.radio(f"Which column has the {label.lower()}?", range(len(candidates) + 1), index=None,
                            format_func=lambda i, c=candidates: c[i] if i < len(c) else "Neither of these",
                            key=f"{key}-{kind}-which-{fld}")
            if pick is None:
                return
            mapping[fld] = candidates[pick] if pick < len(candidates) else None
    with settings:
        cols = st.columns(3)
        for i, (fld, (label, required)) in enumerate(ji.FIELDS[kind].items()):
            with cols[i % 3]:
                current = mapping.get(fld)
                at = options.index(current) if current in options else 0
                # The key includes the current choice, so an answer to a question above
                # resets this field instead of being overridden by an older value.
                mapping[fld] = st.selectbox(
                    f"{label}{' *' if required else ''}", options, index=at,
                    format_func=lambda h: NOT_MAPPED if h is None else h, key=f"{key}-{kind}-map-{fld}-{at}",
                )
    problems = ji.validate_mapping(mapping, headers, kind)
    if problems:
        for p in problems:
            st.info(p)
        return

    # Amount meaning: asked when an invoice or bill has several lines and the amount
    # column's name doesn't say whether it is each line's price or the document's total.
    amount_scope = None
    scope = ji.amount_scope_question(headers, records, mapping, kind)
    if scope:
        what = "invoice" if kind == "invoices" else "bill"
        # The answer is keyed to the whole mapping and the question, so changing how lines are
        # grouped (or which column is the amount) asks again instead of reusing an old answer.
        asked = hashlib.sha256(repr((sorted(mapping.items(), key=str), scope)).encode("utf-8")).hexdigest()[:12]
        amount_scope = st.radio(
            f"In {name}, {scope['label']} has {scope['lines']} lines. What is '{mapping['amount']}' "
            "on each line?", ji.AMOUNT_SCOPES, index=None,
            format_func={"line": "That line's own amount (count every line)",
                         "document": f"The whole {what}'s total, repeated on each line"}.get,
            key=f"{key}-{kind}-scope-{asked}")
        if amount_scope is None:
            return

    # A line equal to the sum of its document's other lines may be a subtotal, or a real line
    # that adds up by coincidence: the owner says which, one line at a time. This applies
    # whether the column says it holds line amounts or the owner did.
    subtotals: dict[int, bool] = {}
    asked_sums = hashlib.sha256(repr((sorted(mapping.items(), key=str), amount_scope)).encode("utf-8")).hexdigest()[:12]
    for item in ji.subtotal_questions(headers, records, mapping, kind, amount_scope):
        answer = st.radio(
            f"In {name}, row {item['row']} of {item['label']} shows {item['amount']}, which equals its other "
            "lines added together. Is it a subtotal?", (False, True), index=None,
            format_func={False: "No, it's a real line (count it)", True: "Yes, a subtotal (don't count it)"}.get,
            key=f"{key}-{kind}-subtotal-{asked_sums}-{item['row']}")
        if answer is None:
            return
        subtotals[item["row"]] = answer

    # Date format: automatic unless the dates could genuinely mean two different days.
    # Answers are keyed to the file type and date column, so a changed choice asks again.
    values = ji.column_values(headers, records, mapping["date"])
    example = next((v.strip() for v in values if v and v.strip()), None)
    date_key = f"{key}-{kind}-{headers.index(mapping['date'])}"
    formats = list(ji.DATE_FORMATS)
    date_format = ji.suggest_date_format(values)
    if date_format is None:
        question = ji.date_question(values)
        if question:
            date_format = st.radio(f"In {name}, what date is {question['example']}?", list(question["options"]),
                                   format_func=question["options"].get, index=None, key=f"{date_key}-ask")
        else:
            # Dates use mixed styles, or none could be read: let the owner pick the main
            # format. Rows it can't read are then listed with reasons, never dropped.
            date_format = st.radio(f"Which date format does {name} mainly use?", formats,
                                   format_func=lambda f: describe_format(f, example), index=None,
                                   key=f"{date_key}-pick")
        if date_format is None:
            return
    with settings:
        date_format = st.selectbox("Date format", formats, index=formats.index(date_format),
                                   format_func=lambda f: describe_format(f, example),
                                   key=f"{date_key}-override-{date_format}")

    result = ji.intake(headers, records, mapping, kind, date_format, amount_scope, subtotals)
    st.caption(f"Read as {KIND_LABELS[kind]}, dates as {date_format}.")
    for item in ji.missing_report(result):
        # Report text can quote values from the file, so it is shown as plain text.
        st.text(f"{LEVEL_LABELS[item['level']]}: {item['text']}")

    if result.rejected:
        with st.expander(f"Rows that couldn't be used ({len(result.rejected)})"):
            # Formula-safe values, because the table toolbar can also export CSV.
            st.dataframe(
                pd.DataFrame([{"Row in file": r["row"], "Why": ji.safe_cell(" ".join(r["reasons"])),
                               "Original row": ji.safe_cell(" | ".join(r["cells"]))} for r in result.rejected]),
                hide_index=True, width="stretch",
            )
    return result


def money_cell(amount) -> str:
    return "—" if amount is None else jp.format_money(amount)


def show_profit(results: list[ji.IntakeResult], pending: list[str]) -> None:
    """Profit by job and customer, once every file is dealt with and there is exactly one sales
    file and one costs file."""
    st.header("Profit by job")
    if pending:
        # A file still waiting for an answer (or unreadable) could hold sales or costs.
        st.info("Profit by job waits until every file above is read: answer the questions for "
                + ", ".join(pending) + ", or remove it.")
        return
    invoices = [r for r in results if r.kind == "invoices"]
    costs = [r for r in results if r.kind == "costs"]
    if len(invoices) != 1 or len(costs) != 1:
        st.info("Profit by job needs exactly one sales file and one costs file, each fully read above. "
                "Answer any questions above, or upload one of each.")
        return
    report = jp.job_profit(invoices[0], costs[0])
    if not report.available:
        for reason in report.reasons:
            st.info(reason)
        return
    st.caption(report.basis)
    st.caption(f"Imported sales lines are dated {report.invoice_dates[0]} to {report.invoice_dates[1]}; "
               f"imported cost lines {report.cost_dates[0]} to {report.cost_dates[1]}. "
               "Lines that couldn't be imported are listed with each file above.")
    st.caption("'Complete' means these files have the job's sales, labor and materials or outsourced work, every "
               "cost typed and nothing failed to import. MarginX can't tell whether the files cover every cost "
               "of the job, so check that they span the whole job.")
    counts = {s: sum(1 for j in report.jobs if j.status == s) for s in jp.STATUS_ORDER}
    st.text(f"{len(report.jobs)} jobs: {counts['complete']} complete, {counts['provisional']} provisional "
            f"(missing costs, shown with reasons), {counts['unavailable']} without a figure.")
    shown = [c for c in jp.CATEGORIES if any(j.costs[c] for j in report.jobs)]
    # Text from the files is formula-safe, because the table toolbar can export CSV.
    st.dataframe(pd.DataFrame([{
        "Job": ji.safe_cell(j.job_id), "Customer": ji.safe_cell(", ".join(j.customers)),
        "Sales": money_cell(j.sales if j.invoice_lines else None),
        **{jp.CATEGORY_LABELS[c]: money_cell(j.costs[c]) for c in shown},
        "Direct contribution": money_cell(j.contribution), "Status": jp.STATUS_LABELS[j.status],
        "Why": ji.safe_cell(" ".join(j.reasons)),
    } for j in report.jobs]), hide_index=True, width="stretch")

    st.subheader("By customer")
    st.dataframe(pd.DataFrame([{
        "Customer": ji.safe_cell(c.customer), "Jobs": ji.safe_cell(", ".join(c.jobs)),
        # A customer with no figure shows no amounts at all, not a misleading $0.00.
        "Sales": money_cell(c.sales if c.contribution is not None else None),
        "Costs": money_cell(c.total_costs if c.contribution is not None else None),
        "Direct contribution": money_cell(c.contribution), "Status": jp.STATUS_LABELS[c.status],
        "Why": ji.safe_cell(" ".join(c.reasons)),
    } for c in report.customers]), hide_index=True, width="stretch")
    for note in report.notes:
        st.text(f"Note: {note}")


seen_files: dict[bytes, str] = {}
results: list[ji.IntakeResult] = []
pending: list[str] = []
for file_position, (file_name, file_data) in enumerate(files):
    digest = hashlib.sha256(file_data).digest()
    result = show_file(file_position, file_name, file_data, seen_files.get(digest))
    if result is None:
        pending.append(file_name)
    elif result != EXCLUDED:
        results.append(result)
    seen_files.setdefault(digest, file_name)
show_profit(results, pending)
