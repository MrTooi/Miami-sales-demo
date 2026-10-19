"""MarginX Progress: one owner view of the build, this week's checklist and what needs you.

Read-only owner tooling. GitHub is the source of truth; this page never mutates
repository, workflow, product, financial, or customer state, and shows UNKNOWN
rather than guessing when GitHub can't be read.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from command_center.progress_logic import (  # noqa: E402
    ci_state,
    latest_review,
    latest_weekly_checklist,
    next_action,
    parse_build_steps,
    parse_checklist,
    progress,
    step_status,
)

REPO = "MrTooi/Miami-sales-demo"
API = "https://api.github.com"
ET = ZoneInfo("America/New_York")
STATUS_ICON = {"DONE": "✅", "IN PROGRESS": "🔨", "NOT STARTED": "⬜"}

st.set_page_config(page_title="MarginX Progress", page_icon="◈", layout="wide")


def _token() -> str | None:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("GITHUB_TOKEN")
    except Exception:
        return None


@st.cache_data(ttl=30, show_spinner=False)
def gh(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "marginx-command-center",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        return None, f"GitHub API {exc.code}"
    except Exception as exc:
        return None, str(exc)


@st.cache_data(ttl=60, show_spinner=False)
def raw_text(path: str, ref: str = "main") -> str | None:
    try:
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{REPO}/{ref}/{path}", timeout=10) as response:
            return response.read().decode("utf-8")
    except Exception:
        return None


def when(value: str | None) -> str:
    if not value:
        return "unknown"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ET).strftime("%b %d, %I:%M %p ET")


st.title("MarginX Progress")
st.caption(
    f"Live from GitHub · refreshed {datetime.now(ET).strftime('%b %d, %I:%M %p ET')} · read-only. "
    "Statuses come from ticked boxes, PRs, reviews and CI; nothing here is estimated."
)
if st.button("Refresh now"):
    st.cache_data.clear()
    st.rerun()

pulls_open, err_open = gh(f"/repos/{REPO}/pulls?state=open&per_page=50")
pulls_closed, err_closed = gh(f"/repos/{REPO}/pulls?state=closed&per_page=50&sort=updated&direction=desc")
issues, err_issues = gh(f"/repos/{REPO}/issues?state=open&per_page=50")
all_pulls = (pulls_open or []) + (pulls_closed or [])

# --- Needs you -------------------------------------------------------------
st.header("Needs your attention")
if err_open:
    st.warning(f"UNKNOWN: could not read open PRs ({err_open}).")
else:
    ready = [p for p in pulls_open if not p.get("draft")]
    if not ready:
        st.success("No open pull requests waiting.")
    for pr in ready:
        number, sha = pr["number"], pr["head"]["sha"]
        comments, _ = gh(f"/repos/{REPO}/issues/{number}/comments?per_page=100")
        runs, _ = gh(f"/repos/{REPO}/commits/{sha}/check-runs?per_page=50")
        commit, _ = gh(f"/repos/{REPO}/commits/{sha}")
        review = latest_review(comments or [])
        head_time = ((commit or {}).get("commit") or {}).get("committer", {}).get("date")
        fresh = bool(review and head_time and (review["at"] or "") >= head_time)
        ci = ci_state(None if runs is None else runs.get("check_runs", []))
        action = next_action(review, ci, fresh)
        verdict = f"[{review['verdict']}]({review['url']})" if review else "none yet"
        if not fresh and review:
            verdict += " (older commit)"
        tone = st.success if action.startswith("Ready") else st.info if action.startswith("Needs") else st.warning
        tone(f"**[PR #{number}]({pr['html_url']}) {pr['title']}**  \n"
             f"Next: **{action}** · Review: {verdict} · Tests: {ci}")

# --- Build steps ---------------------------------------------------------
st.header("MarginX build steps")
steps = parse_build_steps(raw_text("docs/MVP_SPEC.md"))
if not steps:
    st.warning("UNKNOWN: could not read the build order from docs/MVP_SPEC.md on main.")
elif err_open or err_closed:
    st.warning("UNKNOWN: could not read pull requests to work out step status.")
else:
    done = 0
    for step in steps:
        status, pr = step_status(step["number"], all_pulls)
        done += status == "DONE"
        link = f" · [PR #{pr['number']}]({pr['html_url']})" if pr else ""
        st.markdown(f"{STATUS_ICON[status]} **Step {step['number']}: {step['title']}** · {status}{link}")
    st.progress(done / len(steps), text=f"{done} of {len(steps)} build steps merged")
    st.caption("A step counts as done only when a PR titled “MarginX step N: …” is merged.")

# --- This week's checklist -------------------------------------------------
weekly = None if err_issues else latest_weekly_checklist(issues or [])
st.header("This week's checklist")
if err_issues:
    st.warning(f"UNKNOWN: could not read issues ({err_issues}).")
elif weekly is None:
    st.info("No open weekly checklist issue found.")
else:
    st.markdown(f"[#{weekly['number']} {weekly['title']}]({weekly['html_url']}) · boxes are ticked on GitHub")
    groups = parse_checklist(weekly.get("body"))
    sections: dict[str, list] = {}
    for group in groups:
        sections.setdefault(group["section"], []).append(group)
    cols = st.columns(max(1, len(sections)))
    for col, (section, section_groups) in zip(cols, sections.items()):
        with col:
            items = [i for g in section_groups for i in g["items"]]
            d, t = progress(items)
            st.subheader(section)
            st.progress(d / t if t else 0.0, text=f"{d} of {t} done")
            for group in section_groups:
                gd, gt = progress(group["items"])
                with st.expander(f"{group['title'].split(' — ')[-1]} · {gd}/{gt}"):
                    for item in group["items"]:
                        st.markdown(f"{'✅' if item['done'] else '⬜'} {item['text']}")

# --- Recently merged -------------------------------------------------------
st.header("Merged in the last 7 days")
cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
recent = sorted(
    (p for p in (pulls_closed or []) if p.get("merged_at") and p["merged_at"] >= cutoff),
    key=lambda p: p["merged_at"], reverse=True,
)
if err_closed:
    st.warning(f"UNKNOWN: could not read merged PRs ({err_closed}).")
elif not recent:
    st.info("Nothing merged in the last 7 days.")
for pr in recent[:10]:
    st.markdown(f"- {when(pr['merged_at'])} · [PR #{pr['number']}]({pr['html_url']}) {pr['title']}")
if len(recent) > 10:
    with st.expander(f"{len(recent) - 10} more"):
        for pr in recent[10:]:
            st.markdown(f"- {when(pr['merged_at'])} · [PR #{pr['number']}]({pr['html_url']}) {pr['title']}")
