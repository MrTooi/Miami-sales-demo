"""Private owner dashboard for Ledger project operations.

Internal tooling only. This app is intentionally read-only: it displays GitHub-derived
project/readiness state and never mutates repository, workflow, product, or customer data.
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
import streamlit.components.v1 as components

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

# Auto-refresh the owner view so repository/workflow changes appear without manual reload.
# The app remains read-only; this only reloads the page in the browser.
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
      .pill {display:inline-block; padding:.22rem .55rem; border:1px solid #2a3b53; border-radius:999px;
             font-size:.72rem; margin-right:.35rem; color:#b9c7d8; background:#0d141e;}
      div[data-testid="stMetric"] {background:#0b1017;border:1px solid #1c2737;padding:12px 14px;border-radius:14px;}
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
        detail = exc.read().decode("utf-8", errors="ignore")[:500]
        return None, f"GitHub API {exc.code}: {detail or exc.reason}"
    except Exception as exc:
        return None, str(exc)


@st.cache_data(ttl=30, show_spinner=False)
def raw_text(path: str, ref: str = "main") -> str | None:
    url = f"https://raw.githubusercontent.com/{REPO}/{ref}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read().decode("utf-8")
    except Exception:
        return None


def short_sha(value: str | None) -> str:
    return value[:8] if value else "unknown"


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


def operator_minutes() -> list[int]:
    text = raw_text(".github/workflows/agent-operator.yml") or ""
    match = re.search(r"cron:\s*['\"]([0-9,]+)\s+\*\s+\*\s+\*\s+\*['\"]", text)
    if not match:
        return [17, 47]
    minutes = []
    for part in match.group(1).split(","):
        try:
            minutes.append(int(part))
        except ValueError:
            pass
    return sorted(set(m for m in minutes if 0 <= m <= 59)) or [17, 47]


def next_operator_slot(now: datetime | None = None) -> datetime:
    now = now or datetime.now(ET)
    for hour_offset in range(0, 3):
        base = (now + timedelta(hours=hour_offset)).replace(second=0, microsecond=0)
        for minute in operator_minutes():
            candidate = base.replace(minute=minute)
            if candidate > now:
                return candidate
    return (now + timedelta(hours=1)).replace(minute=operator_minutes()[0], second=0, microsecond=0)


def card(label: str, value: str, note: str, tone: str = "info"):
    st.markdown(
        f'<div class="cc-card"><div class="cc-label">{label}</div>'
        f'<div class="cc-value {tone}">{value}</div><div class="cc-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


# ---------- Gather live state ----------
branch, branch_err = gh(f"/repos/{REPO}/branches/main")
main_sha = ((branch or {}).get("commit") or {}).get("sha")

runs, runs_err = gh(f"/repos/{REPO}/actions/runs?branch=main&per_page=40")
all_runs = (runs or {}).get("workflow_runs", [])
schedule_runs = [r for r in all_runs if r.get("event") == "schedule" and r.get("path", "").endswith(OPERATOR_WORKFLOW)]
latest_operator = schedule_runs[0] if schedule_runs else None

latest_ci = next((r for r in all_runs if r.get("path") == ".github/workflows/tests.yml"), None)

pulls, pulls_err = gh(f"/repos/{REPO}/pulls?state=open&per_page=12")
issues, issues_err = gh(f"/repos/{REPO}/issues?state=open&per_page=40")
open_issues = [i for i in (issues or []) if "pull_request" not in i]

# Only a completed successful readiness carrier can have final evidence.
evidence_runs = []
for run in schedule_runs[:12]:
    if run.get("run_attempt") != 1 or run.get("conclusion") != "success":
        continue
    artifacts, err = gh(f"/repos/{REPO}/actions/runs/{run['id']}/artifacts?per_page=100")
    if err or not artifacts:
        continue
    names = [a.get("name", "") for a in artifacts.get("artifacts", []) if not a.get("expired")]
    if any(name == f"{EVIDENCE_PREFIX}{run['id']}" for name in names):
        evidence_runs.append(run)

evidence_count = min(len(evidence_runs), 3)
phase_labels = ["Suite A", "Suite B", "Suite C"]

# ---------- Header ----------
st.markdown('<div class="cc-kicker">LEDGER / OWNER OPERATIONS</div>', unsafe_allow_html=True)
st.markdown('<div class="cc-title">Command Center</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="cc-sub">Live read-only view of readiness, scheduling, CI, work in progress, blockers and evidence. Auto-refreshes every {AUTO_REFRESH_SECONDS}s.</div>',
    unsafe_allow_html=True,
)

if any([branch_err, runs_err, pulls_err, issues_err]):
    st.warning("Some live GitHub data is unavailable. Unknown values are shown instead of guessed values.")

# ---------- Top status ----------
cols = st.columns(4)
with cols[0]:
    ci_ok = bool(latest_ci and latest_ci.get("conclusion") == "success")
    card("Main / CI", "HEALTHY" if ci_ok else "CHECK", f"main {short_sha(main_sha)} · CI {latest_ci.get('status','unknown') if latest_ci else 'unknown'}", "ok" if ci_ok else "warn")
with cols[1]:
    if evidence_count >= 3:
        card("Readiness", "TECHNICAL GATE", "A/B/C evidence complete · human approval still required", "ok")
    else:
        card("Readiness", f"{evidence_count}/3 PASSED", f"Next: {phase_labels[evidence_count]}", "warn" if evidence_count == 0 else "info")
with cols[2]:
    nxt = next_operator_slot()
    card("Next Operator Slot", nxt.strftime("%I:%M %p ET").lstrip("0"), f"Schedule minutes: {', '.join(f':{m:02d}' for m in operator_minutes())}", "info")
with cols[3]:
    if latest_operator:
        conclusion = latest_operator.get("conclusion") or latest_operator.get("status", "unknown")
        card("Latest Scheduled Run", conclusion.upper(), f"#{latest_operator.get('run_number')} · {age(latest_operator.get('created_at'))} · SHA {short_sha(latest_operator.get('head_sha'))}", "ok" if conclusion == "success" else "warn")
    else:
        card("Latest Scheduled Run", "UNKNOWN", "No Operator schedule run visible in the current API window", "warn")

st.markdown("---")

# ---------- A/B/C ----------
st.subheader("AI Team Readiness")
progress_cols = st.columns(3)
for idx, label in enumerate(phase_labels):
    with progress_cols[idx]:
        if idx < evidence_count:
            card(label, "VERIFIED PASS", "Valid final-readiness evidence artifact found on a successful schedule-originated run.", "ok")
        elif idx == evidence_count:
            state = "IN PROGRESS / NEXT" if latest_operator else "WAITING"
            card(label, state, "Must originate from a genuine GitHub schedule event; manual runs never count.", "warn")
        else:
            card(label, "LOCKED", "Previous suite must pass first.", "info")

st.caption("Dashboard progression is deliberately conservative: a suite counts only when a successful schedule-originated carrier run has a non-expired final readiness evidence artifact.")

# ---------- Work / approvals ----------
st.markdown("---")
left, right = st.columns([1.15, 0.85])
with left:
    st.subheader("Current Work")
    if pulls:
        for pr in pulls[:8]:
            st.markdown(f"**PR #{pr['number']}** · {pr['title']}  ")
            st.caption(f"{pr.get('head',{}).get('ref','')} → {pr.get('base',{}).get('ref','main')} · updated {age(pr.get('updated_at'))}")
    else:
        st.info("No open pull requests visible.")

with right:
    st.subheader("Human Attention")
    attention = []
    for issue in open_issues:
        title = issue.get("title", "")
        if any(word in title.lower() for word in ["readiness", "approval", "gate", "block", "risk"]):
            attention.append(issue)
    if attention:
        for issue in attention[:8]:
            st.markdown(f"**#{issue['number']}** · {issue['title']}")
            st.caption(f"updated {age(issue.get('updated_at'))}")
    else:
        st.success("No obvious approval/blocker issue detected from open issue titles.")

# ---------- Activity ----------
st.markdown("---")
st.subheader("Recent System Activity")
if all_runs:
    for run in all_runs[:12]:
        event = run.get("event", "unknown")
        conclusion = run.get("conclusion") or run.get("status", "unknown")
        icon = "✓" if conclusion == "success" else ("•" if conclusion in {"queued", "in_progress"} else "!")
        st.markdown(f"`{icon}` **{run.get('name','Workflow')}** · {event} · **{conclusion}** · `{short_sha(run.get('head_sha'))}` · {age(run.get('created_at'))}")
else:
    st.info("No Actions activity available.")

# ---------- Guardrails ----------
st.markdown("---")
st.subheader("Guardrails")
g1, g2, g3, g4 = st.columns(4)
with g1:
    card("Product Work", "PAUSED", "Remains behind the readiness gate.", "warn")
with g2:
    card("Command Center", "READ ONLY", "No merge, deploy, delete or financial actions.", "ok")
with g3:
    card("Customer Data", "NONE", "Dashboard reads repository/project metadata only.", "ok")
with g4:
    card("Unknown Data", "VISIBLE", "Missing evidence is shown as unknown, never inferred.", "ok")

st.caption(f"Ledger Command Center · Internal owner tooling · GitHub is the primary source of operational truth · live refresh {AUTO_REFRESH_SECONDS}s")
