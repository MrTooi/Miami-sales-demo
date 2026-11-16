"""A test page for the QuickBooks question screen (issue #128, step 6b), on a made-up report only.

Run it with `streamlit run tests/qbo_question_screen_app.py` to look at the screen, or through Streamlit's
AppTest (tests/test_quickbooks_screens.py). No page of the app links here: QuickBooks uploads stay refused
until the switch-on PR.
"""
import sys
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import streamlit as st  # noqa: E402

import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_screens as qscreens  # noqa: E402

L = fx.line
X = "Customer X (fictional)"


@st.cache_data
def made_up_report_bytes() -> bytes:
    """Job A for Customer X, a sale with no job, a credit memo, a deposit, a vendor bill and an office expense."""
    return fx.xlsx(fx.report_rows({
        "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                      L(3, "Invoice", "1002", X, D("700"), None),
                                      L(4, "Credit Memo", "1003", f"{X}:Job A", D("-200"), None),
                                      L(5, "Deposit", "", f"{X}:Job A", D("50"), None, "", "Checking")])],
        "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", D("1000"), None),
                                        L(6, "Bill", "B-2", "Garden Supply (fictional)", D("900"), None)]),
                     ("Office Supplies", [L(7, "Expense", "", "Office Depot (fictional)", D("500"), None)])]}))


st.warning("Test page: made-up data only. Every company, customer, vendor and amount here is fictional.")
report = qp.read_profit_and_loss_detail("made_up_profit_and_loss_detail.xlsx", made_up_report_bytes())
answers = qscreens.question_screen(report)
st.session_state["qbo-test-answers"] = answers  # for the tests
