"""Deterministic scheduled-readiness history classification (evaluation infrastructure only).

Pure functions over GitHub Actions API-shaped dictionaries. No network, no model
calls, no repository mutation. Every ambiguity raises ``ReadinessHistoryError`` so
callers fail closed instead of guessing.

Semantics preserved from Issue #69: three successful attempt-1 evidence runs are
required (A, B, C in order); a paid-relevant failure blocks a blind retry of the
same SHA; unverifiable history refuses to advance.
"""
from __future__ import annotations

import re
from typing import Callable

EVIDENCE_PREFIX = "agent-final-readiness-evidence-"
BLIND_INPUT_PREFIX = "agent-final-readiness-blind-input-"
READINESS_ARTIFACT_PREFIX = "agent-final-readiness-"
REQUIRED_SUCCESSES = 3
SUITE_BY_SUCCESS_COUNT = {0: "a", 1: "b", 2: "c"}

# Prepare-stage steps whose failure proves nothing about agent behavior and
# happens before any model spend (GitHub/API/runner infrastructure or fail-closed
# history guards). Deterministic tests and bundle building are deliberately absent:
# a failure there is a code/content defect, not transient infrastructure.
PRE_MODEL_INFRA_STEPS = frozenset({
    "Set up job",
    "Select next suite from verified carrier history and enforce retry barrier",
    "Checkout exact scheduled commit without persisted credentials",
    "Require reviewed hardening change after a prior failed paid run",
    "Set up Python",
    "Upload blind-only model input",
})
THRESHOLD_FAILURE_STEP = "Fail closed when suite did not meet readiness threshold"

# Reviewed-hardening gate. A behavioral (paid-relevant, threshold) failure may only
# be unlocked by changes that can alter blind behavior. Cadence/workflow plumbing and
# unrelated tests may not. Readiness-infrastructure repair paths unlock only
# infrastructure-kind failures.
BEHAVIOR_SHAPING_PATTERN = re.compile(
    r"^(AGENTS\.md|\.github/copilot-instructions\.md|\.github/agents/|\.github/skills/|agent_evals/)"
)
INFRASTRUCTURE_REPAIR_PATTERN = re.compile(
    r"^(\.github/workflows/agent-final-readiness-core\.yml$"
    r"|\.github/workflows/agent-operator\.yml$"
    r"|agent_evals/(scheduled_readiness|readiness_history)\.py$"
    r"|tests/test_(agent_scheduled_readiness|readiness_)[A-Za-z0-9_]*\.py$)"
)


class ReadinessHistoryError(ValueError):
    """History cannot be verified; the caller must refuse to advance."""


def _jobs_ending(jobs: list[dict], suffix: str) -> list[dict]:
    return [j for j in jobs if str(j.get("name", "")).endswith(suffix)]


def model_stage_started(jobs: list[dict]) -> int:
    count = 0
    for job in jobs:
        name = str(job.get("name", ""))
        if (name.endswith("final-readiness-blind-pass") or name.endswith("final-readiness-judge-pass")) \
                and job.get("conclusion") != "skipped" and job.get("started_at") is not None:
            count += 1
    return count


def require_first_attempt(run: dict) -> None:
    """Only attempt 1 may influence suite selection; anything else needs a human."""
    if run.get("run_attempt") != 1:
        raise ReadinessHistoryError(
            f"run {run.get('id')} has run_attempt={run.get('run_attempt')!r}; "
            "only run_attempt == 1 may influence suite selection (reruns are ambiguous)"
        )


def failure_kind(jobs: list[dict]) -> str:
    """'behavioral' only when the suite ran to threshold scoring and failed it.

    Anything unproven is reported as 'behavioral' (the stricter retry gate).
    """
    for job in _jobs_ending(jobs, "final-readiness-validate-and-record"):
        for step in job.get("steps") or []:
            if step.get("name") == THRESHOLD_FAILURE_STEP and step.get("conclusion") == "failure":
                return "behavioral"
    record_ran = any(
        j.get("conclusion") != "skipped" and j.get("started_at") is not None
        for j in _jobs_ending(jobs, "final-readiness-validate-and-record")
    )
    if model_stage_started(jobs) and not record_ran:
        return "infrastructure"
    return "behavioral"


def _prepare_failed_only_in_infra_steps(prepare: dict) -> bool:
    conclusion = prepare.get("conclusion")
    if conclusion in {"cancelled", "timed_out"}:
        return True
    if conclusion != "failure":
        return False
    steps = prepare.get("steps")
    if not isinstance(steps, list) or not steps:
        return False  # cannot prove which step failed
    failed = [s.get("name") for s in steps if s.get("conclusion") in {"failure", "timed_out"}]
    return bool(failed) and all(name in PRE_MODEL_INFRA_STEPS for name in failed)


def classify_run(run: dict, jobs: list[dict], artifacts: list[dict]) -> str:
    """Classify a completed, core-bearing schedule run.

    Returns one of: 'ignore' (no readiness work), 'success', 'pre_model_failure',
    'paid_relevant_failure'. Raises ReadinessHistoryError on ambiguity.
    """
    require_first_attempt(run)
    rid = run["id"]
    conclusion = run.get("conclusion")
    markers = _jobs_ending(jobs, "final-readiness-prepare")
    readiness_jobs = [j for j in jobs if "final-readiness" in str(j.get("name", ""))]
    started = model_stage_started(jobs)
    readiness_artifacts = [a for a in artifacts if str(a.get("name", "")).startswith(READINESS_ARTIFACT_PREFIX)]

    if not markers and not readiness_jobs and not started and not readiness_artifacts and conclusion != "success":
        return "ignore"
    if len(markers) != 1:
        raise ReadinessHistoryError(f"run {rid}: {len(markers)} prepare markers; ambiguous history")

    if conclusion == "success":
        expected = f"{EVIDENCE_PREFIX}{rid}"
        valid = [a for a in artifacts if a.get("name") == expected and a.get("expired") is False]
        return "success" if len(valid) == 1 else "success_missing_evidence"

    non_input_artifacts = [a for a in readiness_artifacts if not str(a.get("name", "")).startswith(BLIND_INPUT_PREFIX)]
    if started == 0 and not non_input_artifacts and conclusion in {"failure", "cancelled", "timed_out"}:
        if markers[0].get("conclusion") == "success":
            # Prepare finished but no model stage ever started: only a cancellation is benign.
            if conclusion == "cancelled":
                return "pre_model_failure"
        elif _prepare_failed_only_in_infra_steps(markers[0]):
            return "pre_model_failure"
    return "paid_relevant_failure"


def hardening_allows_retry(changed_paths: list[str], kind: str) -> bool:
    """Deterministic reviewed-hardening decision for a retry after a paid-relevant failure."""
    if kind not in {"behavioral", "infrastructure"}:
        raise ReadinessHistoryError(f"unknown failure kind: {kind}")
    if any(BEHAVIOR_SHAPING_PATTERN.match(p) and not INFRASTRUCTURE_REPAIR_PATTERN.match(p)
           for p in changed_paths):
        return True
    if kind == "infrastructure":
        return any(INFRASTRUCTURE_REPAIR_PATTERN.match(p) for p in changed_paths)
    return False


def select_suite(
    runs: list[dict],
    details: Callable[[dict], dict],
    current_run_id: int,
    current_sha: str,
    window_complete: bool,
) -> dict:
    """Pick the next suite from a newest-first, possibly bounded run window.

    ``details(run)`` returns ``{'has_core': bool, 'jobs': [...], 'artifacts': [...]}``
    and must raise on any API failure. Scanning stops at three successes, or at the
    first run predating the readiness core (the migration boundary). If neither is
    reached and the window was truncated, history is insufficient and we fail closed.
    """
    candidates = [r for r in runs if r.get("id") != current_run_id
                  and r.get("event") == "schedule" and r.get("status") == "completed"]
    candidates.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    successes = 0
    latest_failure: dict | None = None
    boundary = False
    for run in candidates:
        info = details(run)
        if not info.get("has_core"):
            boundary = True
            break
        kind = classify_run(run, info["jobs"], info["artifacts"])
        if kind in {"ignore", "pre_model_failure"}:
            continue
        if kind == "success_missing_evidence":
            raise ReadinessHistoryError(f"run {run['id']}: success lacks exactly one valid evidence artifact")
        if kind == "success":
            successes += 1
            if successes >= REQUIRED_SUCCESSES:
                break
            continue
        if latest_failure is None and successes == 0:
            latest_failure = {"run": run, "kind": failure_kind(info["jobs"])}
    if successes >= REQUIRED_SUCCESSES:
        return {"execute": False, "suite": "complete"}
    if not window_complete and not boundary:
        raise ReadinessHistoryError("bounded history window is insufficient to prove the A/B/C sequence")
    if latest_failure is not None and latest_failure["run"]["head_sha"] == current_sha:
        raise ReadinessHistoryError("most recent paid-relevant run failed on this exact commit; refusing blind retry")
    result = {"execute": True, "suite": SUITE_BY_SUCCESS_COUNT[successes]}
    if latest_failure is not None:
        result["failed_sha"] = latest_failure["run"]["head_sha"]
        result["failure_kind"] = latest_failure["kind"]
    return result
