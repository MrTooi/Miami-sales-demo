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
    UNIT_STEP_LABEL,
    ci_state,
    latest_weekly_checklist,
    next_action,
    parse_build_steps,
    parse_checklist,
    progress,
    recent_merges,
    review_for_head,
    step_status,
)

REPO = "MrTooi/Miami-sales-demo"
API = "https://api.github.com"
ET = ZoneInfo("America/New_York")
PAGE = 100
MAX_PAGES = 10
STATUS_ICON = {UNIT_STEP_LABEL: "🟦", "IN PROGRESS": "🔨", "NOT STARTED": "⬜", "UNKNOWN": "❔"}

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


def gh_all(path: str) -> tuple[list | None, bool, str | None]:
    """Read every page of a list endpoint. Returns (rows, complete, error)."""
    rows: list = []
    sep = "&" if "?" in path else "?"
    for page in range(1, MAX_PAGES + 1):
        data, err = gh(f"{path}{sep}per_page={PAGE}&page={page}")
        if err or not isinstance(data, list):
            return (rows or None), False, err or "unexpected response"
        rows.extend(data)
        if len(data) < PAGE:
            return rows, True, None
    return rows, False, None


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

pulls_open, open_complete, err_open = gh_all(f"/repos/{REPO}/pulls?state=open")
pulls_closed, closed_complete, err_closed = gh_all(f"/repos/{REPO}/pulls?state=closed&sort=updated&direction=desc")
issues, issues_complete, err_issues = gh_all(f"/repos/{REPO}/issues?state=open")
all_pulls = (pulls_open or []) + (pulls_closed or [])
for name, complete, err in (("open PRs", open_complete, err_open), ("closed PRs", closed_complete, err_closed),
                            ("open issues", issues_complete, err_issues)):
    if not complete:
        st.warning(f"PARTIAL: the {name} could not all be read ({err or 'too many pages'}); "
                   "statuses that depend on them show UNKNOWN.")

# --- Needs you -------------------------------------------------------------
st.header("Needs your attention")
if pulls_open is None:
    st.warning(f"UNKNOWN: could not read open PRs ({err_open}).")
else:
    ready = [p for p in pulls_open if not p.get("draft")]
    if not ready:
        st.info("No open, non-draft pull requests found." if open_complete else "UNKNOWN: open PRs were only partly read.")
    for pr in ready:
        number, sha = pr["number"], pr["head"]["sha"]
        comments, comments_complete, _ = gh_all(f"/repos/{REPO}/issues/{number}/comments")
        runs, err_r = gh(f"/repos/{REPO}/commits/{sha}/check-runs?per_page={PAGE}")
        partial = not comments_complete
        review = None if partial else review_for_head(comments, sha)
        ci = ci_state(None if err_r or runs is None else runs.get("check_runs", []),
                      None if runs is None else runs.get("total_count"))
        action = "Check reviews (comments could not be fully read)" if partial else next_action(review, ci)
        if review:
            source = "automated, verified" if review["kind"] == "automated" else "manual, source not verified"
            verdict = f"[{review['verdict']}]({review['url']}) on `{sha[:7]}` ({source})"
        else:
            verdict = f"none on current commit `{sha[:7]}`"
        tone = st.success if action.startswith("Ready") else st.info if action.startswith("Needs") else st.warning
        tone(f"**[PR #{number}]({pr['html_url']}) {pr['title']}**  \n"
             f"Next: **{action}** · Review: {verdict} · Tests: {ci}")
    st.caption("A PR shows as ready only with a verified automated PASS on its exact current commit and a "
               "successful `unit-tests` check. Merging is always your decision.")

# --- Build steps ---------------------------------------------------------
st.header("MarginX build steps")
steps = parse_build_steps(raw_text("docs/MVP_SPEC.md"))
if not steps:
    st.warning("UNKNOWN: could not read the build order from docs/MVP_SPEC.md on main.")
elif pulls_open is None or pulls_closed is None:
    st.warning("UNKNOWN: could not read pull requests to work out step status.")
else:
    merged = 0
    for step in steps:
        status, pr = step_status(step["number"], all_pulls, complete=open_complete and closed_complete)
        merged += status == UNIT_STEP_LABEL
        link = f" · [PR #{pr['number']}]({pr['html_url']})" if pr else ""
        st.markdown(f"{STATUS_ICON[status]} **Step {step['number']}: {step['title']}** · {status}{link}")
    st.progress(merged / len(steps), text=f"{merged} of {len(steps)} step PRs merged (completion not verified)")
    st.caption("This counts merged PRs titled “MarginX step N: …”. A merged PR is not proof the step's "
               "acceptance criteria are met; check the PR's review and tests.")

# --- This week's checklist -------------------------------------------------
weekly = None if issues is None else latest_weekly_checklist(issues)
st.header("This week's checklist")
if issues is None:
    st.warning(f"UNKNOWN: could not read issues ({err_issues}).")
elif weekly is None:
    st.info("No open weekly checklist issue found." if issues_complete else "UNKNOWN: issues were only partly read.")
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
cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
recent, merged_state = recent_merges(pulls_closed or [], cutoff, closed_complete)
if pulls_closed is None:
    st.warning(f"UNKNOWN: could not read merged PRs ({err_closed}).")
elif merged_state == "PARTIAL":
    st.warning("PARTIAL: not every closed PR could be read, so this list may be missing recent merges.")
elif merged_state == "NONE":
    st.info("Nothing merged in the last 7 days.")
for pr in recent[:10]:
    st.markdown(f"- {when(pr['merged_at'])} · [PR #{pr['number']}]({pr['html_url']}) {pr['title']}")
if len(recent) > 10:
    with st.expander(f"{len(recent) - 10} more"):
        for pr in recent[10:]:
            st.markdown(f"- {when(pr['merged_at'])} · [PR #{pr['number']}]({pr['html_url']}) {pr['title']}")
