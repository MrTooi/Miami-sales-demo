"""Live project map for the private Ledger Command Center.

Read-only owner tooling. GitHub is the source of truth; this page never mutates
repository, workflow, product, financial, or customer state.
"""
from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

# Pages run with only command_center/ on sys.path; add the repository root so the
# shared pure helpers import the same way tests import them.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from command_center.status_logic import (  # noqa: E402
    classify_schedule_slot,
    latest_run_display,
    parse_cron_minutes,
    previous_slot,
)

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


def schedule_minutes() -> list[int] | None:
    # Every cron line counts; any unrecognised shape yields UNKNOWN (None).
    return parse_cron_minutes(raw_text(".github/workflows/agent-operator.yml"))


def previous_operator_slot(now: datetime | None = None) -> datetime | None:
    return previous_slot(now or datetime.now(ET), schedule_minutes())


def issue_row(number: int, label: str):
    data, err = gh(f"/repos/{REPO}/issues/{number}")
    if err or not data:
        st.markdown(f"**{html.escape(label)}** · `UNKNOWN` · Issue #{number}")
        st.caption("GitHub state unavailable; no progress inferred.")
        return
    state = str(data.get("state", "unknown")).upper()
    title = html.escape(str(data.get("title") or label))
    updated = parse_dt(data.get("updated_at"))
    updated_text = updated.astimezone(ET).strftime("%b %d, %I:%M %p ET") if updated else "unknown"
    st.markdown(f"**{html.escape(label)}** · `{state}` · [{title}]({data.get('html_url')})")
    st.caption(f"Issue #{number} · updated {updated_text}. OPEN/CLOSED is repository state, not a guessed completion percentage.")


fetched_at = datetime.now(ET)
branch, branch_err = gh(f"/repos/{REPO}/branches/main")
main_sha = ((branch or {}).get("commit") or {}).get("sha")
runs, runs_err = gh(f"/repos/{REPO}/actions/runs?branch=main&per_page=60")
all_runs = (runs or {}).get("workflow_runs", [])
operator_runs = [
    run for run in all_runs
    if run.get("event") == "schedule" and run.get("path", "").endswith(OPERATOR_WORKFLOW)
]
latest_operator = operator_runs[0] if operator_runs else None
pulls, pulls_err = gh(f"/repos/{REPO}/pulls?state=open&per_page=50")

st.title("Ledger Project Map")
st.caption(
    f"Live owner view · data fetched {fetched_at.strftime('%I:%M:%S %p ET').lstrip('0')} · GitHub-derived facts only; unknown data stays UNKNOWN."
)

if any([branch_err, runs_err, pulls_err]):
    st.warning("Some live GitHub data is unavailable. This page will not guess missing status.")

expected_slot = previous_operator_slot(fetched_at)
state, state_note = classify_schedule_slot(
    now=fetched_at,
    expected_slot=expected_slot,
    latest_run=latest_operator,
    runs_error=bool(runs_err),
    grace_minutes=SCHEDULE_GRACE_MINUTES,
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current main", short_sha(main_sha))
c2.metric("Scheduler", state)
c3.metric("Open PRs", len(pulls or []))
latest_value, _latest_tone, latest_note = latest_run_display(latest_operator, expected_slot)
c4.metric("Latest schedule", latest_value, help=latest_note)
st.caption(state_note)

st.divider()
st.subheader("Project gates and active work")
for issue_number, label in PROJECT_ISSUES:
    issue_row(issue_number, label)

st.divider()
st.subheader("Readiness evidence telemetry")
candidate_runs = []
evidence_errors = []
for run in operator_runs[:12]:
    if run.get("run_attempt") != 1 or run.get("conclusion") != "success":
        continue
    artifacts, err = gh(f"/repos/{REPO}/actions/runs/{run['id']}/artifacts?per_page=100")
    if err or not artifacts:
        evidence_errors.append(run.get("id"))
        continue
    expected_name = f"{EVIDENCE_PREFIX}{run['id']}"
    exact = [
        artifact for artifact in artifacts.get("artifacts", [])
        if artifact.get("name") == expected_name and not artifact.get("expired")
    ]
    if len(exact) == 1:
        candidate_runs.append(run)

st.info(
    "Artifact-name presence is telemetry only. This page does not assign Suite A/B/C or claim a pass from artifact presence; the authoritative readiness workflow validates suite order, hashes, metadata, score and provenance."
)
if evidence_errors:
    st.warning("Evidence telemetry is UNKNOWN because one or more artifact requests failed.")
elif candidate_runs:
    for run in candidate_runs[:3]:
        st.markdown(
            f"**EVIDENCE PRESENT — UNVERIFIED HERE** · [schedule run #{run.get('run_number')}]({run.get('html_url')}) · `{short_sha(run.get('head_sha'))}`"
        )
else:
    st.caption("No successful schedule-originated candidate evidence artifact is currently visible.")

st.divider()
st.subheader("Current pull requests")
if pulls:
    for pr in pulls[:12]:
        title = html.escape(str(pr.get("title", "Untitled")))
        st.markdown(f"**PR #{pr['number']}** · [{title}]({pr['html_url']})")
        st.caption(f"{pr.get('head', {}).get('ref', 'unknown')} → {pr.get('base', {}).get('ref', 'main')}")
else:
    st.info("No open pull requests visible.")

st.divider()
st.subheader("Non-negotiable status")
st.warning("Ledger product implementation remains PAUSED behind the readiness gate. This internal page does not grant approval, trigger workflows, merge code, deploy, or change financial/customer data.")
