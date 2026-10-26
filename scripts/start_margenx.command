#!/bin/bash
# Double-click to start MargenX in pilot mode on this Mac, with the latest approved version.
#
# MargenX runs only from its own copy in ~/MargenX-app: a git worktree of the project, never the
# project folder itself, so whatever branch the project folder is on doesn't matter. Before
# starting, the copy must be that registered worktree, unchanged, and on an approved version (one
# that is on main as last fetched from GitHub); otherwise nothing starts. Each start updates the
# copy to the latest main when GitHub can be reached, otherwise it says so and uses the copy here.
# It then checks the Python setup against the version's requirements and opens MargenX at
# http://localhost:8501, on this laptop only. Close this window (or press Ctrl+C) to stop MargenX.
#
# The MARGENX_* variables below exist for the launcher's tests; leave them unset.

REPO="${MARGENX_REPO:-$HOME/Documents/GitHub/Miami-sales-demo}"
APP="${MARGENX_APP:-$HOME/MargenX-app}"
VENV="${MARGENX_VENV:-$HOME/.venvs/miami-sales-demo}"
PORT="${MARGENX_PORT:-8501}"

stop() {
  echo
  echo "$1"
  echo "MargenX did not start."
  read -r -p "Press Return to close this window." _ || true
  exit 1
}

real() { (cd "$1" 2>/dev/null && pwd -P); }

[ -d "$REPO/.git" ] || stop "Can't find the MargenX project at $REPO."
[ -x "$VENV/bin/streamlit" ] && [ -x "$VENV/bin/python" ] || stop "Can't find MargenX's Python setup at $VENV."
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  stop "Something is already running at port $PORT. If MargenX is already open, use that window, or close it first."
fi

# An existing copy must be this project's own registered worktree (not the project folder, another
# folder or another repository) and unchanged. It is never forced or cleaned: a problem stops here.
if [ -e "$APP" ]; then
  app_real="$(real "$APP")"
  [ -n "$app_real" ] && [ "$app_real" != "$(real "$REPO")" ] || stop "$APP isn't MargenX's own copy. Move it somewhere else, then try again."
  registered=no
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) [ "$(real "${line#worktree }")" = "$app_real" ] && registered=yes ;;
    esac
  done < <(git -C "$REPO" worktree list --porcelain 2>/dev/null)
  [ "$registered" = yes ] || stop "$APP isn't MargenX's own copy. Move it somewhere else, then try again."
  [ -z "$(git -C "$APP" status --porcelain 2>/dev/null)" ] || stop "$APP has been changed, so MargenX won't run it. Ask Claude Code to check that folder."
fi

echo "Getting the latest approved MargenX..."
if git -C "$REPO" fetch --quiet origin main; then
  online=yes
else
  online=no
  echo "Couldn't reach GitHub, so this is the version already on this Mac."
fi
git -C "$REPO" rev-parse --verify --quiet origin/main >/dev/null || stop "There's no approved version of MargenX on this Mac yet. Connect to the internet and try again."
if [ ! -e "$APP" ]; then
  git -C "$REPO" worktree add --quiet --detach "$APP" origin/main || stop "Couldn't set up $APP."
elif [ "$online" = yes ]; then
  git -C "$APP" checkout --quiet --detach origin/main || stop "Couldn't update $APP."
fi

# Approved means on main, as last fetched from GitHub: a local or unmerged version never runs.
head="$(git -C "$APP" rev-parse --verify --quiet HEAD)" || stop "Couldn't read the version in $APP."
git -C "$REPO" merge-base --is-ancestor "$head" origin/main || stop "The copy in $APP isn't an approved version of MargenX."
echo "MargenX version $(git -C "$APP" log -1 --format='%h from %cd' --date=format:'%b %d, %Y')."

cd "$APP" || stop "Couldn't open $APP."
# The Python setup must have every package this version needs, at the version it needs.
"$VENV/bin/python" - requirements.txt <<'PY' || stop "MargenX's Python setup doesn't match this version. In Terminal, run: $VENV/bin/pip install -r $APP/requirements.txt"
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

echo "Opening MargenX in your browser. Close this window to stop it."
echo
if [ -z "$MARGENX_NO_BROWSER" ]; then
  (sleep 4; open "http://localhost:$PORT") &
fi
MARGINX_PILOT=1 exec "$VENV/bin/streamlit" run marginx_pilot.py --server.address localhost --server.port "$PORT" \
  --server.headless true --browser.gatherUsageStats false
