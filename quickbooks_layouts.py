"""MargenX: recognising a supported QuickBooks Online report, step 2 of the plan in issue #128.

One report is supported first: **Profit and Loss Detail**, exported from QuickBooks Online with
"Export to Excel", on the accrual basis (Alex's 2026-11-04 decision). A file is recognised only when
it is exactly the layout seen on 2026-10-26 (issue #128, "Layouts seen"):

- Excel row 1: the company name, alone in column A.
- Row 2: the title "Profit and Loss Detail", alone in column A.
- Row 3: the period, such as "January 1-October 26, 2026", alone in column A.
- Row 4: empty. Any other line there (a filter, a currency, an extra header detail) isn't in the
  layout seen, so the file isn't recognised.
- Row 5: the column names. Column A has no name; the others are only names from the layout seen.
- Then the report's own rows, and at the end a footer such as "Accrual Basis Monday, October 26,
  2026 07:04 PM GMTZ", which gives the basis. A cash-basis or missing basis isn't recognised.

Anything else fails closed: the file is refused with a plain reason, and nothing from it is used (S2).

Recognising a report never counts anything. Reading its lines, checking each "Total for ..." against
its lines (step 3) and finding customers, jobs and accounts (step 4) come later, so for now
job_intake still refuses a recognised report, with a reason that says what was recognised.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import quickbooks_rules as qr

PROFIT_AND_LOSS_DETAIL = qr.PROFIT_AND_LOSS_DETAIL

# Column names of Profit and Loss Detail in the layout seen (after column A, which has no name).
# Required: the columns a line needs. Optional: columns seen in the layout that MargenX never uses
# for money; they may be left out of the export (for example Location or Class, which QuickBooks
# shows only for companies that track them). Any other column isn't in the layout seen.
PNL_REQUIRED_COLUMNS = ("Transaction date", "Transaction type", "Num", "Name", "Amount")
PNL_OPTIONAL_COLUMNS = ("Location", "Class full name", "Description", "Item split account", "Balance")

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTH = "(" + "|".join(MONTHS) + ")"
# "January 1-October 26, 2026" (seen), and the same across two years: "November 1, 2025-October 31, 2026".
PERIOD_ONE_YEAR = re.compile(rf"{_MONTH} (\d{{1,2}})-{_MONTH} (\d{{1,2}}), (\d{{4}})")
PERIOD_TWO_YEARS = re.compile(rf"{_MONTH} (\d{{1,2}}), (\d{{4}})-{_MONTH} (\d{{1,2}}), (\d{{4}})")
# "Accrual Basis Monday, October 26, 2026 07:04 PM GMTZ" (seen). Only the time zone seen, "GMTZ", is
# accepted; any other form (an offset such as "GMT-04:00") isn't the layout seen and is refused. The date
# and time say when the report was run; only the basis is used, but every part must be real.
FOOTER = re.compile(rf"(Accrual|Cash) Basis ({'|'.join(WEEKDAYS)}), {_MONTH} (\d{{1,2}}), (\d{{4}}) "
                    r"(\d{1,2}):(\d{2}) (AM|PM) GMTZ")


@dataclass(frozen=True)
class ProfitAndLossDetailLayout:
    """A Profit and Loss Detail file whose layout passed every check. Nothing in it is counted yet."""
    company: str
    period: str  # as written in row 3
    period_start: date
    period_end: date
    basis: str  # "Accrual": the only basis recognised for now
    footer: str  # as written
    footer_row: int  # Excel row number
    header_row: int  # Excel row number of the column names (5)
    columns: dict[str, int]  # column name -> position (0 = column A)
    body: tuple[tuple[int, tuple[str, ...]], ...]  # every non-empty row between the column names and the footer


@dataclass(frozen=True)
class Recognition:
    """What a file was recognised as. layout is set only when problems is empty."""
    report: str  # the report the file claims to be (its title)
    layout: ProfitAndLossDetailLayout | None
    problems: tuple[str, ...]  # plain reasons the file isn't exactly the layout MargenX knows


def _clean(text: str) -> str:
    """Repeated or odd spaces never change what a cell says ("Profit  and Loss Detail")."""
    return " ".join((text or "").split())


def _alone_in_column_a(cells: list[str] | tuple[str, ...]) -> str | None:
    """The text of a row that holds one filled cell, in column A; None for any other row."""
    filled = [i for i, c in enumerate(cells) if c and c.strip()]
    return _clean(cells[0]) if filled == [0] else None


def claims_profit_and_loss_detail(signs: list[str]) -> bool:
    """True when the file's title (one of the QuickBooks signs found above its lines) is "Profit and Loss
    Detail": the file then gets that report's checks, and their plain reasons, rather than the general
    refusal."""
    return any(qr._text(sign) == qr._text(f"the title '{PROFIT_AND_LOSS_DETAIL}'") for sign in signs)


def _date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), MONTHS.index(month) + 1, int(day))
    except ValueError:
        return None


def _period(text: str) -> tuple[date, date] | str:
    """The report's dates from row 3, or the plain reason they can't be read."""
    one, two = PERIOD_ONE_YEAR.fullmatch(text), PERIOD_TWO_YEARS.fullmatch(text)
    if one:
        start_month, start_day, end_month, end_day, year = one.groups()
        start, end = _date(year, start_month, start_day), _date(year, end_month, end_day)
    elif two:
        start_month, start_day, start_year, end_month, end_day, end_year = two.groups()
        start, end = _date(start_year, start_month, start_day), _date(end_year, end_month, end_day)
    else:
        return (f"row 3 says '{text}', which isn't a date range MargenX can read (the layout it knows says, for "
                "example, 'January 1-October 26, 2026')")
    if start is None or end is None:
        return f"row 3 says '{text}', which isn't a real date range"
    if start > end:
        return f"row 3 says '{text}', which starts after it ends"
    return start, end


def _footer(text: str) -> tuple[str, str | None]:
    """(basis, problem) for the report's last line."""
    found = FOOTER.fullmatch(text)
    if not found:
        return "", ("the last line isn't the basis line MargenX knows (for example 'Accrual Basis Monday, "
                    f"October 26, 2026 07:04 PM GMTZ'); it says '{qr._shown(text)}'")
    basis, weekday, month, day, year, hour, minute, _ = found.groups()
    run_on = _date(year, month, day)
    if run_on is None or WEEKDAYS[run_on.weekday()] != weekday or not (1 <= int(hour) <= 12 and int(minute) < 60):
        return "", f"the last line, '{qr._shown(text)}', doesn't hold a real date and time"
    if basis == "Cash":
        return "", "it's a cash-basis report, and MargenX knows only the accrual-basis layout"
    return basis, None


def recognise_profit_and_loss_detail(table: list[tuple[int, list[str]]], *, is_xlsx: bool) -> Recognition:
    """Check a file against the Profit and Loss Detail layout seen (see the module docstring).

    table: every non-empty row of the file with its row number, as job_intake reads it. Every
    problem found is listed, so the owner sees all of them at once.
    """
    problems: list[str] = []
    if not is_xlsx:
        problems.append("it's a CSV file, and MargenX knows only the Excel version of this report")
    rows = dict(table)

    company = _alone_in_column_a(rows.get(1, ()))
    if not company:
        problems.append("row 1 should hold only the company name, in column A")
    if _alone_in_column_a(rows.get(2, ())) != PROFIT_AND_LOSS_DETAIL:
        problems.append("row 2 should hold only the title 'Profit and Loss Detail', in column A")
    period_text = _alone_in_column_a(rows.get(3, ()))
    period: tuple[date, date] | str = "row 3 should hold only the report's dates, in column A"
    if period_text:
        period = _period(period_text)
    if isinstance(period, str):
        problems.append(period)
    if 4 in rows:
        problems.append(f"row 4 should be empty, but it holds '{qr._shown(' '.join(c for c in rows[4] if c.strip()))}'. "
                        "Extra lines above the column names (for example a filter or a currency) aren't in the "
                        "layout MargenX knows")

    columns: dict[str, int] = {}
    header = rows.get(5)
    if header is None:
        problems.append("row 5 should hold the column names")
    else:
        names = list(header)
        while names and not names[-1].strip():
            names.pop()
        if not names or names[0].strip():
            problems.append("column A of row 5 should have no name, as in the layout MargenX knows")
        known = PNL_REQUIRED_COLUMNS + PNL_OPTIONAL_COLUMNS
        for position, raw in enumerate(names[1:], start=1):
            name = _clean(raw)
            if not name:
                problems.append(f"the column in {_letter(position)} has no name")
            elif name not in known:
                problems.append(f"it has a column MargenX doesn't know: '{qr._shown(name)}'")
            elif name in columns:
                problems.append(f"the column '{name}' appears twice")
            else:
                columns[name] = position
        missing = [name for name in PNL_REQUIRED_COLUMNS if name not in columns]
        if missing:
            problems.append("it's missing the column" + ("s " if len(missing) > 1 else " ")
                            + ", ".join(f"'{m}'" for m in missing))
        width = len(names)
        for number, cells in table:
            extra = [i for i, c in enumerate(cells) if i >= width and c.strip()]
            if number > 5 and extra:
                problems.append(f"row {number} has a value in column {_letter(extra[0])}, which has no name")
                break

    basis, footer_text, footer_row = "", "", 0
    after_header = [(n, cells) for n, cells in table if n > 5]
    if not after_header:
        problems.append("there is nothing below the column names")
    else:
        footer_row, last = after_header[-1]
        footer_text = _alone_in_column_a(last) or ""
        if not footer_text:
            problems.append("the last line should be the basis line (for example 'Accrual Basis Monday, October 26, "
                            "2026 07:04 PM GMTZ'), alone in column A, so MargenX can't tell whether it's accrual or cash")
        else:
            basis, problem = _footer(footer_text)
            if problem:
                problems.append(problem)
        for number, cells in after_header[:-1]:
            basis_line = next((_clean(c) for c in cells if qr.BASIS_FOOTER.match(_clean(c))), "")
            if basis_line:  # in any column, not only the first filled cell
                problems.append(f"row {number} looks like a second basis line ('{qr._shown(basis_line)}')")
        if len(after_header) < 2:
            problems.append("it has no rows between the column names and the basis line")

    if problems:
        return Recognition(PROFIT_AND_LOSS_DETAIL, None, tuple(dict.fromkeys(problems)))
    start, end = period  # type: ignore[misc]
    layout = ProfitAndLossDetailLayout(
        company=company, period=period_text, period_start=start, period_end=end, basis=basis, footer=footer_text,
        footer_row=footer_row, header_row=5, columns=columns,
        body=tuple((n, tuple(cells)) for n, cells in after_header[:-1]))
    return Recognition(PROFIT_AND_LOSS_DETAIL, layout, ())


def _letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


# Every QuickBooks report is refused for now (its lines aren't counted yet, steps 3 and 4), so no
# refusal sends the owner to export a QuickBooks report again (the PR #134 review).
NOT_YET = "MargenX can't use QuickBooks reports yet, so nothing from this file was used."
PLAIN_LIST = ("For now, upload a plain list with one row per sale or cost, with columns such as Date, Customer, "
              "Job and Amount.")


def quickbooks_refusal(table: list[tuple[int, list[str]]], title_lines: int, *, is_xlsx: bool) -> str | None:
    """The plain reason a QuickBooks file is refused, or None for any other file (S2).

    Says what made MargenX think the file came from QuickBooks, and what to upload instead.
    - A Profit and Loss Detail file gets its own checks: it is either recognised, or told exactly
      how it differs from the layout MargenX knows. Either way it is still refused for now, because
      its lines aren't read yet (steps 3 and 4).
    - "Transaction List by Customer" mixes invoices with customer payments: never a sales file.
    - Any other QuickBooks look-alike is refused, naming the sign that was found.
    """
    signs = qr.quickbooks_signs(table, title_lines)
    if not signs:
        return None
    if claims_profit_and_loss_detail(signs):
        found = recognise_profit_and_loss_detail(table, is_xlsx=is_xlsx)
        if found.layout:
            layout = found.layout
            return (f"This is QuickBooks' Profit and Loss Detail report for {layout.company} ({layout.period}, "
                    f"{layout.basis.lower()} basis). MargenX recognises this report, but {NOT_YET} {PLAIN_LIST}")
        shown = found.problems[:3]
        more = len(found.problems) - len(shown)
        return (f"This looks like a QuickBooks report (it has the title '{PROFIT_AND_LOSS_DETAIL}'), but it isn't "
                "exactly in the layout MargenX knows: " + "; ".join(shown) + (f" (and {more} more)" if more else "")
                + f". Exporting it again won't help yet: {NOT_YET} {PLAIN_LIST}")
    if any(qr.TRANSACTION_LIST.match(sign.removeprefix("the title '")) for sign in signs if sign.startswith("the title")):
        return ("This looks like QuickBooks' \"Transaction List by Customer\" report. It mixes invoices with "
                "customer payments, and its totals add both together, so it can't be used as a sales file "
                "(and it has no costs). Nothing from this file was used. " + PLAIN_LIST)
    sign = signs[0]
    reason = (f"This looks like a QuickBooks report (it has {sign}), and MargenX can't read this QuickBooks report "
              f"yet, so nothing from this file was used. {PLAIN_LIST}")
    if not sign.startswith("the title"):
        # Says what to change without asking the owner to delete anything (the PR #134 review).
        advice = {"the columns": "rename those columns", "the column": "rename that column"}.get(
            sign.split(" '")[0], "reword the first cell of that row")
        reason += (f" If this file didn't come from QuickBooks, {advice} and upload it again: QuickBooks uses "
                   "the same words.")
    return reason
