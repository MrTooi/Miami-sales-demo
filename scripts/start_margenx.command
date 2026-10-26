#!/bin/bash
# Double-click to start MargenX in pilot mode on this Mac, with the latest approved version.
#
# Approved means exactly the commit at the tip of main in the MargenX repository on GitHub, at the
# address written below: the launcher asks GitHub for it on every start, so it needs the internet
# (a phone hotspot is fine). It never takes "approved" from the project's own settings (its origin,
# refs or stored objects), which aren't trusted.
#
# MargenX runs only from its own copy in ~/MargenX-app, a registered git worktree of the project,
# never the project folder itself. Before starting, nothing in the copy may be changed or added
# (only __pycache__ folders, test caches and Finder files are allowed), and every file must match the
# approved commit byte for byte, checked by recomputing each object's fingerprint from that commit
# down. Nothing in the copy is forced or cleaned: a problem stops the launch with a message. Git and
# the launcher's own Python checks run with every feature that could run another program switched
# off. The Python setup is checked against the version's requirements, then MargenX opens at
# http://localhost:8501, on this laptop only. Close this window (or press Ctrl+C) to stop MargenX.
#
# The MARGENX_* variables below exist for the launcher's tests; leave them unset.

APPROVED_URL="https://github.com/MrTooi/Miami-sales-demo.git"
REPO="${MARGENX_REPO:-$HOME/Documents/GitHub/Miami-sales-demo}"
APP="${MARGENX_APP:-$HOME/MargenX-app}"
VENV="${MARGENX_VENV:-$HOME/.venvs/miami-sales-demo}"
PORT="${MARGENX_PORT:-8501}"
PROTOCOLS=(-c protocol.allow=never -c protocol.https.allow=always)
if [ -n "$MARGENX_TEST_URL" ]; then  # tests only: a local repository stands in for GitHub
  APPROVED_URL="$MARGENX_TEST_URL"
  PROTOCOLS+=(-c protocol.file.allow=always)
fi

stop() {
  echo
  echo "$1"
  echo "MargenX did not start."
  read -r -p "Press Return to close this window." _ || true
  exit 1
}

real() { (cd "$1" 2>/dev/null && pwd -P); }

# Git can be set up to run other programs (a file monitor, hooks, filters, credential and transport
# helpers) or to swap objects (replace refs). Every git command here ignores this Mac's system and
# personal git settings, ignores replace refs, and runs with those features off; the project's own
# settings must not name any of them (checked below).
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0
GIT_SAFE=(-c core.fsmonitor=false -c core.hooksPath=/dev/null -c core.untrackedCache=false
          -c core.attributesFile=/dev/null "${PROTOCOLS[@]}")
g() { git "${GIT_SAFE[@]}" "$@"; }

check_git_config() {
  local cfg bad
  cfg="$(g -C "$1" config --list --show-scope 2>&1)" || stop "Couldn't read the git settings in $1 ($cfg)."
  bad="$(printf '%s\n' "$cfg" | awk -F'\t' '$1 != "command" { split($2, kv, "="); print kv[1] }' \
    | grep -Ei '^(filter\.|core\.(fsmonitor|hookspath|attributesfile|sshcommand|gitproxy|askpass)$|credential\.|include\.|includeif\.|url\.|http\.|protocol\.|uploadpack\.|remote\.[^.]+\.(uploadpack|receivepack|vcs|proxy)$)' \
    | sort -u | tr '\n' ' ')"
  [ -z "$bad" ] || stop "$1 has git settings that can run other programs ($bad), so MargenX won't start. Ask Claude Code to check them."
}

# The copy must be exactly the commit given (its own HEAD before an update, the approved one after).
# Git's summaries aren't trusted alone: a failing git command stops here; files flagged so git
# ignores their edits (assume-unchanged, skip-worktree) are refused; anything added is refused; and
# every committed file is compared byte for byte with what is on disk, walking the commit's tree with
# each object's fingerprint recomputed, so a planted or swapped object in the project can't pass.
# Nothing in the copy is changed.
verify_copy() {
  (cd / && "$VENV/bin/python" -I - "$APP" "$1" "${GIT_SAFE[@]}") <<'PY' || stop "$APP has been changed or couldn't be checked, so MargenX won't run it. Ask Claude Code to check that folder."
import hashlib
import os
import subprocess
import sys

app, expected, safe = sys.argv[1], sys.argv[2], sys.argv[3:]


def git(*args):
    run = subprocess.run(["git", *safe, "-C", app, *args], capture_output=True)
    if run.returncode != 0:
        print(f"  git {args[0]} failed: {run.stderr.decode(errors='replace').strip()}")
        sys.exit(2)
    return run.stdout


def checked(kind, oid):
    """An object's content, refused unless it really has that fingerprint."""
    data = git("cat-file", kind, oid)
    if hashlib.sha1(b"%s %d\0" % (kind.encode(), len(data)) + data).hexdigest() != oid:
        print(f"  the stored {kind} {oid} doesn't match its fingerprint")
        sys.exit(1)
    return data


problems = []
if git("rev-parse", "--verify", "HEAD").decode().strip() != expected:
    problems.append(f"the copy isn't at {expected[:7]}")
for line in git("ls-files", "-v", "-z").split(b"\0"):
    if line and (line[:1].islower() or line[:1] == b"S"):  # assume-unchanged or skip-worktree
        problems.append(f"{line[2:].decode(errors='replace')} is set so git ignores its changes")
for entry in git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored").split(b"\0"):
    if not entry:
        continue
    code, path = entry[:2].decode(errors="replace"), entry[3:].decode(errors="replace")
    parts = path.rstrip("/").split("/")
    # Only caches that never run: Python reads __pycache__ only beside its approved source file (and,
    # in pilot mode, not at all: its cache goes elsewhere). A .pyc anywhere else can be imported on
    # its own, so it is refused like any other extra file.
    if code == "!!" and ("__pycache__" in parts[:-1] or parts[-1] == "__pycache__" or ".pytest_cache" in parts
                         or parts[-1] == ".DS_Store"):
        continue
    problems.append(f"{path} is {'not part of the approved version' if code in ('??', '!!') else 'changed'}")

commit = checked("commit", expected)
tree = commit.split(b"\n", 1)[0]
if not tree.startswith(b"tree "):
    print("  the commit has no tree")
    sys.exit(1)
pending = [(tree[5:].decode(), "")]
while pending:
    oid, prefix = pending.pop()
    data = checked("tree", oid)
    while data:
        head, _, rest = data.partition(b"\0")
        mode, name = head.split(b" ", 1)
        child, data = rest[:20].hex(), rest[20:]
        shown = prefix + name.decode(errors="replace")
        path = os.path.join(app, os.fsdecode(prefix.encode() + name))
        if mode == b"40000":
            pending.append((child, shown + "/"))
            continue
        try:
            if mode == b"120000":
                ok, content = os.path.islink(path), os.fsencode(os.readlink(path))
            elif mode in (b"100644", b"100755"):
                ok = os.path.isfile(path) and not os.path.islink(path)
                with open(path, "rb") as f:
                    content = f.read()
            else:
                raise OSError  # a submodule or something else that can't be checked
        except OSError:
            problems.append(f"{shown} is missing or can't be checked")
            continue
        if not ok or hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest() != child:
            problems.append(f"{shown} is changed")
for problem in problems[:10]:
    print("  " + problem)
sys.exit(1 if problems else 0)
PY
}

[ -d "$REPO/.git" ] || stop "Can't find the MargenX project at $REPO."
[ -x "$VENV/bin/streamlit" ] && [ -x "$VENV/bin/python" ] || stop "Can't find MargenX's Python setup at $VENV."
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  stop "Something is already running at port $PORT. If MargenX is already open, use that window, or close it first."
fi
check_git_config "$REPO"

# An existing copy must be this project's own registered worktree (not the project folder, another
# folder or another repository), with nothing changed or added, before it is touched.
if [ -e "$APP" ]; then
  app_real="$(real "$APP")"
  [ -n "$app_real" ] && [ "$app_real" != "$(real "$REPO")" ] || stop "$APP isn't MargenX's own copy. Move it somewhere else, then try again."
  registered=no
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) [ "$(real "${line#worktree }")" = "$app_real" ] && registered=yes ;;
    esac
  done < <(g -C "$REPO" worktree list --porcelain 2>/dev/null)
  [ "$registered" = yes ] || stop "$APP isn't MargenX's own copy. Move it somewhere else, then try again."
  check_git_config "$APP"
  current="$(g -C "$APP" rev-parse --verify --quiet HEAD)" || stop "Couldn't read the version in $APP."
  verify_copy "$current"
fi

# The approved version comes from GitHub itself, never from the project's settings or refs.
echo "Asking GitHub for the latest approved MargenX..."
approved="$(g ls-remote "$APPROVED_URL" refs/heads/main 2>/dev/null | awk '$2 == "refs/heads/main" { print $1 }')"
case "$approved" in
  *[!0-9a-f]* | "") approved="" ;;
  *) [ "${#approved}" = 40 ] || approved="" ;;
esac
[ -n "$approved" ] || stop "Couldn't reach GitHub to check which version is approved. Connect to the internet (a phone hotspot is fine) and try again."
g -C "$REPO" fetch --quiet --no-tags "$APPROVED_URL" "$approved" || stop "Couldn't download the approved version from GitHub."

if [ ! -e "$APP" ]; then
  g -C "$REPO" worktree add --quiet --detach "$APP" "$approved" || stop "Couldn't set up $APP."
elif [ "$current" != "$approved" ]; then
  # Only ever move forward along main: a version that isn't part of it is never replaced or lost.
  g -C "$REPO" merge-base --is-ancestor "$current" "$approved" || stop "The copy in $APP isn't an approved version of MargenX."
  g -C "$APP" checkout --quiet --detach "$approved" || stop "Couldn't update $APP."
fi
verify_copy "$approved"  # again, after any update: what runs is exactly the approved commit
echo "MargenX version $(g -C "$APP" log -1 --format='%h from %cd' --date=format:'%b %d, %Y' "$approved")."

# The Python setup must have every package this version needs, at the version it needs (checked
# isolated, from outside the copy, so nothing in the copy is imported).
(cd / && "$VENV/bin/python" -I - "$APP/requirements.txt") <<'PY' || stop "MargenX's Python setup doesn't match this version. In Terminal, run: $VENV/bin/pip install -r $APP/requirements.txt"
import sys
from importlib.metadata import PackageNotFoundError, version
from packaging.requirements import Requirement

problems = []
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.split("#", 1)[0].strip()
    if not line:
        continue
    if line.startswith("-"):
        problems.append(f"{line} (can't be checked)")
        continue
    req = Requirement(line)
    if req.marker and not req.marker.evaluate():
        continue
    try:
        installed = version(req.name)
    except PackageNotFoundError:
        problems.append(f"{req.name} isn't installed")
        continue
    if req.specifier and not req.specifier.contains(installed, prereleases=True):
        problems.append(f"{req.name} is {installed}, needs {req.specifier}")
for problem in problems:
    print("  " + problem)
sys.exit(1 if problems else 0)
PY

cd "$APP" || stop "Couldn't open $APP."
echo "Opening MargenX in your browser. Close this window to stop it."
echo
if [ -z "$MARGENX_NO_BROWSER" ]; then
  (sleep 4; open "http://localhost:$PORT") &
fi
# Python keeps its compiled cache in a fresh folder, never in the copy, so no leftover cache file runs.
PYTHONPYCACHEPREFIX="$(mktemp -d "${TMPDIR:-/tmp}/margenx-pycache.XXXXXX")" || stop "Couldn't make a cache folder."
export PYTHONPYCACHEPREFIX
MARGINX_PILOT=1 exec "$VENV/bin/streamlit" run marginx_pilot.py --server.address localhost --server.port "$PORT" \
  --server.headless true --browser.gatherUsageStats false
