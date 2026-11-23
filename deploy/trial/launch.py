"""Starts one MargenX website-trial copy (issue #131, lean v1.2; D-009). PR A2, PR B, the uploads PR.

Two programs run in one container:
- MargenX (Streamlit, trial_app.py), listening on 127.0.0.1 only, so nothing outside the container
  can reach it directly;
- Cloudflare's tunnel (cloudflared), which only connects out to Cloudflare. Cloudflare Access checks
  the login before a request comes through it, and MargenX's gate (trial_access) checks it again.

The rules this launcher keeps:
- **Fail closed.** It starts nothing unless every trial setting is valid (trial_access.TrialConfig)
  and the tunnel token is set.
- **The supervisor (uploads PR, plan v7).** One MargenX process holds at most one consent, and **any
  ending ends that process**: MargenX asks for a *recycle* on its control pipe (trial_control), and the
  launcher kills MargenX's whole process group (SIGKILL), reads the old pipe to its end, and starts a
  fresh, empty MargenX on the same port; the tunnel keeps running. The launcher, in its own process, also
  recycles MargenX when work stays armed for more than WORK_SECONDS, when no heartbeat arrives for
  HEARTBEAT_SECONDS, when its memory passes MEMORY_BYTES, or when it ends by itself. So a stuck MargenX
  is still stopped. **Logouts survive recycling:** the launcher keeps the latest logout time (the
  cutoff) and gives it to every new MargenX before it serves anything; after any death it can't fully
  explain (trial_control.Reader.explained), it first advances the cutoff to now plus a margin, so every
  earlier login must log in again. After MAX_UNEXPLAINED unexplained deaths within UNEXPLAINED_WINDOW,
  it stops for good (below).
- **Never restarts an ended trial, and never exits by itself.** Ending a trial is the host's stop
  (Render: Suspend), which sends SIGTERM, or the operator's stop-now: MargenX's process group is killed
  first (SIGKILL), so no request is handled any more, then the tunnel, and nothing is started again.
  When the tunnel stops by itself, the launcher hits an error, or MargenX can't be kept running, both are
  stopped and the launcher **waits, doing nothing, for the host's stop** instead of exiting: Render would
  restart an exited copy, and a restarted launcher would have forgotten the cutoff. Only the host's stop
  (or settings missing at the start, when nothing was started) ends the launcher.
- **Each program gets only its own settings.** The tunnel token goes to cloudflared only; the trial
  settings go to MargenX only.
- **A stop always wins.** A stop that arrives while MargenX is still starting ends the wait at once,
  and the tunnel is never started. No stop can slip in between the last check and the tunnel's start:
  from that check until the tunnel exists, the host's stop signals are held back and then looked at.
  A stop that arrived before the start means the tunnel is never started; one that arrives during the
  start itself (the few milliseconds of creating the process) means the new tunnel is killed at once,
  without the usual grace period.
- **Closed mode** (`MARGINX_TRIAL_CLOSED=1`, for the stop procedure's restart check): MargenX is given a
  placeholder that is nobody's address instead of the invited email, so this copy itself refuses every
  login, whatever Cloudflare forwards. The launcher says so in its log. Any other value of that setting,
  empty included, starts nothing: a mistyped closed mode never opens the copy.
- **The operator's stop-now** (PR B; `deploy/trial/stop_now.py`, run from the host's shell): the
  launcher stops MargenX, then the tunnel, at once. It is expected to cut every open tab within seconds
  (under 3 s in the local tests with stand-ins; on Render, still to be shown in PR B's release run; for an
  upload in progress, in the uploads PR). Render's Suspend only delivers its stop about 2 minutes after it's pressed (PR #141). The
  launcher then **stays running and does nothing** until the host's own stop, so the host never sees
  the copy end by itself, and never restarts it. A stop-now that arrives while MargenX is still
  starting means the tunnel is never started, exactly like the host's stop. **A stop-now is caught from
  the launcher's very first line** (`catch_early_stop_now`, before any import): one that arrives before
  `run()` is honoured by starting nothing at all, so it can never kill the launcher (SIGUSR1's default
  action) and make the host restart the copy. `stop_now.py` also never signals a launcher that isn't
  catching it yet. **A received stop-now wins however the launcher ends** (the host's stop aside): a
  program stopping by itself, an error, or the cleanup that follows. The last decision is taken with the
  stop signals held back, after both programs are stopped (manual review of PR #147, round 1).
- **Never prints a setting's value or the token,** only which setting is missing or invalid. A recycle's log
  line says only why (`recycled: ...`), never a file, an email or a setting.
"""
from __future__ import annotations

import signal

# A stop-now that arrives before run() installs its handlers (stop_now.py, while the launcher is still
# importing): noted here, and honoured by run() by starting nothing. Without this, SIGUSR1's default
# action would end the launcher, and Render would restart the copy.
EARLY_STOP_NOW: list[int] = []


def catch_early_stop_now() -> None:
    signal.signal(signal.SIGUSR1, lambda signum, frame: EARLY_STOP_NOW.append(signum))


if __name__ == "__main__":
    catch_early_stop_now()  # first, before any other import: see EARLY_STOP_NOW

import os  # noqa: E402
import select  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable, Mapping  # noqa: E402
from pathlib import Path  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

import trial_access as ta  # noqa: E402
import trial_control as tc  # noqa: E402

HOST = "127.0.0.1"
PORT = 8501
# cloudflared's local metrics page, on the container only (its default is "localhost", stated here exactly).
METRICS = "127.0.0.1:20241"
TOKEN_ENV = "TUNNEL_TOKEN"
CLOSED_ENV = "MARGINX_TRIAL_CLOSED"
# Nobody's address: ".invalid" can never be a real email domain (RFC 2606). MargenX's gate knows it too.
CLOSED_INVITE = ta.CLOSED_INVITE
TRIAL_SETTINGS = ("MARGINX_TRIAL", "MARGINX_TRIAL_TEAM_DOMAIN", "MARGINX_TRIAL_AUDIENCE",
                  "MARGINX_TRIAL_INVITED_EMAIL", "MARGINX_TRIAL_HOST")
# What both programs may see besides their own settings: enough to run, nothing else.
BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED")
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)  # the host's stop
STOP_NOW_SIGNAL = signal.SIGUSR1  # the operator's stop-now (stop_now.py)
HELD_SIGNALS = (*STOP_SIGNALS, STOP_NOW_SIGNAL)
READY_SECONDS = 60
STOP_SECONDS = 5
POLL_SECONDS = 0.5

EXIT_STOPPED_BY_HOST = 0
EXIT_PROGRAM_STOPPED = 1  # no longer returned since the uploads PR: the launcher waits for the host instead
EXIT_SETTINGS = 2

# The supervisor's limits (plan v7, section 5; provisional until the release run's measurements).
WORK_SECONDS = 60.0  # armed work (reading an uploaded file) longer than this: MargenX is recycled
HEARTBEAT_SECONDS = 15.0  # no "alive" for this long once MargenX listens: recycled
MEMORY_BYTES = 1_200_000_000  # MargenX's resident memory above this: recycled
MEMORY_EVERY_SECONDS = 0.5
MAX_UNEXPLAINED = 3  # more unexplained deaths than this within the window: stopped for good
UNEXPLAINED_WINDOW = 600.0


def streamlit_command(python: str = sys.executable) -> list[str]:
    """MargenX's server, on this container only, with Streamlit's cross-site protections on and no
    usage statistics, file watching, developer mode or error details in the page. The upload cap and
    the 10-second cleanup of a disconnected tab's session repeat .streamlit/config.toml, so they hold
    even if that file were missing."""
    return [python, "-m", "streamlit", "run", "trial_app.py",
            "--server.address", HOST, "--server.port", str(PORT),
            "--server.headless", "true",
            "--server.enableXsrfProtection", "true",
            "--server.enableCORS", "true",
            "--server.fileWatcherType", "none",
            "--server.runOnSave", "false",
            "--server.maxUploadSize", "5",
            "--server.disconnectedSessionTTL", "10",
            "--browser.gatherUsageStats", "false",
            "--client.showErrorDetails", "none",
            "--client.toolbarMode", "viewer",
            "--global.developmentMode", "false"]


def tunnel_command(cloudflared: str = "cloudflared") -> list[str]:
    """Cloudflare's tunnel, run with its token from the environment (never on the command line, where
    any process could read it). TCP only (http2), no self-updating, no remote diagnostics (they can take
    memory profiles of the traffic passing through), info-level logs (debug logs every header, tokens
    included), and a 1-second grace period, so a stop cuts requests in progress."""
    return [cloudflared, "tunnel", "--no-autoupdate", "--protocol", "http2",
            "--management-diagnostics=false", "--metrics", METRICS, "--loglevel", "info",
            "--grace-period", "1s", "run"]


def problems(environ: Mapping[str, str]) -> list[str]:
    """What's missing or invalid, by setting name only. Empty when the copy may start."""
    found = []
    if ta.TrialConfig.from_environ(environ) is None:
        missing = [name for name in TRIAL_SETTINGS if not environ.get(name, "").strip()]
        found.append("trial settings missing: " + ", ".join(missing) if missing
                     else "trial settings invalid (MARGINX_TRIAL must be 1, and each value in its documented form)")
    if not environ.get(TOKEN_ENV, "").strip():
        found.append(f"tunnel token missing: {TOKEN_ENV}")
    if CLOSED_ENV in environ and environ[CLOSED_ENV].strip() != "1":
        # A mistyped closed mode must never quietly start the copy for the invited person.
        found.append(f"{CLOSED_ENV} invalid: it must be 1, or not set at all")
    return found


def _base(environ: Mapping[str, str]) -> dict[str, str]:
    return {name: environ[name] for name in BASE_ENV if name in environ}


def closed(environ: Mapping[str, str]) -> bool:
    return environ.get(CLOSED_ENV, "").strip() == "1"


def streamlit_env(environ: Mapping[str, str], control_fd: int | None = None, cutoff: float | None = None) -> dict[str, str]:
    """MargenX's settings: the trial's own, the control pipe's number, the logout cutoff (a time, if any), and
    MALLOC_ARENA_MAX=2 (fewer memory arenas, so its memory use stays close to what it really holds)."""
    env = {**_base(environ), **{name: environ[name] for name in TRIAL_SETTINGS if name in environ}}
    if closed(environ):
        env["MARGINX_TRIAL_INVITED_EMAIL"] = CLOSED_INVITE
    env["MALLOC_ARENA_MAX"] = "2"
    if control_fd is not None:
        env[tc.SUPERVISOR_FD_ENV] = str(control_fd)
    if cutoff is not None:
        env[tc.CUTOFF_ENV] = str(int(cutoff) + (0 if float(cutoff).is_integer() else 1))
    return env


def tunnel_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {**_base(environ), TOKEN_ENV: environ[TOKEN_ENV]}


def wait_until_listening(proc, should_stop: Callable[[], bool] = lambda: False, host: str = HOST,
                         port: int = PORT, seconds: float = READY_SECONDS) -> bool:
    """True once something accepts connections on host:port; False if the program stops, a stop is asked
    for, or time runs out."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None or should_stop():
            return False
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(POLL_SECONDS)
    return False


def stop(proc, seconds: float = STOP_SECONDS) -> None:
    """Stop a program: SIGTERM, then SIGKILL if it hasn't stopped in time. (The tunnel.)"""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def kill_app(proc) -> None:
    """End MargenX at once: SIGKILL to its whole process group (it was started as the group's leader), so
    nothing it holds can finish, be read or be sent. Then reap it. Nothing of it can survive."""
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    try:
        if isinstance(pid, int) and pid > 0:
            os.killpg(pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass
    except OSError:
        proc.kill()
    proc.wait()


def _stop_pending() -> bool:
    """A host stop or a stop-now that arrived while the stop signals were held back."""
    return bool(set(HELD_SIGNALS) & signal.sigpending())


def _release_stop_signals() -> None:
    """Runs in a new program just before it starts: it must not inherit the launcher's held-back stop
    signals, or the host's stop couldn't reach it."""
    signal.pthread_sigmask(signal.SIG_UNBLOCK, HELD_SIGNALS)


def _app_preexec() -> None:
    """Runs in a new MargenX just before it starts: the stop signals released, and no core dumps (a crash
    must never write memory, which could hold a file's contents, to disk)."""
    _release_stop_signals()
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def say(message: str) -> None:
    print(f"margenx-trial: {message}", flush=True)


def _wait_for_host_stop(stopped_by_host: Callable[[], bool], poll_seconds: float, why: str | None = None) -> int:
    """Both programs are already stopped. Do nothing until the host's own stop, so the host never sees the
    copy end by itself (Render restarts a running copy that does)."""
    say(why or "stopped now: MargenX and the tunnel are stopped; waiting for the host's stop (Suspend), nothing restarts")
    while not stopped_by_host():
        time.sleep(poll_seconds)
    say("stopping: asked to stop by the host")
    return EXIT_STOPPED_BY_HOST


def resident_bytes(pid: int) -> int | None:
    """A process's resident memory (VmRSS in /proc), or None where that can't be read (not Linux)."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class Generation:
    """One MargenX process and the read end of its own, fresh control pipe."""

    def __init__(self, proc, fd: int, now: float):
        self.proc = proc
        self.fd = fd
        self.reader = tc.Reader()
        self.listening_at = now
        self.last_alive: float | None = None
        self.armed_at: float | None = None
        self.memory_checked = 0.0
        self.reached_end = False

    def read(self, now: float, limit: int = tc.DRAIN_BYTES) -> None:
        """Read what is waiting on the pipe (never blocking), and note heartbeats and armed work."""
        got = 0
        while got < limit:
            try:
                data = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            except OSError:
                self.reached_end = True
                break
            if not data:
                self.reached_end = True
                break
            got += len(data)
            alive_before = self.reader.alive
            self.reader.feed(data)
            if self.reader.alive != alive_before:
                self.last_alive = now
        if self.reader.armed and self.armed_at is None:
            self.armed_at = now
        elif not self.reader.armed:
            self.armed_at = None

    def drain(self, seconds: float = tc.DRAIN_SECONDS, limit: int = tc.DRAIN_BYTES) -> bool:
        """After MargenX's death: read its pipe to the end (the write end closes with the process group).
        True only if the end was reached within the time and size limits."""
        deadline = time.monotonic() + seconds
        got = 0
        while not self.reached_end and got <= limit:
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            ready, _, _ = select.select([self.fd], [], [], min(left, 0.1))
            if not ready:
                continue
            try:
                data = os.read(self.fd, 4096)
            except BlockingIOError:
                continue
            except OSError:
                break
            if not data:
                self.reached_end = True
                break
            got += len(data)
            self.reader.feed(data)
        return self.reached_end and got <= limit

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


class Supervisor:
    """Keeps one MargenX running for the copy, recycling it on any ending (see the module notes)."""

    def __init__(self, environ, spawn, ready, command, poll_seconds, asked_to_stop, procs, clock=time.time,
                 monotonic=time.monotonic, memory=resident_bytes):
        self.environ, self.spawn, self.ready, self.command = environ, spawn, ready, command
        self.poll_seconds, self.asked_to_stop, self.procs = poll_seconds, asked_to_stop, procs
        self.clock, self.monotonic, self.memory = clock, monotonic, memory
        self.cutoff: float | None = None  # logins issued at or before it are refused (trial_control)
        self.unexplained: list[float] = []
        self.current: Generation | None = None

    def start(self) -> Generation | None:
        """Start a fresh MargenX with a fresh pipe, with the stop signals held back from the last check until
        it exists: a stop that arrived first means nothing is started; one during the start itself means the
        new MargenX is killed at once. None if nothing is running afterwards."""
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        signal.pthread_sigmask(signal.SIG_BLOCK, HELD_SIGNALS)
        try:
            if self.asked_to_stop["yes"] or _stop_pending():
                os.close(read_fd)
                return None
            proc = self.procs["app"] = self.spawn(
                self.command, cwd=str(APP_DIR), env=streamlit_env(self.environ, write_fd, self.cutoff),
                pass_fds=(write_fd,), start_new_session=True, preexec_fn=_app_preexec)
            if _stop_pending():
                kill_app(proc)
                os.close(read_fd)
                return None
        except BaseException:
            os.close(read_fd)
            raise
        finally:
            os.close(write_fd)  # only MargenX holds the write end, so its pipe ends when it does
            signal.pthread_sigmask(signal.SIG_UNBLOCK, HELD_SIGNALS)
        self.current = Generation(proc, read_fd, self.monotonic())
        return self.current

    def wait_listening(self, generation: Generation) -> bool:
        if not self.ready(generation.proc, lambda: self.asked_to_stop["yes"]):
            return False
        generation.listening_at = self.monotonic()
        return True

    def check(self, generation: Generation) -> str | None:
        """Why MargenX must be recycled now, or None. Reads its pipe first."""
        now = self.monotonic()
        generation.read(now)
        if generation.reader.invalid:
            return "a malformed control message"
        if generation.reader.recycle:
            return "session ended"
        if generation.proc.poll() is not None:
            return "MargenX stopped by itself"
        if generation.armed_at is not None and now - generation.armed_at > WORK_SECONDS:
            return "work took too long"
        if now - (generation.last_alive or generation.listening_at) > HEARTBEAT_SECONDS:
            return "not responding"
        if now - generation.memory_checked >= MEMORY_EVERY_SECONDS:
            generation.memory_checked = now
            used = self.memory(generation.proc.pid) if isinstance(getattr(generation.proc, "pid", None), int) else None
            if used is not None and used > MEMORY_BYTES:
                return "memory"
        return None

    def end(self, generation: Generation, reason: str) -> bool:
        """Kill MargenX's process group, read its pipe to the end, and settle the cutoff. Returns whether the
        death was explained (a plain End session): only then are earlier logins left as they were."""
        kill_app(generation.proc)
        reached_end = generation.drain()
        generation.close()
        self.current = None
        self.cutoff = tc.later_cutoff(self.cutoff, generation.reader.cutoff)
        explained = reason == "session ended" and generation.reader.explained(reached_end)
        if not explained:
            self.cutoff = tc.unexplained_cutoff(self.cutoff, self.clock())
            self.unexplained.append(self.monotonic())
        return explained

    def too_many_unexplained(self) -> bool:
        now = self.monotonic()
        self.unexplained = [t for t in self.unexplained if now - t <= UNEXPLAINED_WINDOW]
        return len(self.unexplained) > MAX_UNEXPLAINED

    def recycle(self, generation: Generation, reason: str) -> Generation | None:
        """End this MargenX and start a fresh one (fresh pipe, fresh process group, the cutoff given to it).
        None if nothing should run any more: a stop arrived, or too many unexplained deaths."""
        explained = self.end(generation, reason)
        say(f"recycled: {reason}" + ("" if explained else "; every earlier login must log in again"))
        while True:
            if self.asked_to_stop["yes"]:
                return None
            if self.too_many_unexplained():
                return None
            fresh = self.start()
            if fresh is None:
                return None
            if self.wait_listening(fresh):
                return fresh
            if self.asked_to_stop["yes"]:
                return None
            self.end(fresh, "MargenX didn't start listening")
            say("recycled: MargenX didn't start listening; every earlier login must log in again")


def run(environ: Mapping[str, str] = os.environ, spawn: Callable = subprocess.Popen,
        ready: Callable = wait_until_listening, streamlit=None, tunnel=None,
        poll_seconds: float = POLL_SECONDS, before_tunnel: Callable[[], None] = lambda: None,
        before_decision: Callable[[], None] = lambda: None, memory: Callable = resident_bytes,
        clock: Callable[[], float] = time.time) -> int:
    """Start MargenX, wait until it listens, start the tunnel, then supervise both. Returns the exit code.

    However the watch ends (the host's stop, a stop-now, the tunnel stopping by itself, MargenX that can't be
    kept running, or an error), both programs are stopped, MargenX first. Then comes the last decision, with
    every stop signal held back: **only the host's stop ends the launcher**; otherwise it waits, doing nothing,
    for the host's stop, so Render never restarts the copy (a restarted launcher would have forgotten the
    logout cutoff) (manual review of PR #147, round 1; uploads plan v7).

    The limit, stated honestly: a stop-now that lands after that last check, in the instant before this
    process exits after the host's stop, changes nothing: the host's stop ends the copy anyway."""
    found = problems(environ)
    if found:
        for problem in found:
            say("not starting: " + problem)
        return EXIT_SETTINGS

    asked_to_stop = {"yes": False, "now": False, "host": False}

    def on_stop(signum, frame):
        asked_to_stop["yes"] = True
        if signum == STOP_NOW_SIGNAL:
            asked_to_stop["now"] = True
        else:
            asked_to_stop["host"] = True
    previous = {sig: signal.signal(sig, on_stop) for sig in HELD_SIGNALS}
    if EARLY_STOP_NOW:  # a stop-now that came before these handlers: start nothing (checked after installing them)
        asked_to_stop["yes"] = asked_to_stop["now"] = True
    procs: dict = {}
    supervisor = Supervisor(environ, spawn, ready, streamlit or streamlit_command(), poll_seconds, asked_to_stop,
                            procs, clock=clock, memory=memory)
    why = None
    try:
        try:
            why = _run(environ, spawn, supervisor, tunnel, poll_seconds, before_tunnel, asked_to_stop, procs)
        except BaseException as problem:  # never left running: both programs are stopped just below
            say(f"stopping: the launcher hit an error ({type(problem).__name__}), so MargenX and the tunnel are stopped")
            why = "stopped: MargenX and the tunnel are stopped after an error; waiting for the host's stop (Suspend), nothing restarts"
        finally:
            kill_app(procs.get("app"))  # MargenX first: no request is handled any more
            if supervisor.current is not None:
                supervisor.current.close()
            stop(procs.get("tunnel"))
        # The last decision, with every stop signal held back so none can slip past it.
        signal.pthread_sigmask(signal.SIG_BLOCK, HELD_SIGNALS)
        before_decision()  # tests only: a stop-now arriving here, while held back
        pending = signal.sigpending()
        if STOP_NOW_SIGNAL in pending:
            asked_to_stop["now"] = True
        if set(STOP_SIGNALS) & pending:
            asked_to_stop["host"] = True
        if asked_to_stop["host"]:
            return EXIT_STOPPED_BY_HOST
        signal.pthread_sigmask(signal.SIG_UNBLOCK, HELD_SIGNALS)  # on_stop records the host's stop from here
        return _wait_for_host_stop(lambda: asked_to_stop["host"], poll_seconds,
                                   None if asked_to_stop["now"] else why)
    finally:
        # Still held back while the old handlers come back, so nothing reaches them on the way out.
        signal.pthread_sigmask(signal.SIG_BLOCK, HELD_SIGNALS)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _who(asked_to_stop) -> str:
    """Who asked: a held-back signal counts too (it is handled only after the start)."""
    pending = signal.sigpending()
    if asked_to_stop["host"] or set(STOP_SIGNALS) & pending:
        return "the host"
    return "the operator (stop-now)"


WAITING = "waiting for the host's stop (Suspend), nothing restarts"


def _run(environ, spawn, supervisor, tunnel, poll_seconds, before_tunnel, asked_to_stop, procs) -> str | None:
    """The launcher's start and watch. Returns why it stopped when it wasn't asked to (the line it then
    waits under), or None. Each program is put in `procs` the moment it exists; the caller always stops them."""
    if asked_to_stop["yes"]:  # a stop that came before anything started: nothing is started
        say(f"stopping: asked to stop by {_who(asked_to_stop)} before anything was started")
        return None
    if closed(environ):
        say("closed: this copy refuses every login (the invited email is replaced by nobody's address)")
    app = supervisor.start()
    if app is None:
        say(f"stopping: asked to stop by {_who(asked_to_stop)} before anything was started")
        return None
    is_listening = supervisor.wait_listening(app)
    # From the last check until the tunnel exists, the host's stop signals are held back, so a stop
    # can't slip in between the check and the start: it is seen by the second check below.
    signal.pthread_sigmask(signal.SIG_BLOCK, HELD_SIGNALS)
    try:
        if asked_to_stop["yes"]:
            say(f"stopping: asked to stop by {_who(asked_to_stop)} before the tunnel was started")
            return None
        if not is_listening:
            say("not starting: MargenX didn't start listening on this container")
            return f"stopped: MargenX didn't start; {WAITING}"
        before_tunnel()  # tests only: a stop arriving here, after the check above
        if _stop_pending():  # a stop always wins: the tunnel is never started
            say(f"stopping: asked to stop by {_who(asked_to_stop)} before the tunnel was started")
            return None
        tunnel_proc = procs["tunnel"] = spawn(tunnel or tunnel_command(), cwd=str(APP_DIR), env=tunnel_env(environ),
                                              preexec_fn=_release_stop_signals)
        if _stop_pending():  # the stop came during the start itself: kill the new tunnel at once
            tunnel_proc.kill()
            tunnel_proc.wait()
            say(f"stopping: asked to stop by {_who(asked_to_stop)} while the tunnel was starting; it was killed at once")
            return None
    finally:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, HELD_SIGNALS)  # a held-back stop is handled now
    say("running: MargenX on this container only, and the tunnel")
    while not asked_to_stop["yes"]:
        if tunnel_proc.poll() is not None:
            say("stopping: the tunnel stopped, so MargenX is stopped too (nothing is restarted)")
            return f"stopped: the tunnel stopped; {WAITING}"
        reason = supervisor.check(app)
        if reason is not None:
            app = supervisor.recycle(app, reason)
            if app is None:
                if asked_to_stop["yes"]:
                    break
                say("stopping: MargenX ended unexpectedly too often, so MargenX and the tunnel are stopped "
                    "(nothing is restarted)")
                return f"stopped: MargenX ended unexpectedly too often; {WAITING}"
            continue
        time.sleep(poll_seconds)
    if asked_to_stop["host"]:
        say("stopping: asked to stop by the host")
    else:
        say("stopping now: asked by the operator (stop_now.py); MargenX first, then the tunnel")
    return None


if __name__ == "__main__":
    sys.exit(run())
