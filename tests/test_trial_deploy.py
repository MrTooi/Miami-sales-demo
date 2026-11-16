"""Tests for the website trial's container recipe (PR A2 of issue #131): the launcher, the pinned
packages and cloudflared, and that the image holds exactly the files the trial page needs.

The launcher is run for real in a separate process, with two small stand-in programs in place of
Streamlit and cloudflared (no network, no Cloudflare). Settings are made up.
"""
import ast
import hashlib
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "trial"))

import fetch_cloudflared  # noqa: E402
import launch  # noqa: E402

DOCKERFILE = (ROOT / "deploy" / "trial" / "Dockerfile").read_text()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text()
LOCK = (ROOT / "deploy" / "trial" / "requirements.lock").read_text()
SETTINGS = {"MARGINX_TRIAL": "1", "MARGINX_TRIAL_TEAM_DOMAIN": "https://margenx-test.cloudflareaccess.com",
            "MARGINX_TRIAL_AUDIENCE": "test-aud-tag", "MARGINX_TRIAL_INVITED_EMAIL": "owner-marker@example.com",
            "MARGINX_TRIAL_HOST": "app.example.com", "TUNNEL_TOKEN": "token-marker-0123456789"}


def page_files() -> set[str]:
    """Every repository module the trial entry point imports, followed through, plus the entry points."""
    local = {p.stem for p in ROOT.glob("*.py")}
    seen, todo = set(), ["trial_app.py", "marginx_pilot.py", "pages/1_MargenX_Import.py"]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse((ROOT / name).read_text())):
            if isinstance(node, ast.Import):
                modules = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module.split(".")[0]]
            else:
                continue
            todo += [f"{m}.py" for m in modules if m in local and f"{m}.py" not in seen]
    return seen


def copied_sources() -> set[str]:
    """The source paths of the Dockerfile's COPY lines (continuation lines joined)."""
    text = DOCKERFILE.replace("\\\n", " ")
    sources = set()
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == "COPY":
            sources.update(p for p in parts[1:-1] if not p.startswith("--"))
    return sources


class ImageContentsTests(unittest.TestCase):
    DATA = {"assets/margenx-logo.png", "sample_data/marginx/*.csv", ".streamlit/config.toml"}
    BUILD = {"deploy/trial/fetch_cloudflared.py", "deploy/trial/requirements.lock", "deploy/trial/launch.py"}

    def test_the_image_copies_exactly_what_the_trial_page_needs(self):
        self.assertEqual(page_files() | self.DATA | self.BUILD, copied_sources())

    def test_the_build_folder_lets_in_only_those_files(self):
        lines = [line.strip() for line in DOCKERIGNORE.splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual("*", lines[0])  # everything is left out by default
        self.assertEqual({f"!{p}" for p in copied_sources()}, set(lines[1:]))

    def test_every_page_data_file_exists(self):
        self.assertTrue((ROOT / "assets" / "margenx-logo.png").exists())
        self.assertGreaterEqual(len(list((ROOT / "sample_data" / "marginx").glob("*.csv"))), 2)

    def test_no_secret_or_setting_is_baked_into_the_image(self):
        for line in DOCKERFILE.splitlines():
            if line.split()[:1] in (["ENV"], ["ARG"]) or line.startswith("    "):
                self.assertNotRegex(line.upper(), r"TOKEN|SECRET|PASSWORD|MARGINX_TRIAL|AUD|EMAIL")
        self.assertNotRegex(DOCKERFILE, r"(?m)^\s*ARG\b")  # Render passes its settings as build arguments
        self.assertNotIn("EXPOSE", DOCKERFILE.split("\n# No EXPOSE")[0])
        self.assertNotRegex(DOCKERFILE, r"(?m)^\s*(EXPOSE|HEALTHCHECK)\b")


class PinningTests(unittest.TestCase):
    def test_the_base_image_is_pinned_by_digest(self):
        self.assertRegex(DOCKERFILE, r"(?m)^FROM python:3\.11\.\d+-slim-bookworm@sha256:[0-9a-f]{64}$")

    def test_packages_install_only_from_the_hashed_lock(self):
        self.assertIn("pip install --require-hashes --only-binary=:all: --no-deps -r /tmp/requirements.lock", DOCKERFILE)
        self.assertNotRegex(DOCKERFILE, r"pip install(?!.*--require-hashes)")

    def test_every_locked_package_is_pinned_and_hashed(self):
        entries = re.findall(r"(?m)^([A-Za-z0-9_.\[\]-]+)==(\S+) \\\n((?:    --hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)", LOCK)
        names = [line for line in LOCK.splitlines() if line and not line.startswith((" ", "#"))]
        self.assertEqual(len(names), len(entries))  # no package line without a version and hashes
        self.assertGreater(len(entries), 30)

    def test_every_requirements_pin_is_locked_at_the_same_version(self):
        locked = {name.lower().replace("_", "-"): version
                  for name, version in re.findall(r"(?m)^([A-Za-z0-9_.-]+)==(\S+) \\$", LOCK)}
        for line in (ROOT / "requirements.txt").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                name, version = line.split("==")
                self.assertEqual(version.strip(), locked[name.split("[")[0].lower().replace("_", "-")], name)

    def test_cloudflared_is_pinned_with_its_checksum(self):
        self.assertRegex(fetch_cloudflared.VERSION, r"^\d{4}\.\d+\.\d+$")
        self.assertRegex(fetch_cloudflared.SHA256, r"^[0-9a-f]{64}$")
        self.assertIn(f"/download/{fetch_cloudflared.VERSION}/cloudflared-linux-amd64", fetch_cloudflared.URL)
        self.assertIn("RUN python /tmp/fetch_cloudflared.py", DOCKERFILE)

    def test_the_image_runs_as_an_ordinary_user(self):
        user = DOCKERFILE.index("\nUSER margenx")
        self.assertLess(user, DOCKERFILE.index("\nCMD "))
        self.assertGreater(user, DOCKERFILE.rindex("\nRUN "))  # nothing runs as root after it
        self.assertIn('CMD ["python", "/app/deploy/trial/launch.py"]', DOCKERFILE)


class FetchCloudflaredTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / "download"
        self.source.write_bytes(b"made-up program bytes")
        self.destination = Path(self.folder.name) / "bin" / "cloudflared"
        self.destination.parent.mkdir()

    def test_a_matching_file_is_installed_executable(self):
        good = hashlib.sha256(b"made-up program bytes").hexdigest()
        fetch_cloudflared.fetch(self.source.as_uri(), good, str(self.destination))
        self.assertEqual(b"made-up program bytes", self.destination.read_bytes())
        self.assertTrue(os.access(self.destination, os.X_OK))

    def test_the_build_refuses_any_machine_but_amd64(self):
        fetch_cloudflared.check_machine("x86_64")
        fetch_cloudflared.check_machine("AMD64")
        for other in ("arm64", "aarch64", "i386"):
            with self.assertRaises(SystemExit):
                fetch_cloudflared.check_machine(other)
        self.assertIn("--platform linux/amd64", DOCKERFILE)

    def test_a_wrong_checksum_fails_the_build_and_leaves_nothing(self):
        with self.assertRaises(SystemExit):
            fetch_cloudflared.fetch(self.source.as_uri(), "0" * 64, str(self.destination))
        self.assertEqual([], list(self.destination.parent.iterdir()))


class CommandTests(unittest.TestCase):
    def test_margenx_listens_on_the_container_only_with_protections_on(self):
        cmd = launch.streamlit_command("python")
        flags = dict(zip(cmd[5::2], cmd[6::2]))
        self.assertEqual(["python", "-m", "streamlit", "run", "trial_app.py"], cmd[:5])
        self.assertEqual("127.0.0.1", flags["--server.address"])
        self.assertEqual({"true"}, {flags["--server.enableXsrfProtection"], flags["--server.enableCORS"],
                                     flags["--server.headless"]})
        self.assertEqual("false", flags["--browser.gatherUsageStats"])
        self.assertEqual("none", flags["--server.fileWatcherType"])
        self.assertEqual("none", flags["--client.showErrorDetails"])
        self.assertEqual("false", flags["--global.developmentMode"])
        self.assertEqual("10", flags["--server.disconnectedSessionTTL"])

    def test_the_tunnel_is_tcp_only_quiet_and_without_remote_diagnostics(self):
        cmd = launch.tunnel_command()
        self.assertEqual(["cloudflared", "tunnel"], cmd[:2])
        self.assertEqual("run", cmd[-1])
        self.assertIn("--no-autoupdate", cmd)
        self.assertEqual("http2", cmd[cmd.index("--protocol") + 1])
        self.assertIn("--management-diagnostics=false", cmd)
        self.assertEqual("info", cmd[cmd.index("--loglevel") + 1])  # debug would log every header
        self.assertEqual("1s", cmd[cmd.index("--grace-period") + 1])
        self.assertEqual("127.0.0.1:20241", cmd[cmd.index("--metrics") + 1])  # metrics on the container only
        self.assertFalse(any("token" in part.lower() for part in cmd))  # the token travels in the environment

    def test_each_program_gets_only_its_own_settings(self):
        environ = {**SETTINGS, "PATH": "/usr/bin", "RENDER_SERVICE_ID": "x", "SOMETHING_ELSE": "y"}
        app, tunnel = launch.streamlit_env(environ), launch.tunnel_env(environ)
        self.assertNotIn("TUNNEL_TOKEN", app)
        self.assertEqual("token-marker-0123456789", tunnel["TUNNEL_TOKEN"])
        self.assertFalse(any(name.startswith("MARGINX") for name in tunnel))
        self.assertEqual(SETTINGS["MARGINX_TRIAL_AUDIENCE"], app["MARGINX_TRIAL_AUDIENCE"])
        for env in (app, tunnel):
            self.assertEqual("/usr/bin", env["PATH"])
            self.assertNotIn("RENDER_SERVICE_ID", env)
            self.assertNotIn("SOMETHING_ELSE", env)


class ClosedModeTests(unittest.TestCase):
    def test_closed_mode_gives_margenx_nobodys_address_instead_of_the_invite(self):
        app = launch.streamlit_env({**SETTINGS, "MARGINX_TRIAL_CLOSED": "1"})
        self.assertEqual(launch.CLOSED_INVITE, app["MARGINX_TRIAL_INVITED_EMAIL"])
        config = launch.ta.TrialConfig.from_environ(app)
        self.assertIsNotNone(config)  # MargenX still starts, and refuses the former invite itself
        self.assertNotEqual(SETTINGS["MARGINX_TRIAL_INVITED_EMAIL"], config.invited_email)
        self.assertNotIn("MARGINX_TRIAL_CLOSED", app)

    def test_only_exactly_1_closes_the_copy(self):
        for value in ("", "0", "yes", "true"):
            app = launch.streamlit_env({**SETTINGS, "MARGINX_TRIAL_CLOSED": value})
            self.assertEqual(SETTINGS["MARGINX_TRIAL_INVITED_EMAIL"], app["MARGINX_TRIAL_INVITED_EMAIL"], value)

    def test_any_other_closed_value_starts_nothing(self):
        for value in ("", " ", "0", "yes", "true", "TRUE", "11", "1x", "closed-marker"):
            started = []
            found = launch.problems({**SETTINGS, "MARGINX_TRIAL_CLOSED": value})
            self.assertTrue(found, repr(value))
            self.assertIn("MARGINX_TRIAL_CLOSED", " ".join(found))
            self.assertNotIn("closed-marker", " ".join(found))  # the value itself is never printed
            code = launch.run(environ={**SETTINGS, "MARGINX_TRIAL_CLOSED": value},
                              spawn=lambda *a, **k: started.append(a))
            self.assertEqual(launch.EXIT_SETTINGS, code, repr(value))
            self.assertEqual([], started, repr(value))  # neither MargenX nor the tunnel

    def test_closed_mode_1_and_not_set_both_start(self):
        self.assertEqual([], launch.problems(SETTINGS))
        self.assertEqual([], launch.problems({**SETTINGS, "MARGINX_TRIAL_CLOSED": "1"}))
        self.assertEqual([], launch.problems({**SETTINGS, "MARGINX_TRIAL_CLOSED": " 1 "}))


class SettingsTests(unittest.TestCase):
    def test_every_setting_is_required(self):
        self.assertEqual([], launch.problems(SETTINGS))
        for name in SETTINGS:
            found = launch.problems({k: v for k, v in SETTINGS.items() if k != name})
            self.assertTrue(found, name)
            self.assertIn(name, " ".join(found))

    def test_invalid_values_are_refused_without_printing_them(self):
        found = launch.problems({**SETTINGS, "MARGINX_TRIAL_TEAM_DOMAIN": "https://evil-marker.example.com"})
        self.assertTrue(found)
        self.assertNotIn("evil-marker", " ".join(found))

    def test_without_settings_nothing_is_started(self):
        started = []
        code = launch.run(environ={"TUNNEL_TOKEN": "x"}, spawn=lambda *a, **k: started.append(a))
        self.assertEqual(launch.EXIT_SETTINGS, code)
        self.assertEqual([], started)


STAND_IN = textwrap.dedent("""
    import os, signal, socket, sys, time
    log, role = sys.argv[1], sys.argv[2]
    def note(text):
        with open(log, "a") as f:
            f.write(f"{time.monotonic():.6f} {role} {text}\\n")
    def on_term(signum, frame):
        note("stopped")
        sys.exit(0)
    signal.signal(signal.SIGTERM, on_term)
    note("started env=" + ",".join(sorted(os.environ)))
    note("held back=" + ",".join(sorted(str(int(s)) for s in signal.pthread_sigmask(signal.SIG_BLOCK, []))))
    if role == "app":
        time.sleep(float(sys.argv[5]))  # like Streamlit, it takes a moment before it listens
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", int(sys.argv[3])))
        server.listen()
        note("listening")
    life = float(sys.argv[4])
    time.sleep(life)
    note("ended by itself")
""")

DRIVER = textwrap.dedent("""
    import functools, json, os, signal, subprocess, sys, time
    sys.path.insert(0, sys.argv[1])
    import launch
    log, port, stand_in, app_life, tunnel_life = sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6]
    environ, listen_delay, stop_before_tunnel = json.loads(sys.argv[7]), sys.argv[8], sys.argv[9] == "1"
    def before_tunnel():
        if stop_before_tunnel:  # the host's stop arrives after the launcher's last check
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(0.2)  # plenty of time for a handler to run, if the stop weren't held back
    def spawn(command, **options):  # notes each program the moment the launcher creates it
        with open(log, "a") as f:
            f.write(f"{time.monotonic():.6f} {command[3]} spawned\\n")
        return subprocess.Popen(command, **options)
    code = launch.run(environ=environ, before_tunnel=before_tunnel, spawn=spawn,
                      streamlit=[sys.executable, stand_in, log, "app", str(port), app_life, listen_delay],
                      tunnel=[sys.executable, stand_in, log, "tunnel", "0", tunnel_life, "0"],
                      ready=functools.partial(launch.wait_until_listening, port=port, seconds=20),
                      poll_seconds=0.05)
    sys.exit(code)
""")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LauncherProcessTests(unittest.TestCase):
    """The real launcher in its own process, with stand-ins for Streamlit and cloudflared."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.log = Path(self.folder.name) / "events.log"
        self.stand_in = Path(self.folder.name) / "stand_in.py"
        self.stand_in.write_text(STAND_IN)
        self.driver = Path(self.folder.name) / "driver.py"
        self.driver.write_text(DRIVER)

    def start(self, app_life=60, tunnel_life=60, listen_delay=0, extra=None, stop_before_tunnel=False):
        import json
        environ = {**SETTINGS, "PATH": os.environ.get("PATH", ""), **(extra or {})}
        return subprocess.Popen([sys.executable, str(self.driver), str(ROOT / "deploy" / "trial"), str(self.log),
                                 str(free_port()), str(self.stand_in), str(app_life), str(tunnel_life),
                                 json.dumps(environ), str(listen_delay), "1" if stop_before_tunnel else "0"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def events(self, with_time=False):
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        rows = [line.split(" ", 2) for line in lines]
        return [(float(t), r, x) for t, r, x in rows] if with_time else [[r, x] for _, r, x in rows]

    def wait_for(self, role, text, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if any(r == role and t.startswith(text) for r, t in self.events()):
                return
            time.sleep(0.05)
        self.fail(f"{role} never logged {text!r}: {self.events()}")

    def finish(self, proc):
        out, _ = proc.communicate(timeout=30)
        return proc.returncode, out

    def test_the_host_stop_ends_margenx_first_then_the_tunnel(self):
        proc = self.start()
        self.wait_for("tunnel", "started")
        proc.send_signal(signal.SIGTERM)  # what Render's Suspend does
        code, out = self.finish(proc)
        self.assertEqual(launch.EXIT_STOPPED_BY_HOST, code, out)
        stops = [role for role, text in self.events() if text == "stopped"]
        self.assertEqual(["app", "tunnel"], stops)  # MargenX first: no request is handled any more

    def test_when_the_tunnel_stops_margenx_stops_and_nothing_restarts(self):
        proc = self.start(tunnel_life=0.5)
        code, out = self.finish(proc)
        self.assertEqual(launch.EXIT_PROGRAM_STOPPED, code, out)
        events = self.events()
        self.assertIn(["app", "stopped"], events)
        self.assertEqual(1, sum(1 for r, t in events if r == "tunnel" and t.startswith("started")))
        self.assertEqual(1, sum(1 for r, t in events if r == "app" and t.startswith("started")))
        self.assertIn("nothing is restarted", out)

    def test_when_margenx_stops_the_tunnel_stops_and_nothing_restarts(self):
        proc = self.start(app_life=1.5)
        code, out = self.finish(proc)
        self.assertEqual(launch.EXIT_PROGRAM_STOPPED, code, out)
        events = self.events()
        self.assertIn(["tunnel", "stopped"], events)
        self.assertEqual(1, sum(1 for r, t in events if r == "app" and t.startswith("started")))

    def test_a_stop_while_margenx_is_starting_never_starts_the_tunnel(self):
        proc = self.start(listen_delay=30)  # MargenX would take 30 seconds to listen
        self.wait_for("app", "started")
        asked = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        code, out = self.finish(proc)
        self.assertLess(time.monotonic() - asked, 10)  # the stop doesn't wait for the readiness timeout
        self.assertEqual(launch.EXIT_STOPPED_BY_HOST, code, out)
        self.assertFalse([1 for r, t in self.events() if r == "tunnel"])  # never started
        self.assertIn(["app", "stopped"], self.events())
        self.assertNotIn("running", out)

    def test_a_stop_after_the_last_check_still_never_starts_the_tunnel(self):
        proc = self.start(stop_before_tunnel=True)  # the stop lands between the check and the start
        code, out = self.finish(proc)
        self.assertEqual(launch.EXIT_STOPPED_BY_HOST, code, out)
        self.assertFalse([1 for r, t in self.events() if r == "tunnel"])  # never started
        self.assertIn(["app", "stopped"], self.events())
        self.assertNotIn("running", out)

    def test_the_programs_never_inherit_the_held_back_stop_signals(self):
        proc = self.start()
        self.wait_for("tunnel", "held back")
        proc.send_signal(signal.SIGTERM)
        self.finish(proc)
        held = {r: t.split("=", 1)[1] for r, t in self.events() if t.startswith("held back")}
        for role in ("app", "tunnel"):  # so the host's stop always reaches both programs
            self.assertNotIn(str(int(signal.SIGTERM)), held[role].split(","), role)
            self.assertNotIn(str(int(signal.SIGINT)), held[role].split(","), role)

    def test_closed_mode_says_so_in_the_log_and_margenx_gets_nobodys_address(self):
        proc = self.start(extra={"MARGINX_TRIAL_CLOSED": "1"})
        self.wait_for("tunnel", "started")
        proc.send_signal(signal.SIGTERM)
        code, out = self.finish(proc)
        self.assertIn("closed: this copy refuses every login", out)
        self.assertNotIn("owner-marker", out)

    def test_the_tunnel_starts_only_after_margenx_is_listening(self):
        proc = self.start(listen_delay=1.0)
        self.wait_for("tunnel", "started")
        proc.send_signal(signal.SIGTERM)
        self.finish(proc)
        times = {(r, x.split(" ")[0]): t for t, r, x in self.events(with_time=True)}
        self.assertGreater(times[("tunnel", "started")], times[("app", "listening")])

    def test_each_program_sees_only_its_own_settings_and_nothing_is_printed(self):
        proc = self.start()
        self.wait_for("tunnel", "started")
        proc.send_signal(signal.SIGTERM)
        code, out = self.finish(proc)
        envs = {r: t.split("env=", 1)[1].split(",") for r, t in self.events() if t.startswith("started")}
        self.assertNotIn("TUNNEL_TOKEN", envs["app"])
        self.assertIn("MARGINX_TRIAL_AUDIENCE", envs["app"])
        self.assertIn("TUNNEL_TOKEN", envs["tunnel"])
        self.assertFalse([name for name in envs["tunnel"] if name.startswith("MARGINX")])
        for value in ("token-marker", "owner-marker", "test-aud-tag", "margenx-test"):
            self.assertNotIn(value, out)  # the launcher's own output never shows a setting or the token


if __name__ == "__main__":
    unittest.main()
