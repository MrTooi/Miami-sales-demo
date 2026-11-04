"""The website trial's entry point (issue #131, lean v1.2; D-009). PR A1.

Run with:  streamlit run trial_app.py --server.address 127.0.0.1
The server listens on this machine only; the Cloudflare tunnel (PR A2) is the only way in.

It serves the same single MargenX page as marginx_pilot.py, with trial_access.TrialGate in front of
every request: the page, the live connection, uploads and media. Without every trial setting
(TrialConfig.from_environ), the gate refuses every request. The laptop pilot (marginx_pilot.py and
the Desktop launcher) doesn't use this file and is unchanged.
"""
import os

import streamlit as st
from starlette.middleware import Middleware

import trial_access as ta

app = st.App("marginx_pilot.py",
             middleware=[Middleware(ta.TrialGate, config=ta.TrialConfig.from_environ(os.environ))])
