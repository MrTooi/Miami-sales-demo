"""Starts one MargenX website-trial copy (issue #131, lean v1.2; D-009). PR A2, PR B.

Two programs run in one container:
- MargenX (Streamlit, trial_app.py), listening on 127.0.0.1 only, so nothing outside the container
  can reach it directly;
- Cloudflare's tunnel (cloudflared), which only connects out to Cloudflare. Cloudflare Access checks
  the login before a request comes through it, and MargenX's gate (trial_access) checks it again.

The rules this launcher keeps:
- **Fail closed.** It starts nothing unless every trial setting is valid (trial_access.TrialConfig)
  and the tunnel token is set.
- **Never restarts anything.** When either program stops, the other is stopped and the launcher exits
  with a non-zero code, so the whole copy stops. Ending a trial is the host's stop (Render: Suspend),
  which sends SIGTERM: MargenX is stopped first, so no request is handled any more, then the tunnel.
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
  launcher stops MargenX, then the tunnel, at once, which cuts every open tab and upload within about a
  second. Render's Suspend only delivers its stop about 2 minutes after it's pressed (PR #141). The
  launcher then **stays running and does nothing** until the host's own stop, so the host never sees
  the copy end by itself, and never restarts it. A stop-now that arrives while MargenX is still
  starting means the tunnel is never started, exactly like the host's stop.
- **Never prints a setting's value or the token,** only which setting is missing or invalid.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

import trial_access as ta  # noqa: E402

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
EXIT_PROGRAM_STOPPED = 1
EXIT_SETTINGS = 2


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


def streamlit_env(environ: Mapping[str, str]) -> dict[str, str]:
    env = {**_base(environ), **{name: environ[name] for name in TRIAL_SETTINGS if name in environ}}
    if closed(environ):
        env["MARGINX_TRIAL_INVITED_EMAIL"] = CLOSED_INVITE
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
    """Stop a program: SIGTERM, then SIGKILL if it hasn't stopped in time."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _stop_pending() -> bool:
    """A host stop or a stop-now that arrived while the stop signals were held back."""
    return bool(set(HELD_SIGNALS) & signal.sigpending())


def _release_stop_signals() -> None:
    """Runs in a new program just before it starts: it must not inherit the launcher's held-back stop
    signals, or the host's stop couldn't reach it."""
    signal.pthread_sigmask(signal.SIG_UNBLOCK, HELD_SIGNALS)


def say(message: str) -> None:
    print(f"margenx-trial: {message}", flush=True)


def _wait_for_host_stop(stopped_by_host: Callable[[], bool], poll_seconds: float) -> int:
    """After a stop-now: both programs are already stopped. Do nothing until the host's own stop, so the
    host never sees the copy end by itself (Render restarts a running copy that does)."""
    say("stopped now: MargenX and the tunnel are stopped; waiting for the host's stop (Suspend), nothing restarts")
    while not stopped_by_host():
        time.sleep(poll_seconds)
    say("stopping: asked to stop by the host")
    return EXIT_STOPPED_BY_HOST


def run(environ: Mapping[str, str] = os.environ, spawn: Callable = subprocess.Popen,
        ready: Callable = wait_until_listening, streamlit=None, tunnel=None,
        poll_seconds: float = POLL_SECONDS, before_tunnel: Callable[[], None] = lambda: None) -> int:
    """Start MargenX, wait until it listens, start the tunnel, then watch both. Returns the exit code."""
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
    app = tunnel_proc = None
    try:
        result = _run(environ, spawn, ready, streamlit, tunnel, poll_seconds, before_tunnel, asked_to_stop)
        app, tunnel_proc = result[1], result[2]
        if asked_to_stop["now"] and result[0] == EXIT_STOPPED_BY_HOST and not asked_to_stop["host"]:
            stop(app)  # MargenX first: no request is handled any more
            stop(tunnel_proc)
            return _wait_for_host_stop(lambda: asked_to_stop["host"], poll_seconds)
        return result[0]
    finally:
        stop(app)
        stop(tunnel_proc)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _who(asked_to_stop) -> str:
    """Who asked: a held-back signal counts too (it is handled only after the start)."""
    pending = signal.sigpending()
    if asked_to_stop["host"] or set(STOP_SIGNALS) & pending:
        return "the host"
    return "the operator (stop-now)"


def _run(environ, spawn, ready, streamlit, tunnel, poll_seconds, before_tunnel, asked_to_stop):
    """The launcher's start and watch. Returns (exit code, MargenX, tunnel); the caller stops both programs."""
    app = tunnel_proc = None
    try:
        if closed(environ):
            say("closed: this copy refuses every login (the invited email is replaced by nobody's address)")
        app = spawn(streamlit or streamlit_command(), cwd=str(APP_DIR), env=streamlit_env(environ))
        is_listening = ready(app, lambda: asked_to_stop["yes"])
        # From the last check until the tunnel exists, the host's stop signals are held back, so a stop
        # can't slip in between the check and the start: it is seen by the second check below.
        signal.pthread_sigmask(signal.SIG_BLOCK, HELD_SIGNALS)
        try:
            if asked_to_stop["yes"]:
                say(f"stopping: asked to stop by {_who(asked_to_stop)} before the tunnel was started")
                return EXIT_STOPPED_BY_HOST, app, None
            if not is_listening:
                say("not starting: MargenX didn't start listening on this container")
                return EXIT_PROGRAM_STOPPED, app, None
            before_tunnel()  # tests only: a stop arriving here, after the check above
            if _stop_pending():  # a stop always wins: the tunnel is never started
                say(f"stopping: asked to stop by {_who(asked_to_stop)} before the tunnel was started")
                return EXIT_STOPPED_BY_HOST, app, None
            tunnel_proc = spawn(tunnel or tunnel_command(), cwd=str(APP_DIR), env=tunnel_env(environ),
                                preexec_fn=_release_stop_signals)
            if _stop_pending():  # the stop came during the start itself: kill the new tunnel at once
                tunnel_proc.kill()
                tunnel_proc.wait()
                say(f"stopping: asked to stop by {_who(asked_to_stop)} while the tunnel was starting; it was killed at once")
                return EXIT_STOPPED_BY_HOST, app, tunnel_proc
        finally:
            signal.pthread_sigmask(signal.SIG_UNBLOCK, HELD_SIGNALS)  # a held-back stop is handled now
        say("running: MargenX on this container only, and the tunnel")
        while not asked_to_stop["yes"]:
            if app.poll() is not None:
                say("stopping: MargenX stopped, so the tunnel is stopped too (nothing is restarted)")
                return EXIT_PROGRAM_STOPPED, app, tunnel_proc
            if tunnel_proc.poll() is not None:
                say("stopping: the tunnel stopped, so MargenX is stopped too (nothing is restarted)")
                return EXIT_PROGRAM_STOPPED, app, tunnel_proc
            time.sleep(poll_seconds)
        if asked_to_stop["host"]:
            say("stopping: asked to stop by the host")
        else:
            say("stopping now: asked by the operator (stop_now.py); MargenX first, then the tunnel")
        return EXIT_STOPPED_BY_HOST, app, tunnel_proc
    except BaseException:
        stop(app)
        stop(tunnel_proc)
        raise


if __name__ == "__main__":
    sys.exit(run())
