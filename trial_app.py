"""The website trial's entry point (issue #131, lean v1.2; D-009). PR A1, the uploads PR.

Run with:  streamlit run trial_app.py --server.address 127.0.0.1
The server listens on this machine only; the Cloudflare tunnel (PR A2) is the only way in. In the image,
the launcher (deploy/trial/launch.py) starts it and supervises it.

It serves the same single MargenX page as marginx_pilot.py, with trial_access.TrialGate in front of
every request: the page, the live connection, media and uploads. Without every trial setting
(TrialConfig.from_environ), the gate refuses every request. The laptop pilot (marginx_pilot.py and
the Desktop launcher) doesn't use this file and is unchanged.

Before the app is made (uploads plan v7):
- MargenX's own upload store replaces Streamlit's (trial_access.upload_store_class): Streamlit builds its
  runtime from that module attribute when the app starts, so the running copy uses it (tested).
- Starlette's multipart parser keeps every uploaded part in memory, never in a temporary file on disk: its
  spool threshold is raised above the gate's body limit (by default, a part over 1 MB goes to disk).
- Streamlit's log line for an uncaught page error keeps only the error's type, never its message or its
  traceback, which could quote a value from a file.
"""
import logging
import os

import streamlit as st
import streamlit.runtime.memory_uploaded_file_manager as upload_manager
from starlette.formparsers import MultiPartParser
from starlette.middleware import Middleware

import trial_access as ta


def prepare() -> None:
    upload_manager.MemoryUploadedFileManager = ta.upload_store_class()
    MultiPartParser.spool_max_size = ta.MAX_UPLOAD_BODY + 1
    for name in ("streamlit.error_util", "streamlit.runtime.scriptrunner.script_runner"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, ta.TypeOnly) for f in logger.filters):
            logger.addFilter(ta.TypeOnly())


prepare()
app = st.App("marginx_pilot.py",
             middleware=[Middleware(ta.TrialGate, config=ta.TrialConfig.from_environ(os.environ))])
