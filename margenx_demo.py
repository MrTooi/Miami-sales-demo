"""MargenX public demo link (D-006): the made-up demo sign shop only, and no way to upload a file.

This is the file the hosting service runs for the link the team sends to shop owners
(docs/DEMO_LINK.md). The page recognises it as the app's main script (pilot_safety.DEMO_ENTRY) and
then shows only the clean demo shop: no upload box, no file choice, and pilot mode can't be switched
on. Nothing process-wide is changed.

Fail closed: before the page runs, this checks with the same function the page uses that demo mode
is confirmed. If Streamlit can't say which file started the app, nothing is shown at all, so the
normal app (with its upload box) can never appear on the demo link.
st.navigation replaces the automatic pages/ list, so no other page can be opened.
"""
import streamlit as st

import pilot_safety as ps

if not ps.demo_only(ps.running_main_script()):
    st.error("This demo can't start right now. Please try again later.")
    st.stop()

st.navigation([st.Page("pages/1_MargenX_Import.py", title="MargenX", default=True)]).run()
