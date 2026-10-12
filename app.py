import html
import pandas as pd
import streamlit as st
import altair as alt

st.set_page_config(page_title="Ledger | Sales Overview", page_icon="◼", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
:root {color-scheme:dark}
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {background:#111315!important;color:#F5F2EB!important}
[data-testid="stAppViewContainer"] * {font-family:'DM Sans',sans-serif}
.block-container {max-width:1140px;padding-top:2rem;padding-bottom:4rem}
h1,h2,h3 {font-family:'Manrope',sans-serif!important;letter-spacing:-.045em!important;color:#F5F2EB!important}
h1 {font-size:clamp(2rem,5vw,3rem)!important}
[data-testid="stMetric"] {background:#1C1F20;border:1px solid #303434;border-radius:17px;padding:22px 20px}
[data-testid="stMetricLabel"] {color:#A9AEAA!important}
[data-testid="stMetricValue"] {color:#F5F2EB!important;font-weight:700!important;letter-spacing:-.04em}
[data-testid="stFileUploader"], [data-testid="stDataFrame"], [data-testid="stDateInput"] {border-radius:14px}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#303434}
div.stButton>button, div.stDownloadButton>button {background:#D5F478!important;color:#172014!important;border:0!important;border-radius:12px!important;font-weight:700}
[data-testid="stCaptionContainer"], .stCaption {color:#929994!important}
section[data-testid="stSidebar"] {background:#191B1D}
.eyebrow {color:#D5F478;font-size:.75rem;letter-spacing:.18em;font-weight:800}
.subtle {color:#9FA6A1;font-size:.92rem}
.rule {height:1px;background:#303434;margin:1.4rem 0}
.service {margin:0 0 1.2rem 0}
.service-top {display:flex;justify-content:space-between;gap:12px;margin-bottom:9px;font-size:.9rem}
.service-name {color:#E8E9E4}
.service-value {color:#D5F478;font-weight:700}
.track {background:#2C3030;height:8px;border-radius:12px;overflow:hidden}
.fill {height:100%;background:#D5F478;border-radius:12px}
@media(max-width:640px){.block-container{padding:1.3rem 1rem 3rem} [data-testid="stMetric"]{padding:15px 12px} [data-testid="stMetricValue"]{font-size:1.45rem}}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="eyebrow">LEDGER / BUSINESS INTELLIGENCE</div>',unsafe_allow_html=True)
st.title("Your numbers, at a glance.")
st.markdown('<p class="subtle">A clearer view of sales, performance, and where revenue comes from.</p>',unsafe_allow_html=True)

@st.cache_data
def demo_data():
    return pd.read_csv("sample_sales.csv")

def clean_sales(df):
    df=df.copy()
    df.columns=[str(c).strip().lower() for c in df.columns]
    missing={"date","service","amount"}-set(df.columns)
    if missing:
        raise ValueError("Missing columns: "+", ".join(sorted(missing)))
    df["date"]=pd.to_datetime(df["date"],errors="coerce")
    df["amount"]=pd.to_numeric(df["amount"].astype(str).str.replace(r"[$,]","",regex=True),errors="coerce")
    df["service"]=df["service"].astype("string").str.strip()
    bad=df["date"].isna()|df["amount"].isna()|df["service"].isna()|(df["service"]=="")
    return df.loc[~bad].copy(),int(bad.sum())

with st.expander("Import data & filters",expanded=False):
    uploaded=st.file_uploader("Upload a CSV or Excel file",type=["csv","xlsx"],help="Required columns: date, service, amount")
    st.caption("Negative amounts count as refunds. Files are processed for this session; avoid sensitive data.")

try:
    raw=(pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)) if uploaded else demo_data()
    data,skipped=clean_sales(raw)
except Exception as exc:
    st.error(f"Could not read the file: {exc}")
    st.stop()
if skipped:
    st.warning(f"Excluded {skipped} invalid rows.")
if data.empty:
    st.warning("No valid transactions.")
    st.stop()

if uploaded is None:
    st.caption("● DEMO MODE — fictional printing business transactions")
minimum,maximum=data["date"].min().date(),data["date"].max().date()
dates=st.date_input("Reporting period",value=(minimum,maximum),min_value=minimum,max_value=maximum)
if not isinstance(dates,tuple) or len(dates)!=2:
    st.info("Choose a start and end date.")
    st.stop()
filtered=data.loc[data["date"].dt.date.between(*dates)].copy()
if filtered.empty:
    st.warning("No transactions in this period.")
    st.stop()

revenue=float(filtered["amount"].sum())
count=len(filtered)
average=revenue/count
st.markdown('<div class="rule"></div>',unsafe_allow_html=True)
a,b,c=st.columns(3)
a.metric("NET REVENUE",f"${revenue:,.2f}")
b.metric("TRANSACTIONS",f"{count:,}")
c.metric("AVG. TRANSACTION",f"${average:,.2f}")

st.markdown("### Revenue over time")
st.caption("Monthly net sales · USD")
monthly=filtered.assign(month=filtered["date"].dt.to_period("M").dt.to_timestamp()).groupby("month",as_index=False)["amount"].sum()
chart=alt.Chart(monthly).mark_area(line={"color":"#D5F478","strokeWidth":3},color=alt.Gradient(gradient="linear",stops=[alt.GradientStop(color="#D5F478",offset=0),alt.GradientStop(color="#D5F478",offset=1)],x1=0,x2=0,y1=0,y2=1),opacity=.18).encode(
    x=alt.X("month:T",title=None,axis=alt.Axis(format="%b %Y",labelColor="#A9AEAA",labelAngle=0,grid=False,tickCount=6)),
    y=alt.Y("amount:Q",title=None,axis=alt.Axis(labelColor="#A9AEAA",gridColor="#303434",format="$,.0f"),scale=alt.Scale(zero=True)),
    tooltip=[alt.Tooltip("month:T",title="Month",format="%B %Y"),alt.Tooltip("amount:Q",title="Revenue",format="$,.2f")]
).properties(height=245).configure_view(stroke=None).configure(background="#111315")
st.altair_chart(chart,use_container_width=True)

st.markdown("### Where your revenue comes from")
st.caption("Services ranked by net revenue")
services=filtered.groupby("service")["amount"].sum().sort_values(ascending=False)
max_abs=max(float(services.abs().max()),1)
for service,value in services.items():
    width=max(0,min(100,100*float(value)/max_abs))
    safe=html.escape(str(service))
    st.markdown(f'<div class="service"><div class="service-top"><span class="service-name">{safe}</span><span class="service-value">${value:,.2f}</span></div><div class="track"><div class="fill" style="width:{width:.1f}%"></div></div></div>',unsafe_allow_html=True)

with st.expander("View individual transactions"):
    st.dataframe(filtered.sort_values("date",ascending=False),use_container_width=True,hide_index=True)
st.markdown("### Export your report")
summary=pd.DataFrame({"metric":["net_revenue","transactions","average_transaction"],"value":[round(revenue,2),count,round(average,2)]})
x,y=st.columns(2)
x.download_button("Download summary",summary.to_csv(index=False),"sales_summary.csv","text/csv",use_container_width=True)
y.download_button("Download transactions",filtered.to_csv(index=False),"filtered_sales.csv","text/csv",use_container_width=True)
st.caption("LEDGER DEMO · Not intended for confidential business data.")
