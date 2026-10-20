"""MargenX pilot entry point: only the MargenX page, nothing else.

Pilot sessions start the app with this file (docs/PILOT_VISIT_CHECKLIST.md). app.py now opens
the same single page; the older Ledger screen with its own upload boxes and SQLite storage was retired.
st.navigation replaces the automatic pages/ list, so no other page can be opened either.
"""
import streamlit as st

st.navigation([st.Page("pages/1_MargenX_Import.py", title="MargenX", default=True)]).run()
