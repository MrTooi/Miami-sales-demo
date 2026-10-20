"""MargenX public demo link (D-006): the made-up demo sign shop only, and no way to upload a file.

This is the file the hosting service runs for the link the team sends to shop owners
(docs/DEMO_LINK.md). The page recognises it as the app's main script (pilot_safety.DEMO_ENTRY) and
then shows only the clean demo shop: no upload box, no file choice, and pilot mode can't be switched
on. Nothing process-wide is changed. st.navigation replaces the automatic pages/ list, so no other
page can be opened.
"""
import streamlit as st

st.navigation([st.Page("pages/1_MargenX_Import.py", title="MargenX", default=True)]).run()
