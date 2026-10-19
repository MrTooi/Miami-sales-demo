"""MarginX step 1: drop in CSV files, see what's missing.

Designed so the owner does as little as possible: MarginX works out the file
type, the columns and the date format itself, and asks one plain question only
when it genuinely can't tell. It never guesses money: anything it can't read is
listed with a reason.

Pilot preview: made-up files only (D-003). Files are processed in memory for
this session and are never saved.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import job_intake as ji  # noqa: E402
from ui_theme import apply_theme  # noqa: E402

SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"
SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")
KIND_LABELS = {"invoices": "sales / invoices", "costs": "costs / bills"}
NOT_MAPPED = "(not in this file)"
LEVEL_LABELS = {"problem": "Problem", "gap": "Missing", "info": "Note"}

st.set_page_config(page_title="MarginX | Check your data", page_icon="▰", layout="wide")
apply_theme()

st.title("MarginX: check your data")
st.warning(
    "**Pilot preview: use the sample files or made-up data only.** Don't upload real customer, invoice or bank "
    "files yet. Files are checked in memory for this session and never saved."
)

use_samples = st.toggle("Try it with the made-up sample files", value=True)
files: list[tuple[str, bytes]] = []
if use_samples:
    files = [(name, (SAMPLES / name).read_bytes()) for name in SAMPLE_FILES]
else:
    uploads = st.file_uploader("Drop your sales and cost CSV files here", type=["csv"], accept_multiple_files=True)
    confirmed = st.checkbox("These files are made-up (no real customer, invoice or bank data).")
    if ji.upload_allowed(False, bool(uploads), confirmed):
        files = [(u.name, u.getvalue()) for u in uploads]
    elif uploads:
        st.info("Tick the box above to continue.")
if not files:
    st.stop()


def show_file(name: str, data: bytes) -> None:
    """Read one file and show its results, asking only what MarginX can't work out."""
    st.header(name)
    key = ji.confirmation_key(data, "file", {}, "")  # stable per file contents
    try:
        headers, records = ji.read_csv(data)
    except ji.IntakeError as exc:
        st.error(f"This file can't be read: {exc}")
        return

    kind = ji.detect_kind(headers)
    if kind is None:
        kind = st.radio(f"Is {name} a list of sales or of costs?", list(KIND_LABELS),
                        format_func=KIND_LABELS.get, index=None, key=f"{key}-kind")
        if kind is None:
            return

    # Columns: suggested automatically; the owner is asked only for required ones MarginX can't find.
    mapping = ji.suggest_mapping(headers, kind)
    options: list[str | None] = [None, *headers]
    for fld, (label, required) in ji.FIELDS[kind].items():
        if required and not mapping[fld]:
            mapping[fld] = st.selectbox(f"Which column has the {label.lower()}?", options, index=None,
                                        format_func=lambda h: NOT_MAPPED if h is None else h,
                                        key=f"{key}-{kind}-ask-{fld}")
    with st.expander("How MarginX read this file (change anything that's wrong)"):
        cols = st.columns(3)
        for i, (fld, (label, required)) in enumerate(ji.FIELDS[kind].items()):
            with cols[i % 3]:
                current = mapping.get(fld)
                # The key includes the current choice, so an answer to a question above
                # resets this field instead of being overridden by an older value.
                mapping[fld] = st.selectbox(
                    f"{label}{' *' if required else ''}", options,
                    index=options.index(current) if current in options else 0,
                    format_func=lambda h: NOT_MAPPED if h is None else h,
                    key=f"{key}-{kind}-map-{fld}-{options.index(current) if current in options else 0}",
                )
    problems = ji.validate_mapping(mapping, headers, kind)
    if problems:
        for p in problems:
            st.info(p)
        return

    # Date format: automatic unless the dates could genuinely mean two different days.
    values = ji.column_values(headers, records, mapping["date"])
    date_format = ji.suggest_date_format(values)
    if date_format is None:
        question = ji.date_question(values)
        if question is None:
            st.info("MarginX couldn't read any dates in the date column. Check the column choice above.")
            return
        date_format = st.radio(f"In {name}, what date is {question['example']}?", list(question["options"]),
                               format_func=question["options"].get, index=None, key=f"{key}-datefmt")
        if date_format is None:
            return

    result = ji.intake(headers, records, mapping, kind, date_format)
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
            st.download_button("Download these rows to fix", ji.rejected_rows_csv(result),
                               file_name=f"marginx_rows_to_fix_{name}", mime="text/csv", key=f"{key}-download")


for file_name, file_data in files:
    show_file(file_name, file_data)
