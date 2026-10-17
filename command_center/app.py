"""Private owner dashboard for Ledger project operations.

Internal tooling only. This app is intentionally read-only: it displays GitHub-derived
project/readiness state and never mutates repository, workflow, product, or customer data.
"""
from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

# `streamlit run command_center/app.py` puts only this folder on sys.path; add the
# repository root so the shared pure helpers import the same way tests import them.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from command_center.status_logic import latest_run_display, next_slot, parse_cron_minutes  # noqa: E402

REPO = "MrTooi/Miami-sales-demo"
API = "https://api.github.com"
ET = ZoneInfo("America/New_York")
OPERATOR_WORKFLOW = "agent-operator.yml"
EVIDENCE_PREFIX = "agent-final-readiness-evidence-"
AUTO_REFRESH_SECONDS = 30

st.set_page_config(
    page_title="Ledger Command Center",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

components.html(
    f"""
    <script>
      setTimeout(function() {{ window.parent.location.reload(); }}, {AUTO_REFRESH_SECONDS * 1000});
    </script>
    """,
    height=0,
    width=0,
)

st.markdown(
    """
    <style>
      .stApp { background: #07090d; color: #eef3ff; }
      [data-testid="stHeader"] { background: transparent; }
      .block-container { max-width: 1500px; padding-top: 1.8rem; padding-bottom: 4rem; }
      .cc-kicker { color:#6ee7ff; letter-spacing:.14em; font-size:.75rem; font-weight:700; }
      .cc-title { font-size:2.15rem; font-weight:800; line-height:1.05; margin:.2rem 0 .35rem; }
      .cc-sub { color:#94a3b8; margin-bottom:1.3rem; }
      .cc-card { border:1px solid #1d2a3b; background:linear-gradient(180deg,#0c1119,#090d13);
                 border-radius:16px; padding:16px 18px; min-height:118px; }
      .cc-label { color:#7f8da3; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; }
      .cc-value { font-size:1.45rem; font-weight:760; margin-top:.35rem; }
      .cc-note { color:#8fa0b5; font-size:.82rem; margin-top:.35rem; }
      .ok { color:#6ef7b7; } .warn { color:#ffd166; } .bad { color:#ff7b8b; } .info { color:#75c8ff; }
      hr { border-color:#17202d !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


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
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        return None, f"GitHub API {exc.code}: {detail or exc.reason}"
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


def short_sha(value: str | None) -> str:
    return value[:8] if value else "UNKNOWN"


def dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def age(value: str | None) -> str:
    stamp = dt(value)
    if not stamp:
        return "unknown"
    seconds = max(0, int((datetime.now(timezone.utc) - stamp).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def operator_minutes() -> list[int] | None:
    # Every cron line counts; any unrecognised shape yields UNKNOWN (None).
    return parse_cron_minutes(raw_text(".github/workflows/agent-operator.yml"))


def next_operator_slot(now: datetime | None = None) -> datetime | None:
    return next_slot(now or datetime.now(ET), operator_minutes())


def card(label: str, value: str, note: str, tone: str = "info"):
    safe_label = html.escape(str(label))
    safe_value = html.escape(str(value))
    safe_note = html.escape(str(note))
    st.markdown(
        f'<div class="cc-card"><div class="cc-label">{safe_label}</div>'
        f'<div class="cc-value {tone}">{safe_value}</div><div class="cc-note">{safe_note}</div></div>',
        unsafe_allow_html=True,
    )


fetched_at = datetime.now(ET)
branch, branch_err = gh(f"/repos/{REPO}/branches/main")
main_sha = ((branch or {}).get("commit") or {}).get("sha")

runs, runs_err = gh(f"/repos/{REPO}/actions/runs?branch=main&per_page=60")
all_runs = (runs or {}).get("workflow_runs", [])
schedule_runs = [
    run for run in all_runs
    if run.get("event") == "schedule" and run.get("path", "").endswith(OPERATOR_WORKFLOW)
]
latest_operator = schedule_runs[0] if schedule_runs else None

latest_ci = next(
    (
        run for run in all_runs
        if run.get("path") == ".github/workflows/tests.yml" and run.get("head_sha") == main_sha
    ),
    None,
)

pulls, pulls_err = gh(f"/repos/{REPO}/pulls?state=open&per_page=20")
issues, issues_err = gh(f"/repos/{REPO}/issues?state=open&per_page=50")
open_issues = [issue for issue in (issues or []) if "pull_request" not in issue]

# Artifact-name presence is useful progress telemetry, but is NOT authoritative readiness.
# The final readiness workflow validates metadata, suite ordering and hashes more deeply.
evidence_presence_runs = []
evidence_fetch_errors = []
for run in schedule_runs[:12]:
    if run.get("run_attempt") != 1 or run.get("conclusion") != "success":
        continue
    artifacts, err = gh(f"/repos/{REPO}/actions/runs/{run['id']}/artifacts?per_page=100")
    if err or not artifacts:
        evidence_fetch_errors.append(run.get("id"))
        continue
    expected = f"{EVIDENCE_PREFIX}{run['id']}"
    matches = [
        artifact for artifact in artifacts.get("artifacts", [])
        if artifact.get("name") == expected and not artifact.get("expired")
    ]
    if len(matches) == 1:
        evidence_presence_runs.append(run)

st.markdown('<div class="cc-kicker">LEDGER / OWNER OPERATIONS</div>', unsafe_allow_html=True)
st.markdown('<div class="cc-title">Command Center</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="cc-sub">Live read-only project view · auto-refresh {AUTO_REFRESH_SECONDS}s · data fetched {fetched_at.strftime("%I:%M:%S %p ET").lstrip("0")}</div>',
    unsafe_allow_html=True,
)

if any([branch_err, runs_err, pulls_err, issues_err]) or evidence_fetch_errors:
    st.warning("Some GitHub evidence is unavailable. Affected status is shown as CHECK/UNKNOWN rather than guessed.")

cols = st.columns(4)
with cols[0]:
    if branch_err or not main_sha:
        card("Main / CI", "UNKNOWN", "Current main could not be verified.", "warn")
    elif latest_ci and latest_ci.get("conclusion") == "success":
        card("Main / CI", "HEALTHY", f"main {short_sha(main_sha)} · CI success on this exact SHA", "ok")
    elif latest_ci:
        ci_state = latest_ci.get("conclusion") or latest_ci.get("status") or "unknown"
        card("Main / CI", "CHECK", f"main {short_sha(main_sha)} · CI {ci_state} on this exact SHA", "warn")
    else:
        card("Main / CI", "UNKNOWN", f"main {short_sha(main_sha)} · no CI result visible for this exact SHA", "warn")

with cols[1]:
    if runs_err or evidence_fetch_errors:
        card("Readiness", "UNKNOWN", "Evidence retrieval is incomplete; no pass count inferred.", "warn")
    else:
        card(
            "Readiness",
            "VALIDATION PENDING",
            f"{len(evidence_presence_runs)} candidate evidence artifact(s) present; authoritative A/B/C verification remains in the readiness workflow.",
            "warn",
        )

with cols[2]:
    next_slot = next_operator_slot()
    minutes = operator_minutes()
    if next_slot and minutes:
        card(
            "Next Operator Slot",
            next_slot.strftime("%I:%M %p ET").lstrip("0"),
            "Schedule minutes: " + ", ".join(f":{minute:02d}" for minute in minutes),
            "info",
        )
    else:
        card("Next Operator Slot", "UNKNOWN", "Current cron could not be parsed from main; no fallback time is invented.", "warn")

with cols[3]:
    run_value, run_tone, run_note = latest_run_display(latest_operator)
    if latest_operator:
        run_note = (
            f"#{latest_operator.get('run_number')} · {age(latest_operator.get('created_at'))} · "
            f"SHA {short_sha(latest_operator.get('head_sha'))} · {run_note}"
        )
    card("Latest Scheduled Run", run_value, run_note, run_tone)

st.markdown("---")
st.subheader("AI Team Readiness")
st.info(
    "The Command Center does not self-certify A/B/C. Artifact presence is shown as progress telemetry only. "
    "A suite becomes truly verified only when the authoritative readiness validation accepts its metadata, hashes, suite order, score and provenance."
)
if evidence_fetch_errors:
    st.warning("Candidate evidence count is UNKNOWN because at least one artifact request failed.")
elif evidence_presence_runs:
    for run in evidence_presence_runs[:3]:
        st.markdown(
            f"**EVIDENCE PRESENT — UNVERIFIED HERE** · [scheduled run #{run.get('run_number')}]({run.get('html_url')}) · `{short_sha(run.get('head_sha'))}`"
        )
else:
    st.caption("No successful schedule-originated candidate evidence artifact is currently visible.")

st.markdown("---")
left, right = st.columns([1.15, 0.85])
with left:
    st.subheader("Current Work")
    if pulls:
        for pr in pulls[:10]:
            title = html.escape(str(pr.get("title", "Untitled")))
            st.markdown(f"**PR #{pr['number']}** · {title}")
            st.caption(
                f"{pr.get('head', {}).get('ref', 'unknown')} → {pr.get('base', {}).get('ref', 'main')} · updated {age(pr.get('updated_at'))}"
            )
    else:
        st.info("No open pull requests visible.")

with right:
    st.subheader("Human Attention")
    attention = []
    for issue in open_issues:
        title = str(issue.get("title", ""))
        if any(word in title.lower() for word in ["readiness", "approval", "gate", "block", "risk", "demo"]):
            attention.append(issue)
    if attention:
        for issue in attention[:10]:
            st.markdown(f"**#{issue['number']}** · {html.escape(str(issue.get('title', 'Untitled')))}")
            st.caption(f"updated {age(issue.get('updated_at'))}")
    else:
        st.info("No obvious approval/blocker issue detected from the available issue titles.")

st.markdown("---")
st.subheader("Recent System Activity")
if all_runs:
    for run in all_runs[:12]:
        event = html.escape(str(run.get("event", "unknown")))
        state = html.escape(str(run.get("conclusion") or run.get("status") or "unknown"))
        name = html.escape(str(run.get("name", "Workflow")))
        st.markdown(
            f"**{name}** · `{event}` · **{state}** · `{short_sha(run.get('head_sha'))}` · {age(run.get('created_at'))}"
        )
else:
    st.info("No Actions activity available.")

st.markdown("---")
st.subheader("Guardrails")
g1, g2, g3, g4 = st.columns(4)
with g1:
    card("Product Work", "PAUSED", "Human approval is still required after the readiness gate.", "warn")
with g2:
    card("Command Center", "READ ONLY", "No merge, deploy, rerun, delete or financial actions.", "ok")
with g3:
    card("Customer Data", "NONE", "Repository/project metadata only.", "ok")
with g4:
    card("Unknown Data", "VISIBLE", "Missing evidence is never converted into a green status.", "ok")

st.caption("Use the Project Map page for live gate/issues status, scheduler late/missed visibility, PRs and evidence-run links.")
