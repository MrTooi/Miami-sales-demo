"""LEDGER — resilient prototype financial intelligence dashboard."""
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

st.set_page_config(
    page_title="LEDGER | Profit Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    html,body,[data-testid="stAppViewContainer"],[data-testid="stHeader"]{background:#111416!important;color:#F4F3EC!important}
    [data-testid="stAppViewContainer"] *{font-family:'DM Sans',sans-serif}
    .block-container{max-width:1120px;padding-top:2rem;padding-bottom:4rem}
    h1,h2,h3{font-family:'Manrope',sans-serif!important;color:#F4F3EC!important;letter-spacing:-.035em!important}
    [data-testid="stMetric"]{background:#1C2221;border:1px solid #303936;border-radius:16px;padding:18px}
    [data-testid="stMetricLabel"]{color:#ADB5AE!important}
    [data-testid="stMetricValue"]{color:#F4F3EC!important}
    div.stDownloadButton>button{background:#D5F478!important;color:#182119!important;border:0;border-radius:12px}
    .eyebrow{color:#D5F478;font-size:.75rem;letter-spacing:.15em;font-weight:800}
    .subtle{color:#A3AAA5;font-size:.9rem}
    @media(max-width:640px){.block-container{padding:1.2rem .85rem 3rem}[data-testid="stMetric"]{padding:12px}[data-testid="stMetricValue"]{font-size:1.25rem}}
    </style>
    """,
    unsafe_allow_html=True,
)


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

st.markdown('<div class="eyebrow">LEDGER / PROFIT INTELLIGENCE</div>', unsafe_allow_html=True)
st.title("Know where the money goes.")
st.markdown(
    '<p class="subtle">Understand profitability, investigate costs, and review evidence behind each finding.</p>',
    unsafe_allow_html=True,
)
st.warning("PROTOTYPE · Not audited, not production-ready. Use fictional or anonymized data only.")

with st.expander("Import CSV or Excel records", expanded=False):
    sales_file = st.file_uploader(
        "Sales file",
        type=["csv", "xlsx"],
        key="sales",
        help="Required: id (or order_id), date, service, amount. Negative amounts are refunds.",
    )
    sales_source = st.selectbox(
        "Sales file source",
        ["manual_upload", "square_export", "quickbooks_export", "other_export"],
        disabled=sales_file is None,
        help="Labels the source for duplicate/conflict tracking. This is not a live integration.",
    )
    expenses_file = st.file_uploader(
        "Expense file",
        type=["csv", "xlsx"],
        key="expenses",
        help="Required: id, date, category (direct or operating), amount.",
    )
    st.caption("Both files must cover the same accounting period for meaningful profit results. Missing expenses are never estimated.")
    st.caption("For safety, this public prototype must not receive confidential financial records.")

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
    st.caption("● FICTIONAL DEMO DATA · Miami printing business")
    ledger_source = "fictional_demo"
elif sales_file is not None and expenses_file is None:
    st.info("Sales uploaded without expenses. Profit will be unavailable.")
    ledger_source = sales_source
elif sales_file is None and expenses_file is not None:
    st.error("Upload matching sales data alongside expense data; demo sales cannot be mixed with uploaded expenses.")
    st.stop()
else:
    ledger_source = sales_source

# Integrity storage is intentionally non-fatal in the public cloud demo.
# Financial analysis must remain viewable even if ephemeral SQLite storage is unavailable.
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

min_date = sales["date"].min().date()
max_date = sales["date"].max().date()
selected = st.date_input("Reporting period", (min_date, max_date), min_value=min_date, max_value=max_date)
if not isinstance(selected, tuple) or len(selected) != 2:
    st.info("Select both start and end dates.")
    st.stop()
start, end = selected
s = sales[sales["date"].dt.date.between(start, end)].copy()
e = expenses[expenses["date"].dt.date.between(start, end)].copy() if expenses is not None else None
if s.empty:
    st.info("No sales transactions in this reporting period.")
    st.stop()
if e is not None and e.empty:
    st.warning("No expenses were recorded in the selected period. Zero recorded expenses does not prove zero actual costs.")

expenses_complete = (
    sales_file is None and expenses_file is None
) or (
    e is not None
    and not e.empty
    and st.checkbox("I confirm the expense file includes all direct and operating costs for this reporting period.")
)
result = analyze(s, e, expenses_complete=expenses_complete)

tabs = st.tabs(["Overview", "Cost observations", "Transactions", "Import integrity"])

with tabs[0]:
    a, b, c, d = st.columns(4)
    a.metric("NET REVENUE", dollars(result["net_revenue"]))
    b.metric("GROSS PROFIT", dollars(result["gross_profit"]) if result["profit_available"] else "Unavailable")
    c.metric("OPERATING PROFIT", dollars(result["operating_profit"]) if result["profit_available"] else "Unavailable")
    d.metric("REFUNDS", dollars(result["refund_total"]))

    if not result["profit_available"]:
        st.info(
            "Profit unavailable: "
            + result.get("profit_unavailable_reason", "Expense coverage unverified")
            + ". Revenue is not profit."
        )
    else:
        st.caption("Gross profit = net revenue − direct costs. Operating profit = gross profit − operating expenses. Completeness is self-reported, not independently audited.")
        if result["operating_margin_pct"] is not None:
            st.metric("OPERATING MARGIN", f'{result["operating_margin_pct"]:.1f}%')

    st.subheader("Revenue over time")
    monthly = s.assign(month=s["date"].dt.to_period("M").dt.to_timestamp())
    monthly = monthly.groupby("month", as_index=False)["amount"].agg(
        lambda amounts: sum(amounts, Decimal("0.00"))
    )
    monthly["amount_exact"] = monthly["amount"].map(lambda value: f"${value:,.2f}")
    monthly["amount"] = monthly["amount"].map(float)
    chart = (
        alt.Chart(monthly)
        .mark_line(color="#D5F478", strokeWidth=3, point=True)
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y", labelAngle=0, labelColor="#AAB2AB")),
            y=alt.Y("amount:Q", title=None, axis=alt.Axis(format="$,.0f", labelColor="#AAB2AB", gridColor="#303936")),
            tooltip=[
                alt.Tooltip("month:T", format="%b %Y"),
                alt.Tooltip("amount_exact:N", title="Exact net revenue"),
            ],
        )
        .properties(height=250)
        .configure_view(stroke=None)
        .configure(background="#111416")
    )
    st.altair_chart(chart, width="stretch")

    revenue_by_month = monthly.copy()
    revenue_by_month["Month"] = revenue_by_month["month"].dt.strftime("%B %Y")
    revenue_by_month["Net revenue (USD)"] = revenue_by_month["amount_exact"]
    st.markdown("**Monthly net revenue (exact amounts)**")
    st.dataframe(revenue_by_month[["Month", "Net revenue (USD)"]], hide_index=True, width="stretch")
    st.caption("Net revenue reflects sales minus refunds, not cash held in the bank.")

    if e is not None:
        st.subheader("Recorded costs")
        direct = sum((value for value in e.loc[e["category"] == "direct", "amount"]), Decimal("0.00"))
        operating = sum((value for value in e.loc[e["category"] == "operating", "amount"]), Decimal("0.00"))
        st.dataframe(
            pd.DataFrame(
                [
                    {"Category": "Recorded direct costs", "Amount": dollars(direct)},
                    {"Category": "Recorded operating expenses", "Amount": dollars(operating)},
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        if not result["profit_available"]:
            st.caption("These are recorded costs only. Expense completeness has not been confirmed, so profit remains unavailable.")

with tabs[1]:
    st.subheader("What the records show")
    st.caption("Observed totals are not proof of waste or guaranteed savings. More detailed job and supplier records are needed for true profit-leak diagnosis.")
    items = findings(s, e)
    if not items:
        st.info("No cost or refund observations in this period.")
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{html.escape(item['title'])}**")
            st.metric("Recorded amount", dollars(item["amount"]))
            st.write(item["detail"])
            st.caption("Calculation: " + item["basis"])

with tabs[2]:
    st.subheader("Sales")
    st.dataframe(s, width="stretch", hide_index=True)
    if e is not None:
        st.subheader("Expenses")
        st.dataframe(e, width="stretch", hide_index=True)
    st.download_button("Download filtered sales", s.to_csv(index=False), "ledger_sales.csv", "text/csv")
    if e is not None:
        st.download_button("Download filtered expenses", e.to_csv(index=False), "ledger_expenses.csv", "text/csv")

with tabs[3]:
    st.subheader("Import integrity")
    st.caption("Prototype-only storage. It can disappear when the app restarts and is not a production database.")

    if sales_file is None:
        st.info("The fictional demo does not write to persistent storage. Upload anonymized test data to exercise duplicate and reconciliation controls.")
    elif not integrity_available:
        st.warning("The financial dashboard is available, but prototype persistence is temporarily unavailable in this cloud session.")
        if integrity_error:
            st.caption("Storage detail: " + integrity_error)
    else:
        if sales_integrity_batch.get("replayed"):
            st.info("Current sales batch was already imported. No additional stored transactions were created.")
        else:
            st.success(
                f"Current sales import: {sales_integrity_batch['inserted_count']} new, "
                f"{sales_integrity_batch['duplicate_count']} duplicates ignored, "
                f"{sales_integrity_batch['conflict_count']} conflicts requiring review."
            )

        try:
            with LedgerStore(workspace_db) as store:
                stored_transactions = store.list_transactions(workspace_id)
                unresolved_conflicts = store.list_conflicts(workspace_id)
                reconciliation = store.reconciliation_status(workspace_id)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("STORED RECORDS", len(stored_transactions))
            m2.metric("UNRESOLVED CONFLICTS", len(unresolved_conflicts))
            m3.metric("CONFIRMED TRANSFERS", reconciliation["confirmed_links"])
            m4.metric("UNMATCHED TRANSFERS", reconciliation["unmatched_payouts"] + reconciliation["unmatched_bank_deposits"])

            if stored_transactions:
                summary = pd.DataFrame(stored_transactions)
                summary = summary.groupby(["source", "kind"], as_index=False).size().rename(columns={"size": "records"})
                st.markdown("**Stored records by source and type**")
                st.dataframe(summary, hide_index=True, width="stretch")

            st.divider()
            st.subheader("Payout / bank deposit reconciliation")
            transfer_source = st.text_input("Transfer file source", value="square", key="transfer_source")
            transfer_file = st.file_uploader("Transfer file", type=["csv", "xlsx"], key="transfer_file")
            if transfer_file is not None:
                try:
                    records = normalize_transfer_frame(read_file(transfer_file), workspace_id, transfer_source)
                    batch_id = deterministic_batch_id(records, f"transfer-{transfer_source}")
                    with LedgerStore(workspace_db) as store:
                        transfer_batch = store.ingest(records, batch_id=batch_id)
                    st.success(
                        f"Transfer import: {transfer_batch['inserted_count']} new, "
                        f"{transfer_batch['duplicate_count']} duplicates ignored, "
                        f"{transfer_batch['conflict_count']} conflicts."
                    )
                except Exception as exc:
                    st.error(f"Transfer import rejected: {exc}")

            with LedgerStore(workspace_db) as store:
                matches = store.find_reconciliation_candidates(workspace_id)

            if matches["ambiguous_groups"]:
                st.warning("Some equal-amount transfer groups are ambiguous. LEDGER will not guess which records match.")
                st.dataframe(pd.DataFrame(matches["ambiguous_groups"]), hide_index=True, width="stretch")
            if matches["candidates"]:
                st.markdown("**Suggested exact transfer matches**")
                candidate_table = pd.DataFrame(matches["candidates"])
                candidate_table["amount"] = candidate_table["amount"].map(dollars)
                st.dataframe(candidate_table, hide_index=True, width="stretch")
                st.caption("Exact amount matches are suggestions only; production reconciliation will require explicit review and stronger source evidence.")
            elif reconciliation["recorded_payouts"] or reconciliation["recorded_bank_deposits"]:
                st.info("No unambiguous exact transfer matches are currently available.")
        except Exception as exc:
            st.warning("Integrity workspace became unavailable, but the financial dashboard remains usable.")
            st.caption("Storage detail: " + str(exc))

st.caption("LEDGER · DEVELOPMENT BUILD · Not suitable for confidential client information.")
