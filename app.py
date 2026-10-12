import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Miami Sales Dashboard", page_icon="📊", layout="wide")
st.title("Miami Small Business Sales Dashboard")
st.caption("Interactive prototype · All included sample transactions are fictional")
st.info("Upload a CSV or Excel file with columns: date, service, amount. Negative amounts count as refunds.")

@st.cache_data
def demo_data():
    return pd.read_csv("sample_sales.csv")

def clean_sales(df):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"date", "service", "amount"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    df["service"] = df["service"].astype("string").str.strip()
    bad = df["date"].isna() | df["amount"].isna() | df["service"].isna() | (df["service"] == "")
    return df.loc[~bad].copy(), int(bad.sum())

uploaded = st.file_uploader("Upload sales data", type=["csv", "xlsx"])
try:
    raw = (pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)) if uploaded else demo_data()
    data, skipped = clean_sales(raw)
except Exception as exc:
    st.error(f"Unable to load sales data: {exc}")
    st.stop()

if skipped:
    st.warning(f"{skipped} invalid transaction(s) were excluded.")
if data.empty:
    st.warning("No valid transactions to display.")
    st.stop()

minimum, maximum = data["date"].min().date(), data["date"].max().date()
dates = st.date_input("Date range", value=(minimum, maximum), min_value=minimum, max_value=maximum)
if not isinstance(dates, tuple) or len(dates) != 2:
    st.info("Select both dates.")
    st.stop()
filtered = data.loc[data["date"].dt.date.between(*dates)].copy()
if filtered.empty:
    st.warning("No transactions in this date range.")
    st.stop()

revenue = filtered["amount"].sum()
count = len(filtered)
a, b, c = st.columns(3)
a.metric("Net revenue", f"${revenue:,.2f}")
b.metric("Transactions", f"{count:,}")
c.metric("Average transaction", f"${revenue/count:,.2f}")

monthly = filtered.assign(month=filtered["date"].dt.to_period("M").astype(str)).groupby("month")["amount"].sum()
services = filtered.groupby("service")["amount"].sum().sort_values(ascending=False)
left, right = st.columns(2)
with left:
    st.subheader("Monthly revenue")
    st.bar_chart(monthly)
with right:
    st.subheader("Revenue by service")
    st.bar_chart(services)
st.subheader("Transaction details")
st.dataframe(filtered.sort_values("date", ascending=False), use_container_width=True, hide_index=True)
summary = pd.DataFrame({"metric": ["net_revenue", "transactions", "average_transaction"], "value": [round(revenue, 2), count, round(revenue/count, 2)]})
st.download_button("Download summary CSV", summary.to_csv(index=False), "sales_summary.csv", "text/csv")
st.download_button("Download filtered transactions", filtered.to_csv(index=False), "filtered_sales.csv", "text/csv")
st.caption("Prototype only. Do not upload private or sensitive business/customer records.")
