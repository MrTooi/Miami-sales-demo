"""Helpers that connect normalized dashboard data to the persistent integrity store.

These functions deliberately keep the dashboard's accounting calculations separate
from the persistent source ledger. Stored records are useful for idempotency,
conflict review, and payout/deposit reconciliation; they are not automatically
summed across sources because cross-source duplication can exist.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json

import pandas as pd

from finance_engine import money


TRANSFER_KINDS = {"payout", "bank_deposit"}


def sales_to_integrity_records(sales: pd.DataFrame, tenant_id: str, source: str) -> list[dict]:
    """Convert an already-normalized sales frame to source-ledger records.

    Negative sales are stored as positive refund records so the persistent ledger
    never relies on amount sign to infer transaction meaning.
    """
    if sales is None or sales.empty:
        raise ValueError("Sales data cannot be empty")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source is required")

    records = []
    for row in sales.itertuples(index=False):
        amount = Decimal(row.amount)
        kind = "refund" if amount < 0 else "sale"
        records.append(
            {
                "tenant_id": tenant_id.strip(),
                "source": source.strip().lower(),
                "external_id": str(row.id).strip(),
                "kind": kind,
                "amount": str(abs(amount)),
                "currency": "USD",
            }
        )
    return records


def normalize_transfer_frame(frame: pd.DataFrame, tenant_id: str, source: str) -> list[dict]:
    """Validate payout/bank-deposit import data for the reconciliation ledger.

    Required columns: external_id (or id), kind, amount. Currency is optional and
    defaults to USD. Only payout and bank_deposit are accepted in this import.
    """
    if frame is None or frame.empty:
        raise ValueError("Transfer file is empty")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source is required")

    df = frame.copy()
    df.columns = [str(column).strip().lower() for column in df.columns]
    if df.columns.duplicated().any():
        raise ValueError("Duplicate column headers")
    if "id" in df.columns and "external_id" not in df.columns:
        df = df.rename(columns={"id": "external_id"})
    missing = {"external_id", "kind", "amount"} - set(df.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    if "currency" not in df.columns:
        df["currency"] = "USD"

    records = []
    seen = set()
    for row in df.itertuples(index=False):
        external_id = str(row.external_id).strip()
        kind = str(row.kind).strip().lower()
        currency = str(row.currency).strip().upper()
        if not external_id:
            raise ValueError("Blank external_id")
        if external_id in seen:
            raise ValueError("Duplicate external_id in transfer file")
        seen.add(external_id)
        if kind not in TRANSFER_KINDS:
            raise ValueError("Transfer kind must be payout or bank_deposit")
        if currency != "USD":
            raise ValueError("Only USD is supported in this prototype")
        amount = money(row.amount)
        if amount < 0:
            raise ValueError("Transfer amounts must be nonnegative")
        records.append(
            {
                "tenant_id": tenant_id.strip(),
                "source": source.strip().lower(),
                "external_id": external_id,
                "kind": kind,
                "amount": str(amount),
                "currency": currency,
            }
        )
    return records


def deterministic_batch_id(records: list[dict], namespace: str) -> str:
    """Return a stable batch ID so Streamlit reruns do not create duplicate batches."""
    if not records:
        raise ValueError("Cannot fingerprint an empty batch")
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("namespace is required")
    canonical = json.dumps(
        sorted(records, key=lambda r: (r["tenant_id"], r["source"], r["external_id"])),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{namespace.strip().lower()}-{digest}"
