"""The operator's stop-now for one MargenX website-trial copy (issue #131, lean v1.2; PR B).

Run it in the host's shell on the running copy (Render: the service's Shell tab):

    python /app/deploy/trial/stop_now.py

It asks the copy's launcher (deploy/trial/launch.py) to stop MargenX, then the tunnel, at once. Every
open tab and upload should be cut within seconds (under 3 s in the local tests, with stand-in programs;
the time on Render is measured in PR B's release run), instead of the ~2 minutes Render's Suspend takes
to reach the copy (measured three times in PR #141). The launcher then stays running and does nothing
until the host's own stop, so the host never restarts the copy. It is part of the stop procedure
(docs/TRIAL_DEPLOYMENT.md, section 7), never a replacement for Suspend: Suspend is still pressed.

It finds the launcher by its command line in /proc and sends it SIGUSR1. It prints only process
numbers and what happened: no setting, token or email. It changes nothing else.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

LAUNCHER = "deploy/trial/launch.py"
STOP_NOW_SIGNAL = signal.SIGUSR1
STOPPED_LINE = "stopped now"


def launchers(proc: Path = Path("/proc"), me: int | None = None) -> list[int]:
    """The process numbers of every running launcher (a Python whose command runs launch.py)."""
    me = os.getpid() if me is None else me
    found = []
    for entry in proc.iterdir() if proc.is_dir() else ():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:  # it ended meanwhile, or isn't ours to read
            continue
        words = [a.decode("utf-8", "replace") for a in args if a]
        if len(words) >= 2 and "python" in Path(words[0]).name and any(w.endswith(LAUNCHER) for w in words[1:]):
            found.append(int(entry.name))
    return sorted(found)


def main(proc: Path = Path("/proc"), kill=os.kill, clock=time.time) -> int:
    found = launchers(proc)
    if not found:
        print("stop-now: no MargenX launcher is running here. Nothing was done. Go on with Suspend (section 7).")
        return 1
    if len(found) > 1:
        print(f"stop-now: {len(found)} launchers found ({', '.join(map(str, found))}); asking each to stop now.")
    sent = 0
    for pid in found:
        try:
            kill(pid, STOP_NOW_SIGNAL)
            sent += 1
        except OSError as problem:
            print(f"stop-now: couldn't reach launcher {pid}: {problem.strerror}")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))
    if not sent:
        print("stop-now: nothing was stopped. Go on with Suspend (section 7).")
        return 1
    print(f"stop-now: asked at {stamp}. The copy's log should now show '{STOPPED_LINE}' within a few seconds; "
          "open tabs lose their connection. Suspend is still pressed (section 7).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
