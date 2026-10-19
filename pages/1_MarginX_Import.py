"""MarginX step 1: drop in CSV files, see what's missing.

Designed so the owner does as little as possible: MarginX works out the file
type, the columns and the date format itself, and asks one plain question only
when it genuinely can't tell. Every automatic choice is shown and can be changed.
It never guesses money: anything it can't read is listed with a reason.

Pilot preview: made-up files only (D-003). Files are processed in memory for
this session and are never saved.
"""
from __future__ import annotations

import hashlib
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
# Deposits, transfers and payments are cash movements, not sales or costs (MVP spec).
BANK_MESSAGE = ("MarginX can't read bank, card or payment statements yet: deposits, payments and transfers "
                "aren't sales or costs. Export your invoices and your bills from your accounting software instead.")

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


def describe_format(name: str, example: str | None) -> str:
    """A format label with what the file's first date would mean in it."""
    if not example:
        return name
    parsed = ji._parse_date(example, ji.DATE_FORMATS[name])
    return f"{name}: {example} = {parsed:%B} {parsed.day}, {parsed.year}" if parsed else f"{name} (doesn't fit {example})"


def show_file(position: int, name: str, data: bytes, same_as: str | None = None) -> None:
    """Read one file and show its results, asking only what MarginX can't work out."""
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
        return

    detected = ji.detect_kind(headers)
    if detected is None:
        kind = st.radio(f"What kind of file is {name}?", [*KIND_LABELS, "bank"],
                        format_func=lambda k: KIND_LABELS.get(k, "a bank, card or payment statement"),
                        index=None, key=f"{key}-kind-ask")
        if kind is None:
            return
        if kind == "bank":
            st.info(BANK_MESSAGE)
            return
    else:
        kind = detected
    settings = st.expander("How MarginX read this file (change anything that's wrong)")
    with settings:
        kind = st.radio("File type", [*KIND_LABELS, "bank"], index=list(KIND_LABELS).index(kind),
                        format_func=lambda k: KIND_LABELS.get(k, "a bank, card or payment statement"), horizontal=True,
                        key=f"{key}-kind-{kind}")
    if kind == "bank":
        st.info(BANK_MESSAGE)
        return

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


seen_files: dict[bytes, str] = {}
for file_position, (file_name, file_data) in enumerate(files):
    digest = hashlib.sha256(file_data).digest()
    show_file(file_position, file_name, file_data, seen_files.get(digest))
    seen_files.setdefault(digest, file_name)
