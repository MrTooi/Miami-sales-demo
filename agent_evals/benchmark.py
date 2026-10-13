from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "agent_evals" / "team_profiles.json"
SCENARIOS_PATH = ROOT / "agent_evals" / "scenarios.json"


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    covered: bool
    missing_capabilities: tuple[str, ...]
    high_risk_review_ready: bool


@dataclass(frozen=True)
class TeamResult:
    lineup: str
    scenario_results: tuple[ScenarioResult, ...]

    @property
    def coverage_rate(self) -> float:
        if not self.scenario_results:
            return 0.0
        return sum(result.covered for result in self.scenario_results) / len(self.scenario_results)

    @property
    def high_risk_review_rate(self) -> float:
        high_risk = [result for result in self.scenario_results if result.high_risk_review_ready is not None]
        if not high_risk:
            return 1.0
        return sum(result.high_risk_review_ready for result in high_risk) / len(high_risk)

    @property
    def score(self) -> float:
        return round((self.coverage_rate * 80.0) + (self.high_risk_review_rate * 20.0), 2)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profiles() -> dict:
    return _load_json(PROFILES_PATH)


def load_scenarios() -> list[dict]:
    return _load_json(SCENARIOS_PATH)["scenarios"]


def lineup_capabilities(profile_data: dict, lineup: str) -> set[str]:
    agents = profile_data["agents"]
    names = profile_data["lineups"][lineup]
    capabilities: set[str] = set()
    for name in names:
        capabilities.update(agents[name]["capabilities"])
    return capabilities


def independent_review_capabilities(profile_data: dict, lineup: str) -> set[str]:
    agents = profile_data["agents"]
    names = profile_data["lineups"][lineup]
    capabilities: set[str] = set()
    for name in names:
        if agents[name].get("independent_review"):
            capabilities.update(agents[name]["capabilities"])
    return capabilities


def _high_risk_review_ready(required: Iterable[str], reviewer_caps: set[str]) -> bool:
    required = set(required)
    # High-risk work must have independent quality review and independent
    # security/data-integrity review where those concerns are present.
    if "testing" in required or "release" in required:
        if not ({"qa", "testing"} & reviewer_caps):
            return False
    if required & {"security", "auth", "privacy", "tenant_isolation", "data_integrity", "agent_governance", "risk_triage"}:
        if not ({"security", "data_integrity", "agent_governance"} & reviewer_caps):
            return False
    return True


def benchmark_lineup(lineup: str) -> TeamResult:
    profile_data = load_profiles()
    capabilities = lineup_capabilities(profile_data, lineup)
    reviewer_caps = independent_review_capabilities(profile_data, lineup)
    results: list[ScenarioResult] = []

    for scenario in load_scenarios():
        required = set(scenario["required"])
        missing = tuple(sorted(required - capabilities))
        covered = not missing
        review_ready = True
        if scenario["risk"] == "high":
            review_ready = _high_risk_review_ready(required, reviewer_caps)
        results.append(
            ScenarioResult(
                scenario_id=scenario["id"],
                covered=covered,
                missing_capabilities=missing,
                high_risk_review_ready=review_ready,
            )
        )

    return TeamResult(lineup=lineup, scenario_results=tuple(results))


def benchmark_all() -> list[TeamResult]:
    data = load_profiles()
    return [benchmark_lineup(name) for name in data["lineups"]]


def best_lineup() -> TeamResult:
    return max(benchmark_all(), key=lambda result: result.score)


if __name__ == "__main__":
    for result in sorted(benchmark_all(), key=lambda item: item.score, reverse=True):
        print(
            f"{result.lineup}: score={result.score:.2f} "
            f"coverage={result.coverage_rate:.1%} "
            f"high_risk_review={result.high_risk_review_rate:.1%}"
        )
        for scenario in result.scenario_results:
            if not scenario.covered:
                print(f"  MISS {scenario.scenario_id}: {', '.join(scenario.missing_capabilities)}")
