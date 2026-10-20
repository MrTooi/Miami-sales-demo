"""MargenX: the app's main entry point (`streamlit run app.py`). It opens only the MargenX page.

The older dashboard screen that used to live here (Ledger, the product's earlier name and design)
was retired on 2026-10-20 by the owner's decision. That screen kept imports in a SQLite file on the
laptop, so it was switched off in pilot mode. Now no entry point can reach it. The page itself
applies the pilot rules (pilot_safety.py). marginx_pilot.py does the same thing and is still the
documented way to start a pilot visit (docs/PILOT_VISIT_CHECKLIST.md).
st.navigation replaces the automatic pages/ list, so no other page can be opened.
"""
import streamlit as st

st.navigation([st.Page("pages/1_MargenX_Import.py", title="MargenX", default=True)]).run()
