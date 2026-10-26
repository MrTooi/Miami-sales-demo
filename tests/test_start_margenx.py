"""The double-click launcher: it starts only MargenX's own, unchanged, approved copy in pilot mode.

Each test builds a throwaway "GitHub" repository, a clone of it (the project folder) and a
stand-in Python setup whose streamlit only records how it was started, then runs the launcher.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "start_margenx.command"
GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(shutil.which("bash") and shutil.which("git") and os.name == "posix", "needs bash and git")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.origin = self.root / "origin"
        self.origin.mkdir()
        git("init", "-q", "-b", "main", cwd=self.origin)
        # The only requirement is one the test's own Python has, at its own version.
        import packaging
        (self.origin / "requirements.txt").write_text(f"packaging=={packaging.__version__}\n")
        (self.origin / "marginx_pilot.py").write_text("# stand-in\n")
        (self.origin / ".gitignore").write_text("__pycache__/\n*.py[cod]\n.DS_Store\n*.local\n")  # like the project's
        self.v1 = self.commit("v1")
        self.repo = self.root / "project"
        git("clone", "-q", str(self.origin), str(self.repo), cwd=self.root)
        self.app = self.root / "MargenX-app"
        self.venv = self.root / "venv" / "bin"
        self.venv.mkdir(parents=True)
        self.record = self.root / "started.txt"
        (self.venv / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        (self.venv / "streamlit").write_text(
            f'#!/bin/bash\n{{ pwd -P; echo "pilot=$MARGINX_PILOT"; echo "$@"; echo "cache=$PYTHONPYCACHEPREFIX"; }}'
            f' > "{self.record}"\n')
        for f in ("python", "streamlit"):
            (self.venv / f).chmod(0o755)

    def commit(self, name):
        (self.origin / "version.txt").write_text(name)
        git("add", "-A", cwd=self.origin)
        git("commit", "-q", "-m", name, cwd=self.origin)
        return git("rev-parse", "HEAD", cwd=self.origin)

    def launch(self):
        env = {"HOME": str(self.root), "PATH": os.environ["PATH"], "MARGENX_REPO": str(self.repo),
               "MARGENX_APP": str(self.app), "MARGENX_VENV": str(self.venv.parent),
               "MARGENX_PORT": str(free_port()), "MARGENX_NO_BROWSER": "1", **GIT_ENV}
        return subprocess.run(["bash", str(LAUNCHER)], env=env, input="", capture_output=True, text=True, timeout=60)

    def started(self):
        return self.record.read_text().splitlines() if self.record.exists() else None

    def assert_refused(self, run, words):
        self.assertNotEqual(0, run.returncode, run.stdout)
        self.assertIn(words, run.stdout)
        self.assertIn("MargenX did not start.", run.stdout)
        self.assertIsNone(self.started())

    def test_first_start_sets_up_the_copy_at_main_and_starts_pilot_mode_on_localhost(self):
        run = self.launch()
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        where, pilot, args, cache = self.started()
        self.assertEqual(str(self.app.resolve()), where)
        self.assertEqual("pilot=1", pilot)
        self.assertIn("run marginx_pilot.py --server.address localhost", args)
        self.assertIn("--browser.gatherUsageStats false", args)
        self.assertEqual(self.v1, git("rev-parse", "HEAD", cwd=self.app))
        # Python's compiled cache goes to a fresh folder outside the copy.
        self.assertTrue(cache.startswith("cache=") and len(cache) > 6)
        self.assertNotIn(str(self.app.resolve()), cache)

    def test_a_later_start_updates_the_copy_to_the_new_main(self):
        self.assertEqual(0, self.launch().returncode)
        v2 = self.commit("v2")
        self.assertEqual(0, self.launch().returncode)
        self.assertEqual(v2, git("rev-parse", "HEAD", cwd=self.app))

    def test_offline_it_uses_the_approved_copy_already_here_and_says_so(self):
        self.assertEqual(0, self.launch().returncode)
        git("remote", "set-url", "origin", str(self.root / "unreachable"), cwd=self.repo)
        run = self.launch()
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        self.assertIn("Couldn't reach GitHub", run.stdout)
        self.assertEqual(self.v1, git("rev-parse", "HEAD", cwd=self.app))

    def test_offline_with_no_approved_version_yet_nothing_starts(self):
        git("remote", "set-url", "origin", str(self.root / "unreachable"), cwd=self.repo)
        git("update-ref", "-d", "refs/remotes/origin/main", cwd=self.repo)
        self.assert_refused(self.launch(), "no approved version")

    def test_a_folder_that_is_not_a_repository_never_runs(self):
        self.app.mkdir()
        (self.app / "marginx_pilot.py").write_text("print('not MargenX')\n")
        self.assert_refused(self.launch(), "isn't MargenX's own copy")

    def test_another_repository_in_that_place_never_runs(self):
        git("clone", "-q", str(self.origin), str(self.app), cwd=self.root)  # same code, not this project's worktree
        self.assert_refused(self.launch(), "isn't MargenX's own copy")

    def test_the_project_folder_itself_is_never_used_as_the_copy(self):
        self.app = self.repo
        self.assert_refused(self.launch(), "isn't MargenX's own copy")

    def test_a_changed_copy_is_never_run_or_overwritten(self):
        self.assertEqual(0, self.launch().returncode)
        self.record.unlink()
        (self.app / "marginx_pilot.py").write_text("print('changed')\n")
        self.commit("v2")
        self.assert_refused(self.launch(), "has been changed or couldn't be checked")
        self.assertEqual("print('changed')\n", (self.app / "marginx_pilot.py").read_text())  # left as it was
        (self.app / "marginx_pilot.py").write_text("# stand-in\n")
        (self.app / "extra.py").write_text("print('new file')\n")  # an untracked file counts too
        self.assert_refused(self.launch(), "has been changed or couldn't be checked")

    def go_offline(self):
        git("remote", "set-url", "origin", str(self.root / "unreachable"), cwd=self.repo)

    def first_start(self):
        self.assertEqual(0, self.launch().returncode)
        self.record.unlink()

    def test_a_copy_git_can_not_check_never_runs(self):
        # A corrupted index makes `git status` fail with nothing on its output: that is never "clean".
        self.first_start()
        index = Path(git("rev-parse", "--git-dir", cwd=self.app))
        index = (index if index.is_absolute() else self.app / index) / "index"
        index.write_bytes(index.read_bytes()[:10])
        self.go_offline()
        before = (self.app / "marginx_pilot.py").read_text()
        run = self.launch()
        self.assert_refused(run, "has been changed or couldn't be checked")
        self.assertIn("failed", run.stdout)
        self.assertEqual(before, (self.app / "marginx_pilot.py").read_text())

    def test_edits_hidden_from_git_never_run(self):
        # assume-unchanged and skip-worktree make `git status` show nothing for an edited file.
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.setUp()
                self.first_start()
                git("update-index", flag, "marginx_pilot.py", cwd=self.app)
                (self.app / "marginx_pilot.py").write_text("print('not approved')\n")
                self.assertEqual("", git("status", "--porcelain", cwd=self.app))  # git sees nothing
                self.go_offline()
                run = self.launch()
                self.assert_refused(run, "has been changed or couldn't be checked")
                self.assertIn("marginx_pilot.py", run.stdout)
                self.assertEqual("print('not approved')\n", (self.app / "marginx_pilot.py").read_text())

    def test_extra_ignored_files_never_run_but_caches_are_fine(self):
        self.first_start()
        (self.app / "__pycache__").mkdir()
        (self.app / "__pycache__" / "marginx_pilot.cpython-311.pyc").write_bytes(b"cache")
        (self.app / ".DS_Store").write_bytes(b"finder")
        self.assertEqual(0, self.launch().returncode)  # caches are allowed (and never used)
        self.record.unlink()
        (self.app / "settings.local").write_text("ignored by git, but not part of MargenX\n")
        self.assert_refused(self.launch(), "settings.local is not part of the approved version")

    def test_a_version_that_is_not_on_main_never_runs(self):
        self.assertEqual(0, self.launch().returncode)
        self.record.unlink()
        (self.app / "version.txt").write_text("local")
        git("commit", "-q", "-am", "local", cwd=self.app)  # a local commit, never approved
        git("remote", "set-url", "origin", str(self.root / "unreachable"), cwd=self.repo)  # so it isn't replaced
        self.assert_refused(self.launch(), "isn't an approved version")

    def test_a_python_setup_that_does_not_match_the_version_never_runs(self):
        (self.origin / "requirements.txt").write_text("margenx-test-package-that-does-not-exist==1.0\n")
        self.commit("v2")
        run = self.launch()
        self.assert_refused(run, "Python setup doesn't match")
        self.assertIn("margenx-test-package-that-does-not-exist isn't installed", run.stdout)

    def test_a_missing_python_setup_or_project_stops_with_a_message(self):
        shutil.rmtree(self.venv)
        self.assert_refused(self.launch(), "Can't find MargenX's Python setup")
        self.venv.mkdir(parents=True)
        shutil.rmtree(self.repo)
        self.assert_refused(self.launch(), "Can't find the MargenX project")


if __name__ == "__main__":
    unittest.main()
