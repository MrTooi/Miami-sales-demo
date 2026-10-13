from __future__ import annotations

import subprocess
from pathlib import PurePosixPath
from typing import Iterable


PROTECTED_EXACT = {
    "AGENTS.md",
    "PROJECT_BRIEF.md",
    "LAUNCH_RISK_REGISTER.md",
    "requirements.txt",
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

MAX_CHANGED_FILES = 30


def validate_changed_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    errors: list[str] = []
    for raw in paths:
        value = raw.strip().replace("\\", "/")
        if not value:
            continue
        path = str(PurePosixPath(value))
        normalized.append(path)
        if path in PROTECTED_EXACT or path.startswith(PROTECTED_PREFIXES):
            errors.append(f"protected autonomous-control path changed: {path}")

    if len(set(normalized)) > MAX_CHANGED_FILES:
        errors.append(
            f"autonomous change touches {len(set(normalized))} files; limit is {MAX_CHANGED_FILES}"
        )
    return errors


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_paths() -> list[str]:
    tracked = _git_lines(["git", "diff", "--name-only", "HEAD"])
    untracked = _git_lines(["git", "ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked))


def main() -> int:
    paths = changed_paths()
    errors = validate_changed_paths(paths)
    if errors:
        for error in errors:
            print(f"SCOPE GUARD: {error}")
        return 2
    print(f"Scope guard passed for {len(set(paths))} changed file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
