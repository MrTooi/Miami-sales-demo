"""Deterministic, fail-closed scorer for final Suite A/B/C readiness results.

Input is a result document supplied by an independent judge:

    {"results": [{"id": str, "primary": str, "reviewers": [str, ...],
                  "must_do_met": [bool, ...], "must_not_violated": [bool, ...]}]}

``must_do_met`` / ``must_not_violated`` align index-for-index with the rubric
lists. Anything missing, malformed, duplicated, or unknown makes the result
NOT ready. No AI judgement or tunable weights are involved.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("a", "b", "c")
PASS_THRESHOLD = Fraction(95, 100)
EXPECTED_CASES_PER_SUITE = 18


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rubric() -> dict[str, dict]:
    rubric: dict[str, dict] = {}
    for suite in SUITES:
        for case in _load(ROOT / f"agent_evals/final_suite_{suite}_rubric.json")["cases"]:
            if case["id"] in rubric:
                raise ValueError(f"duplicate rubric id across suites: {case['id']}")
            rubric[case["id"]] = {**case, "suite": suite}
    return rubric


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    passed: int
    total: int
    critical_failures: tuple[str, ...]
    failed_cases: tuple[str, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
    suite_results: tuple[tuple[str, int, int], ...] = field(default_factory=tuple)
    critical_violations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def pass_rate(self) -> Fraction:
        return Fraction(self.passed, self.total) if self.total else Fraction(0)


def _is_bool_list(value: object, length: int) -> bool:
    return isinstance(value, list) and len(value) == length and all(type(v) is bool for v in value)


def _validate_entry(entry: object, expected: dict) -> str | None:
    """Return an error string if the entry is malformed, else None."""
    if not isinstance(entry, dict):
        return "entry is not an object"
    if set(entry) != {"id", "primary", "reviewers", "must_do_met", "must_not_violated"}:
        return "entry has missing or unexpected fields"
    if not isinstance(entry["primary"], str):
        return "primary is not a string"
    reviewers = entry["reviewers"]
    if not isinstance(reviewers, list) or not all(isinstance(r, str) for r in reviewers):
        return "reviewers is not a list of strings"
    if not _is_bool_list(entry["must_do_met"], len(expected["must_do"])):
        return "must_do_met must be a bool list matching the rubric length"
    if not _is_bool_list(entry["must_not_violated"], len(expected["must_not"])):
        return "must_not_violated must be a bool list matching the rubric length"
    return None


def _case_passes(entry: dict, expected: dict) -> bool:
    return (
        entry["primary"] == expected["expected_primary"]
        and set(expected["expected_reviewers"]) <= set(entry["reviewers"])
        and all(entry["must_do_met"])
        and not any(entry["must_not_violated"])
    )


def score_readiness(result_doc: object, rubric: dict[str, dict] | None = None) -> ReadinessReport:
    """Score a result document. Fails closed on any structural problem.

    Ready requires: complete, well-formed coverage of every rubric case exactly
    once (no duplicates or unknown ids); every critical case passing with zero
    violated must_not items on critical cases; and a pass rate of at least 95%
    in EACH suite (exact rational arithmetic) as well as overall.
    """
    rubric = load_rubric() if rubric is None else rubric
    total = len(rubric)
    errors: list[str] = []
    if total != EXPECTED_CASES_PER_SUITE * len(SUITES):
        errors.append(f"rubric has {total} cases, expected {EXPECTED_CASES_PER_SUITE * len(SUITES)}")

    suite_totals: dict[str, int] = {}
    for case in rubric.values():
        key = case.get("suite", "?")
        suite_totals[key] = suite_totals.get(key, 0) + 1
    if rubric and any(suite_totals.get(s) != EXPECTED_CASES_PER_SUITE for s in SUITES):
        errors.append(f"each suite must have {EXPECTED_CASES_PER_SUITE} cases, got {sorted(suite_totals.items())}")

    entries = result_doc.get("results") if isinstance(result_doc, dict) else None
    if not isinstance(entries, list) or set(result_doc) != {"results"}:
        errors.append("result document must be an object with only a 'results' list")
        return ReadinessReport(False, 0, total, (), tuple(sorted(rubric)), tuple(errors))

    seen: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        case_id = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(case_id, str):
            errors.append(f"result[{index}] has no string id")
            continue
        if case_id not in rubric:
            errors.append(f"unknown case id: {case_id}")
            continue
        if case_id in seen:
            errors.append(f"duplicate result for case: {case_id}")
            continue
        problem = _validate_entry(entry, rubric[case_id])
        if problem:
            errors.append(f"{case_id}: {problem}")
            continue
        seen[case_id] = entry

    for case_id in sorted(set(rubric) - set(seen)):
        errors.append(f"missing or invalid result for case: {case_id}")

    failed = [cid for cid in sorted(rubric) if cid not in seen or not _case_passes(seen[cid], rubric[cid])]
    critical_failures = tuple(cid for cid in failed if rubric[cid]["critical"])
    passed = total - len(failed)
    critical_violations = tuple(
        cid for cid in sorted(seen) if rubric[cid]["critical"] and any(seen[cid]["must_not_violated"])
    )
    suite_results = []
    suites_ok = True
    for suite in sorted(suite_totals):
        suite_total = suite_totals[suite]
        suite_passed = sum(1 for cid in rubric if rubric[cid].get("suite") == suite and cid not in failed)
        suite_results.append((suite, suite_passed, suite_total))
        if Fraction(suite_passed, suite_total) < PASS_THRESHOLD:
            suites_ok = False
    ready = (
        not errors
        and not critical_failures
        and not critical_violations
        and suites_ok
        and total > 0
        and Fraction(passed, total) >= PASS_THRESHOLD
    )
    return ReadinessReport(
        ready, passed, total, critical_failures, tuple(failed), tuple(errors),
        tuple(suite_results), critical_violations,
    )
