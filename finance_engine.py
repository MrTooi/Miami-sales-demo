"""Deterministic financial calculations. No inferred costs or savings."""
from collections import Counter
from decimal import Decimal, InvalidOperation


def money(value):
    try:
        if value is None or isinstance(value, bool):
            raise ValueError("Missing/invalid money value")
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
        if not amount.is_finite() or amount.as_tuple().exponent < -2:
            raise ValueError("Money must have at most two decimal places")
        return amount
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc


def summarize(sales, expenses=None, *, expenses_complete=False):
    """Return deterministic period totals.

    Sales are ``{id, amount}`` and may contain negative refund amounts.
    Expenses are ``{id, amount, category}``, where category is direct or
    operating and amount is nonnegative.

    Every supplied record is validated even when expense coverage has not been
    confirmed. Profit is only exposed when expenses are supplied *and* the
    caller explicitly confirms that expense coverage is complete.
    """

    def validate(rows, kind):
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or row.get("id") is None or not str(row.get("id")).strip():
                raise ValueError(f"{kind} row missing ID")
            key = str(row["id"]).strip()
            if key in seen:
                raise ValueError(f"Duplicate {kind} ID: {key}")
            seen.add(key)
            yield row, money(row.get("amount"))

    sales = list(sales)
    sales_values = [amount for _, amount in validate(sales, "sale")]
    revenue = sum(sales_values, Decimal("0.00"))
    result = {
        "net_revenue": revenue,
        "transactions": len(sales),
        "refund_total": -sum((x for x in sales_values if x < 0), Decimal("0.00")),
        "profit_available": False,
    }

    if expenses is None:
        result["profit_unavailable_reason"] = "Expense records not provided"
        return result

    expenses = list(expenses)
    costs = Counter()
    for row, amount in validate(expenses, "expense"):
        if amount < 0:
            raise ValueError("Expense amounts must be nonnegative; use separate adjustment records")
        category = row.get("category")
        if category not in ("direct", "operating"):
            raise ValueError("Expense category must be direct or operating")
        costs[category] += amount

    if not expenses_complete:
        result["profit_unavailable_reason"] = "Expense coverage not confirmed"
        return result

    direct = costs["direct"]
    operating = costs["operating"]
    gross = revenue - direct
    profit = gross - operating
    result.update(
        {
            "direct_costs": direct,
            "operating_expenses": operating,
            "gross_profit": gross,
            "operating_profit": profit,
            "profit_available": True,
            "gross_margin_pct": (gross / revenue * 100 if revenue > 0 else None),
            "operating_margin_pct": (profit / revenue * 100 if revenue > 0 else None),
        }
    )
    return result
