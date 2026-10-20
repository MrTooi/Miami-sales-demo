"""MargenX public demo link (D-006): the made-up demo sign shop only, and no way to upload a file.

This is the file the hosting service runs for the link the team sends to shop owners
(docs/DEMO_LINK.md). It switches on demo-only mode (pilot_safety.DEMO_ENV) before the page runs,
so the page shows only the clean demo shop: no upload box, no file choice, and pilot mode can't
be switched on. st.navigation replaces the automatic pages/ list, so no other page can be opened.
"""
import os

import streamlit as st

from pilot_safety import DEMO_ENV

os.environ[DEMO_ENV] = "1"
st.navigation([st.Page("pages/1_MargenX_Import.py", title="MargenX", default=True)]).run()
