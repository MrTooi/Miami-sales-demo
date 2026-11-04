"""Starts one MargenX website-trial copy (issue #131, lean v1.2; D-009). PR A2.

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
TOKEN_ENV = "TUNNEL_TOKEN"
TRIAL_SETTINGS = ("MARGINX_TRIAL", "MARGINX_TRIAL_TEAM_DOMAIN", "MARGINX_TRIAL_AUDIENCE",
                  "MARGINX_TRIAL_INVITED_EMAIL", "MARGINX_TRIAL_HOST")
# What both programs may see besides their own settings: enough to run, nothing else.
BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED")
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
            "--management-diagnostics=false", "--loglevel", "info", "--grace-period", "1s", "run"]


def problems(environ: Mapping[str, str]) -> list[str]:
    """What's missing or invalid, by setting name only. Empty when the copy may start."""
    found = []
    if ta.TrialConfig.from_environ(environ) is None:
        missing = [name for name in TRIAL_SETTINGS if not environ.get(name, "").strip()]
        found.append("trial settings missing: " + ", ".join(missing) if missing
                     else "trial settings invalid (MARGINX_TRIAL must be 1, and each value in its documented form)")
    if not environ.get(TOKEN_ENV, "").strip():
        found.append(f"tunnel token missing: {TOKEN_ENV}")
    return found


def _base(environ: Mapping[str, str]) -> dict[str, str]:
    return {name: environ[name] for name in BASE_ENV if name in environ}


def streamlit_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {**_base(environ), **{name: environ[name] for name in TRIAL_SETTINGS if name in environ}}


def tunnel_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {**_base(environ), TOKEN_ENV: environ[TOKEN_ENV]}


def wait_until_listening(proc, host: str = HOST, port: int = PORT, seconds: float = READY_SECONDS) -> bool:
    """True once something accepts connections on host:port; False if the program stops or time runs out."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
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


def say(message: str) -> None:
    print(f"margenx-trial: {message}", flush=True)


def run(environ: Mapping[str, str] = os.environ, spawn: Callable = subprocess.Popen,
        ready: Callable = wait_until_listening, streamlit=None, tunnel=None,
        poll_seconds: float = POLL_SECONDS) -> int:
    """Start MargenX, wait until it listens, start the tunnel, then watch both. Returns the exit code."""
    found = problems(environ)
    if found:
        for problem in found:
            say("not starting: " + problem)
        return EXIT_SETTINGS

    asked_to_stop = {"yes": False}

    def on_stop(signum, frame):
        asked_to_stop["yes"] = True
    previous = {sig: signal.signal(sig, on_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    app = tunnel_proc = None
    try:
        app = spawn(streamlit or streamlit_command(), cwd=str(APP_DIR), env=streamlit_env(environ))
        if not ready(app):
            say("not starting: MargenX didn't start listening on this container")
            return EXIT_PROGRAM_STOPPED
        tunnel_proc = spawn(tunnel or tunnel_command(), cwd=str(APP_DIR), env=tunnel_env(environ))
        say("running: MargenX on this container only, and the tunnel")
        while not asked_to_stop["yes"]:
            if app.poll() is not None:
                say("stopping: MargenX stopped, so the tunnel is stopped too (nothing is restarted)")
                return EXIT_PROGRAM_STOPPED
            if tunnel_proc.poll() is not None:
                say("stopping: the tunnel stopped, so MargenX is stopped too (nothing is restarted)")
                return EXIT_PROGRAM_STOPPED
            time.sleep(poll_seconds)
        say("stopping: asked to stop by the host")
        return EXIT_STOPPED_BY_HOST
    finally:
        stop(app)  # MargenX first: no request is handled any more
        stop(tunnel_proc)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(run())
