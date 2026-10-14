from __future__ import annotations

import argparse
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable


PROTECTED_EXACT = {
    ".gitignore",
    "AGENTS.md",
    "PROJECT_BRIEF.md",
    "LAUNCH_RISK_REGISTER.md",
    "requirements.txt",
    "finance_engine.py",
    "transaction_integrity.py",
    "ledger_store.py",
    "app_ledger.py",
    "opportunity_radar/scoring.py",
    "docs/AGENT_OPERATOR.md",
    "docs/AI_ENGINEERING_PIPELINE.md",
    "tests/test_agent_behavioral_cases.py",
    "tests/test_agent_benchmark.py",
    "tests/test_agent_configuration.py",
    "tests/test_agent_operator.py",
    "tests/test_agent_operator_lifecycle.py",
    "tests/test_agent_operator_workflow.py",
    "tests/test_agent_review_gate.py",
    "tests/test_agent_routing_regressions.py",
    "tests/test_agent_scope_guard.py",
}

PROTECTED_PREFIXES = (
    "agent_operator/",
    "agent_evals/",
    ".github/",
)

BENIGN_GENERATED_PARTS = {"__pycache__", ".pytest_cache"}
MAX_CHANGED_FILES = 30


def _normalize(raw: str) -> str:
    return str(PurePosixPath(raw.strip().replace("\\", "/")))


def _is_benign_generated(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(BENIGN_GENERATED_PARTS.intersection(parts)) or path.endswith((".pyc", ".pyo"))


def validate_changed_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    errors: list[str] = []
    for raw in paths:
        if not raw.strip():
            continue
        path = _normalize(raw)
        if _is_benign_generated(path):
            continue
        normalized.append(path)
        if path in PROTECTED_EXACT or path.startswith(PROTECTED_PREFIXES):
            errors.append(f"protected autonomous-control/high-trust path changed: {path}")

    if len(set(normalized)) > MAX_CHANGED_FILES:
        errors.append(
            f"autonomous change touches {len(set(normalized))} files; limit is {MAX_CHANGED_FILES}"
        )
    return errors


def _git_lines(repo: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_paths(repo: Path, base_sha: str) -> list[str]:
    # Diff from the immutable claimed base, not mutable HEAD, so a model cannot
    # hide changes by committing them before the guard runs.
    tracked = _git_lines(repo, ["diff", "--name-only", base_sha])
    # Intentionally do not use --exclude-standard: a model must not be able to
    # edit .gitignore and thereby hide an untracked file from the guard.
    untracked = _git_lines(repo, ["ls-files", "--others"])
    return sorted(set(tracked + untracked))


def current_head(repo: Path) -> str:
    lines = _git_lines(repo, ["rev-parse", "HEAD"])
    if len(lines) != 1:
        raise RuntimeError("could not determine repository HEAD")
    return lines[0]


def existing_tests_changed(repo: Path, base_sha: str, paths: Iterable[str]) -> list[str]:
    base_tests = set(_git_lines(repo, ["ls-tree", "-r", "--name-only", base_sha, "--", "tests"]))
    changed = []
    for raw in paths:
        path = _normalize(raw)
        if path in base_tests:
            changed.append(path)
    return sorted(set(changed))


def evaluate_repository(repo: Path, base_sha: str) -> tuple[list[str], list[str]]:
    repo = repo.resolve()
    paths = changed_paths(repo, base_sha)
    errors = validate_changed_paths(paths)

    head = current_head(repo)
    if head != base_sha:
        errors.append(
            f"repository HEAD changed from claimed base {base_sha} to {head}; autonomous commits are not allowed"
        )

    for path in existing_tests_changed(repo, base_sha, paths):
        errors.append(f"existing test changed or deleted autonomously: {path}")

    return paths, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce LEDGER autonomous change boundaries.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base-sha", default="HEAD")
    args = parser.parse_args()

    paths, errors = evaluate_repository(args.repo, args.base_sha)
    if errors:
        for error in errors:
            print(f"SCOPE GUARD: {error}")
        if paths:
            print("SCOPE GUARD: observed paths:")
            for path in paths:
                print(f"  - {path}")
        return 2
    visible = [path for path in paths if not _is_benign_generated(path)]
    print(f"Scope guard passed for {len(set(visible))} changed file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
