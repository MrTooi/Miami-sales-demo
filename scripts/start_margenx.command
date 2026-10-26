#!/bin/bash
# Double-click to start MargenX in pilot mode on this Mac, with the latest approved version.
#
# MargenX runs from its own copy in ~/MargenX-app, never from the project folder, so whatever
# branch the project folder is on doesn't matter. Each start updates that copy to the latest
# approved version on GitHub (main) when GitHub can be reached; otherwise it uses the copy already
# here and says so. It then opens MargenX at http://localhost:8501, on this laptop only.
# Close this window (or press Ctrl+C in it) to stop MargenX.

REPO="${MARGENX_REPO:-$HOME/Documents/GitHub/Miami-sales-demo}"
APP="$HOME/MargenX-app"
STREAMLIT="$HOME/.venvs/miami-sales-demo/bin/streamlit"
PORT=8501

stop() { echo; echo "$1"; read -r -p "Press Return to close this window."; exit 1; }

[ -d "$REPO/.git" ] || stop "Can't find the MargenX project at $REPO."
[ -x "$STREAMLIT" ] || stop "Can't find MargenX's Python setup at $STREAMLIT."
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  stop "Something is already running at port $PORT. If MargenX is already open, use that window, or close it first."
fi

echo "Getting the latest approved MargenX..."
if git -C "$REPO" fetch --quiet origin main; then
  if [ -d "$APP" ]; then
    git -C "$APP" checkout --quiet --detach --force origin/main || stop "Couldn't update $APP."
  else
    git -C "$REPO" worktree add --quiet --detach "$APP" origin/main || stop "Couldn't set up $APP."
  fi
else
  echo "Couldn't reach GitHub, so this is the version already on this Mac."
  [ -d "$APP" ] || git -C "$REPO" worktree add --quiet --detach "$APP" origin/main || stop "Couldn't set up $APP."
fi
echo "MargenX version $(git -C "$APP" log -1 --format='%h from %cd' --date=format:'%b %-d, %Y')."
echo "Opening MargenX in your browser. Close this window to stop it."
echo

cd "$APP" || stop "Couldn't open $APP."
(sleep 4; open "http://localhost:$PORT") &
MARGINX_PILOT=1 exec "$STREAMLIT" run marginx_pilot.py --server.address localhost --server.port "$PORT" \
  --server.headless true --browser.gatherUsageStats false
