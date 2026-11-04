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
# Saved results written exactly as Excel stores them (17 significant digits). Python writes this
# number as 349.41, since it is the same binary number, so the text is put in the file directly.
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
    cell -> the exact number text to store for that cell."""
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
