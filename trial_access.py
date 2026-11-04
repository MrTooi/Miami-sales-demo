"""The website trial's safety checks (issue #131, lean v1.2; decisions D-008 and D-009). PR A1.

The trial runs MargenX online for one invited person at a time, behind Cloudflare Access (an
emailed one-time code). Cloudflare puts a signed token on every request it lets through. This
module checks that token, and keeps a small in-memory register of which person each MargenX
session belongs to and whether that person has ticked consent in it. `TrialGate` sits in front of
every request Streamlit receives (page, live connection, uploads, media) and refuses anything
that isn't from the invited person. For an upload it also refuses before a single byte of the
file is read, unless that person ticked consent in that exact session.

Nothing here stores anything: the register lives in memory and is gone when the process stops.
The trial is switched on only by its settings (`TrialConfig.from_environ`); without every
setting, the gate refuses every request (fail closed). The laptop pilot mode (pilot_safety) is
separate and unchanged.

Limits, stated honestly:
- The gate trusts Cloudflare's signing keys, fetched from the team's own address. Release check 1
  shows the server is reachable only through the tunnel.
- An open live connection is cut when its next message arrives after the login has expired or
  been ended, not at the exact second. Figures already on screen stay visible until then, and
  files the person saved themselves stay with them.
- Logout ends every MargenX session of that person in this process, and refuses their logins
  issued before the logout. A restart forgets that, but a restart also ends every session.
"""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

TRIAL_ENV = "MARGINX_TRIAL"
TOKEN_HEADER = "cf-access-jwt-assertion"
# Streamlit session and file IDs are letters, digits and dashes. Any other shape is refused.
UPLOAD_PATH = re.compile(r"^/_stcore/upload_file/(?P<session_id>[A-Za-z0-9-]+)/(?P<file_id>[A-Za-z0-9-]+)$")
READ_METHODS = ("GET", "HEAD", "OPTIONS")
# Streamlit's upload cap is 5 MiB (.streamlit/config.toml); the form around the file adds a little.
MAX_UPLOAD_REQUEST_BYTES = 5 * 1024 * 1024 + 64 * 1024
SECURITY_HEADERS = (
    (b"cache-control", b"no-store"),
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"x-frame-options", b"DENY"),
)
CONSENT_TEXT = (
    "I am the person invited to this MargenX trial, and I'm allowed to share these files for my business. "
    "They go only to this private MargenX copy, are read in memory for this session and are not saved by "
    "MargenX. I've left out bank and card details, tax IDs and individual payroll records. I can end the "
    "session at any time."
)
NOT_YET_SUPPORTED = (
    "This trial reads one kind of file only: QuickBooks Online's Profit and Loss Detail report. Reading it "
    "isn't finished yet, so MargenX didn't use this file, and it was removed from this session. You can try "
    "MargenX with the made-up sample files in the meantime."
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

            # PyJWKClient caches the keys and fetches them again for an unknown key ID (keys rotate).
            key_source = jwt.PyJWKClient(config.certs_url, cache_keys=True, lifespan=300)
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
class _Session:
    email: str
    consent: bool = False


@dataclass
class SessionRegister:
    """Which person each MargenX session belongs to, whether they ticked consent in it, and when each
    person last logged out. In memory only; thread-safe (Streamlit runs scripts in other threads)."""

    _sessions: dict[str, _Session] = field(default_factory=dict)
    _logged_out_at: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def bind(self, session_id: str, email: str) -> bool:
        """Tie a session to a person. A session can never move to another person: False if it belongs
        to someone else (the caller then clears it)."""
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                self._sessions[session_id] = _Session(email)
                return True
            return current.email == email

    def set_consent(self, session_id: str, email: str, consent: bool) -> None:
        with self._lock:
            current = self._sessions.get(session_id)
            if current is not None and current.email == email:
                current.consent = consent

    def may_upload(self, session_id: str, email: str) -> bool:
        with self._lock:
            current = self._sessions.get(session_id)
            return current is not None and current.email == email and current.consent

    def belongs_to(self, session_id: str, email: str) -> bool:
        with self._lock:
            current = self._sessions.get(session_id)
            return current is not None and current.email == email

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def log_out(self, email: str, now: float | None = None) -> None:
        """End every session of this person and refuse their logins issued before now."""
        with self._lock:
            self._logged_out_at[email] = time.time() if now is None else now
            for sid in [sid for sid, s in self._sessions.items() if s.email == email]:
                del self._sessions[sid]

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
    """One token checker per trial setting, so Cloudflare's keys are fetched once and cached."""
    if config is None:
        return None
    if config not in _CHECKERS:
        _CHECKERS[config] = TokenChecker(config)
    return _CHECKERS[config]


def _header(scope: Mapping, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


class TrialGate:
    """ASGI middleware in front of all of Streamlit. Every request needs a valid token for the invited
    person, the trial's own Host, and for live connections and uploads, the trial's own Origin.
    Uploads also need consent in that exact session, and are refused before their body is read."""

    def __init__(self, app, config: TrialConfig | None = None, checker: TokenChecker | None = None,
                 register: SessionRegister = REGISTER, clock=time.time):
        self.app = app
        self.config = config
        self.checker = checker if checker is not None else checker_for(config)
        self.register = register
        self.clock = clock

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)  # lifespan events carry no request
            return
        claims = self._allowed(scope)
        if claims is None:
            await self._refuse(scope, send)
            return
        if kind == "websocket":
            await self.app(scope, self._watch_connection(receive, send, claims), send)
            return
        await self.app(scope, receive, self._with_security_headers(send))

    def _allowed(self, scope) -> dict | None:
        """The token's claims if this request may go on; None to refuse it (without reading any body)."""
        if self.config is None or self.checker is None:
            return None  # not configured: fail closed
        host = (_header(scope, b"host") or "").split(":")[0].lower()
        if host != self.config.host:
            return None
        claims = self.checker.claims(_header(scope, TOKEN_HEADER.encode()))
        if claims is None or not self.register.login_allowed(claims["email"], float(claims["iat"])):
            return None
        method = scope.get("method", "GET")
        if scope["type"] == "websocket" or method not in READ_METHODS:
            if _header(scope, b"origin") != self.config.origin:
                return None  # a live connection or upload started from another site
        if scope["type"] == "http" and method not in READ_METHODS:
            # Anything that sends or changes something is refused, except an upload (or its removal) at the
            # exact upload address of this person's own session, with consent ticked there.
            match = UPLOAD_PATH.match(scope.get("path", ""))
            if not match or method not in ("PUT", "DELETE"):
                return None
            if not self.register.may_upload(match["session_id"], claims["email"]):
                return None  # no consent in that session, or another person's session
            if method == "PUT":
                length = _header(scope, b"content-length")
                if not length or not length.isdigit() or int(length) > MAX_UPLOAD_REQUEST_BYTES:
                    return None
        return claims

    async def _refuse(self, scope, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"), *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": b"Not allowed."})

    def _with_security_headers(self, send):
        async def wrapped(message):
            if message["type"] == "http.response.start":
                names = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in SECURITY_HEADERS if k not in names]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)
        return wrapped

    def _watch_connection(self, receive, send, claims):
        """Close a live connection at its next message once the login has expired or been logged out."""
        email, issued, expires = claims["email"], float(claims["iat"]), float(claims["exp"])

        async def wrapped():
            message = await receive()
            if message["type"] == "websocket.receive":
                if self.clock() >= expires or not self.register.login_allowed(email, issued):
                    await send({"type": "websocket.close", "code": 1008})
                    return {"type": "websocket.disconnect", "code": 1008}
            return message
        return wrapped


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
