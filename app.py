"""Ledger — prototype financial intelligence dashboard. Synthetic data only."""
import html
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from data_pipeline import analyze, findings, normalize

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


@st.cache_data
def demo_sales():
    return pd.read_csv("sample_sales.csv",dtype=str)


@st.cache_data
def demo_expenses():
    return pd.read_csv("sample_expenses.csv",dtype=str)


st.markdown('<div class="eyebrow">LEDGER / PROFIT INTELLIGENCE</div>',unsafe_allow_html=True)
st.title("Know where the money goes.")
st.markdown('<p class="subtle">Understand profitability, investigate costs, and review evidence behind each finding.</p>',unsafe_allow_html=True)
st.warning("PROTOTYPE · Not audited, not production-ready. Use fictional or anonymized data only.")

with st.expander("Import CSV or Excel records",expanded=False):
    sales_file=st.file_uploader("Sales file",type=["csv","xlsx"],key="sales",help="Required: id (or order_id), date, service, amount. Negative amounts are refunds.")
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
elif sales_file is not None and expenses_file is None:
    st.info("Sales uploaded without expenses. Profit will be unavailable.")
elif sales_file is None and expenses_file is not None:
    st.error("Upload matching sales data alongside expense data; demo sales cannot be mixed with uploaded expenses.")
    st.stop()

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

tabs=st.tabs(["Overview","Cost observations","Transactions"])
with tabs[0]:
    a,b,c,d=st.columns(4)
    a.metric("NET REVENUE",dollars(result["net_revenue"]))
    b.metric("GROSS PROFIT",dollars(result["gross_profit"]) if result["profit_available"] else "Unavailable")
    c.metric("OPERATING PROFIT",dollars(result["operating_profit"]) if result["profit_available"] else "Unavailable")
    d.metric("REFUNDS",dollars(result["refund_total"]))
    if not result["profit_available"]:
        st.info("Profit unavailable: " + result.get("profit_unavailable_reason", "Expense coverage unverified") + ". Revenue is not profit.")
    else:
        st.caption("Gross profit = net revenue − direct costs. Operating profit = gross profit − operating expenses. Expenses are assumed complete only if the uploader confirms.")
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
st.caption("LEDGER · DEVELOPMENT BUILD · Not suitable for confidential client information.")
