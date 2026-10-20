"""Deterministic financial calculations. No inferred costs or savings."""
import re
from decimal import Decimal, InvalidOperation


# U.S. amounts only: commas strictly as thousands separators ("1,234.56"), a dot for cents.
# "12,50", "1,5" or "1.234,56" could be European style (12.50) or a typo, so they are refused
# rather than read as 1250 or 15 (issue #36).
_US_AMOUNT = re.compile(r"^[+-]?\$?[+-]?(\d+|\d{1,3}(,\d{3})+)(\.\d+)?$")

# The largest amount accepted, positive or negative: just under one trillion dollars. Python's
# Decimal keeps 28 significant digits by default, so a sum of amounts this size stays exact for
# far more rows than any file can hold (a billion of them still fits). A bigger amount is refused
# with its own reason, never rounded or cut short.
MAX_MONEY = Decimal("999999999999.99")


class AmountTooLarge(ValueError):
    """An amount over MAX_MONEY: refused so every sum stays exact.

    Callers check the too_large flag rather than this class: data_pipeline.analyze reloads this
    module, which makes a new class each time, but the flag survives.
    """

    too_large = True


def money(value):
    """An exact Decimal amount: at most two decimals, no larger than MAX_MONEY either way.

    Raises AmountTooLarge (a ValueError) for an amount over MAX_MONEY and ValueError for anything
    that isn't a valid amount. Nothing is ever rounded or cut short.
    """
    text = "" if value is None or isinstance(value, (bool, float)) else str(value).strip()
    if isinstance(value, str) and len(text) > 40 and _US_AMOUNT.match(text):
        # Longer than any amount up to MAX_MONEY can be written ("-$999,999,999,999.99" is 20
        # characters), so it is refused before it is turned into a number.
        raise AmountTooLarge(f"Amount is larger than {MAX_MONEY:,}: {text[:20]}...")
    try:
        if value is None or isinstance(value, (bool, float)):
            # A float is already a binary approximation (0.1 + 0.2 != 0.3), so it is never
            # turned into money; amounts must arrive as text, int or Decimal.
            raise ValueError("Missing/invalid money value")
        if isinstance(value, str) and not _US_AMOUNT.match(text):
            raise ValueError("Not a U.S. dollar amount")
        amount = Decimal(text.replace("$", "").replace(",", ""))
        if not amount.is_finite() or amount.as_tuple().exponent < -2:
            raise ValueError("Money must have at most two decimal places")
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc
    if abs(amount) > MAX_MONEY:
        raise AmountTooLarge(f"Amount is larger than {MAX_MONEY:,}: {value!r}")
    return amount


def summarize(sales, expenses=None, *, expenses_complete=False):
    """Return deterministic period totals.

    Sales are ``{id, amount}`` and may contain negative refund amounts.
    Expenses are ``{id, amount, category}``, where category is direct or
    operating and amount is nonnegative.

    Every supplied record is validated even when expense coverage has not been
    confirmed. Recorded cost totals are exposed when valid expense records are
    supplied, but profit is only exposed when the caller explicitly confirms
    expense coverage is complete.
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
    direct = Decimal("0.00")
    operating = Decimal("0.00")
    for row, amount in validate(expenses, "expense"):
        if amount < 0:
            raise ValueError("Expense amounts must be nonnegative; use separate adjustment records")
        category = row.get("category")
        if category == "direct":
            direct += amount
        elif category == "operating":
            operating += amount
        else:
            raise ValueError("Expense category must be direct or operating")

    result["direct_costs"] = direct
    result["operating_expenses"] = operating

    if not expenses_complete:
        result["profit_unavailable_reason"] = "Expense coverage not confirmed"
        return result

    gross = revenue - direct
    profit = gross - operating
    result.update(
        {
            "gross_profit": gross,
            "operating_profit": profit,
            "profit_available": True,
            "gross_margin_pct": (gross / revenue * 100 if revenue > 0 else None),
            "operating_margin_pct": (profit / revenue * 100 if revenue > 0 else None),
        }
    )
    return result
