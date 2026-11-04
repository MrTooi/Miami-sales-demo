"""Made-up QuickBooks Online reports in the layouts seen on 2026-10-26 (issue #128, "Layouts seen").

Every company, customer, vendor, number and amount here is made up. Only the shape copies what
QuickBooks Online's "Export to Excel" wrote for Profit and Loss Detail: the title rows, the column
names, text dates, nested account headings closed by "Total for ..." rows (written as formulas with
their saved results), "Total Income" / "Gross Profit" summary rows, an "Other Income" heading in
column B, three empty rows and the basis footer. No Intuit file is used or kept.
"""
from __future__ import annotations

import io
import re
import zipfile
from decimal import Decimal

from openpyxl import Workbook

COMPANY = "Biscayne Landscaping (fictional)"
PERIOD = "January 1-October 26, 2026"
FOOTER = "Accrual Basis Monday, October 26, 2026 07:04 PM GMTZ"
COLUMNS = [None, "Transaction date", "Transaction type", "Num", "Name", "Location", "Class full name", "Description",
           "Item split account", "Amount", "Balance"]


def line(day: int, kind: str, num: str, name: str, amount: float, balance: float, description: str = "",
         split: str = "Accounts Receivable (A/R)") -> list:
    """One report line, as QuickBooks writes it: column A empty, the date as text (MM/DD/YYYY)."""
    return [None, f"10/{day:02d}/2026", kind, num, name, "", "", description, split, amount, balance]


def total(label: str, amount: float) -> list:
    """A "Total for ..." or summary row: the label in column A, the amount in the Amount column (J)."""
    return [label, None, None, None, None, None, None, None, None, amount]


# The report body, Excel rows 6 to 36. Fuel's stored totals carry the float noise seen in the real
# export (STORED below); its lines add up to exactly 349.41.
BODY = [
    ["Ordinary Income/Expenses"],                                                                    # 6
    ["Income"],                                                                                      # 7
    ["Design income"],                                                                               # 8
    line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 900.0, 900.0, "Patio design"),        # 9
    line(9, "Sales Receipt", "1002", "Bay Clinic (fictional)", 300.0, 1200.0, "Planters", "Checking"),  # 10
    total("Total for Design income", 1200.0),                                                        # 11
    total("Total Income", 1200.0),                                                                   # 12
    ["Cost of Goods Sold"],                                                                          # 13
    ["Cost of Goods Sold"],                                                                          # 14
    line(2, "Invoice", "1001", "Coral Cafe (fictional):Patio", 150.0, 150.0, "Pavers"),              # 15
    total("Total Cost of Goods Sold", 150.0),                                                        # 16
    total("Total Cost of Goods Sold", 150.0),                                                        # 17
    total("Gross Profit", 1050.0),                                                                   # 18
    ["Expenses"],                                                                                    # 19
    ["Automobile"],                                                                                  # 20
    ["Fuel"],                                                                                        # 21
    line(4, "Expense", "", "Bayside Fuel (fictional)", 200.11, 200.11, "Truck fuel", "Mastercard"),  # 22
    line(18, "Expense", "", "Bayside Fuel (fictional)", 149.30, 349.41, "Truck fuel", "Mastercard"),  # 23
    total("Total for Fuel", 349.40999999999997),                                                     # 24
    total("Total for Automobile with sub-accounts", 349.40999999999997),                             # 25
    total("Total Expenses", 349.40999999999997),                                                     # 26
    total("Net Ordinary Income", 700.59),                                                            # 27
    ["Other Income/Expense"],                                                                        # 28
    [None, "Other Income"],                                                                          # 29
    ["Other Expense"],                                                                               # 30
    ["Miscellaneous"],                                                                               # 31
    line(20, "Check", "305", "County Clerk (fictional)", 80.0, 80.0, "Late filing fee", "Checking"),  # 32
    total("Total for Miscellaneous", 80.0),                                                          # 33
    total("Total Other Expense", 80.0),                                                              # 34
    total("Net Other Income", -80.0),                                                                # 35
    total("Net Income", 620.59),                                                                     # 36
]
FIRST_BODY_ROW = 6
FOOTER_ROW = 40
# Totals as QuickBooks writes them: a formula over the lines, with its saved result.
FORMULAS = {"J11": "J9+J10", "J12": "J11", "J16": "J15", "J17": "J16", "J18": "J12-J17", "J24": "J22+J23",
            "J25": "J24", "J26": "J25", "J33": "J32", "J34": "J33"}
# Saved results written exactly as Excel stores them (17 significant digits). 349.40999999999997 is a
# different number from 349.41, but openpyxl writes numbers with at most 16 significant digits, which
# would store it as 349.41, so the text is put in the file directly.
STORED = {"J24": "349.40999999999997", "J25": "349.40999999999997", "J26": "349.40999999999997"}


def pnl_rows(*, company=COMPANY, title="Profit and Loss Detail", period=PERIOD, columns=None, body=None,
             footer=FOOTER, row4=None) -> list[list]:
    """A whole Profit and Loss Detail report, row by row, with one part changed if asked."""
    head = [[company] if company is not None else [], [title], [period], row4 or [], list(columns or COLUMNS)]
    tail = [[], [], [], [footer]] if footer is not None else []
    return [*head, *(BODY if body is None else body), *tail]


def xlsx(rows, *, formulas: dict[str, str] | None = None, stored: dict[str, str] | None = None,
         sheets: int = 1) -> bytes:
    """An Excel file of the rows. formulas: cell -> formula, written with the cell's value as its saved
    result, as QuickBooks' export does (openpyxl alone would save a formula with no result). stored:
    cell -> the exact number text to store for that cell. A Decimal value is always stored exactly as written,
    as the real export stores amounts ("870.56"): openpyxl alone would turn it into a 16-digit float
    ("870.5599999999999"), which MargenX rightly refuses as not exact cents."""
    from openpyxl.utils import get_column_letter

    exact = {}
    for number, row in enumerate(rows, 1):
        for column, value in enumerate(row, 1):
            if isinstance(value, Decimal):
                exact[f"{get_column_letter(column)}{number}"] = format(value, "f")
    stored = {**exact, **(stored or {})}
    book = Workbook()
    for index in range(sheets):
        sheet = book.active if index == 0 else book.create_sheet()
        for row in rows:
            sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    data = out.getvalue()
    if not (formulas or stored):
        return data
    source, result = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = content.decode()
                for ref, number in (stored or {}).items():
                    text, count = re.subn(rf'(<c r="{ref}"[^>]*><v>)[^<]*(</v>)', rf"\g<1>{number}\g<2>", text)
                    assert count == 1, f"cell {ref} not found"
                for ref, formula in (formulas or {}).items():
                    text, count = re.subn(rf'(<c r="{ref}"[^>]*>)(<v>)', rf"\1<f>{formula}</f>\2", text)
                    assert count == 1, f"cell {ref} not found"
                content = text.encode()
            target.writestr(item, content)
    return result.getvalue()


def csv_bytes(rows) -> bytes:
    def cell(value):
        text = "" if value is None else str(value)
        return f'"{text}"' if "," in text else text
    return "\n".join(",".join(cell(v) for v in row) for row in rows).encode()


def report_rows(sections: dict[str, list[tuple[str, list[list]]]]) -> list[list]:
    """A whole Profit and Loss Detail from sections of accounts and their lines, with every total and
    summary row worked out here (in whole cents) in the layout seen. sections maps "Income", "Cost of
    Goods Sold", "Expenses", "Other Income" or "Other Expense" to [(account, [lines])]."""
    def cents(value) -> int:
        """Exact: a value with fractions of a cent is refused, never rounded (the automated review of 7da2180)."""
        exact = Decimal(str(value))
        if exact != exact.quantize(Decimal("0.01")):
            raise ValueError(f"{value} isn't a whole number of cents")
        return int(exact * 100)

    def money(c: int) -> Decimal:
        return Decimal(c) / 100  # written to the workbook exactly

    body: list[list] = [["Ordinary Income/Expenses"]]
    sums: dict[str, int] = {}

    def section(name: str) -> None:
        accounts = sections.get(name)
        if not accounts:
            sums[name] = 0
            return
        body.append([name])
        total = 0
        for account, lines in accounts:
            body.append([account])
            account_total = sum(cents(l[9]) for l in lines)
            body.extend(lines)
            body.append(total_row(f"Total for {account}", money(account_total)))
            total += account_total
        body.append(total_row(f"Total {name}", money(total)))
        sums[name] = total

    def total_row(label, amount):
        return [label, None, None, None, None, None, None, None, None, amount]

    section("Income")
    section("Cost of Goods Sold")
    body.append(total_row("Gross Profit", money(sums["Income"] - sums["Cost of Goods Sold"])))
    section("Expenses")
    ordinary = sums["Income"] - sums["Cost of Goods Sold"] - sums["Expenses"]
    body.append(total_row("Net Ordinary Income", money(ordinary)))
    if sections.get("Other Income") or sections.get("Other Expense"):
        body.append(["Other Income/Expense"])
        if sections.get("Other Income"):
            section("Other Income")
        else:
            body.append([None, "Other Income"])
            sums["Other Income"] = 0
        section("Other Expense")
        body.append(total_row("Net Other Income", money(sums["Other Income"] - sums["Other Expense"])))
        ordinary += sums["Other Income"] - sums["Other Expense"]
    body.append(total_row("Net Income", money(ordinary)))
    return pnl_rows(body=body)


# --- Sales by Customer Detail, in the layout seen (step 5a) ----------------------------------------

SBCD_COLUMNS = [None, "Transaction date", "Transaction type", "Num", "Product/Service full name", "Description",
                "Quantity", "Sales price", "Amount", "Balance"]


def sale(day: int, kind: str, num: str, product: str, quantity, price, amount=None, description: str = "") -> list:
    """One Sales by Customer Detail line, as QuickBooks writes it. Amount = Quantity × Sales price unless given."""
    quantity, price = Decimal(str(quantity)), Decimal(str(price))
    if amount is None:
        amount = (quantity * price).quantize(Decimal("0.01"))
    return [None, f"10/{day:02d}/2026", kind, num, product, description, quantity, price, Decimal(str(amount)), None]


def sbcd_rows(customers, *, company=COMPANY, period=PERIOD, footer=FOOTER, row4=None, columns=None) -> list[list]:
    """A whole Sales by Customer Detail from customers given as (name, own lines, [(sub-customer, lines)]), with
    every total (Amount and Quantity) worked out exactly here, and the grand TOTAL."""
    def sums(lines):
        return (sum((Decimal(str(l[8])) for l in lines), Decimal("0")),
                sum((Decimal(str(l[6])) for l in lines if l[6] not in (None, "")), Decimal("0")))

    def total(label, lines):
        amount, quantity = sums(lines)
        return [label, None, None, None, None, None, quantity, None, amount]

    body, everything = [], []
    for name, lines, subs in customers:
        body.append([name])
        body.extend(lines)
        if lines or not subs:
            body.append(total(f"Total for {name}", lines))
        mine = list(lines)
        for sub, sub_lines in subs:
            body.append([sub])
            body.extend(sub_lines)
            body.append(total(f"Total for {sub}", sub_lines))
            mine += sub_lines
        if subs:
            body.append(total(f"Total for {name} with sub-customers", mine))
        everything += mine
    body.append(total("TOTAL", everything))
    head = [[company], ["Sales by Customer Detail"], [period], row4 or [], list(columns or SBCD_COLUMNS)]
    return [*head, *body, [], [], [], [footer]]
