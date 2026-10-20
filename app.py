"""LEDGER — business-grade financial intelligence prototype."""
import html
import os
import tempfile
import uuid
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from app_ledger import deterministic_batch_id, normalize_transfer_frame, sales_to_integrity_records
from data_pipeline import analyze, findings, normalize
from ledger_store import LedgerStore
from pilot_safety import MADE_UP_TEXT, PILOT_ENV
from ui_theme import apply_theme, confidence_card, render_footer, render_header, section_header

st.set_page_config(
    page_title="LEDGER | Financial Intelligence",
    page_icon="▰",
    layout="wide",
    initial_sidebar_state="collapsed",
)
apply_theme()

# The older Ledger demo has no pilot consent and keeps imports in a SQLite file, so it is
# switched off entirely whenever pilot mode is set (pilot sessions use marginx_pilot.py).
if os.environ.get(PILOT_ENV, "").strip() == "1":
    st.error("The Ledger demo is turned off during pilot sessions. Start MarginX with marginx_pilot.py "
             "(see docs/PILOT_VISIT_CHECKLIST.md).")
    st.stop()


def dollars(value):
    return f"${Decimal(str(value)):,.2f}"


def read_file(upload):
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(upload, dtype=str, keep_default_na=False)
    return pd.read_excel(upload, dtype=str, keep_default_na=False)


@st.cache_data
def demo_sales():
    return pd.read_csv("sample_sales.csv", dtype=str)


@st.cache_data
def demo_expenses():
    return pd.read_csv("sample_expenses.csv", dtype=str)


if "ledger_workspace_id" not in st.session_state:
    st.session_state["ledger_workspace_id"] = uuid.uuid4().hex
workspace_id = st.session_state["ledger_workspace_id"]
workspace_db = os.path.join(tempfile.gettempdir(), f"ledger-{workspace_id}.db")

render_header()

with st.expander("Data sources & imports", expanded=False):
    # Demo only: own files are accepted (and kept in the demo's SQLite file) only once they are
    # confirmed as made-up, and the upload boxes don't appear before that.
    made_up = st.checkbox(MADE_UP_TEXT, key="legacy_made_up")
    source_col, sales_col, expense_col = st.columns([0.9, 1.15, 1.15])
    with source_col:
        sales_source = st.selectbox(
            "Sales source",
            ["manual_upload", "square_export", "quickbooks_export", "other_export"],
            help="Used for duplicate and conflict tracking. This is not a live connection yet.",
        )
    sales_file = expenses_file = None
    if made_up:
        with sales_col:
            sales_file = st.file_uploader(
                "Sales file",
                type=["csv", "xlsx"],
                key="sales",
                help="Required: id (or order_id), date, service, amount. Negative amounts are refunds.",
            )
        with expense_col:
            expenses_file = st.file_uploader(
                "Expense file",
                type=["csv", "xlsx"],
                key="expenses",
                help="Required: id, date, category (direct or operating), amount.",
            )
    st.caption("Sales and expense files should cover the same accounting period. Missing costs are never estimated.")

try:
    sales = normalize(read_file(sales_file) if sales_file else demo_sales(), "sales")
    if expenses_file:
        expenses = normalize(read_file(expenses_file), "expenses")
    elif sales_file is None:
        expenses = normalize(demo_expenses(), "expenses")
    else:
        expenses = None
except Exception as exc:
    st.error(f"Import rejected: {exc}")
    st.stop()

if sales_file is None and expenses_file is None:
    data_mode = "demo"
    ledger_source = "fictional_demo"
elif sales_file is not None and expenses_file is None:
    data_mode = "incomplete"
    ledger_source = sales_source
    st.info("Sales are loaded, but no expense file is present. Profit will remain unavailable.")
elif sales_file is None and expenses_file is not None:
    st.error("Upload matching sales data alongside expense data; demo sales cannot be mixed with uploaded expenses.")
    st.stop()
else:
    data_mode = "uploaded"
    ledger_source = sales_source

# Prototype integrity storage is deliberately non-fatal.
integrity_available = False
sales_integrity_batch = None
integrity_error = None
if sales_file is not None:
    try:
        integrity_records = sales_to_integrity_records(sales, workspace_id, ledger_source)
        integrity_batch_id = deterministic_batch_id(integrity_records, "sales")
        with LedgerStore(workspace_db) as store:
            sales_integrity_batch = store.ingest(integrity_records, batch_id=integrity_batch_id)
        integrity_available = True
    except Exception as exc:
        integrity_error = str(exc)

date_col, status_col = st.columns([1.45, 1])
min_date = sales["date"].min().date()
max_date = sales["date"].max().date()
with date_col:
    selected = st.date_input(
        "Reporting period",
        (min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
if not isinstance(selected, tuple) or len(selected) != 2:
    st.info("Select both a start and end date.")
    st.stop()

start, end = selected
s = sales[sales["date"].dt.date.between(start, end)].copy()
e = expenses[expenses["date"].dt.date.between(start, end)].copy() if expenses is not None else None

if s.empty:
    st.info("No sales transactions exist in this reporting period.")
    st.stop()
if e is not None and e.empty:
    st.warning("No expenses were recorded in this period. Zero recorded expenses does not prove zero actual costs.")

if data_mode == "demo":
    expenses_complete = True
elif e is not None and not e.empty:
    with status_col:
        expenses_complete = st.checkbox(
            "Expense coverage is complete",
            help="Confirm only if the uploaded file contains all direct and operating costs for this reporting period.",
        )
else:
    expenses_complete = False

result = analyze(s, e, expenses_complete=expenses_complete)

if data_mode == "demo":
    confidence_label = "DEMO SAMPLE"
    confidence_tone = "dim"
    confidence_detail = "Fictional data with complete sample sales and expenses."
elif result["profit_available"]:
    confidence_label = "PROVISIONAL"
    confidence_tone = "good"
    confidence_detail = "Expense completeness is uploader-attested and has not been independently audited."
else:
    confidence_label = "INCOMPLETE"
    confidence_tone = "warn"
    confidence_detail = result.get("profit_unavailable_reason", "Expense coverage is not confirmed.")

with status_col:
    confidence_card(confidence_label, confidence_detail, confidence_tone)

tabs = st.tabs(["Overview", "Costs", "Transactions", "Data health"])

with tabs[0]:
    section_header("Financial performance", f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}")
    a, b, c, d = st.columns(4)
    a.metric("NET REVENUE", dollars(result["net_revenue"]))
    b.metric("GROSS PROFIT", dollars(result["gross_profit"]) if result["profit_available"] else "Unavailable")
    c.metric("OPERATING PROFIT", dollars(result["operating_profit"]) if result["profit_available"] else "Unavailable")
    d.metric("REFUNDS", dollars(result["refund_total"]))

    if result["profit_available"]:
        margin = result.get("operating_margin_pct")
        if margin is not None:
            st.caption(f"Operating margin: **{margin:.1f}%** · Profit figures use the expense coverage shown above.")
    else:
        st.info("Profit is intentionally withheld because expense coverage is not complete. Revenue should never be presented as profit.")

    st.divider()
    section_header("Revenue trend", "Net sales activity by month")
    monthly = s.assign(month=s["date"].dt.to_period("M").dt.to_timestamp())
    monthly = monthly.groupby("month", as_index=False)["amount"].agg(
        lambda amounts: sum(amounts, Decimal("0.00"))
    )
    monthly["amount_exact"] = monthly["amount"].map(lambda value: f"${value:,.2f}")
    monthly["amount"] = monthly["amount"].map(float)

    chart = (
        alt.Chart(monthly)
        .mark_area(color="#C8F36B", opacity=0.15, line={"color": "#C8F36B", "strokeWidth": 2.5})
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b", labelAngle=0, labelColor="#8F9A93", tickColor="#29322D")),
            y=alt.Y("amount:Q", title=None, axis=alt.Axis(format="$,.0f", labelColor="#8F9A93", gridColor="#202722", tickCount=5)),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%B %Y"),
                alt.Tooltip("amount_exact:N", title="Net revenue"),
            ],
        )
        .properties(height=290)
        .configure_view(stroke=None)
        .configure(background="#0B0F0D")
    )
    st.altair_chart(chart, width="stretch")

    with st.expander("View exact monthly totals"):
        revenue_by_month = monthly.copy()
        revenue_by_month["Month"] = revenue_by_month["month"].dt.strftime("%B %Y")
        revenue_by_month["Net revenue"] = revenue_by_month["amount_exact"]
        st.dataframe(revenue_by_month[["Month", "Net revenue"]], hide_index=True, width="stretch")
        st.caption("Net revenue reflects sales minus refunds. It is not bank cash balance.")

    st.divider()
    section_header("Operating snapshot", "What the selected records contain")
    s1, s2, s3 = st.columns(3)
    s1.metric("TRANSACTIONS", len(s))
    if e is not None:
        direct_snapshot = result.get(
            "direct_costs",
            sum((value for value in e.loc[e["category"] == "direct", "amount"]), Decimal("0.00")),
        )
        operating_snapshot = result.get(
            "operating_expenses",
            sum((value for value in e.loc[e["category"] == "operating", "amount"]), Decimal("0.00")),
        )
        s2.metric("RECORDED DIRECT COSTS", dollars(direct_snapshot))
        s3.metric("RECORDED OPERATING COSTS", dollars(operating_snapshot))
    else:
        s2.metric("RECORDED DIRECT COSTS", "Unavailable")
        s3.metric("RECORDED OPERATING COSTS", "Unavailable")

with tabs[1]:
    section_header(
        "Cost intelligence",
        "Recorded cost activity and evidence-based observations — no estimated savings claims.",
    )
    if e is not None:
        direct = result.get(
            "direct_costs",
            sum((value for value in e.loc[e["category"] == "direct", "amount"]), Decimal("0.00")),
        )
        operating = result.get(
            "operating_expenses",
            sum((value for value in e.loc[e["category"] == "operating", "amount"]), Decimal("0.00")),
        )
        c1, c2 = st.columns(2)
        c1.metric("DIRECT COSTS", dollars(direct))
        c2.metric("OPERATING EXPENSES", dollars(operating))
    else:
        st.info("Upload expense records to unlock cost analysis.")

    items = findings(s, e)
    if not items:
        st.info("No cost or refund observations are present in this period.")
    else:
        st.markdown("##### Record observations")
        for item in items:
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    st.markdown(f"**{html.escape(item['title'])}**")
                    st.caption(item["detail"])
                    st.caption("Basis: " + item["basis"])
                with right:
                    st.metric("Recorded", dollars(item["amount"]))

with tabs[2]:
    section_header("Transaction records", "The underlying records used in this reporting period.")
    sales_tab, expense_tab = st.tabs(["Sales", "Expenses"])
    with sales_tab:
        st.dataframe(s, width="stretch", hide_index=True)
        st.download_button("Download sales CSV", s.to_csv(index=False), "ledger_sales.csv", "text/csv")
    with expense_tab:
        if e is None:
            st.info("No expense file is loaded.")
        else:
            st.dataframe(e, width="stretch", hide_index=True)
            st.download_button("Download expenses CSV", e.to_csv(index=False), "ledger_expenses.csv", "text/csv")

with tabs[3]:
    section_header("Data health", "Source quality, duplicate protection, conflicts, and transfer reconciliation.")
    confidence_card(confidence_label, confidence_detail, confidence_tone, heading="Current financial state")

    if sales_file is None:
        st.info(
            "This fictional demo does not write sample records into the prototype ledger. "
            "Upload anonymized test data to exercise duplicate detection and reconciliation."
        )
    elif not integrity_available:
        st.warning("Financial analysis is available, but the prototype integrity workspace is unavailable in this cloud session.")
        if integrity_error:
            st.caption("Technical detail: " + integrity_error)
    else:
        if sales_integrity_batch.get("replayed"):
            st.success("This sales batch was already seen. No duplicate stored transactions were created.")
        else:
            inserted = sales_integrity_batch["inserted_count"]
            duplicates = sales_integrity_batch["duplicate_count"]
            conflicts = sales_integrity_batch["conflict_count"]
            st.success(
                f"Import processed: {inserted} new · {duplicates} duplicate"
                f"{'s' if duplicates != 1 else ''} ignored · {conflicts} conflict"
                f"{'s' if conflicts != 1 else ''} flagged"
            )

        try:
            with LedgerStore(workspace_db) as store:
                stored_transactions = store.list_transactions(workspace_id)
                unresolved_conflicts = store.list_conflicts(workspace_id)
                reconciliation = store.reconciliation_status(workspace_id)

            h1, h2, h3, h4 = st.columns(4)
            h1.metric("STORED RECORDS", len(stored_transactions))
            h2.metric("OPEN CONFLICTS", len(unresolved_conflicts))
            h3.metric("MATCHED TRANSFERS", reconciliation["confirmed_links"])
            h4.metric(
                "UNMATCHED TRANSFERS",
                reconciliation["unmatched_payouts"] + reconciliation["unmatched_bank_deposits"],
            )

            if stored_transactions:
                with st.expander("Stored records by source"):
                    summary = pd.DataFrame(stored_transactions)
                    summary = (
                        summary.groupby(["source", "kind"], as_index=False)
                        .size()
                        .rename(columns={"size": "records"})
                    )
                    st.dataframe(summary, hide_index=True, width="stretch")

            if unresolved_conflicts:
                st.warning(
                    f"{len(unresolved_conflicts)} transaction conflict"
                    f"{'s' if len(unresolved_conflicts) != 1 else ''} require review before history can be treated as reconciled."
                )
                with st.expander("Review conflict details"):
                    st.dataframe(pd.DataFrame(unresolved_conflicts), hide_index=True, width="stretch")

            st.divider()
            with st.expander("Reconcile payouts & bank deposits", expanded=False):
                st.caption(
                    "Upload one transfer source at a time. Required: external_id (or id), kind, amount. "
                    "kind must be payout or bank_deposit."
                )
                transfer_source = st.text_input(
                    "Transfer source",
                    value="square",
                    key="transfer_source",
                    help="Use a stable source name such as square, chase, or bank_of_america.",
                )
                transfer_file = (st.file_uploader("Transfer file", type=["csv", "xlsx"], key="transfer_file")
                                 if made_up else None)

                if transfer_file is not None:
                    try:
                        records = normalize_transfer_frame(read_file(transfer_file), workspace_id, transfer_source)
                        batch_id = deterministic_batch_id(records, f"transfer-{transfer_source}")
                        with LedgerStore(workspace_db) as store:
                            transfer_batch = store.ingest(records, batch_id=batch_id)
                            reconciliation = store.reconciliation_status(workspace_id)
                        st.success(
                            f"Transfer import: {transfer_batch['inserted_count']} new · "
                            f"{transfer_batch['duplicate_count']} duplicates ignored · "
                            f"{transfer_batch['conflict_count']} conflicts"
                        )
                    except Exception as exc:
                        st.error(f"Transfer import rejected: {exc}")

                with LedgerStore(workspace_db) as store:
                    matches = store.find_reconciliation_candidates(workspace_id)

                if matches["ambiguous_groups"]:
                    st.warning("Some equal-amount transfers are ambiguous. LEDGER will not guess which records match.")
                    st.dataframe(pd.DataFrame(matches["ambiguous_groups"]), hide_index=True, width="stretch")

                if matches["candidates"]:
                    st.markdown("**Suggested exact matches**")
                    candidate_table = pd.DataFrame(matches["candidates"])
                    candidate_table["amount"] = candidate_table["amount"].map(dollars)
                    st.dataframe(candidate_table, hide_index=True, width="stretch")
                    st.caption(
                        "Exact-amount matches are suggestions only. Production reconciliation will require explicit review and stronger source evidence."
                    )
                elif reconciliation["recorded_payouts"] or reconciliation["recorded_bank_deposits"]:
                    st.info("No unambiguous exact transfer matches are currently available.")

            with st.expander("Prototype workspace controls"):
                st.caption(
                    "This temporary SQLite workspace can disappear when the demo restarts. "
                    "Production will use managed persistent storage."
                )
                if st.button("Reset prototype workspace"):
                    for suffix in ("", "-wal", "-shm"):
                        candidate = workspace_db + suffix
                        if os.path.exists(candidate):
                            os.remove(candidate)
                    st.session_state["ledger_workspace_id"] = uuid.uuid4().hex
                    st.rerun()

        except Exception as exc:
            st.warning("The integrity workspace became unavailable, but financial analysis remains usable.")
            st.caption("Technical detail: " + str(exc))

render_footer()
