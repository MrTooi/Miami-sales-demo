"""The website trial's safety checks (issue #131, lean v1.2; decisions D-008 and D-009). PR A1, PR B, uploads PR.

The trial runs MargenX online for one invited person at a time, behind Cloudflare Access.
Cloudflare puts a signed token on every request it lets through. This module checks that token,
and keeps a small in-memory register of which person each MargenX session belongs to. `TrialGate`
sits in front of every request Streamlit receives (page, live connection, media) and refuses
anything that isn't from the invited person.

**Uploads (the uploads PR, plan v7: the process is the boundary).** One MargenX process holds at most
one consent, for one tab, and **any ending ends the whole process**: the launcher (deploy/trial/launch.py)
kills it and starts a fresh, empty one (trial_control). So nothing from an ended consent can be read,
finished, delivered or resumed. Here:
- `TrialState` (one per process): the live connections and which session each serves, the one consented
  session, the upload addresses issued to it, the processing slot, and the `ending` flag.
- **Consent** is granted to the session whose button was clicked, in one locked step, only while that
  session's own connection is the only live connection in the process; from then on every other live
  connection is refused. No cookie and no reload are involved.
- **Every ending is "ending first, browser second":** Log out first sends the launcher the logout time;
  then `ending` is set and the launcher is asked to recycle; only then is the browser answered. If the
  launcher can't be told, MargenX kills itself. While `ending` is set, no upload is accepted or handed on,
  nothing is stored, no processing starts and nothing more is sent on any live connection.
- **An upload** (`PUT /_stcore/upload_file/<session>/<file>`) goes on only if, before the body is read at
  all: a valid login, the trial's own Origin, Streamlit's XSRF token, the consented session with its
  connection live, and an unused address issued to that session over its own connection; with a size cap
  and a total deadline. `TrialUploadStore` stores each file once, never replaces bytes, and gives the page
  only the exact objects it stored. Anything else that sends data is still refused before its body is read.
- Without the launcher's control pipe (a laptop, a test), consent is never granted: uploads need it.

Nothing here stores anything: the register lives in memory and is gone when the process stops.
The trial is switched on only by its settings (`TrialConfig.from_environ`); without every
setting, the gate refuses every request (fail closed). The laptop pilot mode (pilot_safety) is
separate and unchanged.

Limits, stated honestly:
- The gate trusts Cloudflare's signing keys, fetched from the team's own address. Release check 1
  shows the server is reachable only through the tunnel.
- Log out is handled here, not by the page: the Log out button posts to LOGOUT_PATH from the
  trial's own page (checked by Origin), and the gate refuses that person's logins issued up to
  then, retires and closes every MargenX session of theirs in this process, including any tab
  that has disconnected but that Streamlit keeps for a while so it can reconnect (state and any
  uploaded files), and sends the browser on to Cloudflare's own logout. A plain redirect, so it
  works even though the page can no longer load anything. A retired session can never be resumed.
  The register never forgets which person a session belongs to while the process runs, so no
  session Streamlit could still resume escapes a logout. A restart forgets all that, but a
  restart also ends every session.
- Checking a token can mean fetching Cloudflare's keys over the network. Every check (the gate's and
  the page's) runs in TokenChecks' own small pool of threads, off Streamlit's event loop, so a slow
  fetch never freezes the app. Since PR B it has a total deadline and a cap (the PR #137 follow-up):
  a check that hasn't finished within TOKEN_CHECK_SECONDS is refused, and while MAX_PARALLEL_CHECKS
  checks are already running, a new one is refused at once instead of queueing. Refusing is the safe
  side: the browser can simply try again. A thread stuck in a slow fetch keeps its place in the cap
  until the fetch itself gives up (each network wait gives up after KEY_FETCH_TIMEOUT_SECONDS), so
  stuck fetches can never pile up threads. PyJWT still lets one key lookup run at a time, so other
  checks wait behind a slow fetch, a logout included; with the deadline, that wait ends in a refusal
  within TOKEN_CHECK_SECONDS. A refused logout changes nothing, and the person can press it again.
- A live connection is checked about once a second and on every message: it is closed once the
  login has expired or been logged out, and nothing more is sent on it. Since PR B its token is also
  checked again against Cloudflare's current keys every KEY_RECHECK_SECONDS (the other PR #137
  follow-up): if Cloudflare has removed the key that signed it, or the check can't finish (deadline or
  cap), the connection is closed. The browser then reconnects, which needs a fresh, valid token.
  So a key Cloudflare removes cuts an open tab within about KEY_SET_SECONDS + KEY_RECHECK_SECONDS +
  TOKEN_CHECK_SECONDS (the cached key set's life, the next re-check, and that check's deadline), plus
  a moment of scheduling: about 6 minutes and 10 seconds.
  Figures already on screen stay visible (behind Streamlit's "Connection error" box) until the tab is
  closed.
- Closed mode (deploy/trial/launch.py, MARGINX_TRIAL_CLOSED=1) gives MargenX CLOSED_INVITE, nobody's
  address, as the invited email. The gate then refuses every request before any token check, with
  "This MargenX trial copy is closed." Every refusal carries the X-MargenX-Gate header, so a refusal
  seen through Cloudflare can be told apart from Cloudflare's own: that is how the stop procedure's
  restart check shows that the copy itself refuses (PR B). A refused live connection gets the same
  marked 403 instead of a bare close, when the server supports it (the ASGI WebSocket Denial Response
  extension, which uvicorn, Streamlit's server, does).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import os
import re
import secrets
import signal
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

import trial_control as tc

TRIAL_ENV = "MARGINX_TRIAL"
TOKEN_HEADER = "cf-access-jwt-assertion"
UPLOAD_PREFIX = "/_stcore/upload_file"
READ_METHODS = ("GET", "HEAD", "OPTIONS")
# Headers that must appear at most once: with two copies, the gate and Streamlit could read different ones.
SINGLE_HEADERS = (b"host", b"origin", TOKEN_HEADER.encode(), b"sec-websocket-protocol", b"sec-fetch-site")
# The Log out button posts here; the gate answers it itself, then sends the browser to Cloudflare's own logout.
LOGOUT_PATH = "/_trial/logout"
CLOUDFLARE_LOGOUT = "/cdn-cgi/access/logout"
# Replaced on every response: nothing from the trial is stored by the browser or any cache, and no other
# site can show the trial inside a frame.
# Referrer-Policy same-origin keeps the browser sending the trial's real Origin on the Log out form's POST
# (a no-referrer policy would make it "null", which the gate refuses).
FORCED_HEADERS = ((b"cache-control", b"no-store"), (b"x-frame-options", b"DENY"),
                  (b"referrer-policy", b"same-origin"))
# Added next to any policy Streamlit sets (a browser applies every policy it gets, so ours always holds).
ADDED_HEADERS = ((b"content-security-policy", b"frame-ancestors 'none'"),)
SECURITY_HEADERS = FORCED_HEADERS + ADDED_HEADERS
# Cloudflare's key set is fetched again after this many seconds; a key it has removed stops working then.
KEY_SET_SECONDS = 300
# How long each network wait in a fetch of Cloudflare's keys may take (PyJWT's default is 30). Not a total
# deadline for the whole fetch; see the module notes.
KEY_FETCH_TIMEOUT_SECONDS = 5
CHECK_EVERY_SECONDS = 1.0
# A token check (which may fetch Cloudflare's keys) must finish within this, or the request is refused.
TOKEN_CHECK_SECONDS = 8.0
# At most this many token checks run at once; a new one beyond that is refused at once, never queued.
MAX_PARALLEL_CHECKS = 8
# An open live connection's token is checked again against Cloudflare's current keys this often.
KEY_RECHECK_SECONDS = 60.0
# The uploads PR: End session (a plain form post the gate answers) and the page's reload check.
END_PATH = "/_trial/end"
GENERATION_PATH = "/_trial/generation"
# A file at most this size (job_intake's own limit); a request body at most this plus room for its framing.
MAX_UPLOAD_FILE = 5_000_000
MAX_UPLOAD_BODY = MAX_UPLOAD_FILE + 65_536
UPLOAD_SECONDS = 120.0  # a whole upload must arrive within this
MAX_ADDRESSES = 4  # upload addresses ever issued in one process (then: End session to start again)
MAX_STORED = 2  # files held at once (a Profit and Loss Detail, and a Sales by Customer Detail)
MAX_RECEIVING = 2  # uploads arriving at once
WORK_WAIT_SECONDS = 65.0  # how long a page run waits for the processing slot held by an older run
XSRF_HEADER = b"x-xsrftoken"
XSRF_COOKIE = "_streamlit_xsrf"
# Closed mode's invited email (deploy/trial/launch.py): ".invalid" can never be a real email domain (RFC 2606).
CLOSED_INVITE = "closed@margenx.invalid"
# On every refusal, so it can be told apart from Cloudflare's own pages: "refused", or "closed" in closed mode.
GATE_HEADER = b"x-margenx-gate"
CLOSED_MESSAGE = "This MargenX trial copy is closed."
SAMPLES_ONLY_NOTE = (
    "This trial shows MargenX with made-up sample files for now. Reading your own QuickBooks report isn't "
    "finished yet, so there's no upload box: you'll be told when it's ready."
)
# The trial's consent (uploads plan v7; the terms draft, section 5, says the same). The button grants it to this
# tab's own session only.
TRIAL_CONSENT_TEXT = (
    "I own or manage this business and I'm allowed to share this report for the trial. I agree to MargenX reading "
    "the QuickBooks report I add here, on my private MargenX trial copy online (hosted for MargenX by Render, behind "
    "Cloudflare's login). It is read in memory only and not saved by MargenX. Ending the session, logging out, "
    "closing or reloading this tab, a dropped connection, or the end of the trial clears it from MargenX. I won't "
    "add bank or card details, tax ID numbers or individual payroll records."
)
OWN_FILES_NOTE = ("Try MargenX with the made-up samples below, or with your own QuickBooks report (the card below). "
                  "Use one MargenX tab at a time.")
QUICKBOOKS_ONLY = ("MargenX's trial reads only QuickBooks Online's Profit and Loss Detail (and, optionally, its Sales by "
                   "Customer Detail), exported to Excel. This file isn't one of those, so it wasn't read. Remove it, "
                   "and follow the export steps in your guide.")
# A login older than the cutoff (after a logout, or after MargenX was restarted unexpectedly): a way back in.
ENDED_PAGE = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
    "<title>MargenX</title></head><body style='font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;"
    "padding:0 1rem;color:#0E241B'><h1 style='font-size:1.3rem'>Your MargenX session was ended.</h1>"
    "<p>Please log in again. If you see this page again right away, wait half a minute, then try again.</p>"
    "<p><a href='/cdn-cgi/access/logout' style='display:inline-block;background:#0F7A55;color:#fff;padding:.6rem 1.1rem;"
    "border-radius:10px;text-decoration:none'>Log in again</a></p></body></html>"
)
# Answered to End session, from the ending process: it waits for the fresh MargenX, then reloads.
CLEARING_PAGE = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
    "<title>MargenX</title></head><body style='font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;"
    "padding:0 1rem;color:#0E241B'><h1 style='font-size:1.3rem'>Clearing&hellip; one moment</h1>"
    "<p>MargenX is clearing your session. This page reloads by itself.</p>"
    "<script>{script}</script></body></html>"
)


@dataclass(frozen=True)
class TrialConfig:
    """Everything the trial needs, from the host's private settings. None of it is secret, but the
    invited email is personal data, so it lives only in those settings, never in this repository."""

    team_domain: str  # https://<team>.cloudflareaccess.com
    audience: str  # the Access application's AUD tag
    invited_email: str  # the one named person
    host: str  # the app's address, e.g. app.margenx.org

    @property
    def issuer(self) -> str:
        return self.team_domain

    @property
    def certs_url(self) -> str:
        return f"{self.team_domain}/cdn-cgi/access/certs"

    @property
    def origin(self) -> str:
        return f"https://{self.host}"

    @property
    def closed(self) -> bool:
        """Closed mode: the invited email is nobody's address, so this copy refuses everyone."""
        return self.invited_email == CLOSED_INVITE

    @staticmethod
    def requested(environ: Mapping[str, str]) -> bool:
        """Whether the trial switch is set at all (anything but empty or "0"). With the switch set but the
        settings invalid, the page refuses to run rather than fall back to the ordinary page (fail closed)."""
        return environ.get(TRIAL_ENV, "").strip() not in ("", "0")

    @staticmethod
    def from_environ(environ: Mapping[str, str]) -> TrialConfig | None:
        """The trial's settings, or None unless the trial is switched on and every setting is valid."""
        if environ.get(TRIAL_ENV, "").strip() != "1":
            return None
        team = environ.get("MARGINX_TRIAL_TEAM_DOMAIN", "").strip().rstrip("/")
        audience = environ.get("MARGINX_TRIAL_AUDIENCE", "").strip()
        email = environ.get("MARGINX_TRIAL_INVITED_EMAIL", "").strip().lower()
        host = environ.get("MARGINX_TRIAL_HOST", "").strip().lower()
        if not re.fullmatch(r"https://[a-z0-9-]+\.cloudflareaccess\.com", team):
            return None
        if not audience or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return None
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host):
            return None
        return TrialConfig(team, audience, email, host)


class TokenChecker:
    """Checks Cloudflare Access's signed token: RS256 signature, audience, issuer and expiry, then
    that its email is the one invited person. Returns the claims, or None for anything else."""

    def __init__(self, config: TrialConfig, key_source=None):
        self.config = config
        if key_source is None:
            import jwt

            # Only the whole key set is cached, for KEY_SET_SECONDS; no single key is kept beyond it
            # (cache_keys=False). So a key Cloudflare has removed stops working once the set expires. A
            # token with an unknown key ID fetches the set again at once, but PyJWT allows that at most
            # once per 30 seconds (its refresh cooldown): a token signed with a brand-new key may be
            # refused for up to 30 seconds after another unknown-key fetch. Refusing is the safe side.
            key_source = jwt.PyJWKClient(config.certs_url, cache_keys=False, cache_jwk_set=True,
                                         lifespan=KEY_SET_SECONDS, timeout=KEY_FETCH_TIMEOUT_SECONDS)
        self._keys = key_source

    def claims(self, token: str | None) -> dict | None:
        if not token:
            return None
        import jwt

        try:
            key = self._keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.config.audience,
                                issuer=self.config.issuer,
                                options={"require": ["exp", "iat", "aud", "iss", "email"]})
        except Exception:  # bad signature, wrong app, expired, unknown key, malformed: all refused
            return None
        email = str(claims.get("email", "")).strip().lower()
        if email != self.config.invited_email:
            return None
        claims["email"] = email
        return claims


@dataclass
class SessionRegister:
    """Which person each MargenX session belongs to, which sessions were ended by a logout, and when
    each person last logged out. In memory only; thread-safe (Streamlit runs scripts in other threads).
    `loop` is Streamlit's event loop, noted by the gate, so a logout can close sessions on it.

    Nothing is ever forgotten while the process runs: Streamlit keeps a disconnected tab's session for
    a while so it can reconnect, and its owner must stay known until a logout retires it. The records
    are a few short strings per page load, for one invited person over a two-week trial."""

    _sessions: dict[str, str] = field(default_factory=dict)  # session ID -> email
    _retired: set[str] = field(default_factory=set)  # ended by a logout: never usable again
    _logged_out_at: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    loop: asyncio.AbstractEventLoop | None = None

    def bind(self, session_id: str, email: str, issued_at: float) -> bool:
        """Tie a session to a person's login, in one locked step with the check that the login hasn't been
        logged out: a logout can never slip in between the two. False (the caller clears the session) if
        the session belongs to someone else, was ended by a logout, or the login was logged out; in the
        last case the session is retired here, so it can never be resumed either."""
        with self._lock:
            if session_id in self._retired:
                return False
            owner = self._sessions.get(session_id, email)
            if owner != email:
                return False
            ended = self._logged_out_at.get(email)
            if ended is not None and issued_at <= ended:  # the logout won
                self._sessions.pop(session_id, None)
                self._retired.add(session_id)
                return False
            self._sessions[session_id] = email
            return True

    def may_resume(self, session_id: str, email: str) -> bool:
        """Whether a live connection may resume this earlier session: not if a logout ended it, nor if it
        belongs to someone else."""
        with self._lock:
            return session_id not in self._retired and self._sessions.get(session_id, email) == email

    def log_out(self, email: str, now: float | None = None) -> list[str]:
        """Refuse this person's logins issued up to now, and retire every session of theirs. Returns
        those sessions' IDs, so the caller can close them."""
        with self._lock:
            when = time.time() if now is None else now
            self._logged_out_at[email] = max(when, self._logged_out_at.get(email, when))  # never goes back
            ended = [sid for sid, owner in self._sessions.items() if owner == email]
            for sid in ended:
                del self._sessions[sid]
                self._retired.add(sid)
            return ended

    def login_allowed(self, email: str, issued_at: float) -> bool:
        with self._lock:
            ended = self._logged_out_at.get(email)
            return ended is None or issued_at > ended

    def owns(self, session_id: str, email: str) -> bool:
        """Whether this session is tied to this person and wasn't ended by a logout."""
        with self._lock:
            return session_id not in self._retired and self._sessions.get(session_id) == email

    @staticmethod
    def from_environ(environ: Mapping[str, str]) -> SessionRegister:
        """A register that already refuses logins issued at or before the launcher's cutoff
        (trial_control.CUTOFF_ENV): logouts survive MargenX being restarted (uploads plan v7)."""
        register = SessionRegister()
        config = TrialConfig.from_environ(environ)
        value = environ.get(tc.CUTOFF_ENV, "").strip()
        if config is not None and value.isdigit():
            register._logged_out_at[config.invited_email] = float(value)
        return register


class TokenChecks:
    """Runs token checks with a total deadline and a cap on how many run at once (the PR #137 follow-up).

    Each check runs in this pool's own threads, never on Streamlit's event loop. A check that hasn't
    finished within `deadline` seconds is refused (None). While `limit` checks are still running, a new
    one is refused at once: it is never queued. A check stuck in a slow fetch keeps its place until its
    thread really finishes, so stuck checks can never add up to more than `limit` threads."""

    def __init__(self, limit: int = MAX_PARALLEL_CHECKS, deadline: float = TOKEN_CHECK_SECONDS):
        self.limit = limit
        self.deadline = deadline
        self._places = threading.BoundedSemaphore(limit)
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=limit, thread_name_prefix="margenx-token")

    def _start(self, checker: TokenChecker, token: str | None) -> concurrent.futures.Future | None:
        if not self._places.acquire(blocking=False):
            return None  # the cap is reached: refused at once
        try:
            future = self._pool.submit(checker.claims, token)
        except RuntimeError:  # the pool is shutting down: the process is ending
            self._places.release()
            return None
        future.add_done_callback(lambda _: self._places.release())  # the place is freed only when it really ends
        return future

    async def claims(self, checker: TokenChecker, token: str | None) -> dict | None:
        """From the event loop: the token's claims, or None if refused, too slow or over the cap."""
        future = self._start(checker, token)
        if future is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), self.deadline)
        except Exception:  # the deadline passed (or anything else): refused
            return None

    def claims_now(self, checker: TokenChecker, token: str | None) -> dict | None:
        """From a script thread (the page): the same, waiting at most the deadline."""
        future = self._start(checker, token)
        if future is None:
            return None
        try:
            return future.result(timeout=self.deadline)
        except Exception:
            return None


def _kill_own_process() -> None:
    """MargenX's last resort when the launcher can't be told about an ending: end at once. The launcher
    starts MargenX as its process group's leader, so the whole group goes; anywhere else, this process."""
    pid = os.getpid()
    try:
        if os.getpgrp() == pid:
            os.killpg(pid, signal.SIGKILL)
        os.kill(pid, signal.SIGKILL)
    finally:
        os._exit(70)  # never reached in practice


class Control:
    """MargenX's side of the launcher's control pipe (trial_control). Writes never block. An `alive` that
    can't be written now is simply skipped (the launcher notices a missing heartbeat by itself); any other
    message that can't be written whole makes MargenX end itself at once (`kill`), because the launcher must
    never be left not knowing about an ending, a logout or armed work."""

    def __init__(self, fd: int, kill=_kill_own_process):
        self.fd = fd
        self.kill = kill
        self.stopped = False  # once an ending is sent, nothing more is written
        self._lock = threading.Lock()
        os.set_blocking(fd, False)

    @staticmethod
    def from_environ(environ: Mapping[str, str], kill=_kill_own_process) -> Control | None:
        value = environ.get(tc.SUPERVISOR_FD_ENV, "").strip()
        if not value.isdigit():
            return None
        try:
            return Control(int(value), kill)
        except OSError:
            return None

    def _write(self, line: bytes) -> bool:
        try:
            return os.write(self.fd, line) == len(line)
        except OSError:  # full (BlockingIOError), closed or broken: nothing was written
            return False

    def send(self, word: str, when: float | None = None) -> None:
        line = tc.encode(word, when)
        with self._lock:
            if self.stopped:
                return
            if word == tc.RECYCLE:
                self.stopped = True
            ok = self._write(line)
        if not ok:
            self.kill()

    def alive(self) -> None:
        with self._lock:
            if self.stopped:
                return
            try:
                os.write(self.fd, tc.encode(tc.ALIVE))
                return
            except BlockingIOError:
                return  # skipped; the launcher's own check covers a missing heartbeat
            except OSError:
                pass  # the pipe is gone: the launcher can't supervise this process any more
        self.kill()


@dataclass
class Attempt:
    """One upload address issued to the consented session: used at most once."""

    session: str
    state: str = "issued"  # issued -> receiving -> stored | failed; stored -> deleted
    stored: object = None  # the exact object stored for it


class TrialState:
    """This process's live connections, its one consent, its upload addresses and the ending flag (see the
    module notes). Thread-safe: the gate runs on the event loop, the page in script threads."""

    def __init__(self, control: Control | None = None, register: SessionRegister | None = None):
        self.control = control
        self.register = register
        self.generation = secrets.token_hex(16)
        self.ending = False  # read without the lock too: once True, it never goes back
        self._lock = threading.Lock()
        self._connections: dict[int, str | None] = {}  # live connection -> its session, once known
        self._next = 0
        self.consented_session: str | None = None
        self.consented_connection: int | None = None
        self._attempts: dict[str, Attempt] = {}
        self._receiving = 0
        self._slot = threading.Lock()

    # --- endings ---
    def end(self, logout_at: float | None = None) -> bool:
        """Ending first: the logout time (if any) to the launcher, then `ending`, then the recycle request.
        Returns False if there is no launcher to ask (nothing is recycled then)."""
        if self.control is None:
            with self._lock:
                self.ending = self.ending or self.consented_session is not None
            return False
        if logout_at is not None:
            self.control.send(tc.LOGOUT, logout_at)
        with self._lock:
            self.ending = True
        self.control.send(tc.RECYCLE)
        return True

    # --- live connections ---
    def admit(self) -> int | None:
        """A new live connection: its number, or None if it must be refused (consented or ending)."""
        with self._lock:
            if self.ending or self.consented_session is not None:
                return None
            self._next += 1
            self._connections[self._next] = None
            return self._next

    def learn(self, connection: int, session_id: str) -> None:
        with self._lock:
            if connection in self._connections and self._connections[connection] is None:
                self._connections[connection] = session_id

    def leave(self, connection: int) -> None:
        """A live connection has closed. If it was the consented one, the process ends."""
        with self._lock:
            self._connections.pop(connection, None)
            consented = connection == self.consented_connection
        if consented:
            self.end()

    def live(self, connection: int) -> bool:
        with self._lock:
            return connection in self._connections

    # --- consent ---
    def grant(self, session_id: str | None, email: str | None) -> str:
        """Grant this process's consent to the session whose button was clicked. "granted"; "tabs" when it
        isn't the only live connection; "unavailable" otherwise (no launcher, ending, already consented, or
        the session isn't this person's)."""
        if self.control is None or not session_id or not email:
            return "unavailable"
        with self._lock:
            if self.ending or self.consented_session is not None:
                return "unavailable"
            register = self.register
            if register is None or not register.owns(session_id, email):
                return "unavailable"
            mine = [c for c, s in self._connections.items() if s == session_id]
            if len(self._connections) != 1 or len(mine) != 1:
                return "tabs"
            self.consented_session = session_id
            self.consented_connection = mine[0]
            return "granted"

    def is_consented(self, session_id: str | None) -> bool:
        with self._lock:
            return (not self.ending and session_id is not None and session_id == self.consented_session
                    and self.consented_connection in self._connections)

    # --- upload addresses (TrialUploadStore) ---
    def issue(self, session_id: str, count: int) -> list[str]:
        """File IDs for upload addresses: recorded only for the consented session, within the caps."""
        ids = [str(uuid.uuid4()) for _ in range(count)]
        with self._lock:
            if (self.ending or session_id != self.consented_session or count != 1
                    or len(self._attempts) + count > MAX_ADDRESSES):
                return ids  # never recorded: their uploads are refused before any body is read
            for file_id in ids:
                self._attempts[file_id] = Attempt(session_id)
        return ids

    def begin_upload(self, session_id: str, file_id: str) -> bool:
        """Before any body is read: the consented session, its connection live, an unused address issued to
        it, and room. Marks the attempt receiving (once, ever)."""
        with self._lock:
            attempt = self._attempts.get(file_id)
            if (self.ending or session_id != self.consented_session
                    or self.consented_connection not in self._connections
                    or attempt is None or attempt.session != session_id or attempt.state != "issued"
                    or self._receiving >= MAX_RECEIVING
                    or sum(1 for a in self._attempts.values() if a.state == "stored") >= MAX_STORED):
                return False
            attempt.state = "receiving"
            self._receiving += 1
            return True

    def finish_upload(self, file_id: str) -> bool:
        """After the upload handler: whether its file was stored. A receiving attempt that wasn't is failed."""
        with self._lock:
            attempt = self._attempts.get(file_id)
            self._receiving -= 1
            if attempt is None:
                return False
            if attempt.state == "receiving":
                attempt.state = "failed"
            return attempt.state == "stored" and not self.ending

    def commit(self, session_id: str, record) -> bool:
        """The store's add_file: store only for a receiving attempt of the consented session, once."""
        with self._lock:
            attempt = self._attempts.get(getattr(record, "file_id", None))
            if (self.ending or attempt is None or attempt.session != session_id or attempt.state != "receiving"
                    or session_id != self.consented_session or len(getattr(record, "data", b"")) > MAX_UPLOAD_FILE):
                return False
            attempt.state = "stored"
            attempt.stored = record
            return True

    def visible(self, session_id: str, records: list) -> list:
        """The store's get_files: only the exact objects stored for the consented session."""
        with self._lock:
            if self.ending or session_id != self.consented_session:
                return []
            return [r for r in records if (a := self._attempts.get(r.file_id)) is not None
                    and a.state == "stored" and a.stored is r and a.session == session_id]

    def stored(self, file_id: str) -> bool:
        with self._lock:
            attempt = self._attempts.get(file_id)
            return attempt is not None and attempt.state == "stored" and not self.ending

    def may_delete(self, session_id: str, file_id: str) -> bool:
        with self._lock:
            attempt = self._attempts.get(file_id)
            return (not self.ending and session_id == self.consented_session and attempt is not None
                    and attempt.session == session_id)

    def deleted(self, file_id: str) -> None:
        with self._lock:
            attempt = self._attempts.get(file_id)
            if attempt is not None and attempt.state == "stored":
                attempt.state = "deleted"
                attempt.stored = None

    # --- reading an uploaded file ---
    @contextlib.contextmanager
    def processing(self, wait: float = WORK_WAIT_SECONDS):
        """The one processing slot: held until the run reading an uploaded file exits (an overlapping rerun
        waits), with the launcher's deadline armed for exactly that time. Raises Busy if the slot doesn't
        come free in time, Ending once the process is ending."""
        if self.ending or self.control is None:
            raise Ending()
        if not self._slot.acquire(timeout=wait):
            raise Busy()
        try:
            if self.ending:
                raise Ending()
            self.control.send(tc.ARM)
            try:
                yield
            finally:
                self.control.send(tc.DISARM)
        finally:
            self._slot.release()


class Busy(Exception):
    """The processing slot is held by another run."""


class Ending(Exception):
    """This process is ending: nothing more is read or shown."""


def upload_store_class(state: TrialState | None = None):
    """Streamlit's in-memory upload manager, with every decision taken by the trial state (trial_app.py
    installs it before the runtime is made): addresses issued only to the consented session; each file stored
    once, for a receiving attempt; the page given only the exact objects stored. Built on demand, so the
    launcher (which imports this module) never loads Streamlit."""
    from streamlit.runtime.memory_uploaded_file_manager import MemoryUploadedFileManager
    from streamlit.runtime.uploaded_file_manager import UploadFileUrlInfo

    def current() -> TrialState:
        return STATE if state is None else state

    class TrialUploadStore(MemoryUploadedFileManager):
        def get_upload_urls(self, session_id, file_names):
            return [UploadFileUrlInfo(file_id=file_id, upload_url=f"{self.endpoint}/{session_id}/{file_id}",
                                      delete_url=f"{self.endpoint}/{session_id}/{file_id}")
                    for file_id in current().issue(session_id, len(file_names))]

        def add_file(self, session_id, file):
            if current().commit(session_id, file):
                super().add_file(session_id, file)

        def get_files(self, session_id, file_ids):
            return current().visible(session_id, super().get_files(session_id, file_ids))

        def remove_file(self, session_id, file_id):
            current().deleted(file_id)
            super().remove_file(session_id, file_id)

    return TrialUploadStore


class TypeOnly(logging.Filter):
    """For Streamlit's error log records in the trial (trial_app.py): keeps only the error's type, never its
    message or traceback, which could quote a value from an uploaded file."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            kind = record.exc_info[0].__name__ if record.exc_info[0] else "error"
            record.msg, record.args = f"{record.getMessage()} ({kind})", ()
            record.exc_info, record.exc_text, record.stack_info = None, None, None
        return True


def reload_script(generation: str) -> str:
    """The fixed script on every trial page (and the "Clearing" page): every 2 s it asks this copy's
    generation; when it changes (MargenX was restarted) it reloads the page; a refusal or a Cloudflare
    login response (asked for as AJAX, so it is a detectable 401, never followed) sends it to the start,
    where Cloudflare's login shows if needed; no answer for 30 s reloads anyway. It carries no data."""
    if not re.fullmatch(r"[0-9a-f]{32}", generation):
        raise ValueError("not a generation ID")
    return ("(function(){window.__mxGen='" + generation + "';if(window.__mxPoll)return;var since=null;"
            "function go(p){clearInterval(window.__mxPoll);window.location.replace(p);}"
            "window.__mxPoll=setInterval(function(){fetch('" + GENERATION_PATH + "',{cache:'no-store',"
            "credentials:'same-origin',redirect:'manual',headers:{'X-Requested-With':'XMLHttpRequest'}})"
            ".then(function(r){if(r.type==='opaqueredirect'||r.status===401||r.status===403){go('/');return null;}"
            "if(!r.ok){throw new Error('no answer');}return r.text();})"
            ".then(function(t){if(t===null)return;since=null;if(t.trim()!==window.__mxGen){go('/?ended=1');}})"
            ".catch(function(){if(since===null){since=Date.now();}else if(Date.now()-since>30000){go('/?ended=1');}});"
            "},2000);})();")


REGISTER = SessionRegister.from_environ(os.environ)
CHECKS = TokenChecks()
STATE = TrialState(Control.from_environ(os.environ), REGISTER)
_CHECKERS: dict[TrialConfig, TokenChecker] = {}


def checker_for(config: TrialConfig | None) -> TokenChecker | None:
    """One token checker per trial setting, so Cloudflare's key set is fetched once per few minutes."""
    if config is None:
        return None
    if config not in _CHECKERS:
        _CHECKERS[config] = TokenChecker(config)
    return _CHECKERS[config]


def _streamlit_runtime():
    from streamlit.runtime import Runtime

    return Runtime.instance() if Runtime.exists() else None


def end_sessions(session_ids: list[str], register: SessionRegister = REGISTER, delay: float = 0.0,
                 runtime=_streamlit_runtime) -> bool:
    """Close these Streamlit sessions completely (their state and any uploaded files), after `delay`
    seconds, on Streamlit's event loop, where Streamlit requires it. Safe to call from any thread.
    False if it couldn't be scheduled (no event loop noted yet)."""
    if not session_ids:
        return True
    loop = register.loop
    if loop is None:
        return False
    ids = list(session_ids)

    def close_all():
        rt = runtime()
        if rt is None:
            return
        for sid in ids:
            try:
                rt.uploaded_file_mgr.remove_session_files(sid)  # close_session does this too
            except Exception:
                pass
            try:
                rt.close_session(sid)
            except Exception:
                pass

    try:
        loop.call_soon_threadsafe(loop.call_later, delay, close_all)
    except RuntimeError:  # the event loop has stopped: the process is ending, and every session with it
        return False
    return True


def _single_headers(scope: Mapping) -> dict[bytes, str] | None:
    """The headers the gate reads, each at most once; None if any of them appears twice."""
    found: dict[bytes, str] = {}
    for key, value in scope.get("headers", ()):
        name = key.lower()
        if name in SINGLE_HEADERS:
            if name in found:
                return None
            found[name] = value.decode("latin-1")
    return found


def _resumed_session_id(protocols: str | None) -> str | None:
    """The earlier session a live connection asks to resume: the third entry of Sec-WebSocket-Protocol,
    read exactly as Streamlit reads it (streamlit/web/server/starlette/starlette_websocket.py)."""
    if not protocols:
        return None
    entries = [value.strip() for value in protocols.split(",")]
    return entries[2] if len(entries) >= 3 and entries[2] else None


class TrialGate:
    """ASGI middleware in front of all of Streamlit. Every request needs a valid token for the invited
    person and exactly the trial's own Host; live connections also need the trial's own Origin. An upload
    goes on only with the checks in the module notes, all before its body is read; anything else that sends
    data is refused before any body is read. The gate also answers Log out (LOGOUT_PATH), End session
    (END_PATH) and the page's reload check (GENERATION_PATH) itself, and sends the launcher a heartbeat."""

    def __init__(self, app, config: TrialConfig | None = None, checker: TokenChecker | None = None,
                 register: SessionRegister = REGISTER, clock=time.time,
                 check_every: float = CHECK_EVERY_SECONDS, runtime=_streamlit_runtime,
                 checks: TokenChecks | None = None, recheck_every: float = KEY_RECHECK_SECONDS,
                 state: TrialState | None = None, upload_seconds: float = UPLOAD_SECONDS,
                 alive_every: float = 1.0):
        self.state = state if state is not None else STATE
        self.upload_seconds = upload_seconds
        self.alive_every = alive_every
        self._heartbeat = None
        self.app = app
        self.config = config
        self.checker = checker if checker is not None else checker_for(config)
        self.register = register
        self.clock = clock
        self.check_every = check_every
        self.runtime = runtime
        self.checks = checks if checks is not None else CHECKS
        self.recheck_every = recheck_every

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind == "lifespan":
            await self.app(scope, self._watch_startup(receive), send)  # starts the heartbeat at startup
            return
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        self.register.loop = asyncio.get_running_loop()
        if self.config is not None and self.config.closed:
            await self._refuse(scope, send, closed=True)  # closed mode: everyone, before any token check
            return
        headers = self._before_token(scope)
        claims = None
        token = None
        found = None
        if headers is not None:
            token = headers.get(TOKEN_HEADER.encode())
            # Off the event loop, with a deadline and a cap: checking a token may fetch Cloudflare's keys.
            found = await self.checks.claims(self.checker, token) if token else None
            claims = self._after_token(scope, headers, found)  # on the loop again: the latest logouts count
        if claims is None:
            if (found is not None and kind == "http" and scope.get("method") == "GET" and scope.get("path") == "/"
                    and not self.register.login_allowed(found["email"], float(found["iat"]))):
                await self._answer(send, 403, ENDED_PAGE, "text/html", mark=True)  # a way back in: log in again
                return
            await self._refuse(scope, send)
            return
        if kind == "websocket":
            await self._serve_live(scope, receive, send, claims, token)
            return
        path = scope.get("path", "")
        if path == LOGOUT_PATH:
            await self._log_out(scope, send, claims)
            return
        if path == END_PATH:
            await self._end_session(scope, send)
            return
        if path == GENERATION_PATH:
            await self._answer(send, 200, self.state.generation, "text/plain")
            return
        if path.startswith(UPLOAD_PREFIX):
            await self._upload(scope, receive, send)
            return
        await self.app(scope, receive, self._with_security_headers(send))

    def _watch_startup(self, receive):
        """The lifespan's receive, noticing the startup: the heartbeat to the launcher starts then, on the
        event loop, before any request is served."""
        async def watched():
            message = await receive()
            if message.get("type") == "lifespan.startup" and self._heartbeat is None and self.state.control:
                self._heartbeat = asyncio.get_running_loop().create_task(self._beat())
            return message
        return watched

    async def _beat(self):
        while not self.state.ending:
            self.state.control.alive()
            await asyncio.sleep(self.alive_every)

    async def _answer(self, send, status: int, body: str, kind: str, mark: bool = False):
        headers = [(b"content-type", f"{kind}; charset=utf-8".encode()), *SECURITY_HEADERS]
        if mark:
            headers.append((GATE_HEADER, b"refused"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body.encode()})

    def _same_site_post(self, scope) -> bool:
        """A POST from the trial's own page: its Origin is the trial's (every browser sends Origin on a POST),
        and Sec-Fetch-Site, when sent, says same-origin. So another site can't trigger it."""
        headers = _single_headers(scope)
        return (headers is not None and scope.get("method") == "POST" and headers.get(b"origin") == self.config.origin
                and headers.get(b"sec-fetch-site") in (None, "same-origin"))

    async def _end_session(self, scope, send):
        """End session (uploads plan v7): ending first, browser second. The process is marked ending and the
        launcher asked to recycle it, before anything is sent; then the "Clearing" page, which reloads once
        the fresh MargenX answers. Without a launcher, refused (nothing could be cleared for sure)."""
        if not self._same_site_post(scope) or self.state.control is None:
            await self._refuse(scope, send)
            return
        self.state.end()
        with contextlib.suppress(Exception):  # the ending stands whatever happens to the answer
            await self._answer(send, 200, CLEARING_PAGE.format(script=reload_script(self.state.generation)),
                               "text/html")

    async def _log_out(self, scope, send, claims):
        """Log out: refuse this person's logins issued up to now, retire and close all their sessions,
        then send the browser to Cloudflare's own logout. Only a POST from the trial's own page: its
        Origin must be the trial's (every browser sends Origin on a POST), and Sec-Fetch-Site, when sent,
        must say same-origin. So another site can't log the person out. The body is never read."""
        if not self._same_site_post(scope):
            await self._refuse(scope, send)
            return
        now = self.clock()
        if self.state.control is not None:
            # Ending first (uploads plan v7): the logout time, with the margin, goes to the launcher before
            # anything else, so every later MargenX refuses this login too; then the recycle request.
            cutoff = now + tc.CUTOFF_MARGIN_SECONDS
            self.register.log_out(claims["email"], now=cutoff)
            self.state.end(logout_at=cutoff)
        else:
            ended = self.register.log_out(claims["email"], now=now)
            end_sessions(ended, self.register, runtime=self.runtime)
        with contextlib.suppress(Exception):  # the logout stands whatever happens to the answer
            await send({"type": "http.response.start", "status": 303,
                        "headers": [(b"location", CLOUDFLARE_LOGOUT.encode()), *SECURITY_HEADERS]})
            await send({"type": "http.response.body", "body": b""})

    def _upload_target(self, scope) -> tuple[str, str] | None:
        """The session and file ID of an upload address, or None if the request may not go on. Everything
        here is checked before the body is read: the trial's own Origin and Sec-Fetch-Site, Streamlit's XSRF
        token (header against cookie, as Streamlit checks it), one Cookie header, a plain size."""
        path = scope.get("path", "")
        parts = path[len(UPLOAD_PREFIX):].split("/")
        if len(parts) != 3 or parts[0] != "" or not parts[1] or not parts[2]:
            return None
        headers = _single_headers(scope)
        if headers is None or headers.get(b"origin") != self.config.origin:
            return None  # an upload from another site, or a page that isn't the trial's
        if headers.get(b"sec-fetch-site") not in (None, "same-origin"):
            return None
        raw = {}
        for key, value in scope.get("headers", ()):
            name = key.lower()
            if name in (b"cookie", XSRF_HEADER, b"content-length", b"transfer-encoding"):
                if name in raw:
                    return None  # two copies: the gate and Streamlit could read different ones
                raw[name] = value.decode("latin-1")
        if b"transfer-encoding" in raw:
            return None  # a body of unstated length
        try:
            from starlette.requests import cookie_parser
            from streamlit.web.server.starlette.starlette_app_utils import validate_xsrf_token

            if not validate_xsrf_token(raw.get(XSRF_HEADER), cookie_parser(raw.get(b"cookie", "")).get(XSRF_COOKIE)):
                return None
        except Exception:
            return None
        length = raw.get(b"content-length")
        if scope.get("method") == "PUT":
            if length is None or not length.isdigit() or int(length) > MAX_UPLOAD_BODY:
                return None
        elif length not in (None, "0"):
            return None  # a removal has no body
        return parts[1], parts[2]

    async def _upload(self, scope, receive, send):
        """An upload (PUT) or a removal (DELETE) at /_stcore/upload_file/<session>/<file>. Every check is
        made before Streamlit's handler, so before the body is read at all; then Streamlit's own handler
        (its XSRF, size and one-file checks) receives the body with a total deadline, and stores it through
        TrialUploadStore, which commits it once. If it wasn't stored, the answer is a refusal. Any error is a
        plain refusal: nothing about the file is logged or answered."""
        target = self._upload_target(scope)
        if target is None:
            await self._refuse(scope, send)
            return
        session_id, file_id = target
        if scope.get("method") == "DELETE":
            if not self.state.may_delete(session_id, file_id):
                await self._refuse(scope, send)
                return
            await self._pass_upload(scope, receive, send, None)
            return
        if not self.state.begin_upload(session_id, file_id):
            await self._refuse(scope, send)
            return
        try:
            await self._pass_upload(scope, self._limited(receive), send, file_id)
        finally:
            self.state.finish_upload(file_id)

    def _limited(self, receive):
        """The upload body's receive, with a total deadline, ended at once if the process starts ending."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.upload_seconds

        async def limited():
            left = deadline - loop.time()
            if self.state.ending or left <= 0:
                return {"type": "http.disconnect"}
            try:
                message = await asyncio.wait_for(receive(), left)
            except asyncio.TimeoutError:
                return {"type": "http.disconnect"}
            if self.state.ending:
                return {"type": "http.disconnect"}
            return message
        return limited

    async def _pass_upload(self, scope, receive, send, file_id: str | None):
        """Hand the request to Streamlit's own upload handler; its answer reaches the browser only if the file
        was really stored (an upload) and the process isn't ending. Errors become a plain refusal."""
        held = {"started": False, "refused": False}

        async def checked(message):
            if message["type"] == "http.response.start":
                ok = message.get("status") == 204 and not self.state.ending
                if ok and file_id is not None:
                    ok = self.state.stored(file_id)
                if not ok:
                    held["refused"] = True
                    held["started"] = True
                    await self._refuse(scope, send)
                    return
                held["started"] = True
                kept = [(k, v) for k, v in message.get("headers", []) if k.lower() not in {n for n, _ in FORCED_HEADERS}]
                message = {**message, "headers": [*kept, *SECURITY_HEADERS]}
            elif held["refused"]:
                return  # the refusal above already has its body
            await send(message)

        try:
            await self.app(scope, receive, checked)
        except Exception:  # a broken form, an interrupted or slow body, anything: refused, nothing logged
            if not held["started"]:
                with contextlib.suppress(Exception):
                    await self._refuse(scope, send)

    def _before_token(self, scope) -> dict[bytes, str] | None:
        """The checks that need no token: the headers the gate reads, or None to refuse (no body read)."""
        if self.config is None or self.checker is None:
            return None  # not configured: fail closed
        headers = _single_headers(scope)
        if headers is None:
            return None  # a header the gate relies on appears twice
        if headers.get(b"host", "").lower() != self.config.host:
            return None  # exactly the trial's address: no port, no other name
        if scope["type"] == "http":
            method, path = scope.get("method", "GET"), scope.get("path", "")
            if path.startswith(UPLOAD_PREFIX):
                if method not in ("PUT", "DELETE"):
                    return None  # an upload address takes only an upload or a removal
            elif method not in READ_METHODS and not (method == "POST" and path in (LOGOUT_PATH, END_PATH)):
                return None  # nothing else in the trial sends data
        return headers

    def _after_token(self, scope, headers: dict[bytes, str], claims: dict | None) -> dict | None:
        """The token's claims if this request may go on; None to refuse it (without reading any body)."""
        if claims is None or not self.register.login_allowed(claims["email"], float(claims["iat"])):
            return None
        if scope["type"] == "websocket":
            if headers.get(b"origin") != self.config.origin:
                return None  # a live connection started from another site
            resumed = _resumed_session_id(headers.get(b"sec-websocket-protocol"))
            if resumed is not None and not self.register.may_resume(resumed, claims["email"]):
                return None  # a session a logout ended, or someone else's
        return claims

    async def _refuse(self, scope, send, closed: bool = False):
        headers = [(b"content-type", b"text/plain; charset=utf-8"), (GATE_HEADER, b"closed" if closed else b"refused"),
                   *SECURITY_HEADERS]
        body = (CLOSED_MESSAGE if closed else "Not allowed.").encode()
        if scope["type"] == "websocket":
            if "websocket.http.response" in (scope.get("extensions") or {}):
                # The live connection is refused with the same marked 403, so it too can be told apart.
                await send({"type": "websocket.http.response.start", "status": 403, "headers": headers})
                await send({"type": "websocket.http.response.body", "body": body})
            else:
                await send({"type": "websocket.close", "code": 1008})
            return
        await send({"type": "http.response.start", "status": 403, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def _with_security_headers(self, send):
        forced = {name for name, _ in FORCED_HEADERS}

        async def wrapped(message):
            if message["type"] == "http.response.start":
                kept = [(k, v) for k, v in message.get("headers", []) if k.lower() not in forced]
                message = {**message, "headers": [*kept, *SECURITY_HEADERS]}
            await send(message)
        return wrapped

    def _ended(self, claims) -> bool:
        return self.clock() >= float(claims["exp"]) or not self.register.login_allowed(claims["email"],
                                                                                        float(claims["iat"]))

    async def _serve_live(self, scope, receive, send, claims, token=None):
        """Run a live connection, closing it from the server side once its login has expired or been
        logged out: checked about once a second even when nothing is sent, and on every message either
        way. Its token is also checked again against Cloudflare's current keys every recheck_every
        seconds; a refusal, a check that misses its deadline or the cap, all close it. After that,
        nothing more reaches the browser and nothing more from it reaches Streamlit."""
        connection = self.state.admit()
        if connection is None:
            await self._refuse(scope, send)  # consented (one tab only) or ending: no other live connection
            return
        try:
            await self._serve_admitted(scope, receive, send, claims, token, connection)
        finally:
            self.state.leave(connection)  # the consented tab's connection closing ends the process

    async def _serve_admitted(self, scope, receive, send, claims, token, connection):
        lock = asyncio.Lock()
        state = {"ended": False, "watch": None, "rekey": None, "session": None}

        async def end():
            async with lock:
                if state["ended"]:
                    return
                state["ended"] = True
                try:
                    await send({"type": "websocket.close", "code": 1008})
                except Exception:  # the browser already went away
                    pass

        async def watch():
            while not state["ended"]:
                await asyncio.sleep(self.check_every)
                if self._ended(claims):
                    await end()

        async def rekey():
            # Its own task, so a slow key fetch never delays the once-a-second expiry and logout checks.
            while not state["ended"]:
                await asyncio.sleep(self.recheck_every)
                if state["ended"]:
                    return
                if await self.checks.claims(self.checker, token) is None:
                    await end()  # a removed key, or a check that couldn't finish: closed (fail closed)

        async def guarded_send(message):
            if message["type"] == "websocket.send" and (self._ended(claims) or self.state.ending):
                await end()
            if state["session"] is None and message["type"] == "websocket.send":
                found = _new_session_id(message.get("bytes"))
                if found:
                    state["session"] = found
                    self.state.learn(connection, found)
            async with lock:
                if state["ended"]:
                    return  # dropped: the login has ended, or the process is ending
                await send(message)
            if message["type"] == "websocket.accept" and state["watch"] is None:
                state["watch"] = asyncio.create_task(watch())
                state["rekey"] = asyncio.create_task(rekey())

        async def guarded_receive():
            if state["ended"]:
                return {"type": "websocket.disconnect", "code": 1008}
            message = await receive()
            if message["type"] == "websocket.receive" and (self._ended(claims) or self.state.ending
                                                           or not _fair_request(message.get("bytes"))):
                await end()  # an ended login, an ending process, or an address request for more than one file
            if state["ended"] and message["type"] != "websocket.disconnect":
                return {"type": "websocket.disconnect", "code": 1008}
            return message

        try:
            await self.app(scope, guarded_receive, guarded_send)
        finally:
            for task in (state["watch"], state["rekey"]):
                if task is not None:
                    task.cancel()


def _new_session_id(data: bytes | None) -> str | None:
    """The session a live connection serves, from Streamlit's own first `new_session` message on it."""
    if not data:
        return None
    try:
        from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

        msg = ForwardMsg.FromString(data)
        if msg.WhichOneof("type") == "new_session":
            return msg.new_session.initialize.session_id or None
    except Exception:
        return None
    return None


def _fair_request(data: bytes | None) -> bool:
    """False for a request for upload addresses naming anything but exactly one file: the connection is then
    closed before any answer is built (uploads plan v7, section 3). Other messages pass unchanged."""
    if not data:
        return True
    try:
        from streamlit.proto.BackMsg_pb2 import BackMsg

        msg = BackMsg.FromString(data)
    except Exception:
        return True  # not ours to judge: Streamlit reads it (and refuses what it can't parse)
    if msg.WhichOneof("type") == "file_urls_request":
        return len(msg.file_urls_request.file_names) == 1
    return True


def login_from_headers(headers: Mapping[str, str] | None, checker: TokenChecker | None) -> tuple[str, float] | None:
    """The invited person's email and login time for this page view, or None. The page checks the token
    itself too, so a gate mistake alone can't open the trial. The page then binds its session with
    SessionRegister.bind, which checks the login against logouts again, under the register's lock."""
    if headers is None or checker is None:
        return None
    lowered = {k.lower(): v for k, v in headers.items()}
    claims = CHECKS.claims_now(checker, lowered.get(TOKEN_HEADER))  # the same deadline and cap as the gate
    if claims is None or not REGISTER.login_allowed(claims["email"], float(claims["iat"])):
        return None
    return claims["email"], float(claims["iat"])
