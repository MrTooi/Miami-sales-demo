"""Tests for the website trial's PR B (issue #131, lean v1.2): the PR #137 follow-ups, closed mode's own
refusal, and the self-check run inside a copy (deploy/trial/self_check.py).

- Token checks have a total deadline and a cap on how many run at once (trial_access.TokenChecks).
- An open live connection's token is checked again against Cloudflare's current keys.
- Closed mode refuses everyone, before any token check, with a refusal MargenX marks as its own.
- The self-check, run against the real trial page served by real Streamlit, sees MargenX itself refuse
  every probe; and fails against a server that doesn't.

Everything is made up: a locally generated key, example.com emails, no network, no real login service.
"""
import asyncio
import contextlib
import http.server
import io
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "deploy" / "trial"))

import self_check  # noqa: E402
import test_trial_access as t  # noqa: E402
import trial_access as ta  # noqa: E402


class Slow:
    """A token checker that takes `seconds` (a slow key fetch), counting the checks that are running."""

    def __init__(self, seconds, inner=None):
        self.seconds = seconds
        self.inner = inner or t.checker()
        self.running = 0
        self.most = 0
        self.lock = threading.Lock()

    def claims(self, token):
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
        try:
            time.sleep(self.seconds)
            return self.inner.claims(token)
        finally:
            with self.lock:
                self.running -= 1


class Switchable:
    """A token checker whose answer can change: a key Cloudflare removed makes every later check refuse."""

    def __init__(self):
        self.inner = t.checker()
        self.removed = False
        self.calls = 0
        self.delay = 0.0

    def claims(self, token):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return None if self.removed else self.inner.claims(token)


class TokenChecksTests(unittest.TestCase):
    def test_a_check_past_its_deadline_is_refused(self):
        checks = ta.TokenChecks(limit=2, deadline=0.2)
        started = time.monotonic()
        self.assertIsNone(asyncio.run(checks.claims(Slow(1.0), t.token())))
        self.assertLess(time.monotonic() - started, 0.8)  # it doesn't wait for the slow fetch
        self.assertIsNone(checks.claims_now(Slow(1.0), t.token()))

    def test_a_quick_check_gets_its_answer(self):
        checks = ta.TokenChecks(limit=2, deadline=2)
        self.assertEqual(t.INVITED, asyncio.run(checks.claims(t.checker(), t.token()))["email"])
        self.assertEqual(t.INVITED, checks.claims_now(t.checker(), t.token())["email"])
        self.assertIsNone(asyncio.run(checks.claims(t.checker(), t.token(email="someone@example.com"))))

    def test_beyond_the_cap_a_check_is_refused_at_once_and_never_queued(self):
        checks = ta.TokenChecks(limit=2, deadline=5)
        slow = Slow(0.6)

        async def scenario():
            stuck = [asyncio.create_task(checks.claims(slow, t.token())) for _ in range(2)]
            await asyncio.sleep(0.1)
            began = time.monotonic()
            extra = await checks.claims(t.checker(), t.token())  # a quick check, but no place is free
            waited = time.monotonic() - began
            return extra, waited, await asyncio.gather(*stuck)
        extra, waited, stuck = asyncio.run(scenario())
        self.assertIsNone(extra)
        self.assertLess(waited, 0.2)
        self.assertEqual(2, slow.most)
        self.assertTrue(all(r is not None for r in stuck))

    def test_a_stuck_check_keeps_its_place_until_its_thread_really_ends(self):
        checks = ta.TokenChecks(limit=1, deadline=0.1)
        slow = Slow(0.6)
        self.assertIsNone(asyncio.run(checks.claims(slow, t.token())))  # past the deadline: refused
        # Its thread is still in the slow fetch: the place isn't free, so threads can never pile up.
        self.assertIsNone(checks.claims_now(t.checker(), t.token()))
        time.sleep(0.8)  # the slow fetch has ended now
        self.assertEqual(t.INVITED, checks.claims_now(t.checker(), t.token())["email"])
        self.assertLessEqual(slow.most, 1)


class GateDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.register = ta.SessionRegister()

    def test_a_request_behind_a_stuck_key_fetch_is_refused_within_the_deadline(self):
        rec = t.Recorder()
        gate = ta.TrialGate(rec.app, config=t.CONFIG, checker=Slow(2.0), register=self.register,
                            checks=ta.TokenChecks(limit=4, deadline=0.2))
        began = time.monotonic()
        asyncio.run(gate(t.http_scope(tok=t.token()), rec.receive, rec.send))
        self.assertLess(time.monotonic() - began, 1.0)
        self.assertEqual(403, rec.status())
        self.assertFalse(rec.app_called)

    def test_a_logout_behind_a_stuck_key_fetch_gets_a_prompt_answer(self):
        rec = t.Recorder()
        gate = ta.TrialGate(rec.app, config=t.CONFIG, checker=Slow(2.0), register=self.register,
                            checks=ta.TokenChecks(limit=4, deadline=0.2))
        began = time.monotonic()
        asyncio.run(gate(t.http_scope(ta.LOGOUT_PATH, method="POST", tok=t.token(), origin=t.ORIGIN, length=0),
                         rec.receive, rec.send))
        self.assertLess(time.monotonic() - began, 1.0)  # never left hanging behind the fetch
        self.assertEqual(403, rec.status())  # refused: nothing changed, the person can press it again

    def test_the_gate_uses_one_shared_bounded_pool_by_default(self):
        gate = ta.TrialGate(lambda *a: None, config=t.CONFIG, checker=t.checker())
        self.assertIs(ta.CHECKS, gate.checks)
        self.assertEqual(ta.MAX_PARALLEL_CHECKS, ta.CHECKS.limit)
        self.assertEqual(ta.TOKEN_CHECK_SECONDS, ta.CHECKS.deadline)
        self.assertGreater(ta.TOKEN_CHECK_SECONDS, ta.KEY_FETCH_TIMEOUT_SECONDS)  # one slow network wait fits

    def test_the_page_uses_the_same_deadline(self):
        with mock.patch.object(ta, "CHECKS", ta.TokenChecks(limit=2, deadline=0.2)):
            began = time.monotonic()
            self.assertIsNone(ta.login_from_headers({ta.TOKEN_HEADER: t.token()}, Slow(1.0)))
            self.assertLess(time.monotonic() - began, 0.8)


class LiveKeyRecheckTests(unittest.TestCase):
    """An open live connection whose token's key Cloudflare has since removed is closed."""

    def live(self, checker, change, recheck_every=0.05, run_for=0.5):
        got, sent = [], []

        async def app(scope, receive, send):
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.send", "text": "before"})
            got.append(await receive())  # the browser sends nothing: only the gate can end this
            await send({"type": "websocket.send", "text": "after"})

        async def scenario():
            closed = asyncio.Event()

            async def browser_receive():
                try:
                    await asyncio.wait_for(closed.wait(), run_for)
                except asyncio.TimeoutError:
                    pass
                return {"type": "websocket.disconnect", "code": 1000}

            async def browser_send(message):
                sent.append(message)
                if message["type"] == "websocket.close":
                    closed.set()
            gate = ta.TrialGate(app, config=t.CONFIG, checker=checker, register=ta.SessionRegister(),
                                check_every=0.01, recheck_every=recheck_every,
                                checks=ta.TokenChecks(limit=4, deadline=0.2))
            task = asyncio.create_task(gate(t.ws_scope(tok=t.token()), browser_receive, browser_send))
            await asyncio.sleep(0.02)
            change()
            await asyncio.wait_for(task, 3)
        asyncio.run(scenario())
        return got, sent

    def test_a_removed_key_closes_the_open_connection_and_nothing_more_is_sent(self):
        checker = Switchable()
        got, sent = self.live(checker, lambda: setattr(checker, "removed", True))
        self.assertEqual(["websocket.accept", "websocket.send", "websocket.close"], [m["type"] for m in sent])
        self.assertEqual("before", sent[1]["text"])  # "after" never reached the browser
        self.assertEqual("websocket.disconnect", got[0]["type"])

    def test_a_recheck_that_misses_its_deadline_closes_the_connection(self):
        checker = Switchable()
        got, sent = self.live(checker, lambda: setattr(checker, "delay", 1.0))
        self.assertIn("websocket.close", [m["type"] for m in sent])

    def test_a_valid_key_keeps_the_connection_open_and_is_rechecked(self):
        checker = Switchable()
        got, sent = self.live(checker, lambda: None, run_for=0.4)
        self.assertNotIn("websocket.close", [m["type"] for m in sent])
        self.assertGreater(checker.calls, 2)  # the first check, then several rechecks

    def test_the_expiry_check_keeps_running_while_a_recheck_is_slow(self):
        checker = Switchable()
        now = {"t": time.time()}
        sent = []

        async def app(scope, receive, send):
            await send({"type": "websocket.accept"})
            await receive()

        async def scenario():
            closed = asyncio.Event()

            async def browser_receive():
                await closed.wait()
                return {"type": "websocket.disconnect", "code": 1000}

            async def browser_send(message):
                sent.append((time.monotonic(), message["type"]))
                if message["type"] == "websocket.close":
                    closed.set()
            gate = ta.TrialGate(app, config=t.CONFIG, checker=checker, register=ta.SessionRegister(),
                                clock=lambda: now["t"], check_every=0.01, recheck_every=0.01,
                                checks=ta.TokenChecks(limit=4, deadline=5))
            task = asyncio.create_task(gate(t.ws_scope(tok=t.token(exp=time.time() + 60)), browser_receive,
                                            browser_send))
            await asyncio.sleep(0.05)
            checker.delay = 3.0  # the next recheck is stuck in a slow fetch...
            await asyncio.sleep(0.05)
            began = time.monotonic()
            now["t"] += 120  # ...and the login expires meanwhile
            await asyncio.wait_for(task, 2)
            return began
        began = asyncio.run(scenario())
        closes = [at for at, kind in sent if kind == "websocket.close"]
        self.assertTrue(closes)
        self.assertLess(closes[0] - began, 0.5)  # closed by the expiry check, not after the slow fetch


class ClosedModeTests(unittest.TestCase):
    CLOSED = ta.TrialConfig.from_environ({**t.SETTINGS, "MARGINX_TRIAL_INVITED_EMAIL": ta.CLOSED_INVITE})

    def test_closed_mode_is_known_from_the_settings(self):
        self.assertTrue(self.CLOSED.closed)
        self.assertFalse(t.CONFIG.closed)

    def test_closed_mode_refuses_everyone_before_any_token_check_and_says_so(self):
        counted = Switchable()
        for scope in (t.http_scope(tok=t.token()), t.http_scope("/_stcore/health", tok=t.token()),
                      t.http_scope(tok=t.token(email=ta.CLOSED_INVITE)), t.http_scope()):
            rec = t.Recorder()
            gate = ta.TrialGate(rec.app, config=self.CLOSED, checker=counted, register=ta.SessionRegister())
            asyncio.run(gate(scope, rec.receive, rec.send))
            start = rec.sent[0]
            self.assertEqual(403, start["status"])
            self.assertIn((ta.GATE_HEADER, b"closed"), start["headers"])
            self.assertIn((b"cache-control", b"no-store"), start["headers"])
            self.assertEqual(ta.CLOSED_MESSAGE.encode(), rec.sent[1]["body"])
            self.assertFalse(rec.app_called)
            self.assertFalse(rec.body_read)
        self.assertEqual(0, counted.calls)  # no token was even checked
        rec = t.Recorder()
        asyncio.run(ta.TrialGate(rec.app, config=self.CLOSED, checker=counted)(t.ws_scope(tok=t.token()),
                                                                              rec.receive, rec.send))
        self.assertTrue(rec.closed())
        self.assertFalse(rec.app_called)

    def test_an_ordinary_refusal_is_marked_as_the_gates_own(self):
        rec = t.run({"register": ta.SessionRegister()}, t.http_scope())
        self.assertIn((ta.GATE_HEADER, b"refused"), rec.sent[0]["headers"])
        self.assertEqual(b"Not allowed.", rec.sent[1]["body"])
        ok = t.run({"register": ta.SessionRegister()}, t.http_scope(tok=t.token()))
        self.assertNotIn(ta.GATE_HEADER, [k for k, _ in ok.sent[0]["headers"]])  # only on refusals

    def test_the_launcher_and_the_gate_agree_on_nobodys_address(self):
        import launch
        self.assertEqual(ta.CLOSED_INVITE, launch.CLOSED_INVITE)
        self.assertEqual(ta.CLOSED_INVITE, launch.streamlit_env({**t.SETTINGS, launch.CLOSED_ENV: "1"})[
            "MARGINX_TRIAL_INVITED_EMAIL"])


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SelfCheckTests(unittest.TestCase):
    """The self-check run against the real trial page, served by real Streamlit behind the real gate."""

    def serve(self, settings):
        port = free_port()
        # Every outside request goes to a closed local port, so the key fetch fails at once: no network.
        nowhere = "http://127.0.0.1:9"
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "HTTPS_PROXY": nowhere,
               "https_proxy": nowhere, "HTTP_PROXY": nowhere, "http_proxy": nowhere, **settings}
        server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "trial_app.py", "--server.address",
                                   "127.0.0.1", "--server.port", str(port), "--server.headless", "true",
                                   "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none"],
                                  cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (server.terminate(), server.wait(10)))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                return port
            except OSError:
                time.sleep(0.2)
        self.fail("Streamlit never started listening")

    def check(self, port, environ):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self_check.main(["--port", str(port)], environ=environ)
        return code, out.getvalue()

    def test_margenx_itself_refuses_every_probe_in_an_open_copy(self):
        settings = {**t.SETTINGS, "MARGINX_TRIAL_TEAM_DOMAIN": "https://margenx-selfcheck.cloudflareaccess.com"}
        port = self.serve(settings)
        # The forged login makes MargenX look up the made-up team's keys, which fails here: refused either way.
        code, out = self.check(port, settings)
        self.assertEqual(0, code, out)
        self.assertEqual(11, out.count("PASS"), out)
        self.assertIn("all refused by MargenX itself", out)
        self.assertIn("open (invited person only)", out)
        self.assertNotIn(t.INVITED, out)
        self.assertNotIn(t.AUD, out)

    def test_in_closed_mode_every_refusal_says_closed(self):
        port = self.serve({**t.SETTINGS, "MARGINX_TRIAL_INVITED_EMAIL": ta.CLOSED_INVITE})
        code, out = self.check(port, t.SETTINGS)
        self.assertEqual(0, code, out)
        self.assertIn("the copy is in closed mode", out)
        self.assertNotIn("gate refused", out)

    def stand_in(self, status, headers=()):
        """A server that answers every request with `status`: not MargenX's gate."""
        class Answer(http.server.BaseHTTPRequestHandler):
            def answer(self):
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"no")
            do_GET = do_POST = do_PUT = answer

            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Answer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_it_fails_against_a_server_that_lets_requests_through(self):
        code, out = self.check(self.stand_in(200), t.SETTINGS)
        self.assertEqual(1, code)
        self.assertIn("FAIL  page, no login: 200", out)

    def test_a_refusal_that_isnt_marked_as_margenxs_own_doesnt_count(self):
        # Like a refusal from something else in front (Cloudflare's own 403): it proves nothing about MargenX.
        code, out = self.check(self.stand_in(403, [("Cache-Control", "no-store")]), t.SETTINGS)
        self.assertEqual(1, code)
        self.assertIn("FAIL  page, no login: 403, gate not seen", out)

    def test_without_the_trial_address_it_asks_for_it(self):
        code, out = self.check(free_port(), {})
        self.assertEqual(2, code)
        self.assertIn("--host", out)


if __name__ == "__main__":
    unittest.main()
