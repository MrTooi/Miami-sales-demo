"""The website trial's safety checks (issue #131, lean v1.2; decisions D-008 and D-009). PR A1.

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
- Log out is handled here, not by the page: the Log out link opens LOGOUT_PATH, and the gate
  refuses that person's logins issued up to then, retires and closes every MargenX session of
  theirs in this process (state and any uploaded files), and sends the browser on to Cloudflare's
  own logout. A plain redirect, so it works even though the page can no longer load anything.
  A retired session can never be resumed. A restart forgets all that, but a restart also ends
  every session.
- A live connection is checked about once a second and on every message: it is closed once the
  login has expired or been logged out, and nothing more is sent on it. Figures already on screen
  stay visible (behind Streamlit's "Connection error" box) until the tab is closed.
"""
from __future__ import annotations

import asyncio
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
# The Log out link's address, answered by the gate itself; then on to Cloudflare's own logout.
LOGOUT_PATH = "/_trial/logout"
CLOUDFLARE_LOGOUT = "/cdn-cgi/access/logout"
# Replaced on every response: nothing from the trial is stored by the browser or any cache, and no other
# site can show the trial inside a frame.
FORCED_HEADERS = ((b"cache-control", b"no-store"), (b"x-frame-options", b"DENY"))
# Added next to any policy Streamlit sets (a browser applies every policy it gets, so ours always holds).
ADDED_HEADERS = ((b"content-security-policy", b"frame-ancestors 'none'"),)
SECURITY_HEADERS = FORCED_HEADERS + ADDED_HEADERS
# Cloudflare's key set is fetched again after this many seconds; a key it has removed stops working then.
KEY_SET_SECONDS = 300
CHECK_EVERY_SECONDS = 1.0
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
            # (cache_keys=False). So a key Cloudflare has removed stops working within that time. An
            # unknown key ID fetches the set again at once (keys rotate).
            key_source = jwt.PyJWKClient(config.certs_url, cache_keys=False, cache_jwk_set=True,
                                         lifespan=KEY_SET_SECONDS)
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
    `loop` is Streamlit's event loop, noted by the gate, so a logout can close sessions on it."""

    _sessions: dict[str, str] = field(default_factory=dict)  # session ID -> email
    _retired: set[str] = field(default_factory=set)  # ended by a logout: never usable again
    _logged_out_at: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    loop: asyncio.AbstractEventLoop | None = None

    def bind(self, session_id: str, email: str) -> bool:
        """Tie a session to a person. A session can never move to another person, and a session ended
        by a logout can't be used again: False then (the caller clears it)."""
        with self._lock:
            if session_id in self._retired:
                return False
            current = self._sessions.setdefault(session_id, email)
            return current == email

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

    def prune(self, is_active) -> None:
        """Forget sessions Streamlit no longer has (a closed tab is dropped after about 10 seconds)."""
        with self._lock:
            for sid in [sid for sid in self._sessions if not is_active(sid)]:
                del self._sessions[sid]


REGISTER = SessionRegister()
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
                 check_every: float = CHECK_EVERY_SECONDS, runtime=_streamlit_runtime):
        self.app = app
        self.config = config
        self.checker = checker if checker is not None else checker_for(config)
        self.register = register
        self.clock = clock
        self.check_every = check_every
        self.runtime = runtime

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)  # lifespan events carry no request
            return
        self.register.loop = asyncio.get_running_loop()
        claims = self._allowed(scope)
        if claims is None:
            await self._refuse(scope, send)
            return
        if kind == "websocket":
            await self._serve_live(scope, receive, send, claims)
            return
        if scope.get("path") == LOGOUT_PATH:
            await self._log_out(scope, send, claims)
            return
        await self.app(scope, receive, self._with_security_headers(send))

    async def _log_out(self, scope, send, claims):
        """Log out: refuse this person's logins issued up to now, retire and close all their sessions,
        then send the browser to Cloudflare's own logout. Only a plain GET from the trial's own page (or
        typed in), so another site can't log the person out."""
        site = _single_headers(scope).get(b"sec-fetch-site")
        if scope.get("method") != "GET" or site not in (None, "same-origin", "none"):
            await self._refuse(scope, send)
            return
        ended = self.register.log_out(claims["email"], now=self.clock())
        end_sessions(ended, self.register, runtime=self.runtime)
        await send({"type": "http.response.start", "status": 303,
                    "headers": [(b"location", CLOUDFLARE_LOGOUT.encode()), *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": b""})

    def _allowed(self, scope) -> dict | None:
        """The token's claims if this request may go on; None to refuse it (without reading any body)."""
        if self.config is None or self.checker is None:
            return None  # not configured: fail closed
        headers = _single_headers(scope)
        if headers is None:
            return None  # a header the gate relies on appears twice
        if headers.get(b"host", "").lower() != self.config.host:
            return None  # exactly the trial's address: no port, no other name
        if scope["type"] == "http":
            if scope.get("method", "GET") not in READ_METHODS:
                return None  # uploads are off, and nothing else in the trial sends data
            if scope.get("path", "").startswith(UPLOAD_PREFIX):
                return None
        claims = self.checker.claims(headers.get(TOKEN_HEADER.encode()))
        if claims is None or not self.register.login_allowed(claims["email"], float(claims["iat"])):
            return None
        if scope["type"] == "websocket":
            if headers.get(b"origin") != self.config.origin:
                return None  # a live connection started from another site
            resumed = _resumed_session_id(headers.get(b"sec-websocket-protocol"))
            if resumed is not None and not self.register.may_resume(resumed, claims["email"]):
                return None  # a session a logout ended, or someone else's
        return claims

    async def _refuse(self, scope, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"), *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": b"Not allowed."})

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

    async def _serve_live(self, scope, receive, send, claims):
        """Run a live connection, closing it from the server side once its login has expired or been
        logged out: checked about once a second even when nothing is sent, and on every message either
        way. After that, nothing more reaches the browser and nothing more from it reaches Streamlit."""
        lock = asyncio.Lock()
        state = {"ended": False, "watch": None}

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

        async def guarded_send(message):
            if message["type"] == "websocket.send" and self._ended(claims):
                await end()
            async with lock:
                if state["ended"]:
                    return  # dropped: the login has ended
                await send(message)
            if message["type"] == "websocket.accept" and state["watch"] is None:
                state["watch"] = asyncio.create_task(watch())

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
            if state["watch"] is not None:
                state["watch"].cancel()


def identity_from_headers(headers: Mapping[str, str] | None, checker: TokenChecker | None) -> str | None:
    """The invited person's email for this page view, or None. The page checks the token itself too,
    so a gate mistake alone can't open the trial."""
    if headers is None or checker is None:
        return None
    lowered = {k.lower(): v for k, v in headers.items()}
    claims = checker.claims(lowered.get(TOKEN_HEADER))
    if claims is None or not REGISTER.login_allowed(claims["email"], float(claims["iat"])):
        return None
    return claims["email"]
