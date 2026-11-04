"""Tests for the website trial's safety checks (trial_access, PR A1 of issue #131's lean v1.2).

Everything here is made up: a locally generated signing key stands in for Cloudflare's, and the
emails are example.com addresses. No network, no real login service.
"""
import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
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


def token(email=INVITED, aud=AUD, iss=TEAM, iat=None, exp=None, key=KEY, **extra):
    now = time.time()
    claims = {"email": email, "aud": [aud], "iss": iss, "iat": int(now - 5 if iat is None else iat),
              "exp": int(now + 3600 if exp is None else exp), **extra}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})


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


class RegisterTests(unittest.TestCase):
    def test_a_session_belongs_to_one_person_for_good(self):
        r = ta.SessionRegister()
        self.assertTrue(r.bind("s1", INVITED))
        self.assertTrue(r.bind("s1", INVITED))
        self.assertFalse(r.bind("s1", "someone@example.com"))
        self.assertTrue(r.belongs_to("s1", INVITED))

    def test_uploads_need_consent_in_that_exact_session(self):
        r = ta.SessionRegister()
        r.bind("s1", INVITED)
        r.bind("s2", INVITED)
        self.assertFalse(r.may_upload("s1", INVITED))
        r.set_consent("s1", INVITED, True)
        self.assertTrue(r.may_upload("s1", INVITED))
        self.assertFalse(r.may_upload("s2", INVITED))  # another tab of the same person
        self.assertFalse(r.may_upload("s1", "someone@example.com"))
        r.set_consent("s1", "someone@example.com", False)  # another person can't change it
        self.assertTrue(r.may_upload("s1", INVITED))
        r.set_consent("s1", INVITED, False)
        self.assertFalse(r.may_upload("s1", INVITED))
        self.assertFalse(r.may_upload("unknown", INVITED))

    def test_log_out_ends_every_session_and_earlier_logins(self):
        r = ta.SessionRegister()
        for sid in ("s1", "s2"):
            r.bind(sid, INVITED)
            r.set_consent(sid, INVITED, True)
        r.log_out(INVITED, now=1000)
        self.assertFalse(r.may_upload("s1", INVITED))
        self.assertFalse(r.belongs_to("s2", INVITED))
        self.assertFalse(r.login_allowed(INVITED, 999))
        self.assertFalse(r.login_allowed(INVITED, 1000))
        self.assertTrue(r.login_allowed(INVITED, 1001))

    def test_closed_sessions_are_forgotten(self):
        r = ta.SessionRegister()
        r.bind("open", INVITED)
        r.bind("closed", INVITED)
        r.prune(lambda sid: sid == "open")
        self.assertTrue(r.belongs_to("open", INVITED))
        self.assertFalse(r.belongs_to("closed", INVITED))


def http_scope(path="/", method="GET", host=HOST, tok=None, origin=None, length=None):
    headers = [(b"host", host.encode())]
    if tok:
        headers.append((b"cf-access-jwt-assertion", tok.encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    return {"type": "http", "method": method, "path": path, "headers": headers}


def ws_scope(tok=None, origin=ORIGIN, host=HOST):
    scope = http_scope("/_stcore/stream", host=host, tok=tok, origin=origin)
    scope["type"] = "websocket"
    scope.pop("method")
    return scope


class Recorder:
    """An inner app and a client side that record what happened."""

    def __init__(self, incoming=None):
        self.app_called = False
        self.body_read = False
        self.app_got = []
        self.sent = []
        self.incoming = list(incoming or [{"type": "http.request", "body": b"x", "more_body": False}])

    async def app(self, scope, receive, send):
        self.app_called = True
        if scope["type"] == "http":
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
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
            rec = run(self.kw, scope)
            self.assertEqual(403, rec.status())
            self.assertFalse(rec.app_called)
        rec = run(self.kw, http_scope("/media/abc.png", tok=token()))
        self.assertEqual(200, rec.status())

    def test_every_response_says_dont_store_and_dont_frame(self):
        rec = run(self.kw, http_scope(tok=token()))
        headers = dict(rec.sent[0]["headers"])
        self.assertEqual(b"no-store", headers[b"cache-control"])
        self.assertEqual(b"frame-ancestors 'none'", headers[b"content-security-policy"])
        self.assertEqual(b"DENY", headers[b"x-frame-options"])

    def upload(self, session_id="s1", tok=None, origin=ORIGIN, length=1000, method="PUT"):
        return http_scope(f"/_stcore/upload_file/{session_id}/file-1", method=method, tok=tok or token(),
                          origin=origin, length=length)

    def test_an_upload_without_consent_is_refused_before_its_body_is_read(self):
        self.register.bind("s1", INVITED)
        rec = run(self.kw, self.upload())
        self.assertEqual(403, rec.status())
        self.assertFalse(rec.app_called)
        self.assertFalse(rec.body_read)  # not one byte of the file was read

    def test_an_upload_with_consent_in_that_session_goes_through(self):
        self.register.bind("s1", INVITED)
        self.register.set_consent("s1", INVITED, True)
        rec = run(self.kw, self.upload())
        self.assertEqual(200, rec.status())
        self.assertTrue(rec.app_called)

    def test_uploads_into_another_or_unknown_session_are_refused(self):
        self.register.bind("s1", INVITED)
        self.register.set_consent("s1", INVITED, True)
        for scope in (self.upload(session_id="s2"), self.upload(session_id="s1/../s1")):
            rec = run(self.kw, scope)
            self.assertEqual(403, rec.status())
            self.assertFalse(rec.body_read)

    def test_withdrawn_consent_and_logout_refuse_the_next_upload(self):
        self.register.bind("s1", INVITED)
        self.register.set_consent("s1", INVITED, True)
        self.register.set_consent("s1", INVITED, False)
        self.assertEqual(403, run(self.kw, self.upload()).status())
        self.register.set_consent("s1", INVITED, True)
        self.register.log_out(INVITED)
        rec = run(self.kw, self.upload())
        self.assertEqual(403, rec.status())
        self.assertFalse(rec.body_read)

    def test_cross_site_and_oversized_uploads_are_refused(self):
        self.register.bind("s1", INVITED)
        self.register.set_consent("s1", INVITED, True)
        for scope in (self.upload(origin=None), self.upload(origin="https://evil.example.com"),
                      self.upload(length=None), self.upload(length=ta.MAX_UPLOAD_REQUEST_BYTES + 1)):
            rec = run(self.kw, scope)
            self.assertEqual(403, rec.status())
            self.assertFalse(rec.body_read)

    def test_other_sending_requests_are_refused_before_their_body_is_read(self):
        self.register.bind("s1", INVITED)
        self.register.set_consent("s1", INVITED, True)
        for path, method in (("/_stcore/upload_file/s1/file-1/extra", "PUT"), ("/_stcore/upload_file/s1", "PUT"),
                             ("/_stcore/upload_file/s1/file-1", "POST"), ("/", "POST"), ("/media/x", "PUT"),
                             ("/_stcore/anything", "PATCH")):
            rec = run(self.kw, http_scope(path, method=method, tok=token(), origin=ORIGIN, length=10))
            self.assertEqual(403, rec.status(), (path, method))
            self.assertFalse(rec.body_read, (path, method))

    def test_deleting_an_upload_also_needs_consent_in_that_session(self):
        self.register.bind("s1", INVITED)
        self.assertEqual(403, run(self.kw, self.upload(method="DELETE", length=0)).status())

    def test_a_live_connection_needs_the_trial_origin(self):
        for scope in (ws_scope(tok=token(), origin="https://evil.example.com"), ws_scope(tok=token(), origin=None),
                      ws_scope()):
            rec = run(self.kw, scope)
            self.assertTrue(rec.closed())
            self.assertFalse(rec.app_called)
        rec = run(self.kw, ws_scope(tok=token()), Recorder([{"type": "websocket.receive", "text": "hi"}]))
        self.assertTrue(rec.app_called)
        self.assertEqual("websocket.receive", rec.app_got[0]["type"])

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
                self.register.log_out(INVITED)  # logged out in another tab while this one is open
                return await rec.receive()
            await gate(ws_scope(tok=tok), receive, rec.send)
        asyncio.run(scenario())
        self.assertTrue(rec.closed())
        self.assertEqual("websocket.disconnect", rec.app_got[0]["type"])

    def test_after_logout_earlier_logins_are_refused_and_new_ones_work(self):
        old = token(iat=time.time() - 30)
        self.register.log_out(INVITED, now=time.time() - 10)
        self.assertEqual(403, run(self.kw, http_scope(tok=old)).status())
        self.assertEqual(200, run(self.kw, http_scope(tok=token(iat=time.time()))).status())

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
    def run_page(self, email=INVITED, environ=None):
        register = ta.SessionRegister()
        with mock.patch.dict("os.environ", {**SETTINGS, **(environ or {})}), \
                mock.patch.object(ta, "REGISTER", register), \
                mock.patch.object(ta, "identity_from_headers", return_value=email):
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
        self.assertFalse(at.exception, at.exception)
        return at, register

    def test_trial_mode_shows_the_private_trial_and_a_log_out_button(self):
        at, register = self.run_page()
        self.assertIn("Private MargenX trial", at.info[0].value)
        self.assertIn("Log out", [b.label for b in at.button])
        self.assertTrue(at.toggle[0].value)  # starts on the made-up samples
        self.assertEqual(1, len(register._sessions))

    def test_without_a_valid_login_the_page_shows_nothing_else(self):
        at, register = self.run_page(email=None)
        self.assertIn("log in again", at.error[0].value)
        self.assertEqual(0, len(at.toggle))
        self.assertEqual(0, len(register._sessions))

    def test_the_trial_never_turns_into_the_laptop_pilot(self):
        at, _ = self.run_page(environ={"MARGINX_PILOT": "1"})
        self.assertIn("Private MargenX trial", at.info[0].value)
        self.assertEqual(0, len([w for w in at.warning if "Pilot session" in w.value]))

    def test_consent_is_reported_to_the_gate_and_withdrawn_when_unticked(self):
        register = ta.SessionRegister()
        with mock.patch.dict("os.environ", SETTINGS), mock.patch.object(ta, "REGISTER", register), \
                mock.patch.object(ta, "identity_from_headers", return_value=INVITED):
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
            sid = next(iter(register._sessions))
            at.toggle[0].set_value(False).run()
            self.assertEqual([ta.CONSENT_TEXT], [c.label for c in at.checkbox])
            self.assertFalse(register.may_upload(sid, INVITED))
            self.assertEqual(0, len(at.get("file_uploader")))
            at.checkbox[0].check().run()
            self.assertTrue(register.may_upload(sid, INVITED))
            self.assertEqual(1, len(at.get("file_uploader")))
            at.checkbox[0].uncheck().run()
            self.assertFalse(register.may_upload(sid, INVITED))
        self.assertFalse(at.exception, at.exception)

    def test_log_out_ends_the_session_and_sends_the_browser_to_cloudflare(self):
        register = ta.SessionRegister()
        with mock.patch.dict("os.environ", SETTINGS), mock.patch.object(ta, "REGISTER", register), \
                mock.patch.object(ta, "identity_from_headers", return_value=INVITED):
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
            next(b for b in at.button if b.label == "Log out").click().run()
            self.assertIn("logged out", at.info[0].value)
            self.assertEqual(0, len(register._sessions))
            self.assertFalse(register.login_allowed(INVITED, time.time() - 1))
        self.assertFalse(at.exception, at.exception)


if __name__ == "__main__":
    unittest.main()
