"""MarginX step 1: job-level CSV intake with a "what's missing" report.

One CSV at a time (invoices or costs). The owner confirms a column mapping and a
date format; every row is then either accepted or rejected with a plain reason.
Nothing is silently dropped, repaired, coerced or guessed, and cell text is
always data (spreadsheet formulas are never evaluated). This step reports gaps
only; it does not calculate profit (build step 3, docs/MVP_SPEC.md).
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from finance_engine import money

KINDS = ("invoices", "costs")

# field -> (label, required)
FIELDS: dict[str, dict[str, tuple[str, bool]]] = {
    "invoices": {
        "invoice_id": ("Invoice number", True),
        "date": ("Invoice date", True),
        "customer": ("Customer", True),
        "amount": ("Amount", True),
        "job_id": ("Job number", False),
        "description": ("Description", False),
    },
    "costs": {
        "date": ("Date", True),
        "vendor": ("Vendor / payee", True),
        "amount": ("Amount", True),
        "cost_id": ("Bill / reference number", False),
        "job_id": ("Job number", False),
        "cost_type": ("Cost type (materials, labor, outsourced...)", False),
        "memo": ("Memo / description", False),
    },
}

# Normalized header words that suggest a field. Suggestions only; the owner confirms.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "invoice_id": ("invoice id", "invoice", "invoice no", "invoice number", "invoice num", "num", "no", "number", "doc number"),
    "cost_id": ("bill id", "bill", "bill no", "bill number", "reference", "ref", "ref no", "num", "number"),
    "date": ("date", "invoice date", "bill date", "txn date", "transaction date"),
    "customer": ("customer", "customer name", "client", "client name", "name", "bill to"),
    "vendor": ("vendor", "vendor name", "payee", "supplier", "name"),
    "amount": ("amount", "total", "amt", "amount usd", "amt usd", "total amount", "invoice total", "open balance"),
    "job_id": ("job", "job id", "job no", "job number", "job num", "project", "project id", "work order", "wo"),
    "description": ("description", "memo", "item", "service", "product service"),
    "cost_type": ("cost type", "type", "category", "account", "expense type"),
    "memo": ("memo", "description", "note", "notes"),
}

DATE_FORMATS = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
}

LABOR_WORDS = ("labor", "labour", "wages", "payroll")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
MAX_FILE_BYTES = 5_000_000


class IntakeError(ValueError):
    """The file as a whole can't be read; nothing was imported."""


@dataclass
class IntakeResult:
    kind: str
    total_rows: int
    accepted: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # {"row": n, "reasons": [...], "values": {...}}
    mapped_fields: tuple[str, ...] = ()


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", header.lower()).strip()


def read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Parse CSV bytes into headers and string rows, refusing anything ambiguous."""
    if len(data) > MAX_FILE_BYTES:
        raise IntakeError(f"File is larger than {MAX_FILE_BYTES // 1_000_000} MB; split it or contact us.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IntakeError("File isn't UTF-8 text. Re-export it as 'CSV UTF-8' and upload again.") from exc
    if not text.strip():
        raise IntakeError("File is empty.")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        # Row numbers count records as a spreadsheet shows them (header = row 1),
        # before fully blank lines are skipped, so they match the owner's file.
        table = [(number, row) for number, row in enumerate(reader, start=1) if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise IntakeError(f"File isn't valid CSV ({exc}). Check for unbalanced quotes.") from exc
    if not table:
        raise IntakeError("File is empty.")
    headers = [h.strip() for h in table[0][1]]
    if len(headers) < 2:
        raise IntakeError("Only one column was found. The file may use a separator other than commas.")
    if any(not h for h in headers):
        raise IntakeError("A column has no header name. Every column needs a header.")
    if len({h.lower() for h in headers}) != len(headers):
        raise IntakeError("Two columns have the same header name.")
    rows = []
    for number, cells in table[1:]:
        if len(cells) != len(headers):
            rows.append({"__row__": str(number), "__shape_error__": f"has {len(cells)} cells, header has {len(headers)}"})
            continue
        rows.append({"__row__": str(number), **{h: c for h, c in zip(headers, cells)}})
    return headers, rows


def suggest_mapping(headers: list[str], kind: str) -> dict[str, str | None]:
    """Best-guess field -> header suggestions for the owner to confirm. Never applied silently."""
    if kind not in KINDS:
        raise ValueError(f"Unknown file type: {kind}")
    normalized = {h: _norm(h) for h in headers}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for fld in FIELDS[kind]:
        candidates = [_norm(fld.replace("_", " ")), *SYNONYMS.get(fld, ())]
        choice = next((h for c in candidates for h, n in normalized.items() if n == c and h not in used), None)
        mapping[fld] = choice
        if choice:
            used.add(choice)
    return mapping


def validate_mapping(mapping: dict[str, str | None], headers: list[str], kind: str) -> list[str]:
    """Problems with the confirmed mapping; an empty list means it can be used."""
    problems = []
    for fld, (label, required) in FIELDS[kind].items():
        header = mapping.get(fld)
        if required and not header:
            problems.append(f"Choose which column is the {label}.")
        if header and header not in headers:
            problems.append(f"Column '{header}' for {label} isn't in the file.")
    chosen = [h for h in mapping.values() if h]
    for header in {h for h in chosen if chosen.count(h) > 1}:
        problems.append(f"Column '{header}' is used for more than one field.")
    unknown = set(mapping) - set(FIELDS[kind])
    if unknown:
        problems.append("Unknown fields: " + ", ".join(sorted(unknown)))
    return problems


def suggest_date_format(values: list[str]) -> str | None:
    """The single format every non-blank value parses with, else None (owner must choose)."""
    values = [v.strip() for v in values if v and v.strip()]
    fits = [name for name, fmt in DATE_FORMATS.items() if values and all(_parse_date(v, fmt) for v in values)]
    return fits[0] if len(fits) == 1 else None


def _parse_date(value: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), fmt).date()
    except ValueError:
        return None


def intake(headers: list[str], rows: list[dict[str, str]], mapping: dict[str, str | None], kind: str,
           date_format: str) -> IntakeResult:
    """Accept or reject every row with a reason. Raises IntakeError if the mapping is unusable."""
    if kind not in KINDS:
        raise IntakeError(f"Unknown file type: {kind}")
    if date_format not in DATE_FORMATS:
        raise IntakeError("Choose the date format used in the file.")
    problems = validate_mapping(mapping, headers, kind)
    if problems:
        raise IntakeError(" ".join(problems))
    fmt = DATE_FORMATS[date_format]
    result = IntakeResult(kind=kind, total_rows=len(rows), mapped_fields=tuple(f for f, h in mapping.items() if h))
    seen_rows: dict[tuple, int] = {}

    for raw in rows:
        number = int(raw["__row__"])
        values = {f: (raw.get(h) or "").strip() for f, h in mapping.items() if h}
        if "__shape_error__" in raw:
            result.rejected.append({"row": number, "reasons": [f"Row {raw['__shape_error__']}."], "values": {}})
            continue
        reasons = []
        for fld, (label, required) in FIELDS[kind].items():
            if required and not values.get(fld):
                reasons.append(f"{label} is blank.")
        parsed_date = _parse_date(values["date"], fmt) if values.get("date") else None
        if values.get("date") and parsed_date is None:
            reasons.append(f"Date '{values['date']}' doesn't match {date_format}.")
        amount = None
        if values.get("amount"):
            try:
                amount = money(values["amount"])
            except ValueError:
                reasons.append(f"Amount '{values['amount']}' isn't a valid dollar amount (max 2 decimals).")
        if kind == "costs" and amount is not None and amount < 0:
            reasons.append("Cost is negative; record refunds or credits separately.")
        # A repeated invoice/bill number is normal (one line per item); an identical
        # row is not, so it's rejected rather than double-counted.
        fingerprint = tuple(sorted(values.items()))
        if fingerprint in seen_rows:
            reasons.append(f"Exact duplicate of row {seen_rows[fingerprint]}; not imported twice.")
        else:
            seen_rows[fingerprint] = number
        if reasons:
            result.rejected.append({"row": number, "reasons": reasons, "values": values})
            continue
        record = {**values, "row": number, "date": parsed_date.isoformat(), "amount": amount}
        result.accepted.append(record)
    return result


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def missing_report(result: IntakeResult) -> list[dict]:
    """Plain-language gaps: [{"level": "problem"|"gap"|"info", "text": ...}]. Counts only, no profit."""
    items: list[dict] = []
    total, accepted = result.total_rows, result.accepted
    noun = "invoice" if result.kind == "invoices" else "cost"
    if result.rejected:
        items.append({"level": "problem", "text": f"{_count(len(result.rejected), 'row')} of {total} couldn't be imported. "
                      "Each one is listed below with the reason; fix them in the file and upload again."})
    if not accepted:
        items.append({"level": "problem", "text": f"No {noun}s were imported."})
        return items
    if "job_id" not in result.mapped_fields:
        items.append({"level": "gap", "text": f"No job number column was chosen, so these {noun}s can't be linked to jobs. "
                      "Profit by job will need a job number."})
    else:
        unlinked = sum(1 for r in accepted if not r.get("job_id"))
        if unlinked:
            what = "have no job number" if result.kind == "invoices" else "aren't linked to a job"
            items.append({"level": "gap", "text": f"{unlinked} of {len(accepted)} imported {noun}s {what}."})
    id_field = "invoice_id" if result.kind == "invoices" else "cost_id"
    counts = Counter(r.get(id_field) for r in accepted if r.get(id_field))
    multi = {i for i, n in counts.items() if n > 1}
    if multi:
        items.append({"level": "info", "text": f"{_count(len(multi), noun)} span more than one line "
                      f"(for example {sorted(multi)[0]}); each line was imported once."})
    if result.kind == "invoices":
        credits = [r for r in accepted if r["amount"] < 0]
        if credits:
            total_credit = -sum((r["amount"] for r in credits), Decimal("0"))
            items.append({"level": "info", "text": f"{_count(len(credits), 'credit or refund line')} "
                          f"(${total_credit:,.2f} total) were imported as negative amounts."})
    else:
        if "cost_type" not in result.mapped_fields:
            items.append({"level": "gap", "text": "No cost type column was chosen, so materials, labor and outsourced "
                          "work can't be told apart."})
        else:
            untyped = sum(1 for r in accepted if not r.get("cost_type"))
            if untyped:
                items.append({"level": "gap", "text": f"{untyped} of {len(accepted)} imported costs have no cost type."})
            if not any(any(w in r.get("cost_type", "").lower() for w in LABOR_WORDS) for r in accepted):
                items.append({"level": "gap", "text": "No labor costs were found. If staff time goes into jobs, "
                              "profit will look higher than it really is until labor is added."})
    dates = sorted(r["date"] for r in accepted)
    items.append({"level": "info", "text": f"{_count(len(accepted), noun)} imported, dated {dates[0]} to {dates[-1]}."})
    return items


def safe_cell(value: str) -> str:
    """Neutralize spreadsheet formula prefixes when a value is written back out to a file."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def rejected_rows_csv(result: IntakeResult) -> str:
    """The rejected rows with reasons, formula-safe, for the owner to fix and re-upload."""
    out = io.StringIO()
    fields = list(FIELDS[result.kind])
    writer = csv.writer(out)
    writer.writerow(["row", "reasons", *fields])
    for item in result.rejected:
        writer.writerow([item["row"], safe_cell(" ".join(item["reasons"])),
                         *[safe_cell(item["values"].get(f, "")) for f in fields]])
    return out.getvalue()
