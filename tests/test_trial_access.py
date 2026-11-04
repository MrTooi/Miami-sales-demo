"""Tests for the website trial's safety checks (trial_access, PR A1 of issue #131's lean v1.2).

Everything here is made up: a locally generated signing key stands in for Cloudflare's, and the
emails are example.com addresses. No network, no real login service.
"""
import asyncio
import contextlib
import json
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from streamlit.testing.v1 import AppTest

import trial_access as ta

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_MargenX_Import.py")
TEAM = "https://margenx-test.cloudflareaccess.com"
AUD = "test-aud-tag"
INVITED = "owner@example.com"
HOST = "app.example.com"
ORIGIN = f"https://{HOST}"
SETTINGS = {"MARGINX_TRIAL": "1", "MARGINX_TRIAL_TEAM_DOMAIN": TEAM, "MARGINX_TRIAL_AUDIENCE": AUD,
            "MARGINX_TRIAL_INVITED_EMAIL": INVITED, "MARGINX_TRIAL_HOST": HOST}
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CONFIG = ta.TrialConfig.from_environ(SETTINGS)


class FakeKeys:
    """Stands in for PyJWKClient: always returns the test public key."""

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=KEY.public_key())


def token(email=INVITED, aud=AUD, iss=TEAM, iat=None, exp=None, key=KEY, kid="test", **extra):
    now = time.time()
    claims = {"email": email, "aud": [aud], "iss": iss, "iat": int(now - 5 if iat is None else iat),
              "exp": int(now + 3600 if exp is None else exp), **extra}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def key_set(*pairs):
    """A key set as Cloudflare's /cdn-cgi/access/certs serves it: [(key ID, private key)] -> public keys."""
    keys = []
    for kid, key in pairs:
        jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
        keys.append({**jwk, "kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": keys}


def checker():
    return ta.TokenChecker(CONFIG, key_source=FakeKeys())


class ConfigTests(unittest.TestCase):
    def test_off_unless_switched_on_with_every_setting(self):
        self.assertIsNone(ta.TrialConfig.from_environ({}))
        self.assertIsNone(ta.TrialConfig.from_environ({**SETTINGS, "MARGINX_TRIAL": "yes"}))
        for name in SETTINGS:
            if name != "MARGINX_TRIAL":
                self.assertIsNone(ta.TrialConfig.from_environ({**SETTINGS, name: ""}), name)
        self.assertEqual(INVITED, CONFIG.invited_email)

    def test_bad_values_are_refused(self):
        for name, bad in (("MARGINX_TRIAL_TEAM_DOMAIN", "https://evil.example.com"),
                          ("MARGINX_TRIAL_TEAM_DOMAIN", "http://margenx-test.cloudflareaccess.com"),
                          ("MARGINX_TRIAL_INVITED_EMAIL", "not-an-email"),
                          ("MARGINX_TRIAL_HOST", "app.example.com/path")):
            self.assertIsNone(ta.TrialConfig.from_environ({**SETTINGS, name: bad}), (name, bad))


class TokenTests(unittest.TestCase):
    def test_a_valid_token_for_the_invited_person_is_accepted(self):
        self.assertEqual(INVITED, checker().claims(token())["email"])
        self.assertEqual(INVITED, checker().claims(token(email="Owner@Example.com"))["email"])

    def test_everything_else_is_refused(self):
        bad = {
            "no token": None,
            "garbage": "not.a.token",
            "another person": token(email="someone@example.com"),
            "wrong app": token(aud="another-app"),
            "wrong issuer": token(iss="https://other.cloudflareaccess.com"),
            "expired": token(exp=time.time() - 10),
            "forged with another key": token(key=OTHER_KEY),
            "no email": jwt.encode({"aud": [AUD], "iss": TEAM, "iat": int(time.time()), "exp": int(time.time()) + 60},
                                   KEY, algorithm="RS256"),
        }
        for name, value in bad.items():
            self.assertIsNone(checker().claims(value), name)

    def test_a_symmetric_algorithm_trick_is_refused(self):
        # An HS256 token "signed" with something public must never pass as RS256.
        forged = jwt.encode({"email": INVITED, "aud": [AUD], "iss": TEAM, "iat": int(time.time()),
                             "exp": int(time.time()) + 60}, "public-key-material-used-as-a-secret-key-0123", algorithm="HS256")
        self.assertIsNone(checker().claims(forged))

    def test_no_single_key_is_cached_beyond_the_key_set(self):
        self.assertFalse(hasattr(ta.TokenChecker(CONFIG)._keys.get_signing_key, "cache_info"))

    def test_a_key_cloudflare_removed_stops_working_once_the_set_is_fetched_again(self):
        served = {"set": key_set(("old", KEY))}
        with mock.patch.object(ta, "KEY_SET_SECONDS", 0.2), \
                mock.patch.object(jwt.PyJWKClient, "fetch_data", lambda client: served["set"]):
            c = ta.TokenChecker(CONFIG)  # the real key client, with its network fetch replaced
            old = token(kid="old")
            self.assertEqual(INVITED, c.claims(old)["email"])
            served["set"] = key_set(("new", OTHER_KEY))  # Cloudflare rotated: the old key is gone
            time.sleep(0.3)
            self.assertIsNone(c.claims(old))
            self.assertEqual(INVITED, c.claims(token(key=OTHER_KEY, kid="new"))["email"])


class RegisterTests(unittest.TestCase):
    def test_a_session_belongs_to_one_person_for_good(self):
        r = ta.SessionRegister()
        self.assertTrue(r.bind("s1", INVITED))
        self.assertTrue(r.bind("s1", INVITED))
        self.assertFalse(r.bind("s1", "someone@example.com"))
        self.assertTrue(r.may_resume("s1", INVITED))
        self.assertFalse(r.may_resume("s1", "someone@example.com"))
        self.assertTrue(r.may_resume("never-seen", INVITED))  # Streamlit then starts a new session

    def test_log_out_retires_every_session_and_refuses_earlier_logins(self):
        r = ta.SessionRegister()
        r.bind("s1", INVITED)
        r.bind("s2", INVITED)
        r.bind("x", "someone@example.com")
        self.assertEqual(["s1", "s2"], sorted(r.log_out(INVITED, now=1000)))
        for sid in ("s1", "s2"):
            self.assertFalse(r.bind(sid, INVITED))  # never usable again, even by the same person
            self.assertFalse(r.may_resume(sid, INVITED))
        self.assertTrue(r.may_resume("x", "someone@example.com"))
        self.assertFalse(r.login_allowed(INVITED, 999))
        self.assertFalse(r.login_allowed(INVITED, 1000))
        self.assertTrue(r.login_allowed(INVITED, 1001))
        self.assertTrue(r.bind("s3", INVITED))  # a new login gets a new session

    def test_closed_sessions_are_forgotten(self):
        r = ta.SessionRegister()
        r.bind("open", INVITED)
        r.bind("closed", INVITED)
        r.prune(lambda sid: sid == "open")
        self.assertEqual(["open"], r.log_out(INVITED))


class EndSessionsTests(unittest.TestCase):
    def test_sessions_are_closed_on_the_event_loop(self):
        closed, removed = [], []
        register = ta.SessionRegister()

        async def scenario():
            register.loop = asyncio.get_running_loop()
            loop_thread = threading.get_ident()
            rt = SimpleNamespace(
                close_session=lambda sid: closed.append((sid, threading.get_ident() == loop_thread)),
                uploaded_file_mgr=SimpleNamespace(remove_session_files=removed.append))
            # Called from another thread, as a Streamlit script thread would.
            ok = await asyncio.to_thread(ta.end_sessions, ["s1", "s2"], register, 0.1, lambda: rt)
            await asyncio.sleep(0.03)
            self.assertEqual([], closed)  # not before the delay
            await asyncio.sleep(0.2)
            return ok
        self.assertTrue(asyncio.run(scenario()))
        self.assertEqual([("s1", True), ("s2", True)], closed)
        self.assertEqual(["s1", "s2"], removed)

    def test_without_an_event_loop_it_says_so(self):
        self.assertFalse(ta.end_sessions(["s1"], ta.SessionRegister(), 0, lambda: None))
        self.assertTrue(ta.end_sessions([], ta.SessionRegister(), 0, lambda: None))  # nothing to close


def http_scope(path="/", method="GET", host=HOST, tok=None, origin=None, length=None, extra=()):
    headers = [(b"host", host.encode())]
    if tok:
        headers.append((b"cf-access-jwt-assertion", tok.encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    headers.extend(extra)
    return {"type": "http", "method": method, "path": path, "headers": headers}


def ws_scope(tok=None, origin=ORIGIN, host=HOST, resume=None, extra=()):
    protocols = [(b"sec-websocket-protocol", f"streamlit, xsrf-token, {resume}".encode())] if resume else []
    scope = http_scope("/_stcore/stream", host=host, tok=tok, origin=origin, extra=(*protocols, *extra))
    scope["type"] = "websocket"
    scope.pop("method")
    return scope


class Recorder:
    """An inner app and a client side that record what happened."""

    def __init__(self, incoming=None, upstream_headers=()):
        self.app_called = False
        self.body_read = False
        self.app_got = []
        self.sent = []
        self.incoming = list(incoming or [{"type": "http.request", "body": b"x", "more_body": False}])
        self.upstream_headers = list(upstream_headers)

    async def app(self, scope, receive, send):
        self.app_called = True
        if scope["type"] == "http":
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": self.upstream_headers})
            await send({"type": "http.response.body", "body": b"ok"})
        else:
            self.app_got.append(await receive())

    async def receive(self):
        self.body_read = True
        return self.incoming.pop(0)

    async def send(self, message):
        self.sent.append(message)

    def status(self):
        starts = [m for m in self.sent if m["type"] == "http.response.start"]
        return starts[0]["status"] if starts else None

    def closed(self):
        return any(m["type"] == "websocket.close" for m in self.sent)


def run(gate_kwargs, scope, recorder=None):
    recorder = recorder or Recorder()
    gate = ta.TrialGate(recorder.app, **{"config": CONFIG, "checker": checker(), **gate_kwargs})
    asyncio.run(gate(scope, recorder.receive, recorder.send))
    return recorder


class GateTests(unittest.TestCase):
    def setUp(self):
        self.register = ta.SessionRegister()
        self.kw = {"register": self.register}

    def refused(self, scope):
        rec = run(self.kw, scope)
        if scope["type"] == "websocket":
            return rec.closed() and not rec.app_called
        return rec.status() == 403 and not rec.app_called and not rec.body_read

    def test_without_settings_every_request_is_refused(self):
        rec = run({"config": None, "checker": None}, http_scope(tok=token()))
        self.assertEqual(403, rec.status())
        self.assertFalse(rec.app_called)
        rec = run({"config": None, "checker": None}, ws_scope(tok=token()))
        self.assertTrue(rec.closed())
        self.assertFalse(rec.app_called)

    def test_page_and_media_need_a_valid_token_and_the_trial_host(self):
        for scope in (http_scope(), http_scope(tok=token(email="someone@example.com")),
                      http_scope(tok=token(), host="other.example.com"), http_scope("/media/abc.png")):
            self.assertTrue(self.refused(scope))
        rec = run(self.kw, http_scope("/media/abc.png", tok=token()))
        self.assertEqual(200, rec.status())

    def test_the_host_must_be_exactly_the_trial_address(self):
        for host in ("app.example.com:443", "app.example.com:8501", "app.example.com.", "app.example.com@evil.example",
                     "evil.app.example.com", ""):
            self.assertTrue(self.refused(http_scope(tok=token(), host=host)), host)
            self.assertTrue(self.refused(ws_scope(tok=token(), host=host)), host)
        self.assertEqual(200, run(self.kw, http_scope(tok=token(), host="App.Example.com")).status())

    def test_a_header_the_gate_reads_must_not_appear_twice(self):
        twice = {
            "host": http_scope(tok=token(), extra=[(b"host", b"other.example.com")]),
            "token": http_scope(tok=token(), extra=[(b"cf-access-jwt-assertion", b"x")]),
            "origin": ws_scope(tok=token(), extra=[(b"origin", b"https://evil.example.com")]),
            "protocols": ws_scope(tok=token(), extra=[(b"sec-websocket-protocol", b"streamlit, x, s9"),
                                                      (b"sec-websocket-protocol", b"streamlit, x, s8")]),
        }
        for name, scope in twice.items():
            self.assertTrue(self.refused(scope), name)

    def test_every_response_says_dont_store_and_dont_frame(self):
        rec = run(self.kw, http_scope(tok=token()))
        headers = dict(rec.sent[0]["headers"])
        self.assertEqual(b"no-store", headers[b"cache-control"])
        self.assertEqual(b"frame-ancestors 'none'", headers[b"content-security-policy"])
        self.assertEqual(b"DENY", headers[b"x-frame-options"])

    def test_what_streamlit_says_about_caching_and_framing_is_replaced(self):
        upstream = [(b"Cache-Control", b"public, max-age=31536000"), (b"cache-control", b"no-cache"),
                    (b"X-Frame-Options", b"SAMEORIGIN"), (b"content-security-policy", b"default-src 'self'")]
        rec = run(self.kw, http_scope("/static/app.js", tok=token()), Recorder(upstream_headers=upstream))
        headers = [(k.lower(), v) for k, v in rec.sent[0]["headers"]]
        self.assertEqual([b"no-store"], [v for k, v in headers if k == b"cache-control"])
        self.assertEqual([b"DENY"], [v for k, v in headers if k == b"x-frame-options"])
        # A browser applies every policy it gets, so Streamlit's stays and ours is added.
        self.assertEqual([b"default-src 'self'", b"frame-ancestors 'none'"],
                         [v for k, v in headers if k == b"content-security-policy"])

    def test_uploads_are_off_and_refused_before_their_body_is_read(self):
        self.register.bind("s1", INVITED)
        for method in ("PUT", "DELETE", "POST", "GET", "OPTIONS", "HEAD"):
            for path in ("/_stcore/upload_file/s1/file-1", "/_stcore/upload_file/s1", "/_stcore/upload_file"):
                scope = http_scope(path, method=method, tok=token(), origin=ORIGIN, length=10)
                self.assertTrue(self.refused(scope), (method, path))

    def test_nothing_else_that_sends_data_gets_through(self):
        for path, method in (("/", "POST"), ("/media/x", "PUT"), ("/_stcore/anything", "PATCH"), ("/", "DELETE")):
            scope = http_scope(path, method=method, tok=token(), origin=ORIGIN, length=10)
            self.assertTrue(self.refused(scope), (path, method))

    def test_a_live_connection_needs_the_trial_origin(self):
        for scope in (ws_scope(tok=token(), origin="https://evil.example.com"), ws_scope(tok=token(), origin=None),
                      ws_scope()):
            self.assertTrue(self.refused(scope))
        rec = run(self.kw, ws_scope(tok=token()), Recorder([{"type": "websocket.receive", "text": "hi"}]))
        self.assertTrue(rec.app_called)
        self.assertEqual("websocket.receive", rec.app_got[0]["type"])

    def test_a_session_ended_by_logout_or_someone_elses_cannot_be_resumed(self):
        self.register.bind("mine", INVITED)
        self.register.bind("theirs", "someone@example.com")
        ok = Recorder([{"type": "websocket.receive", "text": "hi"}])
        self.assertTrue(run(self.kw, ws_scope(tok=token(), resume="mine"), ok).app_called)
        self.assertTrue(self.refused(ws_scope(tok=token(), resume="theirs")))
        self.register.log_out(INVITED, now=time.time() - 10)
        # Even with a fresh login, the retired session can't be picked up again.
        self.assertTrue(self.refused(ws_scope(tok=token(iat=time.time()), resume="mine")))

    def test_a_live_connection_is_closed_at_its_next_message_after_the_login_expires(self):
        tok = token(exp=time.time() + 60)
        rec = Recorder([{"type": "websocket.receive", "text": "hi"}])
        run({**self.kw, "clock": lambda: time.time() + 120}, ws_scope(tok=tok), rec)
        self.assertTrue(rec.closed())
        self.assertEqual("websocket.disconnect", rec.app_got[0]["type"])

    def test_a_live_connection_is_closed_at_its_next_message_after_logout(self):
        tok = token(iat=time.time() - 30)
        rec = Recorder([{"type": "websocket.receive", "text": "hi"}])
        gate = ta.TrialGate(rec.app, config=CONFIG, checker=checker(), register=self.register)

        async def scenario():
            async def receive():
                self.register.log_out(INVITED, now=time.time() - 10)  # logged out in another tab
                return await rec.receive()
            await gate(ws_scope(tok=tok), receive, rec.send)
        asyncio.run(scenario())
        self.assertTrue(rec.closed())
        self.assertEqual("websocket.disconnect", rec.app_got[0]["type"])

    def live(self, ended_by):
        """An idle live connection (Streamlit waiting, the browser sending nothing) and what reached the browser.
        `ended_by(clock)` ends the login part-way through."""
        got, sent = [], []
        now = {"t": time.time()}

        async def app(scope, receive, send):
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.send", "text": "before"})
            got.append(await receive())  # nothing comes from the browser: only the gate can end this
            await send({"type": "websocket.send", "text": "after"})

        async def scenario():
            closed = asyncio.Event()

            async def browser_receive():
                await closed.wait()
                return {"type": "websocket.disconnect", "code": 1000}

            async def browser_send(message):
                sent.append(message)
                if message["type"] == "websocket.close":
                    closed.set()
            gate = ta.TrialGate(app, config=CONFIG, checker=checker(), register=self.register,
                                clock=lambda: now["t"], check_every=0.01)
            task = asyncio.create_task(gate(ws_scope(tok=token(iat=time.time() - 30, exp=time.time() + 60)),
                                            browser_receive, browser_send))
            await asyncio.sleep(0.05)
            await ended_by(now)
            await asyncio.wait_for(task, 2)
        asyncio.run(scenario())
        return got, sent

    def test_an_idle_live_connection_is_closed_after_logout_and_gets_nothing_more(self):
        async def log_out(now):
            self.register.log_out(INVITED, now=now["t"])  # in another tab, while this one sits idle
        got, sent = self.live(log_out)
        self.assertEqual(["websocket.accept", "websocket.send", "websocket.close"], [m["type"] for m in sent])
        self.assertEqual("before", sent[1]["text"])  # "after" never reached the browser
        self.assertEqual("websocket.disconnect", got[0]["type"])

    def test_an_idle_live_connection_is_closed_when_the_login_expires(self):
        async def expire(now):
            now["t"] += 120
        got, sent = self.live(expire)
        self.assertEqual(["websocket.accept", "websocket.send", "websocket.close"], [m["type"] for m in sent])

    def log_out_via_link(self, tok=None, method="GET", site="same-origin"):
        closed = []
        register = self.register

        async def scenario():
            rt = SimpleNamespace(close_session=closed.append,
                                 uploaded_file_mgr=SimpleNamespace(remove_session_files=lambda sid: None))
            rec = Recorder()
            gate = ta.TrialGate(rec.app, config=CONFIG, checker=checker(), register=register, runtime=lambda: rt)
            extra = [(b"sec-fetch-site", site.encode())] if site else []
            await gate(http_scope(ta.LOGOUT_PATH, method=method, tok=tok or token(iat=time.time() - 30), extra=extra),
                       rec.receive, rec.send)
            await asyncio.sleep(0.05)  # the closing runs on the event loop
            return rec
        return asyncio.run(scenario()), closed

    def test_the_log_out_link_ends_everything_and_goes_to_cloudflares_logout(self):
        self.register.bind("s1", INVITED)
        self.register.bind("s2", INVITED)
        self.register.bind("x", "someone@example.com")
        rec, closed = self.log_out_via_link()
        self.assertEqual(303, rec.status())
        self.assertEqual(b"/cdn-cgi/access/logout", dict(rec.sent[0]["headers"])[b"location"])
        self.assertFalse(rec.app_called)  # answered by the gate: works even though the page can't load
        self.assertEqual(["s1", "s2"], sorted(closed))
        self.assertFalse(self.register.login_allowed(INVITED, time.time() - 1))
        self.assertFalse(self.register.bind("s1", INVITED))
        self.assertTrue(self.register.may_resume("x", "someone@example.com"))

    def test_typed_in_or_older_browsers_can_log_out_too(self):
        for site in ("none", None):
            self.register = ta.SessionRegister()
            rec, _ = self.log_out_via_link(site=site)
            self.assertEqual(303, rec.status(), site)

    def test_another_site_cannot_log_the_person_out(self):
        self.register.bind("s1", INVITED)
        for method, site in (("GET", "cross-site"), ("GET", "same-site"), ("POST", "same-origin"),
                             ("HEAD", "same-origin")):
            rec, closed = self.log_out_via_link(method=method, site=site)
            self.assertEqual(403, rec.status(), (method, site))
            self.assertEqual([], closed)
        self.assertTrue(self.register.login_allowed(INVITED, time.time() - 1))
        self.assertTrue(self.register.bind("s1", INVITED))

    def test_the_log_out_link_needs_a_valid_login_like_everything_else(self):
        rec, closed = self.log_out_via_link(tok=token(email="someone@example.com"))
        self.assertEqual(403, rec.status())
        self.assertTrue(self.register.login_allowed(INVITED, time.time() - 1))

    def test_after_logout_earlier_logins_are_refused_and_new_ones_work(self):
        old = token(iat=time.time() - 30)
        self.register.log_out(INVITED, now=time.time() - 10)
        self.assertEqual(403, run(self.kw, http_scope(tok=old)).status())
        self.assertEqual(200, run(self.kw, http_scope(tok=token(iat=time.time()))).status())

    def test_the_gate_notes_streamlits_event_loop_for_logout(self):
        run(self.kw, http_scope(tok=token()))
        self.assertIsNotNone(self.register.loop)

    def test_lifespan_events_pass_through(self):
        called = []

        async def app(scope, receive, send):
            called.append(scope["type"])
        asyncio.run(ta.TrialGate(app, config=None)({"type": "lifespan"}, None, None))
        self.assertEqual(["lifespan"], called)


class IdentityTests(unittest.TestCase):
    def test_the_page_checks_the_token_itself(self):
        with mock.patch.object(ta, "REGISTER", ta.SessionRegister()):
            self.assertEqual(INVITED, ta.identity_from_headers({"Cf-Access-Jwt-Assertion": token()}, checker()))
            self.assertIsNone(ta.identity_from_headers({}, checker()))
            self.assertIsNone(ta.identity_from_headers(None, checker()))
            self.assertIsNone(ta.identity_from_headers({"cf-access-jwt-assertion": token()}, None))
            self.assertIsNone(ta.identity_from_headers({"cf-access-jwt-assertion": token(email="x@example.com")},
                                                       checker()))


class TrialPageTests(unittest.TestCase):
    def page(self, email=INVITED, environ=None, register=None):
        register = register or ta.SessionRegister()
        patches = [mock.patch.dict("os.environ", {**SETTINGS, **(environ or {})}),
                   mock.patch.object(ta, "REGISTER", register),
                   mock.patch.object(ta, "identity_from_headers", return_value=email)]
        return register, patches

    def run_page(self, **kw):
        register, patches = self.page(**kw)
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
        self.assertFalse(at.exception, at.exception)
        return at, register

    def test_trial_mode_shows_samples_only_and_a_log_out_link(self):
        at, register = self.run_page()
        self.assertIn("Private MargenX trial", at.info[0].value)
        self.assertIn("made-up sample files", at.info[0].value)
        links = [m.value for m in at.markdown if m.value.startswith('<a class="mx-logout"')]
        self.assertEqual([f'<a class="mx-logout" href="{ta.LOGOUT_PATH}" target="_self">Log out</a>'], links)
        self.assertNotIn("Log out", [b.label for b in at.button])
        self.assertEqual(1, len(register._sessions))

    def test_the_trial_has_no_upload_box_and_no_way_to_turn_the_samples_off(self):
        at, _ = self.run_page()
        self.assertEqual([], [t for t in at.toggle if "sample" in t.label])
        self.assertEqual(0, len(at.get("file_uploader")))
        self.assertEqual(0, len(at.checkbox))  # no consent box: nothing of theirs is read yet

    def test_without_a_valid_login_the_page_shows_nothing_else(self):
        at, register = self.run_page(email=None)
        self.assertIn("log in again", at.error[0].value)
        self.assertEqual(0, len(at.toggle))
        self.assertEqual(0, len(register._sessions))

    def test_a_session_ended_by_logout_is_never_shown_again(self):
        register = ta.SessionRegister()
        _, patches = self.page(register=register)
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
            register.log_out(INVITED, now=0)  # a logout in another tab (the fresh-login check is mocked here)
            at.run()
        self.assertIn("log in again", at.error[0].value)
        self.assertEqual(0, len(register._sessions))

    def test_the_trial_never_turns_into_the_laptop_pilot(self):
        at, _ = self.run_page(environ={"MARGINX_PILOT": "1"})
        self.assertIn("Private MargenX trial", at.info[0].value)
        self.assertEqual(0, len([w for w in at.warning if "Pilot session" in w.value]))

    def test_end_session_in_the_trial_talks_about_the_trial_only(self):
        _, patches = self.page()
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
            next(b for b in at.button if b.label.startswith("End session")).click().run()
        self.assertFalse(at.exception, at.exception)
        message = at.success[0].value
        self.assertIn("Session ended", message)
        for laptop_words in ("laptop", "Ctrl", "stop MargenX", "upload"):
            self.assertNotIn(laptop_words, message)

    def test_the_laptop_pilot_has_no_log_out_link(self):
        with mock.patch.dict("os.environ", {"MARGINX_TRIAL": ""}):
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual([], [m for m in at.markdown if m.value.startswith('<a class="mx-logout"')])


if __name__ == "__main__":
    unittest.main()
