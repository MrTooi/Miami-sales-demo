from __future__ import annotations

import subprocess
from pathlib import PurePosixPath
from typing import Iterable


PROTECTED_EXACT = {
    "AGENTS.md",
    "docs/AGENT_OPERATOR.md",
    "docs/AI_ENGINEERING_PIPELINE.md",
    ".github/workflows/agent-operator.yml",
    ".github/workflows/agent-executor.yml",
}

PROTECTED_PREFIXES = (
    "agent_operator/",
    ".github/agents/",
    ".github/skills/",
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


def changed_paths() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        check=True,
        stdout=subprocess.PIPE,
        text=False,
    )
    entries = result.stdout.decode("utf-8", errors="strict").split("\0")
    paths: list[str] = []
    for entry in entries:
        if not entry:
            continue
        # XY<space>path. Renames may be rendered as old -> new; validate both.
        payload = entry[3:] if len(entry) >= 3 else entry
        if " -> " in payload:
            old, new = payload.split(" -> ", 1)
            paths.extend([old, new])
        else:
            paths.append(payload)
    return paths


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
