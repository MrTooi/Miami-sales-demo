from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Iterable


PROTECTED_EXACT = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "PROJECT_BRIEF.md",
    "LAUNCH_RISK_REGISTER.md",
    "requirements.txt",
    "pyproject.toml",
    "setup.cfg",
    "pytest.ini",
    "conftest.py",
    "sitecustomize.py",
    "usercustomize.py",
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

# Prefixes are protected both for existing files and for new files that could
# shadow a protected top-level module/package on Python's import path.
PROTECTED_PREFIXES = (
    "agent_operator/",
    "agent_evals/",
    ".github/",
    "finance_engine/",
    "transaction_integrity/",
    "ledger_store/",
    "app_ledger/",
    "opportunity_radar/scoring/",
)

BENIGN_GENERATED_PARTS = {"__pycache__", ".pytest_cache"}
MAX_CHANGED_FILES = 30
MANIFEST_VERSION = 1


def _normalize(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe repository path: {raw!r}")
    return str(path)


def _is_benign_generated(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(BENIGN_GENERATED_PARTS.intersection(parts)) or path.endswith((".pyc", ".pyo"))


def _git_file_mode(mode: int) -> int:
    """Normalize regular-file permissions to the mode Git actually preserves.

    Git tracks whether a regular file is executable, but not ordinary read/write
    permission differences. Verification deliberately makes trusted inputs
    read-only before proposed tests execute, so comparing full POSIX modes would
    turn that safety lock into a false repository-wide change. Preserve only the
    executable distinction so executable-bit additions remain detectable.
    """

    return 0o755 if mode & 0o111 else 0o644


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raise_walk_error(error: OSError) -> None:
    raise error


def load_allowed_paths(task_contract_path: Path) -> tuple[str, ...]:
    payload = json.loads(task_contract_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("task contract must be a JSON object")
    raw_paths = payload.get("allowed_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("task contract is missing a non-empty allowed_paths list")
    normalized: list[str] = []
    for raw in raw_paths:
        if not isinstance(raw, str):
            raise ValueError("task contract allowed_paths must contain only strings")
        normalized.append(_normalize(raw))
    if len(set(normalized)) != len(normalized):
        raise ValueError("task contract allowed_paths contains duplicates")
    return tuple(normalized)


def snapshot_tree(root: Path) -> dict[str, dict]:
    """Return a git-independent snapshot of repository-visible filesystem state.

    `.git/` is intentionally excluded. The implementation workspace's index,
    config, hooks, rename detection, and ignore rules are therefore not trusted
    inputs to the autonomous scope decision. Filesystem traversal fails closed
    on unreadable entries rather than silently omitting them.
    """

    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository tree does not exist: {root}")

    snapshot: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=_raise_walk_error,
    ):
        directory = Path(dirpath)

        kept_dirs: list[str] = []
        for name in dirnames:
            path = directory / name
            rel = path.relative_to(root).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            if path.is_symlink():
                snapshot[rel] = {"kind": "symlink", "target": os.readlink(path)}
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs

        for name in filenames:
            path = directory / name
            rel = path.relative_to(root).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            if path.is_symlink():
                snapshot[rel] = {"kind": "symlink", "target": os.readlink(path)}
                continue

            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                snapshot[rel] = {
                    "kind": "file",
                    "sha256": _sha256(path),
                    "mode": _git_file_mode(info.st_mode),
                    "size": info.st_size,
                }
            else:
                snapshot[rel] = {
                    "kind": "special",
                    "mode": stat.S_IMODE(info.st_mode),
                }

    return dict(sorted(snapshot.items()))


def diff_snapshots(base: dict[str, dict], current: dict[str, dict]) -> list[dict]:
    changes: list[dict] = []
    for path in sorted(set(base) | set(current)):
        before = base.get(path)
        after = current.get(path)
        if before == after:
            continue

        # Generated caches that exist only in the implementation workspace are
        # ignored because publication is rebuilt from this manifest rather than
        # from the model-controlled tree. A base/tracked cache is never ignored.
        if before is None and after is not None and _is_benign_generated(path):
            continue

        if before is None:
            operation = "add"
        elif after is None:
            operation = "delete"
        else:
            operation = "modify"
        changes.append(
            {
                "path": _normalize(path),
                "operation": operation,
                "before": before,
                "after": after,
            }
        )
    return changes


def validate_changed_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    errors: list[str] = []
    for raw in paths:
        path = _normalize(raw)
        normalized.append(path)
        if path in PROTECTED_EXACT or path.startswith(PROTECTED_PREFIXES):
            errors.append(f"protected autonomous-control/high-trust path changed: {path}")

    if len(set(normalized)) > MAX_CHANGED_FILES:
        errors.append(
            f"autonomous change touches {len(set(normalized))} files; limit is {MAX_CHANGED_FILES}"
        )
    return errors


def validate_changes(
    changes: list[dict],
    base_snapshot: dict[str, dict],
    *,
    allowed_paths: tuple[str, ...] | None = None,
) -> list[str]:
    errors = validate_changed_paths(change["path"] for change in changes)
    allowed = set(allowed_paths) if allowed_paths is not None else None

    for change in changes:
        path = change["path"]
        operation = change["operation"]
        before = change.get("before")
        after = change.get("after")
        posix = PurePosixPath(path)

        if allowed is not None and path not in allowed:
            errors.append(f"path is outside the frozen task allowlist: {path}")

        if operation == "delete":
            errors.append(f"autonomous deletion requires human review: {path}")

        if operation == "modify" and isinstance(before, dict) and before.get("kind") != "file":
            errors.append(f"autonomous replacement of a non-regular base entry is not allowed: {path}")

        if path.startswith("tests/"):
            if path in base_snapshot:
                errors.append(f"existing test changed or deleted autonomously: {path}")
            else:
                valid_new_test = posix.name.startswith("test_") and posix.suffix == ".py"
                if not valid_new_test:
                    errors.append(f"new test path is not an allowed test module: {path}")

        if after is not None and after.get("kind") != "file":
            errors.append(f"autonomous non-regular file change is not allowed: {path}")

        if after is not None and after.get("kind") == "file":
            before_mode = before.get("mode") if isinstance(before, dict) else None
            after_mode = after.get("mode")
            before_exec = bool(before_mode and before_mode & 0o111)
            after_exec = bool(after_mode and after_mode & 0o111)
            if after_exec and not before_exec:
                errors.append(f"autonomous executable-bit addition is not allowed: {path}")

    return errors


def build_manifest(
    source: Path,
    base_tree: Path,
    *,
    allowed_paths: tuple[str, ...] | None = None,
) -> tuple[dict, list[str]]:
    base_snapshot = snapshot_tree(base_tree)
    current_snapshot = snapshot_tree(source)
    changes = diff_snapshots(base_snapshot, current_snapshot)
    errors = validate_changes(changes, base_snapshot, allowed_paths=allowed_paths)
    manifest = {"version": MANIFEST_VERSION, "changes": changes}
    return manifest, errors


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
        raise ValueError("unsupported or malformed change manifest")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        raise ValueError("change manifest is missing changes list")
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("change manifest contains a non-object entry")
        _normalize(str(change.get("path", "")))
        if change.get("operation") not in {"add", "modify", "delete"}:
            raise ValueError("change manifest contains unsupported operation")
    return payload


def _assert_safe_destination(destination: Path, rel: str) -> Path:
    destination = destination.resolve()
    relative = PurePosixPath(_normalize(rel))
    current = destination
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"destination parent is a symlink: {rel}")
    target = destination.joinpath(*relative.parts)
    if target.is_symlink():
        raise ValueError(f"destination path is a symlink: {rel}")
    try:
        target.resolve(strict=False).relative_to(destination)
    except ValueError as exc:
        raise ValueError(f"destination escapes clean checkout: {rel}") from exc
    return target


def apply_manifest(source: Path, destination: Path, manifest: dict) -> None:
    """Materialize verified regular-file changes into a clean base checkout.

    The destination must still match the manifest's recorded base entry for a
    modification. This prevents future symlink/base-tree changes from turning a
    verified file copy into a write outside the intended repository path.
    """

    source = source.resolve()
    destination = destination.resolve()
    for change in manifest["changes"]:
        rel = _normalize(change["path"])
        operation = change["operation"]
        src = source / rel
        dst = _assert_safe_destination(destination, rel)

        if operation == "delete":
            raise ValueError(f"refusing to materialize autonomous deletion: {rel}")

        expected = change.get("after") or {}
        if expected.get("kind") != "file" or not src.is_file() or src.is_symlink():
            raise ValueError(f"verified source is not a regular file: {rel}")
        if _sha256(src) != expected.get("sha256"):
            raise ValueError(f"source changed after verification: {rel}")

        before = change.get("before")
        if operation == "modify":
            if not isinstance(before, dict) or before.get("kind") != "file":
                raise ValueError(f"refusing to replace non-regular base entry: {rel}")
            if not dst.is_file() or dst.is_symlink():
                raise ValueError(f"clean destination no longer matches regular base file: {rel}")
            if _sha256(dst) != before.get("sha256"):
                raise ValueError(f"clean destination changed before materialization: {rel}")
        elif operation == "add" and (dst.exists() or dst.is_symlink()):
            raise ValueError(f"clean destination unexpectedly already exists: {rel}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        os.chmod(dst, int(expected["mode"]))


def _check_command(args: argparse.Namespace) -> int:
    allowed_paths = load_allowed_paths(args.allowed_paths_file)
    manifest, errors = build_manifest(
        args.source,
        args.base_tree,
        allowed_paths=allowed_paths,
    )
    write_manifest(args.manifest_out, manifest)
    if errors:
        for error in errors:
            print(f"SCOPE GUARD: {error}")
        if manifest["changes"]:
            print("SCOPE GUARD: observed changes:")
            for change in manifest["changes"]:
                print(f"  - {change['operation']}: {change['path']}")
        return 2
    print(f"Scope guard passed for {len(manifest['changes'])} changed file(s).")
    return 0


def _apply_command(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    apply_manifest(args.source, args.destination, manifest)
    print(f"Materialized {len(manifest['changes'])} verified change(s) into clean checkout.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce LEDGER autonomous change boundaries.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Compare a workspace to a trusted base tree")
    check.add_argument("--source", type=Path, required=True)
    check.add_argument("--base-tree", type=Path, required=True)
    check.add_argument("--allowed-paths-file", type=Path, required=True)
    check.add_argument("--manifest-out", type=Path, required=True)
    check.set_defaults(handler=_check_command)

    apply = subparsers.add_parser("apply", help="Apply a verified manifest to a clean checkout")
    apply.add_argument("--source", type=Path, required=True)
    apply.add_argument("--destination", type=Path, required=True)
    apply.add_argument("--manifest", type=Path, required=True)
    apply.set_defaults(handler=_apply_command)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
