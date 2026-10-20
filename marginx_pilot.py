"""MarginX pilot entry point: only the MarginX page, nothing else.

Pilot sessions start the app with this file (docs/PILOT_VISIT_CHECKLIST.md), so the older
Ledger demo in app.py, with its own upload boxes and SQLite storage, isn't reachable at all.
st.navigation replaces the automatic pages/ list, so no other page can be opened either.
"""
import streamlit as st

st.navigation([st.Page("pages/1_MarginX_Import.py", title="MarginX", default=True)]).run()
