"""Isolated synthetic finance arithmetic; no product or data-source integration."""

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation, localcontext


def summarize_transactions(records: Iterable[Mapping]) -> dict[str, Decimal]:
    """Total supplied synthetic records in a single currency, without rounding.

    Each record has ``kind`` and ``amount``. Amounts must be nonnegative,
    finite Decimal, integer, or decimal-string values with at most two decimal
    places. Floats and booleans are rejected. Refunds subtract from revenue;
    expenses and provider fees add to costs. Movements affect neither total.

    Profit is revenue minus recorded costs, not a claim of expense completeness.
    Records are counted as supplied; identity/deduplication is outside this trial.
    Inputs and the caller's decimal context are never modified.
    """
    kinds = ("sale", "expense", "provider_fee", "refund", "payout", "bank_deposit")
    validated = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("Transaction must be a mapping")
        kind = record.get("kind")
        if kind not in kinds:
            raise ValueError("Unknown transaction kind")
        value = record.get("amount")
        if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
            raise ValueError("Amount must be Decimal, integer, or decimal string")
        try:
            with localcontext():
                amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Invalid amount") from exc
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError("Amount must be finite, nonnegative, and have at most two decimal places")
        validated.append((kind, amount))

    # Reserve cents plus carry digits so even large totals remain exact under
    # a caller's low-precision decimal context.
    precision = max((amount.adjusted() + 3 for _, amount in validated), default=3)
    with localcontext() as context:
        context.prec = max(3, precision) + len(str(len(validated))) + 1
        context.Emax = max(context.Emax, context.prec)
        context.Emin = min(context.Emin, -2)
        revenue = Decimal("0.00")
        costs = Decimal("0.00")
        for kind, amount in validated:
            if kind == "sale":
                revenue += amount
            elif kind == "refund":
                revenue -= amount
            elif kind in ("expense", "provider_fee"):
                costs += amount
        return {"revenue": revenue, "costs": costs, "profit": revenue - costs}
