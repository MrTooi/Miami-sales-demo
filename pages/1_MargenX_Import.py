"""MargenX step 1: drop in CSV files, see what's missing.

Designed so the owner does as little as possible: MargenX works out the file
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
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import job_intake as ji  # noqa: E402
import job_matching as jm  # noqa: E402
import job_profit as jp  # noqa: E402
import marginx_insights as mi  # noqa: E402
import marginx_ui as ui  # noqa: E402
import pilot_safety as ps  # noqa: E402

SAMPLES = Path(_REPO_ROOT) / "sample_data" / "marginx"
SAMPLE_FILES = ("fictional_invoices.csv", "fictional_costs.csv")
# Clean made-up businesses for showing MargenX to owners, one per kind of business we talk to. Each
# has no questions to answer, one losing job, a big customer who barely makes money, one job
# missing labor, and rent as unlinked overhead.
DEMO_SETS = {
    "demo": ("demo_sign_shop_invoices.csv", "demo_sign_shop_costs.csv"),
    "contractor": ("demo_contractor_invoices.csv", "demo_contractor_costs.csv"),
    "custom_shop": ("demo_custom_shop_invoices.csv", "demo_custom_shop_costs.csv"),
}
DEFAULT_SAMPLE_SET = "demo"
SAMPLE_SET_LABELS = {"demo": "Demo sign shop",
                     "contractor": "Demo remodeling contractor",
                     "custom_shop": "Demo cabinet and metal shop",
                     "test": "Messy test files (errors, gaps and questions)"}
KIND_LABELS = {"invoices": "sales / invoices", "costs": "costs / bills"}
NOT_MAPPED = "(not in this file)"
# A file that is fully dealt with but adds nothing to profit (a bank statement, headers only).
EXCLUDED = "excluded"
# Each read file's identity (job_matching.source_key), by id() of its result, for this run only.
SOURCE_KEYS: dict[int, str] = {}
LEVEL_LABELS = {"problem": "Problem", "gap": "Missing", "info": "Note"}
# Deposits, transfers and payments are cash movements, not sales or costs (MVP spec).
BANK_MESSAGE = ("MargenX can't read bank, card or payment statements yet: deposits, payments and transfers "
                "aren't sales or costs. Export your invoices and your bills from your accounting software instead.")

st.set_page_config(page_title=f"{ui.BRAND} | Where your money is made", page_icon=str(ui.LOGO_PATH), layout="wide")
ui.apply_brand()
ui.apply_app_frame()

def _request_headers():
    try:
        return dict(st.context.headers)
    except Exception:  # no browser request (e.g. tests): never counts as local
        return None


PILOT = ps.pilot_mode(os.environ, st.get_option("server.address"), _request_headers())

# The app's frame: a top bar (brand, session, End session), the check-up's steps down the side, and
# the page beside them. "End session" forgets every file, answer and result: the session's state is
# cleared and the upload box gets a new key, so nothing from the visit stays in the app.
session = st.session_state.get("session_number", 0)
def _release_uploads() -> bool:
    """Delete this browser session's uploaded files from Streamlit's memory and confirm it."""
    try:
        from streamlit.runtime import Runtime
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

        ctx = get_script_run_ctx()
        manager = Runtime.instance().uploaded_file_mgr if Runtime.exists() else None
        return ps.release_uploads(manager, ctx.session_id if ctx else None)
    except Exception:
        return False


with st.container(key="mx-bar"):
    bar_brand, bar_end = st.columns([4, 1.3], vertical_alignment="center")
    with bar_brand:
        ui.top_bar(PILOT)
    end_clicked = bar_end.button("End session and clear everything", width="stretch")
if end_clicked:
    released = _release_uploads()
    st.session_state.clear()
    st.session_state["session_number"] = session + 1
    st.session_state["just_ended"] = "released" if released else "unconfirmed"
    st.rerun()
with st.container(key="mx-shell"):
    side, main = st.columns([1, 3.7])
nav = side.empty()  # the steps, filled in once the page knows which step it's on
with side:
    ui.what_you_get()

with main:
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
    ended = st.session_state.pop("just_ended", None)
    if ended == "released":
        st.success("Session ended. The uploaded files were removed from MargenX's upload storage, and the answers and "
                   "results were cleared from this session. Close this browser tab and stop MargenX to finish the visit. "
                   "The original files on this laptop (Downloads, AirDrop, USB) must still be deleted by hand.")
    elif ended:
        # Never claim a deletion that couldn't be checked.
        st.warning("Answers and results were cleared, but MargenX couldn't confirm the uploaded files were deleted "
                   "from memory. Close this browser tab now and stop MargenX (Ctrl+C) to finish clearing.")
    st.session_state["session_number"] = session

    use_samples = st.toggle("Try it with the made-up sample files", value=not PILOT, key=f"samples-{session}")
    files: list[tuple[str, bytes]] = []
    slots = None  # the "Sales report / Cost report" status under the upload area
    if use_samples:
        sample_set = st.radio("Which made-up files?", list(SAMPLE_SET_LABELS),
                              index=list(SAMPLE_SET_LABELS).index(DEFAULT_SAMPLE_SET),
                              format_func=SAMPLE_SET_LABELS.get, horizontal=True, key=f"sampleset-{session}")
        chosen = DEMO_SETS.get(sample_set, SAMPLE_FILES)
        files = [(name, (SAMPLES / name).read_bytes()) for name in chosen]
    else:
        heading = st.empty()  # shown only until files arrive: then the results take over
        with st.container(key="mx-consent"):
            ui.card_title("Before we start", "The owner reads and ticks this." if PILOT
                          else "Only made-up files outside a pilot session.")
            consent_col, points_col = st.columns([1.6, 1], vertical_alignment="center")
            # The box comes first: the upload area isn't shown, so no file can be received, until it is ticked.
            confirmed = consent_col.checkbox(ps.CONSENT_TEXT if PILOT else ps.MADE_UP_TEXT, key=f"confirm-{session}")
            with points_col:
                ui.privacy_points(PILOT)
        with st.container(key="mx-files"):
            ui.card_title("Drop your reports", "Both files at once, or one at a time.")
            if not confirmed:
                ui.locked_drop()
            else:
                uploads = st.file_uploader("Drop your sales and cost files here (CSV or Excel)", type=["csv", "xlsx"],
                                           accept_multiple_files=True, key=f"upload-{session}",
                                           label_visibility="collapsed")
                if ps.upload_allowed(False, bool(uploads), confirmed):
                    files = [(u.name, u.getvalue()) for u in uploads]
            slots = st.empty()
            with slots.container():
                ui.file_slots(set())
    if not files:
        if not use_samples:
            with heading.container():
                ui.step_heading(1, "Add your reports",
                                "Two exports from QuickBooks or Square: your sales and your costs. CSV or Excel.")
        with nav.container():
            ui.steps(1)
        st.stop()

    # Results go above the files: they're what the owner came for, filled in once every file is read.
    results_area = st.container()


    def describe_format(name: str, example: str | None) -> str:
        """A format label with what the file's first date would mean in it."""
        if not example:
            return name
        parsed = ji._parse_date(example, ji.DATE_FORMATS[name])
        return f"{name}: {example} = {parsed:%B} {parsed.day}, {parsed.year}" if parsed else f"{name} (doesn't fit {example})"


    def show_file(position: int, name: str, data: bytes, same_as: str | None = None) -> ji.IntakeResult | str | None:
        """Read one file and show its results, asking only what MargenX can't work out.

        Returns what was imported; EXCLUDED for a file that adds nothing (a bank statement, headers
        only); or None while a question is unanswered or the file can't be read.
        """
        ui.file_title(name)
        if same_as:
            # Each file is checked on its own and nothing is added up across files yet,
            # but a repeated upload is pointed out rather than reported as if it were new.
            st.warning(f"{ui.md_text(name)} is identical to {ui.md_text(same_as)}. Its rows are the same rows, not new ones; "
                       "upload it only once.")
        # Each file in the list gets its own widget namespace, even if two files are identical.
        key = f"f{position}-{hashlib.sha256(name.encode('utf-8') + data).hexdigest()[:12]}"
        try:
            headers, records, notes = ji.read_file(name, data)
        except ji.IntakeError as exc:
            st.error(f"This file can't be read: {ui.md_text(exc)}")
            return
        for note in notes:
            # How the file was read (title lines skipped, placeholder column names): shown, never hidden.
            st.caption(ui.md_text(note))
        if not records:
            st.info("This file has column headers but no rows, so there is nothing to import.")
            return EXCLUDED

        detected = ji.detect_kind(headers)
        if detected is None:
            kind = st.radio(f"What kind of file is {ui.md_text(name)}?", [*KIND_LABELS, "bank"],
                            format_func=lambda k: KIND_LABELS.get(k, "a bank, card or payment statement"),
                            index=None, key=f"{key}-kind-ask")
            if kind is None:
                return
            if kind == "bank":
                st.info(BANK_MESSAGE)
                return EXCLUDED
        else:
            kind = detected
        settings = st.expander("How MargenX read this file (change anything that's wrong)")
        with settings:
            kind = st.radio("File type", [*KIND_LABELS, "bank"], index=list(KIND_LABELS).index(kind),
                            format_func=lambda k: KIND_LABELS.get(k, "a bank, card or payment statement"), horizontal=True,
                            key=f"{key}-kind-{kind}")
        if kind == "bank":
            st.info(BANK_MESSAGE)
            return EXCLUDED

        # Columns: suggested automatically; the owner is asked for required ones MargenX can't
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
                                format_func=lambda i, c=candidates: ui.md_text(c[i]) if i < len(c) else "Neither of these",
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
                st.info(ui.md_text(p))
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
                f"In {ui.md_text(name)}, {ui.md_text(scope['label'])} has {scope['lines']} lines. "
                f"What is '{ui.md_text(mapping['amount'])}' "
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
                f"In {ui.md_text(name)}, row {item['row']} of {ui.md_text(item['label'])} shows "
                f"{ui.md_text(item['amount'])}, which equals its other "
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
                date_format = st.radio(f"In {ui.md_text(name)}, what date is {ui.md_text(question['example'])}?",
                                       list(question["options"]),
                                       format_func=question["options"].get, index=None, key=f"{date_key}-ask")
            else:
                # Dates use mixed styles, or none could be read: let the owner pick the main
                # format. Rows it can't read are then listed with reasons, never dropped.
                date_format = st.radio(f"Which date format does {ui.md_text(name)} mainly use?", formats,
                                       format_func=lambda f: ui.md_text(describe_format(f, example)), index=None,
                                       key=f"{date_key}-pick")
            if date_format is None:
                return
        with settings:
            date_format = st.selectbox("Date format", formats, index=formats.index(date_format),
                                       format_func=lambda f: describe_format(f, example),
                                       key=f"{date_key}-override-{date_format}")

        result = ji.intake(headers, records, mapping, kind, date_format, amount_scope, subtotals)
        SOURCE_KEYS[id(result)] = jm.source_key(name, data, (position, kind, sorted(mapping.items(), key=str), date_format,
                                                             amount_scope, sorted(subtotals.items())))
        st.caption(f"Read as {KIND_LABELS[kind]}, dates as {date_format}.")
        report = ji.missing_report(result)
        problems_found = sum(1 for item in report if item["level"] != "info")
        with st.expander(f"What MargenX found in this file ({problems_found} to look at)" if problems_found
                         else "What MargenX found in this file"):
            for item in report:
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
        if result.skipped:
            with st.expander(f"Report lines skipped: totals and headings ({len(result.skipped)})"):
                st.dataframe(
                    pd.DataFrame([{"Row in file": r["row"], "Why": ji.safe_cell(r["reason"]),
                                   "Original row": ji.safe_cell(" | ".join(r["cells"]))} for r in result.skipped]),
                    hide_index=True, width="stretch",
                )
        return result


    def money_cell(amount) -> str:
        return "—" if amount is None else jp.format_money(amount)


    def show_profit(results: list[ji.IntakeResult], pending: list[str]) -> bool:
        """Profit by job and customer, once every file is dealt with and there is exactly one sales
        file and one costs file. Returns True when results were shown."""
        if pending:
            # A file still waiting for an answer (or unreadable) could hold sales or costs.
            st.info("Your results appear here once every file below is read: answer the questions for "
                    + ", ".join(ui.md_text(n) for n in pending) + ", or remove it.")
            return False
        invoices = [r for r in results if r.kind == "invoices"]
        costs = [r for r in results if r.kind == "costs"]
        if len(invoices) != 1 or len(costs) != 1:
            st.info("Profit by job needs exactly one sales file and one costs file, each fully read below. "
                    "Answer any questions below, or upload one of each.")
            return False
        sources = (SOURCE_KEYS[id(invoices[0])], SOURCE_KEYS[id(costs[0])])
        report = jp.job_profit(invoices[0], which_job(invoices[0], costs[0], sources))
        if not report.available:
            for reason in report.reasons:
                st.info(ui.md_text(reason))
            return False
        ui.results(report, mi.summarize(report), mi.attention(report), mi.period_text(report))
        for note in report.notes:
            # The overhead note is already shown as the "after overhead" line; the rest stay visible here.
            if "overhead or fee line" not in note:
                st.caption(ui.md_text(note))
        with st.expander("All the details: every job, customer and how the figures are worked out"):
            _details(report)
        return True


    def which_job(invoices: ji.IntakeResult, costs: ji.IntakeResult, sources: tuple[str, str]) -> ji.IntakeResult:
        """Ask the owner which job each cost without a job number was for, and apply the answers.

        MargenX never guesses: every cost starts as "Not sure yet" and stays unlinked until the owner
        picks. Jobs with sales or costs around the cost's date are listed first, only to save time.
        """
        if "job_id" not in invoices.mapped_fields:
            return costs  # no job numbers on the sales either: there are no jobs to choose from
        rows = jm.unmatched(costs)
        job_list = jm.jobs(invoices, costs)
        if not rows or not job_list:
            # Nothing to ask, but a costs file with no job column still gets one (every line blank), so it's
            # read like any other file instead of refused.
            return jm.apply(costs, {}, job_list)
        # Every job starts with "Job ", so no job number can read the same as MargenX's own choices.
        labels = {}
        for job in job_list:
            about = " · ".join(x for x in (job.description, ", ".join(job.customers)) if x)
            labels[job.job_id] = f"Job {job.job_id} · {about}" if about else f"Job {job.job_id}"
        # Answers are keyed to both files themselves (name, exact bytes, every reading choice) and to what was
        # read from them, so any change to either file, even one the reader drops (a report title, the file's
        # name), asks again instead of applying old answers to other records.
        asked = hashlib.sha256(repr((sources, [(r.kind, r.headers, r.mapped_fields, r.total_rows, r.accepted, r.rejected,
                                                r.skipped) for r in (invoices, costs)])).encode("utf-8")).hexdigest()[:32]
        choices: dict[int, tuple[str, str]] = {}
        answered = sum(1 for r in rows if st.session_state.get(f"match-{asked}-{r['row']}", jm.NOT_SURE) != jm.NOT_SURE)
        with st.expander(f"Which job was each cost for? {answered} of {len(rows)} answered", expanded=answered < len(rows)):
            st.caption(f"These {len(rows)} costs don't say which job they were for. If you know, pick the job; if "
                       "you're not sure, leave it. MargenX never guesses: a cost you don't match stays out of every "
                       "job's figure, and those jobs show \"Needs a check\".")
            for line in rows:
                near = jm.nearby(line, job_list)
                others = [j.job_id for j in job_list if j.job_id not in near]
                options = [jm.NOT_SURE, *map(jm.job, near), jm.NOT_A_JOB, *map(jm.job, others)]
                what = " · ".join(x for x in (line.get("vendor"), line.get("cost_type"), line.get("memo")) if x)
                day = date.fromisoformat(line["date"])
                names = {jm.NOT_SURE: "Not sure yet", jm.NOT_A_JOB: "Not for a job (a general business cost)",
                         **{jm.job(j): labels[j] + (" · around that date" if j in near else "") for j in labels}}
                choices[line["row"]] = st.selectbox(
                    ui.md_text(f"{day:%b} {day.day}, {day.year} · {what} · {jp.format_money(line['amount'])} "
                               f"(row {line['row']})"),
                    options, format_func=lambda o, n=names: ui.md_text(n[o]), key=f"match-{asked}-{line['row']}")
        return jm.apply(costs, choices, job_list)


    def _details(report: jp.ProfitReport) -> None:
        st.caption(report.basis)
        st.caption(f"Imported sales lines are dated {report.invoice_dates[0]} to {report.invoice_dates[1]}; "
                   f"imported cost lines {report.cost_dates[0]} to {report.cost_dates[1]}. "
                   "Lines that couldn't be imported are listed with each file below, under Your files.")
        st.caption("'Complete' means these files have the job's sales, labor and materials or outsourced work, every "
                   "cost typed and nothing failed to import. MargenX can't tell whether the files cover every cost "
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
    ui.section("Your files")
    for file_position, (file_name, file_data) in enumerate(files):
        digest = hashlib.sha256(file_data).digest()
        result = show_file(file_position, file_name, file_data, seen_files.get(digest))
        if result is None:
            pending.append(file_name)
        elif result != EXCLUDED:
            results.append(result)
        seen_files.setdefault(digest, file_name)
    with results_area:
        shown = show_profit(results, pending)
    if slots is not None:
        with slots.container():
            ui.file_slots({r.kind for r in results})
    with nav.container():
        ui.steps(3 if shown else 2)
