"""The website trial's safety checks (issue #131, lean v1.2; decisions D-008 and D-009). PR A1, PR B.

The trial runs MargenX online for one invited person at a time, behind Cloudflare Access.
Cloudflare puts a signed token on every request it lets through. This module checks that token,
and keeps a small in-memory register of which person each MargenX session belongs to. `TrialGate`
sits in front of every request Streamlit receives (page, live connection, media) and refuses
anything that isn't from the invited person.

Uploads are switched off in this PR. Until the QuickBooks Profit and Loss Detail reading (#128) is
finished, the trial shows the made-up sample files only: the gate refuses every request to the
upload address, and every request that sends data (any method other than GET, HEAD or OPTIONS),
before any of its body is read. No setting turns uploads on; the PR that enables them must add
consent, and a consent withdrawal that is safe against an upload already in flight.

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
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

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
# Closed mode's invited email (deploy/trial/launch.py): ".invalid" can never be a real email domain (RFC 2606).
CLOSED_INVITE = "closed@margenx.invalid"
# On every refusal, so it can be told apart from Cloudflare's own pages: "refused", or "closed" in closed mode.
GATE_HEADER = b"x-margenx-gate"
CLOSED_MESSAGE = "This MargenX trial copy is closed."
SAMPLES_ONLY_NOTE = (
    "This trial shows MargenX with made-up sample files for now. Reading your own QuickBooks report isn't "
    "finished yet, so there's no upload box: you'll be told when it's ready."
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
            self._logged_out_at[email] = time.time() if now is None else now
            ended = [sid for sid, owner in self._sessions.items() if owner == email]
            for sid in ended:
                del self._sessions[sid]
                self._retired.add(sid)
            return ended

    def login_allowed(self, email: str, issued_at: float) -> bool:
        with self._lock:
            ended = self._logged_out_at.get(email)
            return ended is None or issued_at > ended


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


REGISTER = SessionRegister()
CHECKS = TokenChecks()
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
    person and exactly the trial's own Host; live connections also need the trial's own Origin. Uploads
    and anything else that sends data are refused before any body is read (uploads are off). The gate
    also answers the Log out link itself (LOGOUT_PATH)."""

    def __init__(self, app, config: TrialConfig | None = None, checker: TokenChecker | None = None,
                 register: SessionRegister = REGISTER, clock=time.time,
                 check_every: float = CHECK_EVERY_SECONDS, runtime=_streamlit_runtime,
                 checks: TokenChecks | None = None, recheck_every: float = KEY_RECHECK_SECONDS):
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
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)  # lifespan events carry no request
            return
        self.register.loop = asyncio.get_running_loop()
        if self.config is not None and self.config.closed:
            await self._refuse(scope, send, closed=True)  # closed mode: everyone, before any token check
            return
        headers = self._before_token(scope)
        claims = None
        token = None
        if headers is not None:
            token = headers.get(TOKEN_HEADER.encode())
            # Off the event loop, with a deadline and a cap: checking a token may fetch Cloudflare's keys.
            found = await self.checks.claims(self.checker, token) if token else None
            claims = self._after_token(scope, headers, found)  # on the loop again: the latest logouts count
        if claims is None:
            await self._refuse(scope, send)
            return
        if kind == "websocket":
            await self._serve_live(scope, receive, send, claims, token)
            return
        if scope.get("path") == LOGOUT_PATH:
            await self._log_out(scope, send, claims)
            return
        await self.app(scope, receive, self._with_security_headers(send))

    async def _log_out(self, scope, send, claims):
        """Log out: refuse this person's logins issued up to now, retire and close all their sessions,
        then send the browser to Cloudflare's own logout. Only a POST from the trial's own page: its
        Origin must be the trial's (every browser sends Origin on a POST), and Sec-Fetch-Site, when sent,
        must say same-origin. So another site can't log the person out. The body is never read."""
        headers = _single_headers(scope)
        if (scope.get("method") != "POST" or headers.get(b"origin") != self.config.origin
                or headers.get(b"sec-fetch-site") not in (None, "same-origin")):
            await self._refuse(scope, send)
            return
        ended = self.register.log_out(claims["email"], now=self.clock())
        end_sessions(ended, self.register, runtime=self.runtime)
        await send({"type": "http.response.start", "status": 303,
                    "headers": [(b"location", CLOUDFLARE_LOGOUT.encode()), *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": b""})

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
                return None  # uploads are off
            if method not in READ_METHODS and not (method == "POST" and path == LOGOUT_PATH):
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
        lock = asyncio.Lock()
        state = {"ended": False, "watch": None, "rekey": None}

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
            if message["type"] == "websocket.send" and self._ended(claims):
                await end()
            async with lock:
                if state["ended"]:
                    return  # dropped: the login has ended
                await send(message)
            if message["type"] == "websocket.accept" and state["watch"] is None:
                state["watch"] = asyncio.create_task(watch())
                state["rekey"] = asyncio.create_task(rekey())

        async def guarded_receive():
            if state["ended"]:
                return {"type": "websocket.disconnect", "code": 1008}
            message = await receive()
            if message["type"] == "websocket.receive" and self._ended(claims):
                await end()
            if state["ended"] and message["type"] != "websocket.disconnect":
                return {"type": "websocket.disconnect", "code": 1008}
            return message

        try:
            await self.app(scope, guarded_receive, guarded_send)
        finally:
            for task in (state["watch"], state["rekey"]):
                if task is not None:
                    task.cancel()


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
