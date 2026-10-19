"""Pure helpers for the MarginX Progress page (no network, no Streamlit).

Every status comes from GitHub state: ticked checklist boxes, merged or open
PRs, posted review comments, CI check runs. Nothing is estimated or guessed;
missing or ambiguous evidence shows as UNKNOWN / NEEDS REVIEW, never green.
"""
from __future__ import annotations

import re

CHECKBOX = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*\S)\s*$")
HEADING = re.compile(r"^##\s+(.*\S)\s*$")
BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*\s*$")
STEP_TITLE = re.compile(r"^marginx step (\d+):", re.IGNORECASE)
BUILD_STEP = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*")

# Automated D-004 reviews are posted by the workflow's bot account with a fixed shape.
AUTOMATED_AUTHOR = "github-actions[bot]"
AUTOMATED_HEADER = "## Automated ChatGPT review (D-004)"
AUTOMATED_SHA = re.compile(r"Reviewed commit: `([0-9a-f]{7,40})`")
AUTOMATED_QUALIFYING = re.compile(r"^\*\*Status: qualifying automated review — (PASS WITH WARNINGS|PASS|FAIL)\.\*\*", re.MULTILINE)
AUTOMATED_INCOMPLETE = "**Status: REVIEW INCOMPLETE"
# Manual reviews (ChatGPT via the owner's account) open with a heading naming the reviewed commit.
MANUAL_HEADER = re.compile(r"^## Independent\b[^\n`]*\bChatGPT\b[^\n`]*\breview\b[^\n`]*`([0-9a-f]{7,40})`", re.IGNORECASE)
# The verdict must open the first non-empty line under the heading; quotes, examples
# and later prose are never read as the verdict.
MANUAL_VERDICT = re.compile(r"^\*\*Verdict:(?:\*\*)?\s*\**\s*(PASS WITH WARNINGS|PASS|FAIL)\b")

REQUIRED_CHECKS = ("unit-tests",)
UNIT_STEP_LABEL = "STEP PR MERGED — completion unverified"


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


def step_status(step_number: int, pulls: list[dict], complete: bool = True) -> tuple[str, dict | None]:
    """Build PRs are titled 'MarginX step N: ...'.

    A merged step PR proves only that a PR was merged, not that the step's
    acceptance criteria were met, so it is never reported as DONE. When the PR
    list could not be read completely, an absent step PR is UNKNOWN, not NOT STARTED.
    """
    matches = [p for p in pulls if (m := STEP_TITLE.match(p.get("title") or "")) and int(m.group(1)) == step_number]
    merged = [p for p in matches if p.get("merged_at")]
    if merged:
        return UNIT_STEP_LABEL, max(merged, key=lambda p: p["merged_at"])
    open_prs = [p for p in matches if p.get("state") == "open"]
    if open_prs:
        return "IN PROGRESS", open_prs[0]
    return ("NOT STARTED" if complete else "UNKNOWN"), None


def recent_merges(pulls: list[dict], cutoff_iso: str, complete: bool) -> tuple[list[dict], str]:
    """Merged PRs since the cutoff, newest first, plus OK / NONE / PARTIAL.

    With an incomplete list the answer is PARTIAL even when nothing was found:
    missing pages may hold recent merges.
    """
    rows = sorted((p for p in pulls if p.get("merged_at") and p["merged_at"] >= cutoff_iso),
                  key=lambda p: p["merged_at"], reverse=True)
    if not complete:
        return rows, "PARTIAL"
    return rows, "OK" if rows else "NONE"


def _same_commit(reviewed: str, head_sha: str, *, full: bool) -> bool:
    """Automated reviews must name the full SHA; manual ones may use a 7+ character prefix."""
    reviewed, head_sha = reviewed.lower(), head_sha.lower()
    if full:
        return len(reviewed) == 40 and reviewed == head_sha
    return len(reviewed) >= 7 and head_sha.startswith(reviewed)


def _normalized(body: str | None) -> str:
    return (body or "").replace("﻿", "").strip()


def _header_verdict(body: str) -> str | None:
    """The verdict opening the first non-empty line after the heading, else None."""
    lines = [line.strip() for line in body.splitlines()[1:] if line.strip()]
    if not lines:
        return None
    m = MANUAL_VERDICT.match(lines[0])
    return m.group(1) if m else None


def classify_review(comment: dict) -> dict | None:
    """Recognise a review comment and the commit it covers, or return None.

    kind "automated": posted by the workflow bot in the D-004 shape (source verified).
    kind "manual": an "Independent ChatGPT review" heading naming a commit; the
    author can't be verified (it is posted through the owner's account).
    """
    body = _normalized(comment.get("body"))
    if not body:
        return None
    author = ((comment.get("user") or {}).get("login")) or ""
    base = {"url": comment.get("html_url"), "at": comment.get("created_at")}
    if body.startswith(AUTOMATED_HEADER):
        if author != AUTOMATED_AUTHOR:
            return None  # looks automated but wasn't posted by the workflow
        # The workflow writes its metadata and status above the first `---`; the
        # model's verbatim answer (which may quote anything) comes after it.
        meta = body.split("\n---\n", 1)[0]
        shas = AUTOMATED_SHA.findall(meta)
        if len(shas) != 1:
            # Malformed bot metadata blocks readiness for every commit it might cover
            # (all of them when it names none) instead of being ignored.
            return {**base, "kind": "automated", "sha": None, "shas": shas, "verdict": "UNCLEAR"}
        sha = shas[0]
        incomplete = AUTOMATED_INCOMPLETE in meta
        verdicts = AUTOMATED_QUALIFYING.findall(meta)
        if incomplete and not verdicts:
            return {**base, "kind": "automated", "sha": sha, "verdict": "INCOMPLETE"}
        verdict = verdicts[0] if len(verdicts) == 1 and not incomplete else "UNCLEAR"
        return {**base, "kind": "automated", "sha": sha, "verdict": verdict}
    if header := MANUAL_HEADER.match(body.splitlines()[0]):
        # A recognised review whose verdict can't be read is UNCLEAR, which blocks
        # "ready" rather than letting an older PASS stand.
        return {**base, "kind": "manual", "sha": header.group(1), "verdict": _header_verdict(body) or "UNCLEAR"}
    return None


def review_for_head(comments: list[dict], head_sha: str) -> dict | None:
    """The newest recognised review that covers exactly the PR's current head commit."""
    found = None
    for c in sorted(comments, key=lambda c: c.get("created_at") or ""):
        review = classify_review(c)
        if review is None:
            continue
        if review["sha"] is None:
            # Malformed bot review: it blocks when it names this commit or names none.
            if not review["shas"] or any(_same_commit(s, head_sha, full=False) for s in review["shas"]):
                found = review
        elif review["kind"] == "automated":
            if _same_commit(review["sha"], head_sha, full=True):
                found = review
            elif _same_commit(review["sha"], head_sha, full=False):
                # Names this head only by a shortened SHA: not qualifying, but it blocks.
                found = {**review, "verdict": "UNCLEAR"}
        elif _same_commit(review["sha"], head_sha, full=False):
            found = review
    return found


def collect_check_runs(fetch_page, per_page: int = 100, max_pages: int = 10) -> tuple[list[dict] | None, bool]:
    """Read every page of a check-runs response. `fetch_page(n)` returns (data, error).

    Returns (runs, complete); complete is False on any error, odd response or page cap.
    """
    runs: list[dict] = []
    for page in range(1, max_pages + 1):
        data, err = fetch_page(page)
        if err or not isinstance(data, dict) or not isinstance(data.get("check_runs"), list):
            return (runs or None), False
        runs.extend(data["check_runs"])
        total = data.get("total_count")
        if not isinstance(total, int):
            return runs, False
        if len(runs) >= total or len(data["check_runs"]) < per_page:
            return runs, len(runs) >= total
    return runs, False


def ci_state(check_runs: list[dict] | None, total_count: int | None = None) -> str:
    """PASSING only when every required check completed with 'success' on this commit."""
    if check_runs is None or (total_count is not None and total_count > len(check_runs)):
        return "UNKNOWN"
    required = [r for r in check_runs if r.get("name") in REQUIRED_CHECKS]
    bad = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
    if any(r.get("status") == "completed" and r.get("conclusion") in bad for r in required):
        return "FAILING"
    if not required:
        return "UNKNOWN"
    if any(r.get("status") != "completed" for r in required):
        return "RUNNING"
    if all(r.get("conclusion") == "success" for r in required):
        return "PASSING"
    return "UNKNOWN"


def next_action(review: dict | None, ci: str) -> str:
    """Plain-language next step for an open PR. Only a verified review can make it ready."""
    if ci == "FAILING":
        return "Claude: fix failing tests"
    if review is None:
        return "Needs ChatGPT review of the current commit"
    if review["verdict"] == "UNCLEAR":
        return "Check reviews: the newest review's verdict can't be read"
    if review["verdict"] in ("FAIL", "INCOMPLETE"):
        return "Claude: fix review findings"
    if ci != "PASSING":
        return "Waiting for tests" if ci == "RUNNING" else "Check tests (status unknown)"
    if review["kind"] != "automated":
        return "Manual PASS on this commit: confirm it is ChatGPT's review, then decide"
    return "Ready for your merge decision"
