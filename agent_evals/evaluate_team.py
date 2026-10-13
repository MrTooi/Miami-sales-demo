"""Deterministic structural benchmark for the repository AI team.

This evaluator measures whether the declared team has an explicit owner/reviewer
for representative work. It does NOT prove that an LLM will behave correctly.
Behavioral agent evals must be added once a runnable agent runtime is available.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    passed: bool
    owner_ids: tuple[str, ...]
    missing_owner_capabilities: tuple[str, ...]
    missing_team_capabilities: tuple[str, ...]
    missing_review_capabilities: tuple[str, ...]
    missing_human_approval_gate: bool


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _capabilities(agent: dict[str, Any]) -> set[str]:
    return set(agent.get("capabilities", []))


def evaluate(manifest: dict[str, Any], benchmark: dict[str, Any]) -> list[CaseResult]:
    agents = manifest.get("agents", [])
    team_capabilities: set[str] = set()
    for agent in agents:
        team_capabilities.update(_capabilities(agent))

    results: list[CaseResult] = []

    for case in benchmark.get("cases", []):
        owner_required = set(case.get("owner_capabilities", []))
        team_required = set(case.get("team_required_capabilities", []))
        review_required = set(case.get("required_review_capabilities", []))

        eligible_owners = [
            agent
            for agent in agents
            if agent.get("can_own_task", False)
            and owner_required.issubset(_capabilities(agent))
        ]
        owner_ids = {agent["id"] for agent in eligible_owners}

        owner_union: set[str] = set()
        for agent in agents:
            if agent.get("can_own_task", False):
                owner_union.update(_capabilities(agent))

        missing_owner = owner_required - owner_union if not eligible_owners else set()
        missing_team = team_required - team_capabilities

        missing_review: set[str] = set()
        for review_capability in review_required:
            reviewer_exists = any(
                agent.get("independent_reviewer", False)
                and agent.get("id") not in owner_ids
                and review_capability in _capabilities(agent)
                for agent in agents
            )
            if not reviewer_exists:
                missing_review.add(review_capability)

        approval_required = bool(case.get("requires_human_approval", False))
        missing_approval = approval_required and "human_approval_gate" not in team_capabilities

        passed = bool(eligible_owners) and not (
            missing_owner or missing_team or missing_review or missing_approval
        )

        results.append(
            CaseResult(
                case_id=case["id"],
                passed=passed,
                owner_ids=tuple(sorted(owner_ids)),
                missing_owner_capabilities=tuple(sorted(missing_owner)),
                missing_team_capabilities=tuple(sorted(missing_team)),
                missing_review_capabilities=tuple(sorted(missing_review)),
                missing_human_approval_gate=missing_approval,
            )
        )

    return results


def summary(results: list[CaseResult]) -> dict[str, Any]:
    passed = sum(result.passed for result in results)
    total = len(results)
    return {
        "passed": passed,
        "total": total,
        "coverage_percent": round((passed / total) * 100, 1) if total else 0.0,
        "failed_cases": [result.case_id for result in results if not result.passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate AI team structural coverage")
    parser.add_argument(
        "manifest",
        nargs="?",
        default=str(ROOT / "agent_evals" / "team_manifest.json"),
        help="Path to a team manifest JSON file",
    )
    parser.add_argument(
        "--benchmark",
        default=str(ROOT / "agent_evals" / "benchmark_cases.json"),
        help="Path to benchmark cases JSON",
    )
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    benchmark = load_json(Path(args.benchmark))
    results = evaluate(manifest, benchmark)
    report = summary(results)

    print(json.dumps(report, indent=2))
    for result in results:
        if result.passed:
            continue
        print(
            f"FAIL {result.case_id}: owners={list(result.owner_ids)} "
            f"missing_owner={list(result.missing_owner_capabilities)} "
            f"missing_team={list(result.missing_team_capabilities)} "
            f"missing_review={list(result.missing_review_capabilities)} "
            f"missing_approval={result.missing_human_approval_gate}"
        )

    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
