"""Conservative source-aware transaction integrity checks.

This module never guesses that two unrelated records are the same payment.
It is a stateless building block; production needs persistent tenant-scoped IDs.
"""
from decimal import Decimal
from finance_engine import money

VALID_KINDS = {"sale", "refund", "fee", "payout", "bank_deposit"}

def normalize_record(record):
    """Validate a source record and preserve its exact amount."""
    if not isinstance(record, dict):
        raise ValueError("Transaction must be an object")
    required = ("tenant_id", "source", "external_id", "kind", "amount", "currency")
    for field in required:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"Missing or invalid {field}")
    kind = record["kind"].strip().lower()
    if kind not in VALID_KINDS:
        raise ValueError("Unsupported transaction kind")
    currency = record["currency"].strip().upper()
    if currency != "USD":
        raise ValueError("Only USD is supported in this prototype")
    amount = money(record["amount"])
    if amount < 0:
        raise ValueError("Use a positive amount and an explicit transaction kind")
    return {
        "tenant_id": record["tenant_id"].strip(),
        "source": record["source"].strip().lower(),
        "external_id": record["external_id"].strip(),
        "kind": kind,
        "amount": amount,
        "currency": currency,
    }

def deduplicate(records):
    """Drop identical repeated source events; reject conflicting revisions.

    The identity includes tenant and provider, so the same external ID at two
    providers or two businesses is not automatically a duplicate.
    """
    seen = {}
    unique = []
    duplicates = 0
    for raw in records:
        record = normalize_record(raw)
        key = (record["tenant_id"], record["source"], record["external_id"])
        if key in seen:
            if record != seen[key]:
                raise ValueError(f"Conflicting records for {key}; review required")
            duplicates += 1
            continue
        seen[key] = record
        unique.append(record)
    return unique, duplicates

def sales_summary(records, tenant_id):
    """Calculate payment-derived sales only, not bank cash flow or profit.

    Does not attempt cross-provider matching; unresolved cross-source overlaps
    must be reconciled before labeling results verified.
    """
    unique, duplicates = deduplicate(records)
    selected = [r for r in unique if r["tenant_id"] == tenant_id]
    gross = sum((r["amount"] for r in selected if r["kind"] == "sale"), Decimal("0.00"))
    refunds = sum((r["amount"] for r in selected if r["kind"] == "refund"), Decimal("0.00"))
    fees = sum((r["amount"] for r in selected if r["kind"] == "fee"), Decimal("0.00"))
    payouts = sum((r["amount"] for r in selected if r["kind"] == "payout"), Decimal("0.00"))
    deposits = sum((r["amount"] for r in selected if r["kind"] == "bank_deposit"), Decimal("0.00"))
    return {
        "gross_sales": gross,
        "refunds": refunds,
        "net_sales": gross - refunds,
        "recorded_fees": fees,
        "payouts": payouts,
        "bank_deposits": deposits,
        "duplicate_source_records": duplicates,
        "reconciled": False,
        "note": "Bank deposits and payouts are not additional sales. Cross-source reconciliation is pending.",
    }
