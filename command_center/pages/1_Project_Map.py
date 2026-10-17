"""Live project map for the private Ledger Command Center.

Read-only owner tooling. GitHub is the source of truth; this page never mutates
repository, workflow, product, financial, or customer state.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

REPO = "MrTooi/Miami-sales-demo"
API = "https://api.github.com"
ET = ZoneInfo("America/New_York")
OPERATOR_WORKFLOW = "agent-operator.yml"
EVIDENCE_PREFIX = "agent-final-readiness-evidence-"
SCHEDULE_GRACE_MINUTES = 20
PROJECT_ISSUES = [
    (11, "AI Team Readiness Gate"),
    (69, "Final A → B → C Readiness"),
    (74, "Commercial Reality Gate"),
    (75, "Real Business Discovery Gate"),
    (79, "Private Command Center"),
    (81, "Demo Readiness"),
]

st.set_page_config(page_title="Ledger Project Map", page_icon="◈", layout="wide")


def _token() -> str | None:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("GITHUB_TOKEN")
    except Exception:
        return None


@st.cache_data(ttl=20, show_spinner=False)
def gh(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ledger-command-center",
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


@st.cache_data(ttl=30, show_spinner=False)
def raw_text(path: str, ref: str = "main") -> str | None:
    try:
        with urllib.request.urlopen(
            f"https://raw.githubusercontent.com/{REPO}/{ref}/{path}", timeout=10
        ) as response:
            return response.read().decode("utf-8")
    except Exception:
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def short_sha(value: str | None) -> str:
    return value[:8] if value else "UNKNOWN"


def schedule_minutes() -> list[int]:
    text = raw_text(".github/workflows/agent-operator.yml") or ""
    match = re.search(r"cron:\s*['\"]([0-9,]+)\s+\*\s+\*\s+\*\s+\*['\"]", text)
    if not match:
        return [17, 47]
    values = []
    for part in match.group(1).split(","):
        try:
            value = int(part)
        except ValueError:
            continue
        if 0 <= value <= 59:
            values.append(value)
    return sorted(set(values)) or [17, 47]


def previous_operator_slot(now: datetime | None = None) -> datetime:
    now = now or datetime.now(ET)
    candidates = []
    for hour_offset in range(-2, 1):
        base = (now + timedelta(hours=hour_offset)).replace(second=0, microsecond=0)
        for minute in schedule_minutes():
            candidate = base.replace(minute=minute)
            if candidate <= now:
                candidates.append(candidate)
    return max(candidates)


def schedule_state(latest_run: dict | None, now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(ET)
    expected = previous_operator_slot(now)
    created = parse_dt((latest_run or {}).get("created_at"))
    if created and created.astimezone(ET) >= expected:
        return "ON TRACK", f"Latest schedule event arrived for/after the {expected.strftime('%I:%M %p').lstrip('0')} slot."
    overdue = now - expected
    if overdue > timedelta(minutes=SCHEDULE_GRACE_MINUTES):
        return "LATE / CHECK", f"No schedule event visible for the {expected.strftime('%I:%M %p').lstrip('0')} slot after {SCHEDULE_GRACE_MINUTES}m grace."
    return "WAITING", f"Within the {SCHEDULE_GRACE_MINUTES}m GitHub delivery grace for the {expected.strftime('%I:%M %p').lstrip('0')} slot."


def issue_row(number: int, label: str):
    data, err = gh(f"/repos/{REPO}/issues/{number}")
    if err or not data:
        st.markdown(f"**{label}** · `UNKNOWN` · Issue #{number}")
        st.caption("GitHub state unavailable; no progress inferred.")
        return
    state = str(data.get("state", "unknown")).upper()
    title = data.get("title") or label
    updated = parse_dt(data.get("updated_at"))
    updated_text = updated.astimezone(ET).strftime("%b %d, %I:%M %p ET") if updated else "unknown"
    st.markdown(f"**{label}** · `{state}` · [{title}]({data.get('html_url')})")
    st.caption(f"Issue #{number} · updated {updated_text}. OPEN/CLOSED is shown as repository state, not a guessed completion percentage.")


branch, branch_err = gh(f"/repos/{REPO}/branches/main")
main_sha = ((branch or {}).get("commit") or {}).get("sha")
runs, runs_err = gh(f"/repos/{REPO}/actions/runs?branch=main&per_page=40")
all_runs = (runs or {}).get("workflow_runs", [])
operator_runs = [
    run for run in all_runs
    if run.get("event") == "schedule" and run.get("path", "").endswith(OPERATOR_WORKFLOW)
]
latest_operator = operator_runs[0] if operator_runs else None
pulls, pulls_err = gh(f"/repos/{REPO}/pulls?state=open&per_page=50")

st.title("Ledger Project Map")
st.caption("Live owner view. GitHub-derived facts only; unknown data stays UNKNOWN. Refresh the page for an immediate pull; the main Command Center auto-refreshes every 30 seconds.")

if any([branch_err, runs_err, pulls_err]):
    st.warning("Some live GitHub data is unavailable. This page will not guess missing status.")

state, state_note = schedule_state(latest_operator)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current main", short_sha(main_sha))
c2.metric("Scheduler", state)
c3.metric("Open PRs", len(pulls or []))
c4.metric("Latest schedule", (latest_operator or {}).get("conclusion") or (latest_operator or {}).get("status") or "UNKNOWN")
st.caption(state_note)

st.divider()
st.subheader("Project gates and active work")
for issue_number, label in PROJECT_ISSUES:
    issue_row(issue_number, label)

st.divider()
st.subheader("Readiness evidence")
verified = []
for run in operator_runs[:12]:
    if run.get("run_attempt") != 1 or run.get("conclusion") != "success":
        continue
    artifacts, err = gh(f"/repos/{REPO}/actions/runs/{run['id']}/artifacts?per_page=100")
    if err or not artifacts:
        continue
    expected_name = f"{EVIDENCE_PREFIX}{run['id']}"
    exact = [a for a in artifacts.get("artifacts", []) if a.get("name") == expected_name and not a.get("expired")]
    if len(exact) == 1:
        verified.append(run)

if verified:
    for index, run in enumerate(verified[:3], start=1):
        suite = ["A", "B", "C"][index - 1]
        st.markdown(
            f"**Suite {suite}: VERIFIED EVIDENCE** · [schedule run #{run.get('run_number')}]({run.get('html_url')}) · "
            f"`{short_sha(run.get('head_sha'))}`"
        )
else:
    st.info("No successful A/B/C readiness evidence is currently verified. Failed or manual runs are intentionally not shown as passes.")

st.divider()
st.subheader("Current pull requests")
if pulls:
    for pr in pulls[:12]:
        st.markdown(f"**PR #{pr['number']}** · [{pr['title']}]({pr['html_url']})")
        st.caption(f"{pr.get('head', {}).get('ref', 'unknown')} → {pr.get('base', {}).get('ref', 'main')}")
else:
    st.info("No open pull requests visible.")

st.divider()
st.subheader("Non-negotiable status")
st.warning("Ledger product implementation remains PAUSED behind the readiness gate. This internal page does not grant approval, trigger workflows, merge code, deploy, or change financial/customer data.")
