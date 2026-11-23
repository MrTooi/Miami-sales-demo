"""The uploads PR (issue #131, plan v7): consent, endings and uploads in the website trial's gate and page.

Everything is made up: a local signing key, example.com emails, made-up files with marker text. The upload
tests use Streamlit's own, pinned upload handler (streamlit==1.65.0) behind the real gate. No network.
"""
import asyncio
import contextlib
import io
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from starlette.applications import Starlette
from starlette.formparsers import MultiPartParser
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.runtime.uploaded_file_manager import UploadedFileRec
from streamlit.testing.v1 import AppTest
from streamlit.web.server.starlette.starlette_app_utils import generate_xsrf_token_string
from streamlit.web.server.starlette.starlette_routes import create_upload_routes

import tests.test_trial_access as t
import trial_access as ta
import trial_control as tc
import upload_limits

ROOT = Path(__file__).resolve().parents[1]
NAME_MARKER = "MXNAME7f3a"
CONTENT_MARKER = "MXCONTENT91c2"
XSRF_BYTES = b"k" * 16


class Pipe:
    """A real control pipe, with the launcher's reader on the other end."""

    def __init__(self, test):
        self.read_fd, self.write_fd = os.pipe()
        os.set_blocking(self.read_fd, False)
        test.addCleanup(self.close)
        self.reader = tc.Reader()
        self.words = []

    def read(self):
        try:
            self.words += self.reader.feed(os.read(self.read_fd, 65536))
        except BlockingIOError:
            pass
        return self.words

    def close(self):
        for fd in (self.read_fd, self.write_fd):
            with contextlib.suppress(OSError):
                os.close(fd)


class Killed(BaseException):
    pass


def never_returns():
    raise Killed()


def consented(test, session="s1"):
    """A process state whose one consent belongs to `session`, on connection 1, with a real control pipe."""
    pipe = Pipe(test)
    register = ta.SessionRegister()
    register.bind(session, t.INVITED, t.ISSUED)
    state = ta.TrialState(ta.Control(pipe.write_fd, never_returns), register)
    connection = state.admit()
    state.learn(connection, session)
    test.assertEqual("granted", state.grant(session, t.INVITED))
    return state, pipe, register


def xsrf_headers(ok=True):
    supplied = generate_xsrf_token_string(XSRF_BYTES)
    cookie = generate_xsrf_token_string(XSRF_BYTES if ok else b"z" * 16)
    return [(b"x-xsrftoken", supplied.encode()), (b"cookie", f"_streamlit_xsrf={cookie}".encode())]


def multipart(name="report.xlsx", content=b"made-up", field="file", boundary="mxboundary", extra=b""):
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + content + f"\r\n".encode() + extra
    return body + f"--{boundary}--\r\n".encode()


def upload_scope(session, file_id, body=b"", method="PUT", origin=t.ORIGIN, tok="valid", xsrf=True, length="auto",
                 extra=()):
    headers = [(b"host", t.HOST.encode()), (b"content-type", b"multipart/form-data; boundary=mxboundary")]
    if tok:
        headers.append((b"cf-access-jwt-assertion", (t.token() if tok == "valid" else tok).encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    if xsrf:
        headers += xsrf_headers(xsrf is True)
    if length == "auto":
        length = len(body) if method == "PUT" else None
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    headers.extend(extra)
    return {"type": "http", "method": method, "path": f"{ta.UPLOAD_PREFIX}/{session}/{file_id}", "headers": headers,
            "query_string": b"", "scheme": "http", "server": ("127.0.0.1", 8501), "client": ("127.0.0.1", 1),
            "root_path": ""}


class Client:
    """The browser side: sends a body in chunks (optionally slowly), records every read and every answer."""

    def __init__(self, body=b"", chunk=65536, pause=0.0, then=None, disconnect_after=None):
        self.chunks = [body[i:i + chunk] for i in range(0, len(body), chunk)] or [b""]
        self.pause, self.then, self.disconnect_after = pause, then, disconnect_after
        self.reads = 0
        self.sent = []

    async def receive(self):
        self.reads += 1
        if self.disconnect_after is not None and self.reads > self.disconnect_after:
            return {"type": "http.disconnect"}
        if self.pause:
            await asyncio.sleep(self.pause)
        if self.then and self.reads == 2:
            self.then()
        if not self.chunks:
            await asyncio.sleep(3600)  # a client that never sends the rest
        chunk = self.chunks.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(self.chunks)}

    async def send(self, message):
        self.sent.append(message)

    def status(self):
        return next((m["status"] for m in self.sent if m["type"] == "http.response.start"), None)

    def headers(self):
        start = next((m for m in self.sent if m["type"] == "http.response.start"), {"headers": []})
        return dict(start["headers"])

    def body(self):
        return b"".join(m.get("body", b"") for m in self.sent if m["type"] == "http.response.body")


class UploadBase(unittest.TestCase):
    def setUp(self):
        self.state, self.pipe, self.register = consented(self)
        self.store = ta.upload_store_class(self.state)("/_stcore/upload_file")
        runtime = SimpleNamespace(is_active_session=lambda session_id: True)
        self.streamlit = Starlette(routes=create_upload_routes(runtime, self.store, None))
        self.handler_calls = 0
        old = MultiPartParser.spool_max_size
        MultiPartParser.spool_max_size = ta.MAX_UPLOAD_BODY + 1  # as trial_app.prepare() does
        self.addCleanup(setattr, MultiPartParser, "spool_max_size", old)

    async def counted(self, scope, receive, send):
        self.handler_calls += 1
        await self.streamlit(scope, receive, send)

    def gate(self, **kw):
        return ta.TrialGate(self.counted, config=t.CONFIG, checker=t.checker(), register=self.register,
                            state=self.state, **kw)

    def address(self, session="s1"):
        (info,) = self.store.get_upload_urls(session, ["report.xlsx"])
        return info.file_id

    def send(self, scope, client, **kw):
        asyncio.run(self.gate(**kw)(scope, client.receive, client.send))
        return client

    def upload(self, file_id, body, session="s1", client=None, upload_seconds=None, **kw):
        gate = {} if upload_seconds is None else {"upload_seconds": upload_seconds}
        return self.send(upload_scope(session, file_id, body, **kw), client or Client(body), **gate)

    def stored(self, file_id, session="s1"):
        return self.store.get_files(session, [file_id])


class BeforeTheBodyTests(UploadBase):
    def assert_refused_unread(self, client, why):
        self.assertEqual(403, client.status(), why)
        self.assertEqual(b"refused", client.headers().get(ta.GATE_HEADER), why)
        self.assertEqual(0, client.reads, f"{why}: the body was read")
        self.assertEqual(0, self.handler_calls, f"{why}: Streamlit's handler was reached")

    def test_a_direct_upload_is_refused_before_any_body_is_read_unless_every_check_passes(self):
        body = multipart()
        good = self.address()
        other_good = self.address()
        cases = {
            "no login": dict(tok=None),
            "a forged login": dict(tok=t.token(key=t.OTHER_KEY)),
            "someone else's login": dict(tok=t.token(email="someone@example.com")),
            "an expired login": dict(tok=t.token(exp=time.time() - 10)),
            "another site": dict(origin="https://evil.example.com"),
            "no Origin": dict(origin=None),
            "cross-site": dict(extra=[(b"sec-fetch-site", b"cross-site")]),
            "no XSRF token": dict(xsrf=False),
            "a wrong XSRF token": dict(xsrf="wrong"),
            "two Cookie headers": dict(extra=[(b"cookie", b"a=b")]),
            "no size": dict(length=None),
            "too big": dict(length=ta.MAX_UPLOAD_BODY + 1),
            "a chunked body": dict(extra=[(b"transfer-encoding", b"chunked")]),
            "two hosts": dict(extra=[(b"host", b"other.example.com")]),
        }
        for why, kw in cases.items():
            self.handler_calls = 0
            client = self.send(upload_scope("s1", good, body, **kw), Client(body))
            self.assert_refused_unread(client, why)
        # And with every header right: an address never issued, or issued to another session.
        for why, (session, file_id) in {"an address never issued": ("s1", "made-up-id"),
                                        "another session's path": ("s2", other_good)}.items():
            self.handler_calls = 0
            self.assert_refused_unread(self.send(upload_scope(session, file_id, body), Client(body)), why)
        self.assertEqual([], self.stored(good))

    def test_two_tabs_of_the_same_person_only_the_consenting_one_can_upload(self):
        self.register.bind("s2", t.INVITED, t.ISSUED)  # a second tab of the same person, same login
        issued_to_other = self.store.get_upload_urls("s2", ["report.xlsx"])[0].file_id  # never recorded
        body = multipart()
        for session, file_id in (("s2", issued_to_other), ("s2", self.address())):
            self.handler_calls = 0
            self.assert_refused_unread(self.send(upload_scope(session, file_id, body), Client(body)), session)

    def test_without_consent_and_while_ending_nothing_is_read(self):
        body = multipart()
        file_id = self.address()
        self.state.end()
        self.assertEqual(["recycle"], self.pipe.read())
        self.assert_refused_unread(self.upload(file_id, body), "ending")
        state = ta.TrialState(None, self.register)
        self.assertEqual([], [a for a in state.issue("s1", 1) if a in state._attempts])
        self.assertEqual("unavailable", state.grant("s1", t.INVITED))  # no launcher: no consent at all

    def test_an_address_recorded_for_another_session_is_never_accepted(self):
        """Defense in depth: addresses are only ever recorded for the consented session, but even one recorded
        for another session (planted here directly) is refused."""
        self.state._attempts["planted"] = ta.Attempt("s2")
        self.assertFalse(self.state.begin_upload("s1", "planted"))

    def test_the_consented_tab_gone_means_no_upload(self):
        file_id = self.address()
        self.state.leave(self.state.consented_connection)  # the tab closed: the process ends
        self.assertEqual(["recycle"], self.pipe.read())
        self.assert_refused_unread(self.upload(file_id, multipart()), "the tab is gone")


class ThroughStreamlitTests(UploadBase):
    def test_the_consenting_session_uploads_through_streamlits_own_handler(self):
        file_id = self.address()
        client = self.upload(file_id, multipart(content=b"made-up workbook"))
        self.assertEqual(204, client.status(), client.body())
        self.assertEqual(b"no-store", client.headers().get(b"cache-control"))
        (record,) = self.stored(file_id)
        self.assertEqual(b"made-up workbook", record.data)
        self.assertIs(record, self.state._attempts[file_id].stored)  # the exact object stored
        # The same address can't be used twice: bytes are never replaced.
        self.handler_calls = 0
        again = self.upload(file_id, multipart(content=b"other bytes"))
        self.assertEqual(403, again.status())
        self.assertEqual(0, again.reads)
        self.assertEqual(b"made-up workbook", self.stored(file_id)[0].data)
        # Removing it removes only that file.
        second = self.address()
        self.upload(second, multipart(content=b"second"))
        removed = self.send(upload_scope("s1", file_id, method="DELETE"), Client())
        self.assertEqual(204, removed.status())
        self.assertEqual([], self.stored(file_id))
        self.assertEqual(b"second", self.stored(second)[0].data)

    def test_the_store_never_replaces_bytes_and_shows_only_what_it_stored(self):
        file_id = self.address()
        self.assertTrue(self.state.begin_upload("s1", file_id))
        first = UploadedFileRec(file_id=file_id, name="a.xlsx", type="x", data=b"one")
        self.store.add_file("s1", first)
        self.store.add_file("s1", UploadedFileRec(file_id=file_id, name="a.xlsx", type="x", data=b"two"))
        (record,) = self.stored(file_id)
        self.assertIs(first, record)
        # A file put in Streamlit's storage some other way is never shown.
        super(type(self.store), self.store).add_file("s1", UploadedFileRec(file_id="planted", name="p", type="x",
                                                                            data=b"x"))
        self.assertEqual([], self.stored("planted"))
        self.state.end()
        self.assertEqual([], self.stored(file_id))  # nothing once the process is ending

    def test_a_slow_or_interrupted_upload_stores_nothing(self):
        body = multipart(content=b"x" * 200_000)
        slow = self.upload(self.address(), body, client=Client(body, chunk=10_000, pause=0.05), upload_seconds=0.2)
        self.assertEqual(403, slow.status())
        interrupted = self.upload(self.address(), body, client=Client(body, chunk=10_000, disconnect_after=3))
        self.assertEqual(403, interrupted.status())
        stalled_body = multipart(content=b"y" * 100_000)
        stalled = Client(stalled_body, chunk=10_000)
        stalled.chunks = stalled.chunks[:2]  # the rest never comes
        stalled.chunks[-1] = stalled.chunks[-1]
        self.assertEqual(403, self.upload(self.address(), stalled_body, client=stalled, upload_seconds=0.3).status())
        self.assertEqual([], [a for a in self.state._attempts.values() if a.state == "stored"])

    def test_an_ending_during_an_upload_drops_it_and_reads_nothing_more(self):
        body = multipart(content=b"z" * 300_000)
        client = Client(body, chunk=10_000, then=self.state.end)  # the ending lands after the first chunk
        file_id = self.address()
        self.upload(file_id, body, client=client)
        self.assertEqual(403, client.status())
        self.assertEqual(2, client.reads)  # nothing read after the ending
        self.assertEqual([], self.stored(file_id))

    def test_an_ending_between_two_chunks_stops_the_reading_at_once(self):
        body = multipart(content=b"z" * 300_000)
        client = Client(body, chunk=10_000)
        original = client.receive

        async def receive():
            message = await original()
            if client.reads == 2:  # the ending lands right after the second chunk was handed on
                asyncio.get_running_loop().call_soon(self.state.end)
            return message
        client.receive = receive
        file_id = self.address()
        self.upload(file_id, body, client=client)
        self.assertEqual(403, client.status())
        self.assertEqual(2, client.reads)
        self.assertEqual([], self.stored(file_id))

    def test_once_ending_the_upload_reader_asks_for_no_more_chunks(self):
        calls = []

        async def receive():
            calls.append(1)
            return {"type": "http.request", "body": b"x", "more_body": True}

        async def read_after_ending():
            limited = self.gate()._limited(receive)
            first = await limited()
            self.state.end()
            return first, await limited()
        first, after = asyncio.run(read_after_ending())
        self.assertEqual("http.request", first["type"])
        self.assertEqual("http.disconnect", after["type"])
        self.assertEqual(1, len(calls))  # the browser's next chunk was never even asked for

    def test_streamlits_success_is_turned_into_a_refusal_when_nothing_was_stored(self):
        file_id = self.address()
        with mock.patch.object(self.state, "commit", return_value=False):  # the store refused to commit it
            client = self.upload(file_id, multipart())
        self.assertEqual(403, client.status())
        self.assertEqual(1, self.handler_calls)  # Streamlit's handler did answer, with its 204
        self.assertEqual([], self.stored(file_id))

    def test_broken_forms_are_refused_and_store_nothing(self):
        two_files = multipart(extra=b"--mxboundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"b\"\r\n"
                                    b"\r\nsecond\r\n")
        # Two parts under one field name (never sent by a browser): Streamlit keeps one value per field name, so
        # at most one file is stored, once, at that one address; the other part is dropped from memory.
        file_id = self.address()
        self.assertEqual(204, self.upload(file_id, two_files).status())
        self.assertEqual(1, len(self.stored(file_id)))
        self.assertFalse(self.state.begin_upload("s1", file_id))  # the address is used up
        for why, body in {"no closing boundary": multipart()[:-20],
                          "no file at all": b"--mxboundary--\r\n"}.items():
            file_id = self.address() if len(self.state._attempts) < ta.MAX_ADDRESSES else None
            if file_id is None:
                self.state._attempts.clear()
                file_id = self.address()
            client = self.upload(file_id, body)
            self.assertEqual(403, client.status(), why)
            self.assertEqual([], self.stored(file_id), why)

    def test_uploads_never_spool_to_disk(self):
        rolled = []
        original = tempfile.SpooledTemporaryFile.rollover

        def watched(self_):
            rolled.append(1)
            return original(self_)
        body = multipart(content=os.urandom(4_000_000))
        with mock.patch.object(tempfile.SpooledTemporaryFile, "rollover", watched):
            self.assertEqual(204, self.upload(self.address(), body).status())
            self.assertEqual([], rolled)  # at the cap, in memory only
            MultiPartParser.spool_max_size = 1024 * 1024  # Starlette's default (what trial_app.prepare() changes)
            self.upload(self.address(), body)
            self.assertEqual([1], rolled)  # the planted mistake: a 4 MB part would have gone to disk

    def test_the_caps_on_addresses_receiving_and_stored_files(self):
        self.assertEqual(2, len(self.store.get_upload_urls("s1", ["a", "b"])))  # two names: none recorded
        self.assertEqual({}, {k: v for k, v in self.state._attempts.items()})
        ids = [self.address() for _ in range(ta.MAX_ADDRESSES)]
        self.assertEqual(ta.MAX_ADDRESSES, len(self.state._attempts))
        extra = self.address()
        self.assertNotIn(extra, self.state._attempts)  # beyond the cap: never recorded
        for file_id in ids[:ta.MAX_STORED]:
            self.assertEqual(204, self.upload(file_id, multipart()).status())
        self.assertFalse(self.state.begin_upload("s1", ids[ta.MAX_STORED]))  # two files held already


class EndingFirstTests(unittest.TestCase):
    def post(self, path, state, register=None, origin=t.ORIGIN, site=None, send_fails=False, clock=time.time):
        pipe_words = {}
        extra = [(b"sec-fetch-site", site.encode())] if site else []
        scope = t.http_scope(path, method="POST", tok=t.token(), origin=origin, length=0, extra=extra)
        sent = []

        async def send(message):
            pipe_words.setdefault("at the answer", list(self.pipe.read()))
            if send_fails:
                raise OSError("the browser went away")
            sent.append(message)

        async def receive():
            raise AssertionError("the body is never read")
        gate = ta.TrialGate(lambda *a: None, config=t.CONFIG, checker=t.checker(), register=register or ta.SessionRegister(),
                            state=state, clock=clock)
        asyncio.run(gate(scope, receive, send))
        return sent, pipe_words.get("at the answer")

    def test_end_session_marks_ending_and_tells_the_launcher_before_any_answer(self):
        state, self.pipe, _ = consented(self)
        sent, at_answer = self.post(ta.END_PATH, state)
        self.assertEqual(["recycle"], at_answer)  # told before the first byte of the answer
        self.assertTrue(state.ending)
        self.assertEqual(200, sent[0]["status"])
        page = sent[1]["body"].decode()
        self.assertIn("Clearing", page)
        self.assertIn(state.generation, page)

    def test_the_ending_stands_when_the_answer_fails(self):
        state, self.pipe, _ = consented(self)
        self.post(ta.END_PATH, state, send_fails=True)
        self.assertTrue(state.ending)
        self.assertEqual(["recycle"], self.pipe.read())

    def test_log_out_sends_the_cutoff_first_then_ends(self):
        state, self.pipe, register = consented(self)
        now = 1_000_000.0
        sent, at_answer = self.post(ta.LOGOUT_PATH, state, register=register, clock=lambda: now)
        self.assertEqual(["logout", "recycle"], at_answer)
        self.assertEqual(now + tc.CUTOFF_MARGIN_SECONDS, self.pipe.reader.cutoff)
        self.assertEqual(303, sent[0]["status"])
        self.assertFalse(register.login_allowed(t.INVITED, now + tc.CUTOFF_MARGIN_SECONDS))

    def test_a_logout_whose_message_cant_be_written_ends_margenx_before_answering(self):
        import tests.test_trial_supervisor as sup
        read_fd, write_fd = sup.full_pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        state = ta.TrialState(ta.Control(write_fd, never_returns), ta.SessionRegister())
        scope = t.http_scope(ta.LOGOUT_PATH, method="POST", tok=t.token(), origin=t.ORIGIN, length=0)
        sent = []

        async def send(message):
            sent.append(message)
        gate = ta.TrialGate(lambda *a: None, config=t.CONFIG, checker=t.checker(), register=ta.SessionRegister(),
                            state=state)
        with self.assertRaises(Killed):
            asyncio.run(gate(scope, None, send))
        self.assertEqual([], sent)  # nothing was answered: MargenX ended first

    def test_end_session_from_another_site_or_without_the_launcher_is_refused(self):
        state, self.pipe, _ = consented(self)
        for kw in ({"origin": "https://evil.example.com"}, {"site": "cross-site"}):
            sent, _ = self.post(ta.END_PATH, state, **kw)
            self.assertEqual(403, sent[0]["status"])
        self.assertFalse(state.ending)
        self.assertEqual([], self.pipe.read())
        sent, _ = self.post(ta.END_PATH, ta.TrialState(None, ta.SessionRegister()))
        self.assertEqual(403, sent[0]["status"])


class ConsentTests(unittest.TestCase):
    def state(self):
        self.pipe = Pipe(self)
        register = ta.SessionRegister()
        for session in ("s1", "s2"):
            register.bind(session, t.INVITED, t.ISSUED)
        return ta.TrialState(ta.Control(self.pipe.write_fd, never_returns), register)

    def test_consent_needs_the_clicking_tab_to_be_the_only_live_connection(self):
        state = self.state()
        one, two = state.admit(), state.admit()
        state.learn(one, "s1")
        state.learn(two, "s2")
        self.assertEqual("tabs", state.grant("s1", t.INVITED))  # two tabs open
        state.leave(two)
        self.assertEqual("granted", state.grant("s1", t.INVITED))
        self.assertIsNone(state.admit())  # from now on, no other live connection, reconnects included
        self.assertTrue(state.is_consented("s1"))
        self.assertFalse(state.is_consented("s2"))

    def test_a_connection_whose_session_isnt_known_yet_counts(self):
        state = self.state()
        mine = state.admit()
        state.learn(mine, "s1")
        state.admit()  # another tab connecting, its session not known yet
        self.assertEqual("tabs", state.grant("s1", t.INVITED))

    def test_a_queued_click_from_a_session_now_on_another_connection_grants_nothing(self):
        """Before consent, tab A's session is resumed on another connection (its old one gone): a consent
        click queued in A's session can't grant to a connection that isn't A's own recorded one."""
        state = self.state()
        old = state.admit()
        state.learn(old, "s1")
        state.leave(old)
        resumed = state.admit()  # the session's id isn't known for this connection yet
        self.assertEqual("tabs", state.grant("s1", t.INVITED))
        state.learn(resumed, "s2")  # it turns out to serve another session
        self.assertEqual("tabs", state.grant("s1", t.INVITED))
        self.assertIsNone(state.consented_session)

    def test_no_consent_for_someone_else_or_after_an_ending_or_twice(self):
        state = self.state()
        connection = state.admit()
        state.learn(connection, "s3")  # not bound to the invited person
        self.assertEqual("unavailable", state.grant("s3", t.INVITED))
        self.assertEqual("unavailable", state.grant(None, t.INVITED))
        state = self.state()
        connection = state.admit()
        state.learn(connection, "s1")
        self.assertEqual("granted", state.grant("s1", t.INVITED))
        self.assertEqual("unavailable", state.grant("s1", t.INVITED))
        state = self.state()
        connection = state.admit()
        state.learn(connection, "s1")
        state.end()
        self.assertEqual("unavailable", state.grant("s1", t.INVITED))

    def test_the_processing_slot_arms_the_deadline_for_exactly_the_run_and_overlapping_runs_wait(self):
        state = self.state()
        order = []
        with state.processing():
            self.assertEqual(["arm"], self.pipe.read())
            def second():
                with state.processing(wait=5):
                    order.append("second")
            waiter = threading.Thread(target=second)
            waiter.start()
            time.sleep(0.2)
            self.assertEqual([], order)  # the overlapping run waits for the slot
            order.append("first done")
        waiter.join(5)
        self.assertEqual(["first done", "second"], order)
        self.assertEqual(["arm", "disarm", "arm", "disarm"], self.pipe.read())
        state._slot.acquire()  # a run still holding the slot
        with self.assertRaises(ta.Busy):
            with state.processing(wait=0.1):
                pass
        state._slot.release()
        state.end()
        with self.assertRaises(ta.Ending):
            with state.processing():
                pass


class LiveConnectionTests(unittest.TestCase):
    def serve(self, state, incoming, app_messages=()):
        sent = []

        async def app(scope, receive, send):
            await send({"type": "websocket.accept"})
            for message in app_messages:
                await send(message)
            while True:
                message = await receive()
                if message["type"] == "websocket.disconnect":
                    return

        queue = list(incoming)

        async def receive():
            if queue:
                return queue.pop(0)
            await asyncio.sleep(0.05)
            return {"type": "websocket.disconnect", "code": 1000}

        async def send(message):
            sent.append(message)
        gate = ta.TrialGate(app, config=t.CONFIG, checker=t.checker(), register=state.register, state=state,
                            check_every=0.01)
        asyncio.run(gate(t.ws_scope(tok=t.token()), receive, send))
        return sent

    def test_the_gate_learns_each_connections_session_from_streamlits_first_message(self):
        state = ConsentTests.state(self)
        hello = ForwardMsg()
        hello.new_session.initialize.session_id = "s1"
        seen = {}

        def learn(connection, session):
            seen[connection] = session
        with mock.patch.object(state, "learn", side_effect=learn):
            self.serve(state, [], [{"type": "websocket.send", "bytes": hello.SerializeToString()}])
        self.assertEqual(["s1"], list(seen.values()))

    def test_in_consented_mode_every_other_live_connection_is_refused(self):
        state, pipe, _ = consented(self)
        sent = self.serve(state, [])
        self.assertTrue(any(m["type"] in ("websocket.close", "websocket.http.response.start") for m in sent))
        self.assertFalse(any(m["type"] == "websocket.accept" for m in sent))
        self.assertFalse(state.ending)  # a refused extra tab ends nothing

    def test_a_request_for_more_than_one_upload_address_closes_the_connection(self):
        state = ConsentTests.state(self)
        ask = BackMsg()
        ask.file_urls_request.file_names.extend(["a.xlsx", "b.xlsx"])
        sent = self.serve(state, [{"type": "websocket.receive", "bytes": ask.SerializeToString()}])
        self.assertTrue(any(m["type"] == "websocket.close" for m in sent))

    def test_nothing_more_is_sent_once_the_process_is_ending(self):
        state = ConsentTests.state(self)
        later = {"type": "websocket.send", "bytes": b"results"}

        async def app(scope, receive, send):
            await send({"type": "websocket.accept"})
            state.ending = True  # the process starts ending while results are queued for this connection
            await send(later)
            await receive()
        sent = []

        async def send(message):
            sent.append(message)

        async def receive():
            await asyncio.sleep(0.05)
            return {"type": "websocket.disconnect", "code": 1000}
        gate = ta.TrialGate(app, config=t.CONFIG, checker=t.checker(), register=state.register, state=state,
                            check_every=0.01)
        asyncio.run(gate(t.ws_scope(tok=t.token()), receive, send))
        self.assertTrue(any(m["type"] == "websocket.accept" for m in sent))
        self.assertNotIn(later, sent)


class OtherAnswerTests(unittest.TestCase):
    def test_the_generation_answer_and_the_way_back_in(self):
        state = ta.TrialState()
        rec = t.run({"register": ta.SessionRegister(), "state": state}, t.http_scope(ta.GENERATION_PATH, tok=t.token()))
        self.assertEqual(200, rec.status())
        self.assertEqual(state.generation.encode(), b"".join(m.get("body", b"") for m in rec.sent))
        register = ta.SessionRegister()
        register.log_out(t.INVITED, now=time.time())
        old = t.token(iat=time.time() - 60)
        page = t.run({"register": register, "state": state}, t.http_scope("/", tok=old))
        self.assertIn(b"Log in again", b"".join(m.get("body", b"") for m in page.sent))
        other = t.run({"register": register, "state": state}, t.http_scope("/_stcore/health", tok=old))
        self.assertEqual(b"Not allowed.", b"".join(m.get("body", b"") for m in other.sent))  # only the page
        stranger = t.run({"register": register, "state": state}, t.http_scope("/", tok=t.token(email="x@example.com")))
        self.assertEqual(b"Not allowed.", b"".join(m.get("body", b"") for m in stranger.sent))

    def test_the_reload_script_is_fixed_text_with_only_the_generation(self):
        script = ta.reload_script("0" * 32)
        self.assertIn("X-Requested-With", script)
        self.assertIn("redirect:'manual'", script)
        self.assertIn("r.status===401", script)
        with self.assertRaises(ValueError):
            ta.reload_script("<script>")


def workbook(rows=(("a", "b"),), part_size=None, parts=1):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for i in range(parts):
            data = ("x" * part_size).encode() if part_size else "\n".join(",".join(r) for r in rows).encode()
            archive.writestr(f"xl/part{i}.xml", data)
    return out.getvalue()


class UploadLimitsTests(unittest.TestCase):
    def test_broken_oversized_and_highly_compressed_files_are_refused_plainly(self):
        self.assertIsNone(upload_limits.refusal("report.xlsx", workbook()))
        self.assertEqual(upload_limits.TOO_BIG, upload_limits.refusal("report.xlsx", b"PK" + b"x" * 5_000_000))
        self.assertEqual(upload_limits.BROKEN, upload_limits.refusal("report.xlsx", b"not a workbook"))
        self.assertEqual(upload_limits.BROKEN, upload_limits.refusal("report.xlsx", b"PK\x03\x04broken"))
        bomb = workbook(part_size=30_000_000)  # 30 MB of one letter packs into a few KB
        self.assertLess(len(bomb), 100_000)
        self.assertEqual(upload_limits.TOO_MUCH, upload_limits.refusal("report.xlsx", bomb))
        ratio = workbook(part_size=5_000_000)  # under the total, but over 100 times compressed
        self.assertEqual(upload_limits.TOO_MUCH, upload_limits.refusal("report.xlsx", ratio))
        self.assertEqual(upload_limits.TOO_MUCH, upload_limits.refusal("report.xlsx", workbook(parts=101)))
        many = workbook(part_size=1_000_000, parts=30)  # each part small enough for the ratio rule, 30 MB in all
        self.assertEqual(upload_limits.TOO_MUCH, upload_limits.refusal("report.xlsx", many))
        for message in (upload_limits.TOO_BIG, upload_limits.BROKEN, upload_limits.TOO_MUCH):
            self.assertNotIn("report", message)  # never quotes the file


class MarkerTests(UploadBase):
    """A made-up workbook with a marker in its name and another in its contents: on success, on refusals and
    on a forced failure during storage, neither marker reaches any log record or any refusal."""

    def capture(self):
        records = []

        class Keep(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))
        handler = Keep(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(name)s %(message)s %(exc_text)s"))
        loggers = [logging.getLogger(), *(logging.getLogger(n) for n in list(logging.root.manager.loggerDict))]
        saved = [(lg, lg.level, lg.propagate) for lg in loggers if isinstance(lg, logging.Logger)]
        for lg, _, _ in saved:
            lg.addHandler(handler)
            lg.setLevel(logging.DEBUG)

        def undo():
            for lg, level, _ in saved:
                lg.removeHandler(handler)
                lg.setLevel(level)
        self.addCleanup(undo)
        return records

    def test_neither_marker_reaches_a_log_or_a_refusal(self):
        logs = self.capture()
        name = f"{NAME_MARKER}.xlsx"
        content = f"made-up {CONTENT_MARKER} rows".encode()
        answers = []
        ok = self.upload(self.address(), multipart(name=name, content=content))  # success
        self.assertEqual(204, ok.status())
        answers.append(ok)
        self.assertEqual(name, self.stored(list(self.state._attempts)[0])[0].name)  # stored for the person only
        answers.append(self.upload("never-issued", multipart(name=name, content=content)))  # refused
        answers.append(self.upload(self.address(), multipart(name=name, content=content), length=ta.MAX_UPLOAD_BODY + 1))
        answers.append(self.upload(self.address(), multipart(name=name, content=content)[:-30]))  # broken form
        with mock.patch.object(self.state, "commit", side_effect=RuntimeError(f"forced {NAME_MARKER} {CONTENT_MARKER}")):
            failed = self.upload(self.address(), multipart(name=name, content=content))  # forced failure in storage
        self.assertEqual(403, failed.status())
        answers.append(failed)
        everything = "\n".join(logs) + "".join(repr(a.sent) for a in answers)
        for marker in (NAME_MARKER, CONTENT_MARKER):
            self.assertNotIn(marker, everything)

    def test_the_page_error_log_keeps_only_the_errors_type(self):
        record = logging.LogRecord("streamlit.error_util", logging.ERROR, "x", 1, "Uncaught app execution", (),
                                   (ValueError, ValueError(f"cell {CONTENT_MARKER}"), None))
        ta.TypeOnly().filter(record)
        text = logging.Formatter("%(message)s %(exc_text)s").format(record)
        self.assertNotIn(CONTENT_MARKER, text)
        self.assertIn("ValueError", text)


class TrialAppTests(unittest.TestCase):
    def test_the_running_copy_uses_margenxs_upload_store_and_never_spools(self):
        # In its own process: it builds Streamlit's runtime exactly as `streamlit run trial_app.py` does.
        code = ("import os,sys;sys.path.insert(0,os.getcwd());import trial_app,trial_access as ta;"
                "from starlette.formparsers import MultiPartParser as M;rt=trial_app.app._create_runtime();"
                "print(type(rt.uploaded_file_mgr).__name__, M.spool_max_size > ta.MAX_UPLOAD_BODY)")
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=120,
                             env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")})
        self.assertEqual("TrialUploadStore True", out.stdout.strip(), out.stderr[-2000:])


class FakeUpload:
    def __init__(self, name, data, file_id="f1"):
        self.name, self._data, self.file_id = name, data, file_id

    def getvalue(self):
        return self._data


class TrialPagePieces(unittest.TestCase):
    """The page in trial mode, with the trial state replaced (no gate in AppTest)."""

    def run_page(self, state, uploads=(None, None), environ=None, click=False):
        register = ta.SessionRegister()
        patches = [mock.patch.dict("os.environ", {**t.SETTINGS, **(environ or {})}),
                   mock.patch.object(ta, "REGISTER", register), mock.patch.object(ta, "STATE", state),
                   mock.patch.object(ta, "login_from_headers", return_value=(t.INVITED, t.ISSUED))]
        files = list(uploads)
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            if any(files):
                import streamlit as st
                stack.enter_context(mock.patch.object(st, "file_uploader", side_effect=lambda *a, **k: files.pop(0)
                                                      if files else None))
            at = AppTest.from_file(t.PAGE, default_timeout=30)
            at.run()
            if click:
                next(b for b in at.button if b.label.startswith("I agree")).click().run()
        return at

    def control(self):
        self.pipe = Pipe(self)
        return ta.Control(self.pipe.write_fd, never_returns)

    def test_without_the_launcher_the_trial_offers_no_upload(self):
        at = self.run_page(ta.TrialState(None))
        self.assertFalse(at.exception, at.exception)
        self.assertEqual([], [b for b in at.button if b.label.startswith("I agree")])
        self.assertIn("made-up sample files", at.info[0].value)

    def test_the_consent_card_asks_the_state_and_says_when_other_tabs_are_open(self):
        state = ta.TrialState(self.control())
        with mock.patch.object(state, "grant", return_value="tabs") as grant:
            at = self.run_page(state, click=True)
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(1, grant.call_count)
        self.assertIn("Close your other MargenX tabs", at.warning[0].value)
        self.assertEqual(0, len(at.get("file_uploader")))

    def consented_state(self):
        state = ta.TrialState(self.control())
        return state, mock.patch.object(state, "is_consented", return_value=True)

    def test_after_consent_the_tab_shows_two_upload_boxes_and_no_samples(self):
        state, consent = self.consented_state()
        with consent:
            at = self.run_page(state)
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(2, len(at.get("file_uploader")))
        self.assertEqual(0, len(at.radio))  # no sample choice
        self.assertIn("Your own QuickBooks report", at.info[0].value)

    def test_a_file_that_isnt_a_supported_quickbooks_report_is_refused(self):
        state, consent = self.consented_state()
        with consent:
            at = self.run_page(state, uploads=(FakeUpload("list.xlsx", workbook()), None))
        self.assertFalse(at.exception, at.exception)
        self.assertIn("reads only QuickBooks Online's Profit and Loss Detail", at.error[0].value)
        self.assertEqual(["arm", "disarm"], self.pipe.read())  # read inside the slot, the deadline armed

    def test_a_quickbooks_report_with_another_file_alongside_is_refused(self):
        state, consent = self.consented_state()
        found = SimpleNamespace(quickbooks=True, other=[object()])
        with consent, mock.patch("quickbooks_upload.sort_files", return_value=found), \
                mock.patch("quickbooks_upload.show") as show:
            at = self.run_page(state, uploads=(FakeUpload("pnl.xlsx", workbook()), FakeUpload("other.xlsx", workbook())))
        self.assertFalse(at.exception, at.exception)
        self.assertIn("reads only QuickBooks Online's Profit and Loss Detail", at.error[0].value)
        show.assert_not_called()

    def test_an_oversized_or_broken_file_is_refused_before_any_reader(self):
        state, consent = self.consented_state()
        with consent, mock.patch("quickbooks_upload.sort_files") as reader:
            at = self.run_page(state, uploads=(FakeUpload("big.xlsx", b"PK" + b"x" * 5_000_001), None))
        self.assertIn(upload_limits.TOO_BIG, at.error[0].value)
        reader.assert_not_called()

    def test_a_failure_while_reading_shows_a_plain_message_and_logs_nothing_from_the_file(self):
        state, consent = self.consented_state()
        logs = MarkerTests.capture(self)
        failure = ValueError(f"cell B7 says {CONTENT_MARKER}")
        with consent, mock.patch("quickbooks_upload.sort_files", side_effect=failure):
            at = self.run_page(state, uploads=(FakeUpload(f"{NAME_MARKER}.xlsx", workbook()), None))
        self.assertFalse(at.exception, at.exception)
        self.assertIn("MargenX couldn't read this file", at.error[0].value)
        shown = " ".join(e.value for e in at.error)
        self.assertNotIn(CONTENT_MARKER, shown)
        for marker in (NAME_MARKER, CONTENT_MARKER):
            self.assertNotIn(marker, "\n".join(logs))
        self.assertEqual(["arm", "disarm"], self.pipe.read())


if __name__ == "__main__":
    unittest.main()
