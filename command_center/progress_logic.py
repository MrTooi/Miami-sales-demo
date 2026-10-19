"""Pure helpers for the MarginX Progress page (no network, no Streamlit).

Every status comes from GitHub state: ticked checklist boxes, merged or open
PRs, posted review verdicts, CI conclusions. Nothing is estimated or guessed;
missing evidence shows as UNKNOWN or NOT STARTED.
"""
from __future__ import annotations

import re

CHECKBOX = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*\S)\s*$")
HEADING = re.compile(r"^##\s+(.*\S)\s*$")
BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*\s*$")
# Matches both "**Verdict:** FAIL" and "**Verdict: FAIL — ...**". Only the first
# verdict in a comment counts, so quoted examples further down are ignored.
VERDICT = re.compile(r"\*\*Verdict:(?:\*\*)?\s*\**\s*(PASS WITH WARNINGS|PASS|FAIL)\b")
STEP_TITLE = re.compile(r"^marginx step (\d+)\b", re.IGNORECASE)
BUILD_STEP = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*")


def parse_checklist(markdown: str | None) -> list[dict]:
    """Group `- [ ]` / `- [x]` items under their `##` section and bold sub-heading."""
    groups: list[dict] = []
    section, sub = "", ""
    for line in (markdown or "").splitlines():
        if m := HEADING.match(line):
            section, sub = m.group(1), ""
            continue
        if m := BOLD_LINE.match(line.strip()):
            sub = m.group(1)
            continue
        if m := CHECKBOX.match(line):
            title = f"{section} — {sub}" if sub else section
            if not groups or groups[-1]["title"] != title:
                groups.append({"section": section, "title": title, "items": []})
            groups[-1]["items"].append({"text": m.group(2), "done": m.group(1) in "xX"})
    return groups


def progress(items: list[dict]) -> tuple[int, int]:
    return sum(1 for i in items if i["done"]), len(items)


def latest_weekly_checklist(issues: list[dict]) -> dict | None:
    weekly = [
        i for i in issues
        if "pull_request" not in i and (i.get("title") or "").lower().startswith("weekly checklist")
    ]
    return max(weekly, key=lambda i: i.get("created_at") or "", default=None)


def parse_build_steps(spec_markdown: str | None) -> list[dict]:
    """Numbered bold items under '## Build order' in docs/MVP_SPEC.md."""
    steps, inside = [], False
    for line in (spec_markdown or "").splitlines():
        if line.startswith("## "):
            inside = line.lower().startswith("## build order")
            continue
        if inside and (m := BUILD_STEP.match(line)):
            steps.append({"number": int(m.group(1)), "title": m.group(2).rstrip(".")})
    return steps


def step_status(step_number: int, pulls: list[dict]) -> tuple[str, dict | None]:
    """Build PRs are titled 'MarginX step N: ...'. Merged wins over open; closed-unmerged is ignored."""
    matches = [p for p in pulls if (m := STEP_TITLE.match(p.get("title") or "")) and int(m.group(1)) == step_number]
    merged = [p for p in matches if p.get("merged_at")]
    if merged:
        return "DONE", max(merged, key=lambda p: p["merged_at"])
    open_prs = [p for p in matches if p.get("state") == "open"]
    if open_prs:
        return "IN PROGRESS", open_prs[0]
    return "NOT STARTED", None


def latest_review(comments: list[dict]) -> dict | None:
    """Most recent comment carrying a review verdict (manual or automated)."""
    found = None
    for c in sorted(comments, key=lambda c: c.get("created_at") or ""):
        body = c.get("body") or ""
        if "**Status: REVIEW INCOMPLETE" in body:
            found = {"verdict": "INCOMPLETE", "url": c.get("html_url"), "at": c.get("created_at")}
        elif m := VERDICT.search(body):
            found = {"verdict": m.group(1), "url": c.get("html_url"), "at": c.get("created_at")}
    return found


def ci_state(check_runs: list[dict] | None) -> str:
    if check_runs is None:
        return "UNKNOWN"
    if not check_runs:
        return "NO CHECKS"
    if any(r.get("status") != "completed" for r in check_runs):
        return "RUNNING"
    bad = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
    if any(r.get("conclusion") in bad for r in check_runs):
        return "FAILING"
    return "PASSING"


def next_action(review: dict | None, ci: str, reviewed_after_head: bool) -> str:
    """Plain-language next step for an open PR."""
    if ci == "FAILING":
        return "Claude: fix failing tests"
    if review is None or not reviewed_after_head:
        return "Needs ChatGPT review"
    if review["verdict"] in ("FAIL", "INCOMPLETE"):
        return "Claude: fix review findings"
    if ci != "PASSING":
        return "Waiting for tests"
    return "Ready for your merge decision"
