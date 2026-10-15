"""Deterministic controls for the final scheduled Agent OS blind evaluation.

The model calls are intentionally separated from these controls. Pass 1 is validated
against blind prompt IDs and repo-agent IDs only. Pass 2 is validated against the
already-frozen Pass-1 routing plus the hidden rubric. Semantic grading remains the
independent judge's responsibility; malformed or rewritten evidence fails closed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

try:
    from agent_evals.final_readiness import score_readiness
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution
    from final_readiness import score_readiness

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("a", "b", "c")
BLIND_FIELDS = {
    "id",
    "primary",
    "reviewers",
    "risk",
    "proposed_action",
    "verification_plan",
    "approval_requirements",
    "uncertainty",
    "refusals",
}
JUDGE_FIELDS = {"id", "primary", "reviewers", "must_do_met", "must_not_violated"}
VALID_RISKS = {"low", "medium", "high", "critical"}


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty_string(item) for item in value)
    )


def _bool_list(value: object, expected_length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == expected_length
        and all(type(item) is bool for item in value)
    )


def _assert_suite(suite: str) -> None:
    if suite not in SUITES:
        raise ValueError(f"unknown suite {suite!r}; expected one of {SUITES}")


def load_prompt_cases(root: Path, suite: str) -> list[dict]:
    _assert_suite(suite)
    doc = _load(root / "agent_evals" / f"final_suite_{suite}_prompts.json")
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
        raise ValueError(f"suite {suite} prompt document is malformed")
    return doc["cases"]


def load_rubric_cases(root: Path, suite: str) -> list[dict]:
    _assert_suite(suite)
    doc = _load(root / "agent_evals" / f"final_suite_{suite}_rubric.json")
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
        raise ValueError(f"suite {suite} rubric document is malformed")
    return doc["cases"]


def repo_agent_ids(root: Path) -> set[str]:
    doc = _load(root / "agent_evals" / "team_profiles.json")
    agents = doc.get("agents") if isinstance(doc, dict) else None
    if not isinstance(agents, dict):
        raise ValueError("team_profiles.json is malformed")
    return {
        agent_id
        for agent_id, config in agents.items()
        if isinstance(config, dict) and config.get("source") == "repo"
    }


def validate_blind_output(doc: object, suite: str, root: Path = ROOT) -> list[str]:
    """Return fail-closed structural/routing errors for a frozen blind answer."""
    _assert_suite(suite)
    errors: list[str] = []
    prompt_cases = load_prompt_cases(root, suite)
    expected_ids = [case.get("id") for case in prompt_cases]
    if len(expected_ids) != 18 or any(not isinstance(case_id, str) for case_id in expected_ids):
        errors.append(f"suite {suite} prompt set must contain exactly 18 string IDs")
        return errors
    if len(set(expected_ids)) != len(expected_ids):
        errors.append(f"suite {suite} prompt IDs are duplicated")
        return errors

    if not isinstance(doc, dict) or set(doc) != {"suite", "cases"}:
        return ["blind output must contain exactly top-level keys: suite, cases"]
    if doc.get("suite") != suite:
        errors.append(f"blind output suite must be {suite!r}")
    cases = doc.get("cases")
    if not isinstance(cases, list):
        errors.append("blind output cases must be a list")
        return errors
    if len(cases) != 18:
        errors.append(f"blind output must contain exactly 18 cases, got {len(cases)}")

    valid_agents = repo_agent_ids(root)
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    for index, case in enumerate(cases):
        prefix = f"blind cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if set(case) != BLIND_FIELDS:
            errors.append(f"{prefix} has missing or unexpected fields")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or case_id not in expected_ids:
            errors.append(f"{prefix} has unknown/non-string id {case_id!r}")
            continue
        if case_id in seen:
            errors.append(f"duplicate blind case id: {case_id}")
            continue
        seen.add(case_id)
        by_id[case_id] = case

        primary = case.get("primary")
        reviewers = case.get("reviewers")
        if primary not in valid_agents:
            errors.append(f"{case_id}: primary is not a valid repo agent: {primary!r}")
        if not isinstance(reviewers, list) or not reviewers:
            errors.append(f"{case_id}: reviewers must be a non-empty list")
        elif any(reviewer not in valid_agents for reviewer in reviewers):
            errors.append(f"{case_id}: reviewer list contains a non-repo agent")
        else:
            if len(reviewers) != len(set(reviewers)):
                errors.append(f"{case_id}: reviewers contain duplicates")
            if primary in reviewers:
                errors.append(f"{case_id}: primary may not review itself")

        if case.get("risk") not in VALID_RISKS:
            errors.append(f"{case_id}: invalid risk classification")
        for field in ("proposed_action", "uncertainty"):
            if not _nonempty_string(case.get(field)):
                errors.append(f"{case_id}: {field} must be a non-empty string")
        for field in ("verification_plan", "approval_requirements", "refusals"):
            if not _nonempty_string_list(case.get(field)):
                errors.append(f"{case_id}: {field} must be a non-empty list of strings")

    missing = [case_id for case_id in expected_ids if case_id not in by_id]
    if missing:
        errors.append(f"blind output missing case IDs: {', '.join(missing)}")
    return errors


def validate_judge_output(
    blind_doc: object,
    judge_doc: object,
    suite: str,
    root: Path = ROOT,
) -> list[str]:
    """Validate judge evidence and prove it did not rewrite frozen routing fields."""
    _assert_suite(suite)
    errors = validate_blind_output(blind_doc, suite, root)
    if errors:
        return [f"frozen blind evidence invalid: {error}" for error in errors]

    if not isinstance(judge_doc, dict) or set(judge_doc) != {"suite", "results"}:
        return ["judge output must contain exactly top-level keys: suite, results"]
    if judge_doc.get("suite") != suite:
        errors.append(f"judge output suite must be {suite!r}")
    results = judge_doc.get("results")
    if not isinstance(results, list):
        errors.append("judge results must be a list")
        return errors
    if len(results) != 18:
        errors.append(f"judge output must contain exactly 18 results, got {len(results)}")

    blind_by_id = {case["id"]: case for case in blind_doc["cases"]}
    rubric_cases = load_rubric_cases(root, suite)
    rubric_by_id = {case.get("id"): case for case in rubric_cases if isinstance(case, dict)}
    expected_ids = set(blind_by_id)
    if len(rubric_cases) != 18 or set(rubric_by_id) != expected_ids:
        errors.append("hidden rubric IDs do not exactly match the frozen blind suite")
        return errors

    seen: set[str] = set()
    for index, result in enumerate(results):
        prefix = f"judge results[{index}]"
        if not isinstance(result, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if set(result) != JUDGE_FIELDS:
            errors.append(f"{prefix} has missing or unexpected fields")
            continue
        case_id = result.get("id")
        if not isinstance(case_id, str) or case_id not in expected_ids:
            errors.append(f"{prefix} has unknown/non-string id {case_id!r}")
            continue
        if case_id in seen:
            errors.append(f"duplicate judge result id: {case_id}")
            continue
        seen.add(case_id)

        frozen = blind_by_id[case_id]
        if result.get("primary") != frozen["primary"]:
            errors.append(f"{case_id}: judge rewrote frozen primary")
        if result.get("reviewers") != frozen["reviewers"]:
            errors.append(f"{case_id}: judge rewrote frozen reviewers")

        rubric = rubric_by_id[case_id]
        if not _bool_list(result.get("must_do_met"), len(rubric.get("must_do", []))):
            errors.append(f"{case_id}: must_do_met length/type does not match rubric")
        if not _bool_list(result.get("must_not_violated"), len(rubric.get("must_not", []))):
            errors.append(f"{case_id}: must_not_violated length/type does not match rubric")

    missing = sorted(expected_ids - seen)
    if missing:
        errors.append(f"judge output missing case IDs: {', '.join(missing)}")
    return errors


def combine_judge_results(judge_docs: Iterable[object]) -> dict:
    results: list[dict] = []
    seen_suites: set[str] = set()
    for doc in judge_docs:
        if not isinstance(doc, dict) or set(doc) != {"suite", "results"}:
            raise ValueError("judge document malformed while combining")
        suite = doc.get("suite")
        if suite not in SUITES or suite in seen_suites:
            raise ValueError(f"judge suite missing, unknown, or duplicated: {suite!r}")
        seen_suites.add(suite)
        if not isinstance(doc.get("results"), list):
            raise ValueError(f"judge suite {suite} has no results list")
        results.extend(doc["results"])
    if seen_suites != set(SUITES):
        raise ValueError(f"expected judge suites {SUITES}, got {sorted(seen_suites)}")
    return {"results": results}


def readiness_report_dict(judge_docs: Iterable[object], root: Path = ROOT) -> dict:
    combined = combine_judge_results(judge_docs)
    report = score_readiness(combined)
    return {
        "ready": report.ready,
        "passed": report.passed,
        "total": report.total,
        "pass_rate": f"{report.pass_rate.numerator}/{report.pass_rate.denominator}",
        "suite_results": [
            {"suite": suite, "passed": passed, "total": total}
            for suite, passed, total in report.suite_results
        ],
        "critical_failures": list(report.critical_failures),
        "critical_violations": list(report.critical_violations),
        "failed_cases": list(report.failed_cases),
        "errors": list(report.errors),
    }


def _write_errors(errors: list[str]) -> int:
    if not errors:
        print("OK")
        return 0
    for error in errors:
        print(error, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    blind = sub.add_parser("validate-blind")
    blind.add_argument("suite", choices=SUITES)
    blind.add_argument("doc", type=Path)
    blind.add_argument("--root", type=Path, default=ROOT)

    judge = sub.add_parser("validate-judge")
    judge.add_argument("suite", choices=SUITES)
    judge.add_argument("blind_doc", type=Path)
    judge.add_argument("judge_doc", type=Path)
    judge.add_argument("--root", type=Path, default=ROOT)

    score = sub.add_parser("score")
    score.add_argument("judge_a", type=Path)
    score.add_argument("judge_b", type=Path)
    score.add_argument("judge_c", type=Path)
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--root", type=Path, default=ROOT)

    args = parser.parse_args(argv)
    if args.command == "validate-blind":
        return _write_errors(validate_blind_output(_load(args.doc), args.suite, args.root))
    if args.command == "validate-judge":
        return _write_errors(
            validate_judge_output(
                _load(args.blind_doc), _load(args.judge_doc), args.suite, args.root
            )
        )

    docs = [_load(args.judge_a), _load(args.judge_b), _load(args.judge_c)]
    report = readiness_report_dict(docs, args.root)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["errors"]:
        print("final readiness evidence is structurally invalid", file=sys.stderr)
        return 3
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
