"""Strict, auditable import contracts for Ledger CSV/Excel data."""
from decimal import Decimal
import importlib

import pandas as pd
import finance_engine
from finance_engine import money


def normalize(frame, kind):
    if kind not in ("sales", "expenses"):
        raise ValueError("Unknown dataset type")
    if frame is None or frame.empty:
        raise ValueError(f"{kind.title()} file is empty")
    df=frame.copy()
    df.columns=[str(c).strip().lower() for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError("Duplicate column headers")
    if kind=="sales":
        if "order_id" in df.columns and "id" not in df.columns:
            df=df.rename(columns={"order_id":"id"})
        required={"id","date","service","amount"}
    else:
        required={"id","date","category","amount"}
    missing=required-set(df.columns)
    if missing:
        raise ValueError("Missing columns: "+", ".join(sorted(missing)))
    if df[["id","date","amount"]].isna().any().any():
        raise ValueError("Missing IDs, dates, or amounts; no rows were silently dropped")
    df["id"]=df["id"].astype(str).str.strip()
    if (df["id"]=="").any() or df["id"].duplicated().any():
        raise ValueError("Blank or duplicate transaction IDs")
    dates=pd.to_datetime(df["date"],format="%Y-%m-%d",errors="coerce")
    if dates.isna().any():
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    df["date"]=dates
    df["amount"]=[money(v) for v in df["amount"]]
    if kind=="sales":
        df["service"]=df["service"].astype("string").str.strip()
        if df["service"].isna().any() or (df["service"]=="").any():
            raise ValueError("Missing service")
    else:
        df["category"]=df["category"].astype("string").str.strip().str.lower()
        if (~df["category"].isin(["direct","operating"])).any():
            raise ValueError("Expense category must be direct or operating")
        if any(v<0 for v in df["amount"]):
            raise ValueError("Expense amounts must be nonnegative")
        if "description" not in df:
            df["description"]=""
    return df


def analyze(sales, expenses=None, *, expenses_complete=False):
    """Compute period summary using the current on-disk finance engine.

    Streamlit Community Cloud can hot-reload the entry script while retaining
    imported helper modules in a long-lived worker. Reloading this small,
    stateless engine at the calculation boundary prevents an older function
    signature from surviving a deployment and causing a TypeError.
    """
    engine = importlib.reload(finance_engine)
    sales_rows=[{"id":r.id,"amount":str(r.amount)} for r in sales.itertuples(index=False)]
    expense_rows=None if expenses is None else [
        {"id":r.id,"amount":str(r.amount),"category":r.category}
        for r in expenses.itertuples(index=False)]
    return engine.summarize(sales_rows,expense_rows,expenses_complete=bool(expenses_complete))


def findings(sales, expenses=None):
    """Observed amounts only. Never call them savings or assert a cause."""
    observations=[]
    refunds=sum((-v for v in sales["amount"] if v<0),Decimal("0"))
    if refunds>0:
        observations.append({"title":"Refund activity","amount":refunds,
                             "detail":"Total negative sales entries; investigate reasons and avoidable causes.",
                             "basis":"Sum of negative sales amounts (absolute value)"})
    if expenses is not None:
        for category,label in (("direct","Direct costs"),("operating","Operating expenses")):
            amount=sum((v for v in expenses.loc[expenses["category"]==category,"amount"]),Decimal("0"))
            if amount>0:
                observations.append({"title":label,"amount":amount,
                                     "detail":"Recorded expense total, not a verified loss or savings opportunity.",
                                     "basis":f"Sum of expense amounts categorized as {category}"})
    return observations
