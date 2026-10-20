"""MarginX step 3a: safety basics for the sit-down pilot.

A pilot shop's real files are used only on a team laptop, with the shop owner present:
MarginX runs locally, reads files in memory, never saves them, and forgets everything when
the session ends. Real files are allowed only when pilot mode is switched on, the app listens
on a loopback address, AND the browser's request itself looks local (a loopback Host and no
proxy or tunnel forwarding headers). Otherwise MarginX stays made-up data only.

Limit, stated honestly: these checks catch ordinary deployments, proxies and tunnels, but code
alone can't prove that nothing forwards traffic to the laptop. The pilot checklist therefore
requires that no tunnel, proxy or remote-access tool runs during a visit.

Allowing real data at all still needs the owner's separate decision (D-003); this module only
makes the sit-down setup safe when that decision is given.
"""
from __future__ import annotations

from collections.abc import Mapping

PILOT_ENV = "MARGINX_PILOT"
LOCAL_ADDRESSES = {"localhost", "127.0.0.1", "::1"}

CONSENT_TEXT = (
    "I own or manage this business and agree to MarginX reading these files on this laptop, with me present. "
    "The files go only to MarginX on this laptop, never to an outside server; they are read in memory only and "
    "are not saved or kept after this session. I can stop at any time, and I can ask for the session to be "
    "ended right away."
)
MADE_UP_TEXT = "These files are made-up (no real customer, invoice or bank data)."


def pilot_mode(environ: Mapping[str, str], server_address: str | None,
               headers: Mapping[str, str] | None = None) -> bool:
    """True only when pilot mode is switched on, the app listens on a loopback address, and the
    current request looks local (see request_is_local). An unset address (Streamlit's default
    listens on every network address) does not count."""
    switched_on = environ.get(PILOT_ENV, "").strip() == "1"
    loopback = (server_address or "").strip().lower() in LOCAL_ADDRESSES
    return switched_on and loopback and request_is_local(headers)


# Headers that proxies, load balancers and tunnels add; a direct local browser sends none.
FORWARDING_HEADERS = {"x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip",
                      "cf-connecting-ip", "true-client-ip", "x-original-forwarded-for", "via"}


def request_is_local(headers: Mapping[str, str] | None) -> bool:
    """True only for a request with a loopback Host header and no forwarding headers.

    Unknown headers (None) never count as local: pilot mode then stays off.
    """
    if headers is None:
        return False
    lowered = {k.lower(): v for k, v in headers.items()}
    if lowered.keys() & FORWARDING_HEADERS:
        return False
    host = lowered.get("host", "").strip().lower()
    if host.startswith("["):  # [::1]:8501
        name = host[1:].split("]")[0]
    else:
        name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return name in LOCAL_ADDRESSES


def release_uploads(manager, session_id: str | None) -> bool:
    """Delete every file this session uploaded from Streamlit's upload storage, then check.

    Returns True only when the storage can be inspected and holds nothing for the session.
    Relies on Streamlit's in-memory upload manager (pinned streamlit==1.65.0, see
    requirements.txt): remove_session_files() and its file_storage dict. If either is
    missing, nothing can be confirmed and False is returned, so the page never claims a
    deletion it couldn't check.
    """
    if manager is None or not session_id:
        return False
    try:
        manager.remove_session_files(session_id)
        storage = manager.file_storage
    except Exception:
        return False
    return isinstance(storage, dict) and not storage.get(session_id)


def upload_allowed(use_sample: bool, has_upload: bool, confirmed: bool) -> bool:
    """A file of one's own is processed only after its box is ticked: "made-up" outside pilot
    mode, the shop owner's consent in pilot mode (the page shows the right box)."""
    return use_sample or (has_upload and confirmed)
