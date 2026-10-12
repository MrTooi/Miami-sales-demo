"""Ledger — prototype financial intelligence dashboard. Synthetic data only."""
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

st.set_page_config(page_title="Ledger | Profit Intelligence",page_icon="📊",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>
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
</style>""",unsafe_allow_html=True)


def dollars(v):
    return f"${Decimal(str(v)):,.2f}"


def read_file(upload):
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(upload,dtype=str,keep_default_na=False)
    return pd.read_excel(upload,dtype=str,keep_default_na=False)


def reset_workspace(path):
    for suffix in ("", "-wal", "-shm"):
        candidate=path+suffix
        if os.path.exists(candidate):
            os.remove(candidate)


@st.cache_data
def demo_sales():
    return pd.read_csv("sample_sales.csv",dtype=str)


@st.cache_data
def demo_expenses():
    return pd.read_csv("sample_expenses.csv",dtype=str)


if "ledger_workspace_id" not in st.session_state:
    st.session_state["ledger_workspace_id"]=uuid.uuid4().hex
workspace_id=st.session_state["ledger_workspace_id"]
workspace_db=os.path.join(tempfile.gettempdir(),f"ledger-{workspace_id}.db")

st.markdown('<div class="eyebrow">LEDGER / PROFIT INTELLIGENCE</div>',unsafe_allow_html=True)
st.title("Know where the money goes.")
st.markdown('<p class="subtle">Understand profitability, investigate costs, and review evidence behind each finding.</p>',unsafe_allow_html=True)
st.warning("PROTOTYPE · Not audited, not production-ready. Use fictional or anonymized data only.")

with st.expander("Import CSV or Excel records",expanded=False):
    sales_file=st.file_uploader("Sales file",type=["csv","xlsx"],key="sales",help="Required: id (or order_id), date, service, amount. Negative amounts are refunds.")
    sales_source=st.selectbox(
        "Sales file source",
        ["manual_upload","square_export","quickbooks_export","other_export"],
        disabled=sales_file is None,
        help="This labels the source for duplicate/conflict tracking. It is not a live integration.",
    )
    expenses_file=st.file_uploader("Expense file",type=["csv","xlsx"],key="expenses",help="Required: id, date, category (direct or operating), amount.")
    st.caption("Both files must cover the same accounting period for meaningful profit results. Missing expenses are never estimated.")
    st.caption("For safety, this public prototype must not receive confidential financial records.")

try:
    sales=normalize(read_file(sales_file) if sales_file else demo_sales(),"sales")
    expenses=normalize(read_file(expenses_file),"expenses") if expenses_file else (normalize(demo_expenses(),"expenses") if sales_file is None else None)
except Exception as exc:
    st.error(f"Import rejected: {exc}")
    st.stop()

if sales_file is None and expenses_file is None:
    st.caption("● FICTIONAL DEMO DATA · Miami printing business")
    ledger_source="fictional_demo"
elif sales_file is not None and expenses_file is None:
    st.info("Sales uploaded without expenses. Profit will be unavailable.")
    ledger_source=sales_source
elif sales_file is None and expenses_file is not None:
    st.error("Upload matching sales data alongside expense data; demo sales cannot be mixed with uploaded expenses.")
    st.stop()
else:
    ledger_source=sales_source

try:
    integrity_records=sales_to_integrity_records(sales,workspace_id,ledger_source)
    integrity_batch_id=deterministic_batch_id(integrity_records,"sales")
    with LedgerStore(workspace_db) as store:
        sales_integrity_batch=store.ingest(integrity_records,batch_id=integrity_batch_id)
except Exception as exc:
    st.error(f"Persistent integrity check failed: {exc}")
    st.stop()

if sales_integrity_batch["conflict_count"]:
    st.warning("This import contains transaction IDs that conflict with records already stored in this prototype workspace. Review them in Import integrity before treating history as reconciled.")

min_date=sales["date"].min().date()
max_date=sales["date"].max().date()
selected=st.date_input("Reporting period",(min_date,max_date),min_value=min_date,max_value=max_date)
if not isinstance(selected,tuple) or len(selected)!=2:
    st.info("Select both start and end dates.")
    st.stop()
start,end=selected
s=sales[sales["date"].dt.date.between(start,end)].copy()
e=expenses[expenses["date"].dt.date.between(start,end)].copy() if expenses is not None else None
if s.empty:
    st.info("No sales transactions in this reporting period.")
    st.stop()
if e is not None and e.empty:
    st.warning("No expenses were recorded in the selected period. Zero recorded expenses does not prove zero actual costs.")
expenses_complete = (sales_file is None and expenses_file is None) or (e is not None and not e.empty and st.checkbox('I confirm the expense file includes all direct and operating costs for this reporting period.'))
result=analyze(s,e,expenses_complete=expenses_complete)

tabs=st.tabs(["Overview","Cost observations","Transactions","Import integrity"])
with tabs[0]:
    a,b,c,d=st.columns(4)
    a.metric("NET REVENUE",dollars(result["net_revenue"]))
    b.metric("GROSS PROFIT",dollars(result["gross_profit"]) if result["profit_available"] else "Unavailable")
    c.metric("OPERATING PROFIT",dollars(result["operating_profit"]) if result["profit_available"] else "Unavailable")
    d.metric("REFUNDS",dollars(result["refund_total"]))
    if not result["profit_available"]:
        st.info("Profit unavailable: " + result.get("profit_unavailable_reason", "Expense coverage unverified") + ". Revenue is not profit.")
    else:
        st.caption("Gross profit = net revenue − direct costs. Operating profit = gross profit − operating expenses. Completeness is self-reported, not independently audited.")
        if result["operating_margin_pct"] is not None:
            st.metric("OPERATING MARGIN",f'{result["operating_margin_pct"]:.1f}%')
    st.subheader("Revenue over time")
    monthly=s.assign(month=s["date"].dt.to_period("M").dt.to_timestamp())
    monthly=monthly.groupby("month",as_index=False)["amount"].agg(lambda amounts: sum(amounts, Decimal("0.00")))
    monthly["amount_exact"]=monthly["amount"].map(lambda v: f"${v:,.2f}")
    monthly["amount"]=monthly["amount"].map(float)
    chart=alt.Chart(monthly).mark_line(color="#D5F478",strokeWidth=3,point=True).encode(
        x=alt.X("month:T",title=None,axis=alt.Axis(format="%b %Y",labelAngle=0,labelColor="#AAB2AB")),
        y=alt.Y("amount:Q",title=None,axis=alt.Axis(format="$,.0f",labelColor="#AAB2AB",gridColor="#303936")),
        tooltip=[alt.Tooltip("month:T",format="%b %Y"),alt.Tooltip("amount_exact:N",title="Exact net revenue")]
    ).properties(height=250).configure_view(stroke=None).configure(background="#111416")
    st.altair_chart(chart,width="stretch")
    st.markdown("**Monthly net revenue (exact amounts)**")
    revenue_by_month=monthly.copy()
    revenue_by_month["Month"]=revenue_by_month["month"].dt.strftime("%B %Y")
    revenue_by_month["Net revenue (USD)"]=revenue_by_month["amount_exact"]
    st.dataframe(revenue_by_month[["Month","Net revenue (USD)"]],hide_index=True,width="stretch")
    st.caption("Net revenue reflects sales minus refunds, not cash held in the bank.")
    if e is not None and result["profit_available"]:
        st.subheader("Cost breakdown")
        st.dataframe(pd.DataFrame([
            {"Category":"Direct costs","Recorded amount":dollars(result["direct_costs"])},
            {"Category":"Operating expenses","Recorded amount":dollars(result["operating_expenses"])}
        ]),hide_index=True,width="stretch")
with tabs[1]:
    st.subheader("What the records show")
    st.caption("Observed totals are not proof of waste or guaranteed savings. More detailed job and supplier records are needed for true profit-leak diagnosis.")
    items=findings(s,e)
    if not items:
        st.info("No cost or refund observations in this period.")
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{html.escape(item['title'])}**")
            st.metric("Recorded amount",dollars(item["amount"]))
            st.write(item["detail"])
            st.caption("Calculation: "+item["basis"])
with tabs[2]:
    st.subheader("Sales")
    st.dataframe(s,width="stretch",hide_index=True)
    if e is not None:
        st.subheader("Expenses")
        st.dataframe(e,width="stretch",hide_index=True)
    st.download_button("Download filtered sales",s.to_csv(index=False),"ledger_sales.csv","text/csv")
    if e is not None:
        st.download_button("Download filtered expenses",e.to_csv(index=False),"ledger_expenses.csv","text/csv")
with tabs[3]:
    st.subheader("Import integrity")
    st.caption("Session-isolated prototype storage. It can disappear when the app restarts and is not a production database. Do not upload confidential records.")

    with LedgerStore(workspace_db) as store:
        stored_transactions=store.list_transactions(workspace_id)
        unresolved_conflicts=store.list_conflicts(workspace_id)
        reconciliation=store.reconciliation_status(workspace_id)

    m1,m2,m3,m4=st.columns(4)
    m1.metric("STORED RECORDS",len(stored_transactions))
    m2.metric("UNRESOLVED CONFLICTS",len(unresolved_conflicts))
    m3.metric("CONFIRMED TRANSFERS",reconciliation["confirmed_links"])
    m4.metric("UNMATCHED TRANSFERS",reconciliation["unmatched_payouts"]+reconciliation["unmatched_bank_deposits"])

    if sales_integrity_batch.get("replayed"):
        st.info("Current sales batch was already imported. No additional stored transactions were created.")
    else:
        st.write(
            f"Current sales import: {sales_integrity_batch['inserted_count']} new, "
            f"{sales_integrity_batch['duplicate_count']} duplicates ignored, "
            f"{sales_integrity_batch['conflict_count']} conflicts requiring review."
        )

    if stored_transactions:
        source_summary=pd.DataFrame(stored_transactions)
        source_summary=(source_summary.groupby(["source","kind"],as_index=False)
                        .size().rename(columns={"size":"records"}))
        st.markdown("**Stored records by source and type**")
        st.dataframe(source_summary,hide_index=True,width="stretch")
        st.caption("LEDGER does not automatically add totals across different sources because the same economic event may appear in more than one system.")

    st.divider()
    st.subheader("Payout / bank deposit reconciliation")
    st.caption("Upload one source at a time. Required columns: external_id (or id), kind, amount. kind must be payout or bank_deposit. currency is optional and defaults to USD.")
    transfer_source=st.text_input("Transfer file source",value="square",key="transfer_source",help="Examples: square, bank_of_america, chase. Use a stable source name across uploads.")
    transfer_file=st.file_uploader("Transfer file",type=["csv","xlsx"],key="transfer_file")
    if transfer_file is not None:
        try:
            transfer_records=normalize_transfer_frame(read_file(transfer_file),workspace_id,transfer_source)
            transfer_batch_id=deterministic_batch_id(transfer_records,f"transfer-{transfer_source}")
            with LedgerStore(workspace_db) as store:
                transfer_batch=store.ingest(transfer_records,batch_id=transfer_batch_id)
            if transfer_batch.get("replayed"):
                st.info("This transfer batch was already imported. No additional records were created.")
            else:
                st.success(
                    f"Transfer import accepted: {transfer_batch['inserted_count']} new, "
                    f"{transfer_batch['duplicate_count']} duplicates ignored, "
                    f"{transfer_batch['conflict_count']} conflicts."
                )
        except Exception as exc:
            st.error(f"Transfer import rejected: {exc}")

    with LedgerStore(workspace_db) as store:
        match_info=store.find_reconciliation_candidates(workspace_id)
        unresolved_conflicts=store.list_conflicts(workspace_id)
        reconciliation=store.reconciliation_status(workspace_id)

    if match_info["ambiguous_groups"]:
        st.warning("Some equal-amount transfer groups are ambiguous. LEDGER will not guess which records match.")
        st.dataframe(pd.DataFrame(match_info["ambiguous_groups"]),hide_index=True,width="stretch")

    candidates=match_info["candidates"]
    if candidates:
        st.markdown("**Suggested exact transfer matches**")
        candidate_table=pd.DataFrame(candidates)
        candidate_table["amount"]=candidate_table["amount"].map(dollars)
        st.dataframe(candidate_table,hide_index=True,width="stretch")
        labels=[
            f"{c['payout_source']}:{c['payout_external_id']} → {c['deposit_source']}:{c['deposit_external_id']} · {dollars(c['amount'])}"
            for c in candidates
        ]
        selected_match=st.selectbox("Match to confirm",labels,key="reconciliation_candidate")
        selected_candidate=candidates[labels.index(selected_match)]
        reviewed_match=st.checkbox("I reviewed the source records and confirm these are the same transfer.",key="reviewed_match")
        if st.button("Confirm selected transfer match",disabled=not reviewed_match):
            try:
                with LedgerStore(workspace_db) as store:
                    store.confirm_reconciliation(
                        workspace_id,
                        payout_source=selected_candidate["payout_source"],
                        payout_external_id=selected_candidate["payout_external_id"],
                        deposit_source=selected_candidate["deposit_source"],
                        deposit_external_id=selected_candidate["deposit_external_id"],
                        note="Confirmed in Streamlit prototype after user review",
                    )
                st.success("Transfer match confirmed and stored in the reconciliation audit trail.")
                st.rerun()
            except Exception as exc:
                st.error(f"Reconciliation rejected: {exc}")
    elif reconciliation["recorded_payouts"] or reconciliation["recorded_bank_deposits"]:
        st.info("No unambiguous exact transfer matches are currently available.")

    if unresolved_conflicts:
        st.divider()
        st.subheader("Conflict review")
        conflict_labels=[
            f"#{c['id']} · {c['source']}:{c['external_id']} · existing {dollars(c['existing_amount'])} vs incoming {dollars(c['incoming_amount'])}"
            for c in unresolved_conflicts
        ]
        selected_conflict_label=st.selectbox("Conflict",conflict_labels,key="conflict_choice")
        selected_conflict=unresolved_conflicts[conflict_labels.index(selected_conflict_label)]
        st.dataframe(pd.DataFrame([selected_conflict]),hide_index=True,width="stretch")
        reviewed_conflict=st.checkbox("I reviewed the source evidence for this conflict.",key="reviewed_conflict")
        keep_col,accept_col=st.columns(2)
        if keep_col.button("Keep existing record",disabled=not reviewed_conflict):
            try:
                with LedgerStore(workspace_db) as store:
                    store.resolve_conflict(selected_conflict["id"],"keep_existing",note="Resolved in Streamlit prototype")
                st.success("Conflict resolved: existing canonical record kept.")
                st.rerun()
            except Exception as exc:
                st.error(f"Conflict resolution rejected: {exc}")
        if accept_col.button("Accept incoming revision",disabled=not reviewed_conflict):
            try:
                with LedgerStore(workspace_db) as store:
                    store.resolve_conflict(selected_conflict["id"],"accept_incoming",note="Resolved in Streamlit prototype")
                st.success("Conflict resolved: incoming revision became the canonical stored record.")
                st.rerun()
            except Exception as exc:
                st.error(f"Conflict resolution rejected: {exc}")

    st.divider()
    st.caption(reconciliation["note"])
    if st.button("Reset this prototype workspace"):
        reset_workspace(workspace_db)
        st.session_state["ledger_workspace_id"]=uuid.uuid4().hex
        st.rerun()

st.caption("LEDGER · DEVELOPMENT BUILD · Not suitable for confidential client information.")
