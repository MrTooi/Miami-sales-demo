"""The uploads PR (issue #131, plan v7): the control pipe and the launcher's supervisor.

Made-up everything: stand-in processes, real pipes, a fake clock. No network, no real login service.
"""
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

import tests.test_trial_access as t
import trial_access as ta
import trial_control as tc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "trial"))
import launch  # noqa: E402


class EncodeTests(unittest.TestCase):
    def test_each_message_is_one_short_line_from_a_fixed_set(self):
        for word in tc.WORDS:
            line = tc.encode(word)
            self.assertEqual(f"{word}\n".encode(), line)
            self.assertLessEqual(len(line), tc.MAX_LINE)
        self.assertEqual(b"logout 1001\n", tc.encode(tc.LOGOUT, 1000.2))  # rounded up: never earlier
        with self.assertRaises(ValueError):
            tc.encode("hello")
        with self.assertRaises(ValueError):
            tc.encode(tc.LOGOUT)


class ReaderTests(unittest.TestCase):
    def test_messages_split_across_reads_or_several_in_one_are_read_whole(self):
        r = tc.Reader()
        self.assertEqual([], r.feed(b"al"))
        self.assertEqual(["alive"], r.feed(b"ive\nar"))
        self.assertEqual(["arm", "disarm", "logout", "recycle"], r.feed(b"m\ndisarm\nlogout 1700000000\nrecycle\n"))
        self.assertEqual(1_700_000_000, r.cutoff)
        self.assertTrue(r.recycle)
        self.assertTrue(r.explained(reached_end=True))

    def test_the_first_bad_line_makes_the_whole_stream_invalid(self):
        for bad in (b"hello\n", b"logout soon\n", b"logout -5\n", b"x" * 70 + b"\n", b"recycle \n", b"x" * 64):
            r = tc.Reader()
            r.feed(b"recycle\n" + bad)
            self.assertTrue(r.invalid, bad)
            self.assertFalse(r.explained(reached_end=True), bad)
            self.assertEqual([], r.feed(b"alive\n"))  # nothing more is accepted after it

    def test_a_death_is_explained_only_by_a_complete_recycle_and_a_full_read(self):
        r = tc.Reader()
        r.feed(b"alive\n")
        self.assertFalse(r.explained(True))  # no recycle
        r.feed(b"recycle\n")
        self.assertFalse(r.explained(False))  # the end of the pipe wasn't reached
        self.assertTrue(r.explained(True))
        r.feed(b"ali")  # a line without its newline after it
        self.assertFalse(r.explained(True))

    def test_cutoffs_never_go_back_and_an_unexplained_death_adds_the_margin(self):
        self.assertEqual(200, tc.later_cutoff(200, 100))
        self.assertEqual(300, tc.later_cutoff(200, 300))
        self.assertEqual(100, tc.later_cutoff(None, 100))
        self.assertEqual(1000 + tc.CUTOFF_MARGIN_SECONDS, tc.unexplained_cutoff(None, 1000))
        self.assertEqual(5000, tc.unexplained_cutoff(5000, 1000))  # never lowered
        r = tc.Reader()
        r.feed(b"logout 500\nlogout 400\n")
        self.assertEqual(500, r.cutoff)


class Killed(BaseException):
    """What MargenX ending itself looks like in a test: the call never returns."""


class FakeKill:
    def __init__(self):
        self.called = 0

    def __call__(self):
        self.called += 1
        raise Killed()


def full_pipe():
    """A pipe whose buffer is full of valid heartbeats: the next non-blocking write fails without writing."""
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    line = tc.encode(tc.ALIVE)
    while True:
        try:
            if os.write(write_fd, line) != len(line):
                raise AssertionError("a short write")
        except BlockingIOError:
            break
    return read_fd, write_fd


class ControlTests(unittest.TestCase):
    def pipe(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(lambda: [os.close(fd) for fd in (read_fd, write_fd) if _is_open(fd)])
        return read_fd, write_fd

    def test_messages_go_on_the_pipe_and_nothing_follows_a_recycle(self):
        read_fd, write_fd = self.pipe()
        kill = FakeKill()
        control = ta.Control(write_fd, kill)
        control.alive()
        control.send(tc.LOGOUT, 1234)
        control.send(tc.RECYCLE)
        control.alive()  # after the recycle: nothing more is written, the heartbeat included
        control.send(tc.ARM)
        self.assertEqual(b"alive\nlogout 1234\nrecycle\n", os.read(read_fd, 4096))
        self.assertEqual(0, kill.called)

    def test_a_message_that_cant_be_written_ends_margenx_at_once(self):
        read_fd, write_fd = full_pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        kill = FakeKill()
        control = ta.Control(write_fd, kill)
        control.alive()  # a heartbeat that can't be written now is skipped
        self.assertEqual(0, kill.called)
        with self.assertRaises(Killed):
            control.send(tc.LOGOUT, 1234)  # a logout that can't be written: MargenX ends itself
        self.assertEqual(1, kill.called)

    def test_a_closed_pipe_ends_margenx_too(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        kill = FakeKill()
        control = ta.Control(write_fd, kill)
        with self.assertRaises(Killed):
            control.alive()
        self.assertEqual(1, kill.called)
        os.close(write_fd)

    def test_the_control_comes_from_the_launchers_setting_only(self):
        self.assertIsNone(ta.Control.from_environ({}))
        self.assertIsNone(ta.Control.from_environ({tc.SUPERVISOR_FD_ENV: "x"}))
        read_fd, write_fd = self.pipe()
        self.assertIsNotNone(ta.Control.from_environ({tc.SUPERVISOR_FD_ENV: str(write_fd)}))


def _is_open(fd):
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def sleeper(seconds=60):
    """A real stand-in MargenX: its own process group, as the launcher starts it."""
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"], start_new_session=True)


class SupervisorTests(unittest.TestCase):
    """The launcher's decisions, on real pipes and real (stand-in) processes, with a fake clock."""

    def supervisor(self, **kw):
        self.wall, self.mono = Clock(1_800_000_000.0), Clock(100.0)
        asked = {"yes": False, "now": False, "host": False}
        self.asked = asked
        spawned = []

        def spawn(command, **options):
            proc = sleeper()
            spawned.append((proc, options))
            self.addCleanup(launch.kill_app, proc)
            return proc
        self.spawned = spawned
        sup = launch.Supervisor(t.SETTINGS, kw.get("spawn", spawn), lambda proc, should_stop: True, ["margenx"], 0.01,
                                asked, {}, clock=self.wall, monotonic=self.mono, memory=kw.get("memory", lambda pid: 0))
        return sup

    def generation(self, sup, written: bytes = b"", close_write=True):
        """A generation whose MargenX wrote these bytes on its pipe, then died (its write end closed)."""
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        if written:
            os.write(write_fd, written)
        if close_write:
            os.close(write_fd)
        else:
            self.addCleanup(os.close, write_fd)
        proc = sleeper()
        self.addCleanup(launch.kill_app, proc)
        gen = launch.Generation(proc, read_fd, self.mono())
        sup.current = gen
        return gen

    def test_a_plain_end_session_keeps_the_login_and_every_earlier_logout(self):
        sup = self.supervisor()
        sup.cutoff = 1_700_000_000.0
        gen = self.generation(sup, b"alive\nrecycle\n")
        self.assertEqual("session ended", sup.check(gen))
        self.assertTrue(sup.end(gen, "session ended"))
        self.assertEqual(1_700_000_000.0, sup.cutoff)  # unchanged: the same login still works
        self.assertIsNotNone(gen.proc.poll())  # killed and reaped

    def test_a_logout_on_the_pipe_is_kept_and_given_to_the_next_margenx(self):
        sup = self.supervisor()
        gen = self.generation(sup, b"logout 1800000050\nrecycle\n")
        sup.end(gen, "session ended")
        self.assertEqual(1_800_000_050, sup.cutoff)
        fresh = sup.start()
        env = self.spawned[-1][1]["env"]
        self.assertEqual("1800000050", env[tc.CUTOFF_ENV])
        register = ta.SessionRegister.from_environ(env)
        self.assertFalse(register.login_allowed(t.INVITED, 1_800_000_050))  # at the cutoff: refused
        self.assertTrue(register.login_allowed(t.INVITED, 1_800_000_051))
        launch.kill_app(fresh.proc)
        fresh.close()

    def test_the_combined_case_failed_logout_write_then_death_then_replacement_then_old_login_replay(self):
        """The v6 review's blocker: the logout message can't be written (a full pipe), so MargenX kills itself;
        the launcher's replacement must still refuse the login just ended."""
        sup = self.supervisor()
        old_login = time.time() - 600  # issued ten minutes ago (real time), still valid at Cloudflare
        read_fd, write_fd = full_pipe()
        os.set_blocking(read_fd, False)
        kill = FakeKill()
        control = ta.Control(write_fd, kill)
        state = ta.TrialState(control, ta.SessionRegister())
        with self.assertRaises(Killed):
            state.end(logout_at=self.wall() + tc.CUTOFF_MARGIN_SECONDS)  # Log out: its first write fails...
        self.assertEqual(1, kill.called)  # ...so MargenX ends itself (here: the stand-in is killed below)
        self.assertFalse(state.ending)  # it never got further
        os.close(write_fd)
        proc = sleeper()
        gen = launch.Generation(proc, read_fd, self.mono())
        launch.kill_app(proc)  # MargenX's death
        reason = sup.check(gen)
        self.assertEqual("MargenX stopped by itself", reason)
        self.assertFalse(sup.end(gen, reason))  # unexplained
        fresh = sup.start()  # the replacement
        env = self.spawned[-1][1]["env"]
        register = ta.SessionRegister.from_environ(env)
        self.assertFalse(register.login_allowed(t.INVITED, old_login))  # the old login is refused
        self.assertFalse(register.login_allowed(t.INVITED, self.wall() + tc.CUTOFF_MARGIN_SECONDS))
        # ...by the replacement's gate too, which answers the page with the way back in (log in again).
        old = t.token(iat=old_login)
        rec = t.run({"register": register, "state": ta.TrialState()}, t.http_scope(tok=old))
        self.assertEqual(403, rec.status())
        self.assertFalse(rec.app_called)
        self.assertIn(b"Log in again", b"".join(m.get("body", b"") for m in rec.sent))
        self.assertIn(b"/cdn-cgi/access/logout", b"".join(m.get("body", b"") for m in rec.sent))
        launch.kill_app(fresh.proc)
        fresh.close()

    def test_any_death_not_fully_explained_advances_the_cutoff(self):
        cases = {
            "a crash": (b"alive\n", "MargenX stopped by itself"),
            "a logout, then a crash": (b"logout 1800000010\n", "MargenX stopped by itself"),
            "a malformed line after the recycle": (b"recycle\nnonsense\n", "session ended"),
            "a cut-off line after the recycle": (b"recycle\nali", "session ended"),
            "the launcher's own deadline": (b"arm\n", "work took too long"),
            "a missing heartbeat": (b"", "not responding"),
            "memory": (b"alive\n", "memory"),
        }
        for name, (written, reason) in cases.items():
            sup = self.supervisor()
            gen = self.generation(sup, written)
            self.assertFalse(sup.end(gen, reason), name)
            self.assertGreaterEqual(sup.cutoff, self.wall() + tc.CUTOFF_MARGIN_SECONDS, name)

    def test_an_incomplete_read_of_the_old_pipe_is_unexplained_even_after_a_recycle(self):
        # The write end still open elsewhere: the end of the pipe is never reached within the time limit.
        sup = self.supervisor()
        gen = self.generation(sup, b"recycle\n", close_write=False)
        started = time.monotonic()
        self.assertFalse(sup.end(gen, "session ended"))
        self.assertLess(time.monotonic() - started, tc.DRAIN_SECONDS + 1.5)
        self.assertIsNotNone(sup.cutoff)
        # More than the read limit after a recycle: unexplained too.
        sup = self.supervisor()
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        proc = sleeper()
        gen = launch.Generation(proc, read_fd, self.mono())
        def write_too_much():
            try:
                os.write(write_fd, b"recycle\n")
                for _ in range(20):
                    os.write(write_fd, b"alive\n" * 1000)
            except OSError:
                pass  # the launcher stopped reading: expected
            finally:
                os.close(write_fd)
        writer = threading.Thread(target=write_too_much)
        writer.start()
        self.assertFalse(sup.end(gen, "session ended"))
        writer.join(5)

    def test_the_work_deadline_holds_while_heartbeats_continue(self):
        sup = self.supervisor()
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        os.set_blocking(read_fd, False)
        proc = sleeper()
        self.addCleanup(launch.kill_app, proc)
        gen = launch.Generation(proc, read_fd, self.mono())
        os.write(write_fd, b"alive\narm\n")
        self.assertIsNone(sup.check(gen))
        for _ in range(int(launch.WORK_SECONDS) + 1):
            self.mono.now += 1
            os.write(write_fd, b"alive\n")  # MargenX is responding the whole time
            reason = sup.check(gen)
            if reason:
                break
        self.assertEqual("work took too long", reason)
        self.assertGreater(self.mono.now - 100, launch.WORK_SECONDS)
        # Disarmed in time: no recycle.
        os.write(write_fd, b"disarm\n")
        gen.armed_at = None
        self.assertIsNone(sup.check(gen))
        gen.close()

    def test_a_missing_heartbeat_and_too_much_memory_each_recycle(self):
        sup = self.supervisor()
        gen = self.generation(sup, close_write=False)
        self.mono.now += launch.HEARTBEAT_SECONDS + 0.1
        self.assertEqual("not responding", sup.check(gen))
        sup = self.supervisor(memory=lambda pid: launch.MEMORY_BYTES + 1)
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        os.set_blocking(read_fd, False)
        proc = sleeper()
        self.addCleanup(launch.kill_app, proc)
        gen = launch.Generation(proc, read_fd, self.mono())
        os.write(write_fd, b"alive\n")
        self.assertEqual("memory", sup.check(gen))
        gen.close()

    def test_too_many_unexplained_deaths_stop_for_good(self):
        sup = self.supervisor()
        for _ in range(launch.MAX_UNEXPLAINED):
            sup.end(self.generation(sup), "MargenX stopped by itself")
        self.assertFalse(sup.too_many_unexplained())
        sup.end(self.generation(sup), "MargenX stopped by itself")
        self.assertTrue(sup.too_many_unexplained())
        self.assertIsNone(sup.recycle(self.generation(sup), "MargenX stopped by itself"))
        self.mono.now += launch.UNEXPLAINED_WINDOW + 1  # long ago ones no longer count
        self.assertFalse(sup.too_many_unexplained())

    def test_a_stop_wins_in_every_phase_of_a_recycle(self):
        # Before the start: nothing is started.
        sup = self.supervisor()
        self.asked["yes"] = True
        self.assertIsNone(sup.recycle(self.generation(sup, b"recycle\n"), "session ended"))
        self.assertEqual([], self.spawned)
        # During the start itself (a stop held back while MargenX is being created): killed at once.
        sup = self.supervisor()

        def spawn_then_stop(command, **options):
            proc = sleeper()
            self.addCleanup(launch.kill_app, proc)
            # To this thread, where it is held back (the launcher has no other threads; this test process may)
            signal.pthread_kill(threading.main_thread().ident, launch.STOP_NOW_SIGNAL)
            return proc
        previous = signal.signal(launch.STOP_NOW_SIGNAL, lambda *a: self.asked.update(yes=True, now=True))
        try:
            sup.spawn = spawn_then_stop
            self.assertIsNone(sup.start())
            killed = sup.procs["app"]
            self.assertIsNotNone(killed.poll())
        finally:
            signal.signal(launch.STOP_NOW_SIGNAL, previous)
        # While the fresh MargenX is starting to listen: not waited for, and nothing more started.
        sup = self.supervisor()

        def never_ready(proc, should_stop):
            self.asked["yes"] = True
            return False
        sup.ready = never_ready
        self.assertIsNone(sup.recycle(self.generation(sup, b"recycle\n"), "session ended"))
        self.assertEqual(1, len(self.spawned))

    def test_each_margenx_gets_a_fresh_pipe_its_own_process_group_and_no_core_dumps(self):
        sup = self.supervisor()
        first = sup.start()
        second = sup.start()
        (_, one), (_, two) = self.spawned[-2:]
        self.assertNotEqual(one["pass_fds"], two["pass_fds"])
        self.assertNotEqual(first.fd, second.fd)
        for options in (one, two):
            self.assertTrue(options["start_new_session"])
            self.assertIs(launch._app_preexec, options["preexec_fn"])
            self.assertEqual("2", options["env"]["MALLOC_ARENA_MAX"])
            self.assertEqual(str(options["pass_fds"][0]), options["env"][tc.SUPERVISOR_FD_ENV])
        for gen in (first, second):
            launch.kill_app(gen.proc)
            gen.close()

    def test_killing_margenx_takes_its_whole_process_group(self):
        child = subprocess.Popen([sys.executable, "-c", "import subprocess,sys,time;"
                                  "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
                                  "print(p.pid,flush=True);time.sleep(60)"], start_new_session=True,
                                 stdout=subprocess.PIPE, text=True)
        grandchild = int(child.stdout.readline())
        launch.kill_app(child)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail("a process MargenX started survived")
        child.stdout.close()


class RegisterCutoffTests(unittest.TestCase):
    def test_the_register_starts_with_the_launchers_cutoff_and_refuses_equality(self):
        r = ta.SessionRegister.from_environ({**t.SETTINGS, tc.CUTOFF_ENV: "5000"})
        self.assertFalse(r.login_allowed(t.INVITED, 5000))
        self.assertFalse(r.login_allowed(t.INVITED, 4000))
        self.assertTrue(r.login_allowed(t.INVITED, 5001))
        self.assertTrue(ta.SessionRegister.from_environ(t.SETTINGS).login_allowed(t.INVITED, 1))
        self.assertTrue(ta.SessionRegister.from_environ({**t.SETTINGS, tc.CUTOFF_ENV: "soon"}).login_allowed(t.INVITED, 1))

    def test_a_later_smaller_logout_never_lowers_the_cutoff(self):
        r = ta.SessionRegister()
        r.log_out(t.INVITED, now=5000)
        r.log_out(t.INVITED, now=100)
        self.assertFalse(r.login_allowed(t.INVITED, 4999))


if __name__ == "__main__":
    unittest.main()
