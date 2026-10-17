"""Deterministic scheduled-readiness history selection (evaluation infrastructure only).

The final-readiness core calls this module from its ``prepare`` job to decide which
suite (A, B, C) a genuine scheduled carrier run may attempt, and whether a prior
paid-relevant failure blocks a blind retry. It reads GitHub Actions history only
(through ``gh api``); it never calls a model, writes to GitHub, or mutates the repo.

Semantics preserved from Issue #69:
- only completed ``event=schedule`` carrier runs count, and only their attempt 1;
- a run counts as a success only with exactly one unexpired
  ``agent-final-readiness-evidence-<run_id>`` artifact; three successes stop all work;
- the most recent paid-relevant failure blocks a blind retry on the same commit, and a
  retry on a new commit requires a reviewed change of the right kind;
- any ambiguity raises ``ReadinessHistoryError`` so the caller fails closed.

Issue #87 changes:
- H1: a prepare-stage failure before any model stage, confined to infrastructure
  steps, is ``pre_model_failure`` and no longer becomes the latest paid failure.
- H2: history is scanned newest-first and stops at three successes or at the first
  run whose commit predates the readiness core; commit lookups are cached; an
  explicit scan cap fails closed instead of guessing.
- M1: a behavioral failure may only be unlocked by a change to the exact
  instruction inputs the blind model sees; infrastructure repairs only unlock
  infrastructure failures.
- M3: a run whose latest attempt is not 1 can never count as a success; its
  attempt-1 record still decides whether it was a paid failure.

PR #91 review hardening: before Suite B or C spends anything, prior evidence must have
been produced with today's exact blind instruction inputs (W1); a cancelled run with
any readiness artifact stays paid-relevant as on main (W2); a failure inside a model
call is behavioral, never infrastructure (W3); out-of-order history fails closed (W4).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterable, Iterator

EVIDENCE_PREFIX = "agent-final-readiness-evidence-"
BLIND_INPUT_PREFIX = "agent-final-readiness-blind-input-"
READINESS_ARTIFACT_PREFIX = "agent-final-readiness-"
CORE_PATH = ".github/workflows/agent-final-readiness-core.yml"
CARRIER_WORKFLOW = "agent-operator.yml"
REQUIRED_SUCCESSES = 3
SUITE_BY_SUCCESS_COUNT = {0: "a", 1: "b", 2: "c"}
MAX_RUNS_SCANNED = 1000
SAME_SHA_REFUSAL = (
    "Most recent paid-relevant scheduled run failed on this exact commit; refusing a blind paid retry."
)

# Prepare-job steps whose failure happens before any model spend and proves nothing
# about agent behavior (runner/API/history plumbing or fail-closed guards).
# Deterministic tests and blind-bundle building are deliberately absent: a failure
# there is a content/code defect and stays paid-relevant.
PRE_MODEL_INFRA_STEPS = frozenset({
    "Set up job",
    "Refuse non-schedule provenance and reruns before any work",
    "Checkout exact scheduled commit without persisted credentials",
    "Set up Python",
    "Select next suite from verified carrier history and enforce retry barrier",
    "Require reviewed hardening change after a prior failed paid run",
})
THRESHOLD_FAILURE_STEP = "Fail closed when suite did not meet readiness threshold"
# Steps that invoke the model. A failure inside one is never "infrastructure".
MODEL_CALL_STEPS = frozenset({
    "Run blind read-only Agent OS evaluator",
    "Run isolated read-only independent judge",
})

# The exact instruction files copied into the blind bundle
# (agent_evals/scheduled_readiness.py build_blind_bundle). Only these can change what
# the blind model sees, so only these unlock a retry after a behavioral failure.
BLIND_INSTRUCTION_INPUTS = (
    "AGENTS.md",
    ".github/copilot-instructions.md",
    "agent_evals/team_profiles.json",
)
INFRASTRUCTURE_REPAIR_PATTERN = re.compile(
    r"^(\.github/workflows/agent-final-readiness-core\.yml"
    r"|agent_evals/scheduled_readiness\.py"
    r"|agent_evals/readiness_history\.py)$"
)


class ReadinessHistoryError(ValueError):
    """History cannot be verified; the caller must refuse to advance."""


def _jobs_ending(jobs: list[dict], suffix: str) -> list[dict]:
    return [j for j in jobs if str(j.get("name", "")).endswith(suffix)]


def _job_ran(job: dict) -> bool:
    return job.get("conclusion") != "skipped" and job.get("started_at") is not None


def model_stage_started(jobs: list[dict]) -> int:
    """Count blind/judge model jobs that actually started (skipped jobs never count)."""
    return sum(
        1
        for job in jobs
        if (str(job.get("name", "")).endswith("final-readiness-blind-pass")
            or str(job.get("name", "")).endswith("final-readiness-judge-pass"))
        and _job_ran(job)
    )


def failure_kind(jobs: list[dict]) -> str:
    """Classify a paid-relevant failure.

    ``infrastructure`` only when a model-runtime job (blind pass, judge preparation,
    judge pass) failed before deterministic recording ran, *and* its step list proves
    the failure was in runner plumbing rather than the model call itself. A failure in
    the model step (refusal, turn/time exhaustion, empty or rejected output), a
    malformed or self-reviewing blind answer caught by ``validate-blind``, a threshold
    failure, or anything unproven is ``behavioral`` (the stricter gate).
    """
    for job in _jobs_ending(jobs, "final-readiness-validate-and-record"):
        for step in job.get("steps") or []:
            if step.get("name") == THRESHOLD_FAILURE_STEP and step.get("conclusion") == "failure":
                return "behavioral"
    if any(j.get("conclusion") == "failure" for j in _jobs_ending(jobs, "final-readiness-validate-blind")):
        return "behavioral"
    if any(_job_ran(j) for j in _jobs_ending(jobs, "final-readiness-validate-and-record")):
        return "behavioral"
    failed_runtime_jobs = [
        j
        for suffix in ("final-readiness-blind-pass", "final-readiness-prepare-judge", "final-readiness-judge-pass")
        for j in _jobs_ending(jobs, suffix)
        if j.get("conclusion") in {"failure", "cancelled", "timed_out"}
    ]
    if not failed_runtime_jobs:
        return "behavioral"
    for job in failed_runtime_jobs:
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            return "behavioral"  # cannot prove where it failed
        failed = [s.get("name") for s in steps if s.get("conclusion") in {"failure", "timed_out", "cancelled"}]
        if not failed or any(name in MODEL_CALL_STEPS for name in failed):
            return "behavioral"
    return "infrastructure"


def _prepare_failed_only_in_infra_steps(prepare: dict) -> bool:
    if prepare.get("conclusion") != "failure":
        return False
    steps = prepare.get("steps")
    if not isinstance(steps, list) or not steps:
        return False  # cannot prove which step failed
    failed = [s.get("name") for s in steps if s.get("conclusion") in {"failure", "timed_out", "cancelled"}]
    return bool(failed) and all(name in PRE_MODEL_INFRA_STEPS for name in failed)


def classify_attempt(run_id: int, conclusion: str | None, jobs: list[dict], artifacts: list[dict]) -> str:
    """Classify one completed attempt of a core-bearing carrier run.

    Returns ``ignore``, ``success``, ``success_missing_evidence``,
    ``pre_model_failure`` or ``paid_relevant_failure``; raises on ambiguity.
    """
    markers = _jobs_ending(jobs, "final-readiness-prepare")
    readiness_jobs = [j for j in jobs if "final-readiness" in str(j.get("name", ""))]
    started = model_stage_started(jobs)
    readiness_artifacts = [
        a for a in artifacts if str(a.get("name", "")).startswith(READINESS_ARTIFACT_PREFIX)
    ]

    if not markers and not readiness_jobs and not started and not readiness_artifacts and conclusion != "success":
        return "ignore"
    if len(markers) != 1:
        raise ReadinessHistoryError(
            f"carrier run {run_id} contains the readiness core but has {len(markers)} prepare markers; "
            "refusing ambiguous history"
        )

    if conclusion == "success":
        expected = f"{EVIDENCE_PREFIX}{run_id}"
        valid = [a for a in artifacts if a.get("name") == expected and a.get("expired") is False]
        return "success" if len(valid) == 1 else "success_missing_evidence"

    if conclusion not in {"failure", "cancelled", "timed_out", "startup_failure"}:
        raise ReadinessHistoryError(f"carrier run {run_id} has unexpected conclusion {conclusion!r}")

    # As on main: once any readiness artifact exists (even blind input only), the run is
    # conservatively paid-relevant, so job-name drift can never hide model spend.
    prepare = markers[0]
    if started == 0 and not readiness_artifacts:
        if conclusion == "cancelled" and prepare.get("conclusion") in {"success", "cancelled"}:
            return "pre_model_failure"
        if prepare.get("conclusion") == "failure" and _prepare_failed_only_in_infra_steps(prepare):
            return "pre_model_failure"
    return "paid_relevant_failure"


def classify_run(run: dict, details: dict) -> dict:
    """Classify a completed, core-bearing schedule run using its attempt-1 record.

    ``details`` holds ``jobs`` and ``artifacts`` for the run, plus ``attempt1`` (the
    attempt-1 run object) and ``attempt1_jobs`` when the latest attempt is not 1.
    """
    run_id = run["id"]
    attempt = run.get("run_attempt")
    if attempt == 1:
        status = classify_attempt(run_id, run.get("conclusion"), details["jobs"], details["artifacts"])
        jobs = details["jobs"]
    elif isinstance(attempt, int) and attempt > 1:
        first = details.get("attempt1")
        if not isinstance(first, dict) or first.get("run_attempt") != 1 or first.get("status") != "completed":
            raise ReadinessHistoryError(f"carrier run {run_id}: attempt 1 record could not be verified")
        jobs = details.get("attempt1_jobs")
        if not isinstance(jobs, list):
            raise ReadinessHistoryError(f"carrier run {run_id}: attempt 1 jobs could not be verified")
        # Artifacts are listed per run (all attempts), while jobs come from attempt 1.
        # Any later-attempt artifact therefore only pushes toward paid_relevant_failure,
        # which is the conservative direction.
        status = classify_attempt(run_id, first.get("conclusion"), jobs, details["artifacts"])
        if status in {"success", "success_missing_evidence"}:
            # A rerun makes provenance ambiguous: never count it, but it is not a failure.
            status = "rerun_not_countable"
    else:
        raise ReadinessHistoryError(f"carrier run {run_id} has invalid run_attempt {attempt!r}")
    result = {"run": run, "status": status}
    if status == "paid_relevant_failure":
        result["kind"] = failure_kind(jobs)
    return result


def select_suite(
    runs: Iterable[dict],
    has_core: Callable[[str], bool],
    details: Callable[[dict], dict],
    current_run_id: int,
    current_sha: str,
    max_runs: int = MAX_RUNS_SCANNED,
) -> dict:
    """Choose the next suite from newest-first carrier history.

    ``runs`` yields schedule runs newest-first (it may page lazily). ``has_core(sha)``
    says whether that commit contains the readiness core. ``details(run)`` returns the
    jobs/artifacts (and attempt-1 data for reruns). Both must raise on API failure.
    """
    successes = 0
    success_ids: list[int] = []
    latest: dict | None = None
    scanned = 0
    previous_created: str | None = None
    for run in runs:
        created = run.get("created_at")
        if not isinstance(created, str) or not created:
            raise ReadinessHistoryError(f"carrier run {run.get('id')} has no created_at; refusing ambiguous history")
        # "Latest failure" and the migration boundary both rely on newest-first order.
        if previous_created is not None and created > previous_created:
            raise ReadinessHistoryError("carrier run listing is not newest-first; refusing ambiguous history")
        previous_created = created
        if run.get("id") == current_run_id or run.get("event") != "schedule" or run.get("status") != "completed":
            continue
        scanned += 1
        if scanned > max_runs:
            raise ReadinessHistoryError(
                f"scanned {max_runs} carrier runs without reaching three successes or the core migration "
                "boundary; bounded history is insufficient"
            )
        if not has_core(run["head_sha"]):
            # Migration boundary: this and every older carrier run predate the core.
            break
        result = classify_run(run, details(run))
        status = result["status"]
        if status in {"ignore", "pre_model_failure", "rerun_not_countable"}:
            continue
        if status == "success_missing_evidence":
            raise ReadinessHistoryError(
                f"A readiness-relevant successful carrier run {run['id']} lacks exactly one valid evidence "
                "artifact; refusing to advance."
            )
        if latest is None:
            latest = result
        if status == "success":
            successes += 1
            success_ids.append(run["id"])
            if successes >= REQUIRED_SUCCESSES:
                break

    if successes >= REQUIRED_SUCCESSES:
        return {"execute": False, "suite": "complete"}
    selection = {"execute": True, "suite": SUITE_BY_SUCCESS_COUNT[successes], "prior_success_ids": success_ids}
    if latest is not None and latest["status"] == "paid_relevant_failure":
        if latest["run"]["head_sha"] == current_sha:
            raise ReadinessHistoryError(SAME_SHA_REFUSAL)
        selection["failed_sha"] = latest["run"]["head_sha"]
        selection["failure_kind"] = latest["kind"]
    return selection


def require_matching_instruction_hashes(prior_metadata: list[dict], current: dict[str, str]) -> None:
    """Before any model spend for Suite B or C, prove prior evidence used today's blind inputs.

    A mismatch (including evidence recorded before hashes existed) would otherwise be
    discovered only at Suite C aggregation, after a paid run, with no automatic way
    out. Raising here happens in the pre-model selection step, so no model is called;
    superseding stale A/B evidence is an explicit owner decision.
    """
    for meta in prior_metadata:
        for key, value in current.items():
            if not isinstance(meta, dict) or meta.get(key) != value:
                raise ReadinessHistoryError(
                    f"prior readiness evidence (run {meta.get('run_id') if isinstance(meta, dict) else '?'}) "
                    f"was produced with different or unrecorded blind instruction inputs ({key}); refusing "
                    "model spend. Owner decision required to supersede stale A/B evidence."
                )


def hardening_allows_retry(changed_paths: list[str], kind: str) -> bool:
    """Reviewed-hardening decision for a retry after a paid-relevant failure."""
    if kind not in {"behavioral", "infrastructure"}:
        raise ReadinessHistoryError(f"unknown failure kind: {kind!r}")
    if any(path in BLIND_INSTRUCTION_INPUTS for path in changed_paths):
        return True
    if kind == "infrastructure":
        return any(INFRASTRUCTURE_REPAIR_PATTERN.match(path) for path in changed_paths)
    return False


# --- GitHub access (read-only, via the gh CLI and the job's read-only token) ---

def _gh_json(path: str, paginate: bool = False):
    cmd = ["gh", "api"]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    cmd.append(path)
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise ReadinessHistoryError(f"GitHub API request failed for {path}: {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)


def _gh_exists(path: str) -> bool:
    proc = subprocess.run(["gh", "api", path], text=True, capture_output=True)
    if proc.returncode == 0:
        return True
    if "HTTP 404" in proc.stderr:
        return False
    raise ReadinessHistoryError(f"could not verify {path}: {proc.stderr.strip()[:500]}")


def _iter_schedule_runs(repo: str) -> Iterator[dict]:
    page = 1
    while True:
        data = _gh_json(f"/repos/{repo}/actions/workflows/{CARRIER_WORKFLOW}/runs?event=schedule&per_page=100&page={page}")
        runs = data.get("workflow_runs")
        if not isinstance(runs, list):
            raise ReadinessHistoryError("carrier run listing is malformed")
        yield from runs
        if len(runs) < 100:
            return
        page += 1


def _flatten(pages, key: str) -> list[dict]:
    if not isinstance(pages, list):
        raise ReadinessHistoryError(f"paginated {key} listing is malformed")
    out: list[dict] = []
    for page in pages:
        items = page.get(key) if isinstance(page, dict) else None
        if not isinstance(items, list):
            raise ReadinessHistoryError(f"paginated {key} listing is malformed")
        out.extend(items)
    return out


def github_select(repo: str, current_run_id: int, current_sha: str) -> dict:
    core_cache: dict[str, bool] = {}

    def has_core(sha: str) -> bool:
        if sha not in core_cache:
            core_cache[sha] = _gh_exists(f"/repos/{repo}/contents/{CORE_PATH}?ref={sha}")
        return core_cache[sha]

    def details(run: dict) -> dict:
        rid = run["id"]
        info = {
            "jobs": _flatten(_gh_json(f"/repos/{repo}/actions/runs/{rid}/jobs?filter=all&per_page=100", paginate=True), "jobs"),
            "artifacts": _flatten(_gh_json(f"/repos/{repo}/actions/runs/{rid}/artifacts?per_page=100", paginate=True), "artifacts"),
        }
        if run.get("run_attempt") != 1:
            info["attempt1"] = _gh_json(f"/repos/{repo}/actions/runs/{rid}/attempts/1")
            info["attempt1_jobs"] = _flatten(
                _gh_json(f"/repos/{repo}/actions/runs/{rid}/attempts/1/jobs?per_page=100", paginate=True), "jobs"
            )
        return info

    selection = select_suite(_iter_schedule_runs(repo), has_core, details, current_run_id, current_sha)
    if selection["execute"] and selection["prior_success_ids"]:
        from agent_evals.scheduled_readiness import instruction_hashes

        prior = [_download_evidence_metadata(repo, rid) for rid in selection["prior_success_ids"]]
        require_matching_instruction_hashes(prior, instruction_hashes())
    return selection


def _download_evidence_metadata(repo: str, run_id: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "--repo", repo,
             "--name", f"{EVIDENCE_PREFIX}{run_id}", "--dir", tmp],
            text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise ReadinessHistoryError(
                f"could not download evidence for run {run_id}: {proc.stderr.strip()[:500]}"
            )
        path = Path(tmp) / "metadata.json"
        if not path.is_file():
            raise ReadinessHistoryError(f"evidence for run {run_id} has no metadata.json")
        return json.loads(path.read_text(encoding="utf-8"))


def _changed_paths(failed_sha: str, current_sha: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", failed_sha, current_sha], text=True, capture_output=True
    )
    if proc.returncode != 0:
        raise ReadinessHistoryError(f"could not diff {failed_sha}..{current_sha}: {proc.stderr.strip()[:500]}")
    return [line for line in proc.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("select")
    p.add_argument("--repo", required=True)
    p.add_argument("--current-run-id", type=int, required=True)
    p.add_argument("--current-sha", required=True)
    p.add_argument("--github-output", required=True)
    p = sub.add_parser("hardening-gate")
    p.add_argument("--failed-sha", required=True)
    p.add_argument("--current-sha", required=True)
    p.add_argument("--kind", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "select":
            selection = github_select(args.repo, args.current_run_id, args.current_sha)
            lines = [f"execute={'true' if selection['execute'] else 'false'}", f"suite={selection['suite']}"]
            if "failed_sha" in selection:
                lines.append(f"failed_sha={selection['failed_sha']}")
                lines.append(f"failure_kind={selection['failure_kind']}")
            with open(args.github_output, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            print(json.dumps(selection, sort_keys=True))
        else:
            changed = _changed_paths(args.failed_sha, args.current_sha)
            if not hardening_allows_retry(changed, args.kind):
                print(
                    f"Previous paid run failed ({args.kind}) and no qualifying reviewed hardening change exists; "
                    "refusing retry.",
                    file=sys.stderr,
                )
                print("\n".join(changed), file=sys.stderr)
                return 1
            print(f"Reviewed {args.kind} hardening change found; retry allowed.")
    except ReadinessHistoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
