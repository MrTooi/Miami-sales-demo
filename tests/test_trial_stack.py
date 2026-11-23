"""The uploads PR (issue #131, plan v7): the real launcher supervising the real trial page in real Streamlit.

MargenX here is `streamlit run trial_app.py`, exactly as in the image (on a free port); the tunnel is a
stand-in that just waits. Outside requests go to a closed local port, so nothing reaches the network. The
heartbeat limit is lowered for the test, so a frozen MargenX is noticed in seconds.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import tests.test_trial_access as t

ROOT = Path(__file__).resolve().parents[1]

DRIVER = textwrap.dedent("""
    import functools, json, os, subprocess, sys
    sys.path.insert(0, sys.argv[1])
    import launch
    log, port, environ = sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4])
    launch.HEARTBEAT_SECONDS = 6.0
    def spawn(command, **options):
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        with open(log, "a") as f:
            f.write(("streamlit" if "streamlit" in command else "tunnel") + f" {proc.pid}\\n")
        return proc
    streamlit = [sys.executable, "-m", "streamlit", "run", "trial_app.py", "--server.address", "127.0.0.1",
                 "--server.port", str(port), "--server.headless", "true", "--browser.gatherUsageStats", "false",
                 "--server.fileWatcherType", "none"]
    tunnel = [sys.executable, "-c", "import time; time.sleep(600)"]
    code = launch.run(environ=environ, spawn=spawn, streamlit=streamlit, tunnel=tunnel,
                      ready=functools.partial(launch.wait_until_listening, port=port, seconds=60), poll_seconds=0.1)
    sys.exit(code)
""")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True


class RealStackTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.log = Path(self.folder.name) / "pids.log"
        driver = Path(self.folder.name) / "driver.py"
        driver.write_text(DRIVER)
        self.port = free_port()
        nowhere = "http://127.0.0.1:9"
        environ = {**t.SETTINGS, "TUNNEL_TOKEN": "token-marker", "PATH": os.environ.get("PATH", ""),
                   "HOME": os.environ.get("HOME", ""), "HTTPS_PROXY": nowhere, "https_proxy": nowhere}
        self.proc = subprocess.Popen([sys.executable, str(driver), str(ROOT / "deploy" / "trial"), str(self.log),
                                      str(self.port), json.dumps(environ)], cwd=str(ROOT),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for pid in self.pids("streamlit") + self.pids("tunnel"):
            if not gone(pid):
                os.kill(pid, signal.SIGKILL)

    def pids(self, role):
        if not self.log.exists():
            return []
        return [int(line.split()[1]) for line in self.log.read_text().splitlines() if line.split()[0] == role]

    def wait(self, condition, seconds, what):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.1)
        self.fail(f"never: {what}")

    def listening(self):
        try:
            socket.create_connection(("127.0.0.1", self.port), timeout=1).close()
            return True
        except OSError:
            return False

    def finish(self):
        self.proc.send_signal(signal.SIGTERM)
        out, _ = self.proc.communicate(timeout=60)
        return out

    def test_the_real_page_sends_heartbeats_a_frozen_margenx_is_replaced_and_stop_now_kills_it(self):
        self.wait(lambda: self.pids("tunnel"), 90, "the tunnel started (MargenX listening)")
        first = self.pids("streamlit")[0]
        time.sleep(9)  # longer than the (test) heartbeat limit: a running MargenX keeps beating
        self.assertEqual([first], self.pids("streamlit"))
        os.kill(first, signal.SIGSTOP)  # frozen: none of MargenX's own code can run any more
        self.wait(lambda: len(self.pids("streamlit")) == 2, 30, "a replacement MargenX")
        self.wait(lambda: gone(first), 10, "the frozen MargenX killed")
        second = self.pids("streamlit")[1]
        self.wait(self.listening, 60, "the replacement listening on the same port")
        os.kill(self.proc.pid, signal.SIGUSR1)  # the operator's stop-now
        self.wait(lambda: gone(second), 10, "MargenX killed by the stop-now")
        time.sleep(1.5)
        self.assertEqual(2, len(self.pids("streamlit")))  # nothing restarted after the stop-now
        self.assertIsNone(self.proc.poll())  # the launcher waits for the host's stop
        out = self.finish()
        self.assertEqual(0, self.proc.returncode, out)
        self.assertIn("recycled: not responding; every earlier login must log in again", out)
        self.assertIn("stopped now", out)
        for value in ("token-marker", t.INVITED, t.AUD):
            self.assertNotIn(value, out)


if __name__ == "__main__":
    unittest.main()
