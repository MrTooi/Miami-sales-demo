"""MarginX step 1: job-level CSV intake with a "what's missing" report.

One CSV at a time (invoices or costs). MarginX works out the file type, column
mapping and date format, applies them only when they are unambiguous, and asks the
owner otherwise; every row is then either accepted or rejected with a plain reason.
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

# Normalized header words that suggest a field. A unique match is applied (and shown,
# and changeable); two plausible money or date columns are always asked about.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "invoice_id": ("invoice id", "invoice", "invoice no", "invoice number", "invoice num", "num", "no", "number", "doc number"),
    "cost_id": ("bill id", "bill", "bill no", "bill number", "reference", "ref", "ref no", "num", "number"),
    "date": ("date", "invoice date", "bill date", "txn date", "transaction date"),
    "customer": ("customer", "customer name", "client", "client name", "name", "bill to"),
    "vendor": ("vendor", "vendor name", "payee", "supplier", "name"),
    # Never balances: an open/outstanding balance is what's still owed, not what was billed.
    "amount": ("amount", "total", "amt", "amount usd", "amt usd", "total amount", "invoice total"),
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
_LABOR = re.compile(r"\b(?<!non[- ])(?<!non)(" + "|".join(LABOR_WORDS) + r")\b", re.IGNORECASE)


def is_labor(cost_type: str) -> bool:
    """A whole-word labor category; "Non-labor" or "nonlabor" doesn't count."""
    return bool(_LABOR.search(cost_type or ""))


# Header words that point to one kind of file. "bill to" (an invoice field) is
# removed before looking for the cost word "bill".
INVOICE_WORDS = {"invoice", "invoices", "customer", "client", "sales", "sold"}
COST_WORDS = {"vendor", "payee", "supplier", "expense", "expenses", "purchase", "bill", "bills"}
# Evidence that a file really is bills/expenses; "payee" alone also fits bank statements.
STRONG_COST_WORDS = (COST_WORDS - {"payee"}) | {"cost", "costs"}
# Words typical of bank or card statements, whose rows are cash movements, not costs.
BANK_WORDS = {"deposit", "deposits", "withdrawal", "withdrawals", "debit", "debits", "transfer", "transfers",
              "balance", "posted", "statement", "check", "cheque"}
# Headers describing what's still owed, never the amount billed.
BALANCE_WORDS = {"balance", "due", "outstanding", "owed", "unpaid", "remaining", "open"}

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
MAX_FILE_BYTES = 5_000_000


class IntakeError(ValueError):
    """The file as a whole can't be read; nothing was imported."""


@dataclass
class IntakeResult:
    kind: str
    total_rows: int
    accepted: list[dict] = field(default_factory=list)
    # {"row": n, "reasons": [...], "values": {field: value}, "cells": original cells}
    rejected: list[dict] = field(default_factory=list)
    mapped_fields: tuple[str, ...] = ()
    headers: tuple[str, ...] = ()


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", header.lower()).strip()


@dataclass(frozen=True)
class Record:
    """One CSV record exactly as it appears in the file. Metadata never mixes with cells."""
    row: int  # spreadsheet row number (header = row 1)
    cells: tuple[str, ...]


def _is_blank_line(cells: list[str]) -> bool:
    # Only a truly empty line parses to no cells. Anything else, including "",
    # spaces or a line of separators (",,"), is a record and gets validated.
    return not cells


def read_csv(data: bytes) -> tuple[list[str], list[Record]]:
    """Parse CSV bytes into headers and records, refusing anything ambiguous."""
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
        # Row numbers are record numbers as a spreadsheet shows them (header = row 1),
        # counted before empty lines are skipped. A quoted cell spanning several text
        # lines is still one row, so this can differ from a text editor's line number.
        table = [(number, row) for number, row in enumerate(reader, start=1) if not _is_blank_line(row)]
    except csv.Error as exc:
        raise IntakeError(f"File isn't valid CSV ({exc}). Check for unbalanced quotes.") from exc
    if not table:
        raise IntakeError("File is empty.")
    headers = list(table[0][1])  # kept exactly as written, so exports round-trip
    if len(headers) < 2:
        raise IntakeError("Only one column was found. The file may use a separator other than commas.")
    if any(not h.strip() for h in headers):
        raise IntakeError("A column has no header name. Every column needs a header.")
    if len({h.strip().lower() for h in headers}) != len(headers):
        raise IntakeError("Two columns have the same header name.")
    return headers, [Record(number, tuple(cells)) for number, cells in table[1:]]


def suggest_mapping(headers: list[str], kind: str) -> dict[str, str | None]:
    """Field -> header where exactly one column fits; None where none or (for money and dates) several do."""
    if kind not in KINDS:
        raise ValueError(f"Unknown file type: {kind}")
    normalized = {h: _norm(h) for h in headers}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for fld in FIELDS[kind]:
        candidates = [_norm(fld.replace("_", " ")), *SYNONYMS.get(fld, ())]
        matches = [h for h, n in normalized.items() if n in candidates and h not in used]
        if fld in ("amount", "date") and len(matches) > 1:
            # Two plausible money or date columns (e.g. "Amount" and "Total", or "Date"
            # and "Invoice Date"): never pick one silently; the owner is asked.
            mapping[fld] = None
            continue
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
    amount = mapping.get("amount")
    if amount and is_balance_column(amount):
        # Refused even when chosen by hand: what's still owed isn't what was billed.
        what = "invoice" if kind == "invoices" else "bill"
        problems.append(f"'{amount}' looks like a balance still owed, not the amount billed. "
                        f"Choose the column with the {what} or line total.")
    return problems


def is_balance_column(header: str) -> bool:
    """Headers like "Open Balance", "Amount Due" or "Outstanding" describe what's still owed."""
    return bool(set(_norm(header).split()) & BALANCE_WORDS)


def suggest_date_format(values: list[str]) -> str | None:
    """The format that reads the most dates, if no other format reads as many; else None.

    For example, a file with "10/31/2026" can only be month-first. When two formats
    read the dates equally well (every date is like "10/01/2026"), the meaning is
    truly ambiguous and the owner is asked. Dates the chosen format can't read are
    rejected with a reason, never reinterpreted.
    """
    tied = _tied_formats(values)
    if not tied:
        return None
    if len(tied) > 1:
        # Formats that read every date as the same day (e.g. only "01/01/2026") make
        # no difference; otherwise the owner is asked.
        readings = [[_parse_date(v, DATE_FORMATS[name]) for v in _clean(values)] for name in tied]
        if any(r != readings[0] for r in readings):
            return None
    # Only when no date is readable solely by another format: a file mixing two
    # conventions (e.g. some dates ISO, some month-first) is asked about, because its
    # ambiguous dates could belong to either.
    chosen = DATE_FORMATS[tied[0]]
    mixed = any(not _parse_date(v, chosen) and any(_parse_date(v, f) for f in DATE_FORMATS.values())
                for v in _clean(values))
    return None if mixed else tied[0]


def _clean(values: list[str]) -> list[str]:
    return [v.strip() for v in values if v and v.strip()]


def _tied_formats(values: list[str]) -> list[str]:
    """The formats that read the most dates (none if no format reads any)."""
    values = _clean(values)
    counts = {name: sum(1 for v in values if _parse_date(v, fmt)) for name, fmt in DATE_FORMATS.items()}
    best = max(counts.values(), default=0)
    return [name for name, n in counts.items() if n == best] if best > 0 else []


def date_question(values: list[str]) -> dict | None:
    """When the date format is ambiguous: one example date and what it means in every tied format.

    Returns {"example": "10/01/2026", "options": {"MM/DD/YYYY": "October 1, 2026", ...}},
    or None when no single date can show every tied format a different meaning
    (the caller then asks for the main format directly).
    """
    tied = _tied_formats(values)
    if len(tied) < 2:
        return None  # nothing to choose between
    for example in _clean(values):
        dates = [_parse_date(example, DATE_FORMATS[name]) for name in tied]
        if all(dates) and len(set(dates)) == len(dates):
            return {"example": example,
                    "options": {name: f"{d:%B} {d.day}, {d.year}" for name, d in zip(tied, dates)}}
    return None


def detect_kind(headers: list[str]) -> str | None:
    """Invoices or costs, worked out from the headers; None when it can't be told apart.

    A kind whose required columns are all recognised wins. If both or neither are
    complete, distinctive header words decide, and a tie returns None.
    """
    def complete(kind: str) -> bool:
        mapping = suggest_mapping(headers, kind)
        return all(mapping[f] for f, (_, required) in FIELDS[kind].items() if required)

    tokens = set(" ".join(_norm(h).replace("bill to", "") for h in headers).split())
    score = {"invoices": len(tokens & INVOICE_WORDS), "costs": len(tokens & COST_WORDS)}
    full = [k for k in KINDS if complete(k)]
    if len(full) == 2:
        return None  # the headers fit both kinds of file: ask, never guess
    if len(full) == 1 and score[full[0]] >= max(score.values()):
        found = full[0]
    else:
        candidates = full or list(KINDS)
        ranked = sorted(candidates, key=lambda k: score[k], reverse=True)
        if (len(ranked) > 1 and score[ranked[0]] == score[ranked[1]]) or score[ranked[0]] == 0:
            return None
        found = ranked[0]
    if found == "costs" and (not tokens & STRONG_COST_WORDS or tokens & BANK_WORDS):
        # "Date, Payee, Amount" is also what a bank or card statement looks like, where
        # deposits and transfers aren't costs (MVP spec). Without bill/expense evidence,
        # or with bank-statement words, the owner is asked.
        return None
    return found


def _parse_date(value: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), fmt).date()
    except ValueError:
        return None


def column_values(headers: list[str], records: list[Record], header: str) -> list[str]:
    """The cells of one column, from records whose cell count matches the header."""
    index = headers.index(header)
    return [r.cells[index] for r in records if len(r.cells) == len(headers)]


def intake(headers: list[str], records: list[Record], mapping: dict[str, str | None], kind: str,
           date_format: str) -> IntakeResult:
    """Accept or reject every record with a reason. Raises IntakeError if the mapping is unusable."""
    if kind not in KINDS:
        raise IntakeError(f"Unknown file type: {kind}")
    if date_format not in DATE_FORMATS:
        raise IntakeError("Choose the date format used in the file.")
    problems = validate_mapping(mapping, headers, kind)
    if problems:
        raise IntakeError(" ".join(problems))
    fmt = DATE_FORMATS[date_format]
    index = {f: headers.index(h) for f, h in mapping.items() if h}
    result = IntakeResult(kind=kind, total_rows=len(records), mapped_fields=tuple(index), headers=tuple(headers))
    seen_rows: dict[tuple[str, ...], int] = {}

    for rec in records:
        number = rec.row
        if len(rec.cells) != len(headers):
            result.rejected.append({"row": number, "cells": rec.cells, "values": {},
                                    "reasons": [f"Row has {len(rec.cells)} cells, header has {len(headers)}."]})
            continue
        values = {f: rec.cells[i].strip() for f, i in index.items()}
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
        # A repeated invoice/bill number is normal (one line per item); a row that is
        # identical cell for cell, including unmapped columns, is rejected rather than
        # double-counted.
        if rec.cells in seen_rows:
            reasons.append(f"Exact duplicate of row {seen_rows[rec.cells]}; not imported twice.")
        else:
            seen_rows[rec.cells] = number
        if reasons:
            result.rejected.append({"row": number, "cells": rec.cells, "values": values, "reasons": reasons})
            continue
        # Working values are trimmed (so "J-501 " matches "J-501"); the untouched
        # original cells are kept alongside for provenance.
        record = {**values, "row": number, "date": parsed_date.isoformat(), "amount": amount,
                  "original": {f: rec.cells[i] for f, i in index.items()}, "cells": rec.cells}
        result.accepted.append(record)
    return result


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def missing_report(result: IntakeResult) -> list[dict]:
    """Plain-language gaps: [{"level": "problem"|"gap"|"info", "text": ...}]. Counts only, no profit."""
    items: list[dict] = []
    total, accepted = result.total_rows, result.accepted
    # Each accepted record is one line of a file; one invoice or bill can span several lines.
    noun = "invoice line" if result.kind == "invoices" else "cost line"
    entity = "invoice" if result.kind == "invoices" else "bill"
    if result.rejected:
        items.append({"level": "problem", "text": f"{_count(len(result.rejected), 'row')} of {total} couldn't be imported. "
                      "Each one is listed below with the reason. Fix them where the data comes from "
                      "(for example QuickBooks) and export the file again."})
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
        verb = "spans" if len(multi) == 1 else "span"
        items.append({"level": "info", "text": f"{_count(len(multi), entity)} {verb} more than one line "
                      f"(for example {sorted(multi)[0]}); each line was imported once."})
    if result.kind == "invoices":
        credits = sum(1 for r in accepted if r["amount"] < 0)
        if credits:
            items.append({"level": "info", "text": f"{_count(credits, 'credit or refund line')} "
                          "were imported as negative amounts."})
    else:
        if "cost_type" not in result.mapped_fields:
            items.append({"level": "gap", "text": "No cost type column was chosen, so materials, labor and outsourced "
                          "work can't be told apart."})
        else:
            untyped = sum(1 for r in accepted if not r.get("cost_type"))
            if untyped:
                items.append({"level": "gap", "text": f"{untyped} of {len(accepted)} imported cost lines have no cost type."})
            if not any(is_labor(r.get("cost_type", "")) for r in accepted):
                items.append({"level": "gap", "text": "No labor costs were found. If staff time goes into jobs, "
                              "profit will look higher than it really is until labor is added."})
    # Trimming is visible, never silent: e.g. " J-5" and "J-5" are matched as the same job.
    spaced = [(r, f) for r in accepted for f, v in r["original"].items() if v != v.strip()]
    if spaced:
        r, f = spaced[0]
        items.append({"level": "info", "text": f"{_count(len(spaced), 'value')} had extra spaces at the start or end, "
                      f"which MarginX ignores (for example row {r['row']}: {r['original'][f]!r})."})
    dates = sorted(r["date"] for r in accepted)
    distinct = f" ({_count(len(counts), entity)})" if counts and all(r.get(id_field) for r in accepted) else ""
    items.append({"level": "info", "text": f"{_count(len(accepted), noun)} imported{distinct}, dated {dates[0]} to {dates[-1]}."})
    return items


def upload_allowed(use_sample: bool, has_upload: bool, confirmed_made_up: bool) -> bool:
    """Pilot gate (D-003): an own file is processed only after the owner confirms it is made-up."""
    return use_sample or (has_upload and confirmed_made_up)


def safe_cell(value: str) -> str:
    """Spreadsheet-safe display policy: prefix an apostrophe when a cell could be read as a formula.

    That is when it starts with = + - @ or a tab, carriage return or line feed, or
    when it reaches one of = + - @ after leading spaces or control characters.
    Used for on-screen tables, whose toolbar can export CSV. MarginX offers no
    repair-file download: owners fix data where it lives and export again.
    """
    text = "" if value is None else str(value)
    stripped = text.lstrip("".join(chr(c) for c in range(33)))
    risky = text.startswith(FORMULA_PREFIXES) or stripped.startswith(FORMULA_PREFIXES[:4])
    return "'" + text if risky else text

