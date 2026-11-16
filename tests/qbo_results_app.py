"""A test page for QuickBooks results (issue #128, step 7), on made-up reports only.

The question screen (step 6b) on top and the results below, as the flow will be once switched on. With
session_state["second"] set, a matching made-up Sales by Customer Detail cross-checks the sales, so jobs can
be Complete. Run it with `streamlit run tests/qbo_results_app.py`, or through AppTest
(tests/test_quickbooks_results.py). No page of the app links here: QuickBooks uploads stay refused.
"""
import sys
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import streamlit as st  # noqa: E402

import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_results as qresults  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402
import quickbooks_screens as qscreens  # noqa: E402

L, S = fx.line, fx.sale
X, Y = "Customer X (fictional)", "Customer Y (fictional)"


@st.cache_data
def made_up_reports() -> tuple[bytes, bytes]:
    """Job A for Customer X (a $4,000 invoice, $1,000 of materials); Job B for Customer Y (a $1,500 invoice,
    $2,100 of materials: a job losing money); a $500 office expense. The second report lists the same sales."""
    pnl = fx.xlsx(fx.report_rows({
        "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                      L(3, "Invoice", "1002", f"{Y}:Job B", D("1500"), None)])],
        "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", D("1000"), None),
                                        L(6, "Bill", "B-2", f"{Y}:Job B", D("2100"), None)]),
                     ("Office Supplies", [L(7, "Expense", "", "Office Depot (fictional)", D("500"), None)])]}))
    sbcd = fx.xlsx(fx.sbcd_rows([(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)])]),
                                 (Y, [], [("Job B", [S(3, "Invoice", "1002", "Design", 1, 1500)])])]))
    return pnl, sbcd


st.warning("Test page: made-up data only. Every company, customer, vendor and amount here is fictional.")
pnl_bytes, sbcd_bytes = made_up_reports()
report = qp.read_profit_and_loss_detail("made_up_profit_and_loss_detail.xlsx", pnl_bytes)
check = None
if st.session_state.get("second"):
    check = qc.cross_check(report, qs.read_sales_by_customer_detail("made_up_sales_by_customer.xlsx", sbcd_bytes))
answers = qscreens.question_screen(report, check)
st.divider()
qresults.results_screen(report, answers, check)
