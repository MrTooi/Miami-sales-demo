"""Synthetic evaluation task. Intentionally incorrect; not product code."""


def canonical_net_revenue(events):
    """Return net sales revenue from normalized synthetic events."""
    total = 0.0
    for event in events:
        kind = event["kind"]
        amount = float(event["amount"])
        if kind in {"sale", "payout", "bank_deposit"}:
            total += amount
        elif kind == "refund":
            total -= amount
    return total
