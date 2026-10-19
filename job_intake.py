"""MarginX step 1: job-level CSV intake with a "what's missing" report.

One CSV at a time (invoices or costs). The owner confirms a column mapping and a
date format; every row is then either accepted or rejected with a plain reason.
Nothing is silently dropped, repaired, coerced or guessed, and cell text is
always data (spreadsheet formulas are never evaluated). This step reports gaps
only; it does not calculate profit (build step 3, docs/MVP_SPEC.md).
"""
from __future__ import annotations

import csv
import hashlib
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

# Normalized header words that suggest a field. Suggestions only; the owner confirms.
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
    """The format that reads the most dates, if no other format reads as many; else None.

    For example, a file with "10/31/2026" can only be month-first. When two formats
    read the dates equally well (every date is like "10/01/2026"), the meaning is
    truly ambiguous and the owner is asked. Dates the chosen format can't read are
    rejected with a reason, never reinterpreted.
    """
    values = [v.strip() for v in values if v and v.strip()]
    counts = {name: sum(1 for v in values if _parse_date(v, fmt)) for name, fmt in DATE_FORMATS.items()}
    best = max(counts.values(), default=0)
    winners = [name for name, n in counts.items() if n == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def date_question(values: list[str]) -> dict | None:
    """When the date format is ambiguous: one example date and what it means in each format.

    Returns {"example": "10/01/2026", "options": {"MM/DD/YYYY": "October 1, 2026", ...}}.
    """
    values = [v.strip() for v in values if v and v.strip()]
    counts = {name: sum(1 for v in values if _parse_date(v, fmt)) for name, fmt in DATE_FORMATS.items()}
    best = max(counts.values(), default=0)
    tied = [name for name, n in counts.items() if n == best and n > 0]
    example = next((v for v in values if sum(1 for n in tied if _parse_date(v, DATE_FORMATS[n])) > 1), None)
    if example is None:
        return None
    options = {}
    for name in tied:
        d = _parse_date(example, DATE_FORMATS[name])
        if d:
            options[name] = f"{d:%B} {d.day}, {d.year}"
    return {"example": example, "options": options}


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
    if len(full) == 1 and score[full[0]] >= max(score.values()):
        return full[0]
    candidates = full or list(KINDS)
    ranked = sorted(candidates, key=lambda k: score[k], reverse=True)
    if len(ranked) > 1 and score[ranked[0]] == score[ranked[1]]:
        return None
    return ranked[0] if score[ranked[0]] > 0 else None


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
                items.append({"level": "gap", "text": f"{untyped} of {len(accepted)} imported costs have no cost type."})
            if not any(is_labor(r.get("cost_type", "")) for r in accepted):
                items.append({"level": "gap", "text": "No labor costs were found. If staff time goes into jobs, "
                              "profit will look higher than it really is until labor is added."})
    dates = sorted(r["date"] for r in accepted)
    items.append({"level": "info", "text": f"{_count(len(accepted), noun)} imported, dated {dates[0]} to {dates[-1]}."})
    return items


def confirmation_key(data: bytes, kind: str, mapping: dict[str, str | None], date_format: str) -> str:
    """Identifies exactly what the owner confirmed: this file, this mapping, this date format."""
    choices = repr((kind, sorted((k, v or "") for k, v in mapping.items()), date_format)).encode("utf-8")
    return "confirm-" + hashlib.sha256(hashlib.sha256(data).digest() + choices).hexdigest()[:24]


def upload_allowed(use_sample: bool, has_upload: bool, confirmed_made_up: bool) -> bool:
    """Pilot gate (D-003): an own file is processed only after the owner confirms it is made-up or anonymized."""
    return use_sample or (has_upload and confirmed_made_up)


def safe_cell(value: str) -> str:
    """Spreadsheet-safe export policy: prefix an apostrophe when a cell could be read as a formula.

    That is when it starts with = + - @ or a tab, carriage return or line feed, or
    when it reaches one of = + - @ after leading spaces or control characters.
    """
    text = "" if value is None else str(value)
    stripped = text.lstrip("".join(chr(c) for c in range(33)))
    risky = text.startswith(FORMULA_PREFIXES) or stripped.startswith(FORMULA_PREFIXES[:4])
    return "'" + text if risky else text


def rejected_rows_csv(result: IntakeResult) -> str:
    """Spreadsheet-safe repair export of rejected records, to fix and re-upload.

    Every original column appears under its original header and in its original
    order, plus any extra cells from over-long rows; short rows are padded with
    blanks. This is not an exact byte-for-byte copy: cells and headers that could
    be read as formulas get a leading apostrophe (see safe_cell).
    """
    width = max([len(result.headers), *(len(item["cells"]) for item in result.rejected)])
    taken: set[str] = set()

    def unique(name: str) -> str:
        # Uniqueness is checked on the final, spreadsheet-safe header as read_csv
        # compares it, so the repair file always re-imports. Original headers stay
        # in their columns; only a clashing one gets a numeric suffix.
        candidate, n = name, 1
        while candidate.strip().lower() in taken:
            n += 1
            candidate = f"{name}_{n}"
        taken.add(candidate.strip().lower())
        return candidate

    shop = [unique(safe_cell(h)) for h in result.headers]
    meta = [unique("marginx_row"), unique("marginx_reasons")]
    extra = [unique(f"extra_cell_{i}") for i in range(1, width - len(result.headers) + 1)]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([*meta, *shop, *extra])
    for item in result.rejected:
        cells = list(item["cells"]) + [""] * (width - len(item["cells"]))
        writer.writerow([item["row"], safe_cell(" ".join(item["reasons"])), *[safe_cell(c) for c in cells]])
    return out.getvalue()
