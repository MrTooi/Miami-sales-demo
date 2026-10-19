"""MarginX step 1: upload a CSV, confirm its columns, see what's missing.

Pilot preview: fictional or anonymized files only (D-003). Files are processed
in memory for this session and are never saved.
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
from ui_theme import apply_theme, section_header  # noqa: E402

SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"
KIND_LABELS = {"invoices": "Invoices / sales", "costs": "Costs / bills / expenses"}
NOT_MAPPED = "â€” not in this file â€”"

st.set_page_config(page_title="MarginX | Import", page_icon="â–°", layout="wide")
apply_theme()

st.title("MarginX: import your jobs data")
st.warning(
    "**Pilot preview: use the sample files or made-up data only.** Don't upload real customer, invoice or bank "
    "files yet. Files are checked in memory for this session and never saved."
)

# --- 1. Choose a file ------------------------------------------------------
section_header("1. Choose a file", "One CSV at a time. Excel and multiple files come in a later step.")
kind = st.radio("What's in the file?", list(KIND_LABELS), format_func=KIND_LABELS.get, horizontal=True)
sample_name = "fictional_invoices.csv" if kind == "invoices" else "fictional_costs.csv"
use_sample = st.toggle(f"Use the fictional sample file ({sample_name})", value=True)
upload = None if use_sample else st.file_uploader("CSV file", type=["csv"])
if not use_sample:
    confirmed = st.checkbox("This file is made-up or anonymized (no real customer, invoice or bank data).")
    if upload is not None and not confirmed:
        st.info("Tick the box above to continue.")
        st.stop()

data = (SAMPLES / sample_name).read_bytes() if use_sample else (upload.getvalue() if upload else None)
if data is None:
    st.stop()

try:
    headers, rows = ji.read_csv(data)
except ji.IntakeError as exc:
    st.error(f"This file can't be read: {exc}")
    st.stop()

st.caption(f"{len(rows)} data rows, {len(headers)} columns: {', '.join(headers)}")

# --- 2. Confirm the columns ---------------------------------------------------
section_header("2. Confirm the columns", "MarginX suggests a match; check each one. Nothing is guessed silently.")
suggested = ji.suggest_mapping(headers, kind)
mapping: dict[str, str | None] = {}
options = [NOT_MAPPED, *headers]
cols = st.columns(3)
for i, (fld, (label, required)) in enumerate(ji.FIELDS[kind].items()):
    with cols[i % 3]:
        default = suggested.get(fld)
        choice = st.selectbox(
            f"{label}{' *' if required else ' (optional)'}",
            options,
            index=options.index(default) if default in options else 0,
            key=f"map-{kind}-{fld}",
        )
        mapping[fld] = None if choice == NOT_MAPPED else choice

date_values = [r.get(mapping["date"], "") for r in rows] if mapping.get("date") else []
date_guess = ji.suggest_date_format(date_values)
formats = list(ji.DATE_FORMATS)
date_format = st.selectbox(
    "Date format used in the file *",
    ["Chooseâ€¦", *formats],
    index=formats.index(date_guess) + 1 if date_guess else 0,
    help="Picked automatically only when every date fits exactly one format.",
    key=f"datefmt-{kind}",
)
if date_guess is None and mapping.get("date"):
    st.caption("The dates don't fit a single format, or fit more than one, so please choose.")

problems = ji.validate_mapping(mapping, headers, kind)
if date_format == "Chooseâ€¦":
    problems.append("Choose the date format used in the file.")
if problems:
    for p in problems:
        st.info(p)
    st.stop()

# --- 3. What's missing --------------------------------------------------------
result = ji.intake(headers, rows, mapping, kind, date_format)
section_header("3. What's missing", "Counts only. Profit by job comes in a later step.")
icons = {"problem": "ðŸ”´", "gap": "ðŸŸ ", "info": "â„¹ï¸"}
for item in ji.missing_report(result):
    st.markdown(f"{icons[item['level']]} {item['text']}")

if result.rejected:
    st.subheader(f"Rows that couldn't be imported ({len(result.rejected)})")
    st.dataframe(
        pd.DataFrame([{"Row in file": r["row"], "Why": " ".join(r["reasons"]), **r["values"]} for r in result.rejected]),
        hide_index=True, width="stretch",
    )
    st.download_button("Download these rows to fix", ji.rejected_rows_csv(result),
                       file_name=f"marginx_{kind}_rows_to_fix.csv", mime="text/csv")

if result.accepted:
    with st.expander(f"Imported rows ({len(result.accepted)})"):
        st.dataframe(
            pd.DataFrame([{**r, "amount": f"{r['amount']:,.2f}"} for r in result.accepted]),
            hide_index=True, width="stretch",
        )
