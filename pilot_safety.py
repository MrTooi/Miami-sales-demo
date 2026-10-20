"""MarginX step 3a: safety basics for the sit-down pilot.

A pilot shop's real files are used only on a team laptop, with the shop owner present:
MarginX runs locally, reads files in memory, never saves them, and forgets everything when
the session ends. Real files are allowed only when pilot mode is switched on AND the app is
reachable from this computer alone; anywhere else (a shared or public deployment) MarginX
stays made-up data only. Allowing real data at all still needs the owner's separate decision
(D-003); this module only makes the sit-down setup safe when that decision is given.
"""
from __future__ import annotations

from collections.abc import Mapping

PILOT_ENV = "MARGINX_PILOT"
LOCAL_ADDRESSES = {"localhost", "127.0.0.1", "::1"}

CONSENT_TEXT = (
    "I own or manage this business and agree to MarginX reading these files on this laptop, with me present. "
    "The files are read in memory only and are not saved, uploaded or kept after this session. I can stop at any "
    "time, and I can ask for the session to be ended right away."
)
MADE_UP_TEXT = "These files are made-up (no real customer, invoice or bank data)."


def pilot_mode(environ: Mapping[str, str], server_address: str | None) -> bool:
    """True only when pilot mode is switched on and the app listens on this computer alone.

    Both are required, so a shared or public deployment can never accept real files, even if
    the switch were set there by mistake. An unset address (Streamlit's default listens on
    every network address) does not count as local.
    """
    switched_on = environ.get(PILOT_ENV, "").strip() == "1"
    return switched_on and (server_address or "").strip().lower() in LOCAL_ADDRESSES


def upload_allowed(use_sample: bool, has_upload: bool, confirmed: bool) -> bool:
    """A file of one's own is processed only after its box is ticked: "made-up" outside pilot
    mode, the shop owner's consent in pilot mode (the page shows the right box)."""
    return use_sample or (has_upload and confirmed)
