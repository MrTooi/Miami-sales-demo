from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


class RecoveryError(RuntimeError):
    """Raised when a publication recovery cannot be proven safe."""


_OID_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"could not read trusted recovery JSON {path!s}: {exc}") from exc


def load_manifest(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        raise RecoveryError("scope manifest must be an object with a changes list")
    return payload


def compare_manifests(expected_path: str | Path, observed_path: str | Path) -> None:
    """Require semantic equality between two trusted scope manifests."""

    expected = load_manifest(expected_path)
    observed = load_manifest(observed_path)
    if expected != observed:
        raise RecoveryError("proposal does not match the frozen verified manifest")


def _require_oid(value: str, label: str) -> str:
    if not isinstance(value, str) or not _OID_RE.fullmatch(value):
        raise RecoveryError(f"{label} must be a 40-character lowercase Git object ID")
    return value


def choose_branch_action(
    *,
    remote_exists: bool,
    expected_tree: str,
    base_sha: str,
    remote_tree: str | None = None,
    parent_sha: str | None = None,
    commit_count: int | None = None,
) -> str:
    """Return push/reuse while requiring an exact Git-tree identity for reuse."""

    _require_oid(expected_tree, "expected tree")
    _require_oid(base_sha, "base SHA")
    if not remote_exists:
        return "push"

    if remote_tree is None or parent_sha is None or commit_count is None:
        raise RecoveryError("existing branch requires tree, parent, and commit-count evidence")
    _require_oid(remote_tree, "remote tree")
    _require_oid(parent_sha, "remote parent SHA")
    if commit_count != 1:
        raise RecoveryError("existing proposal branch must contain exactly one commit above the frozen base")
    if parent_sha != base_sha:
        raise RecoveryError("existing proposal branch parent does not equal the frozen base")
    if remote_tree != expected_tree:
        raise RecoveryError("existing proposal Git tree differs from the exact verified proposal tree")
    return "reuse"


def _owner_login(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        login = value.get("login")
        return login if isinstance(login, str) else None
    return None


def choose_pr_action(
    open_prs: list[dict[str, Any]],
    *,
    expected_head_oid: str,
    expected_owner: str,
    expected_base: str = "main",
) -> tuple[str, str | None]:
    """Reuse one exact same-repo draft PR, create when absent, and reject ambiguity."""

    _require_oid(expected_head_oid, "expected PR head")
    if not isinstance(expected_owner, str) or not expected_owner.strip():
        raise RecoveryError("expected repository owner is required")
    if expected_base != "main":
        raise RecoveryError("recovery may target only main")
    if not isinstance(open_prs, list):
        raise RecoveryError("pull request evidence must be a list")
    if len(open_prs) == 0:
        return "create", None
    if len(open_prs) != 1:
        raise RecoveryError("expected at most one open pull request for the proposal branch")

    pr = open_prs[0]
    if not isinstance(pr, dict):
        raise RecoveryError("pull request evidence must contain objects")
    url = pr.get("url")
    if not isinstance(url, str) or not url.startswith("https://github.com/"):
        raise RecoveryError("existing pull request has no trusted GitHub URL")
    if pr.get("isDraft") is not True:
        raise RecoveryError("existing proposal pull request is not draft; human review is required")
    if pr.get("isCrossRepository") is not False:
        raise RecoveryError("existing proposal pull request is cross-repository")
    if _owner_login(pr.get("headRepositoryOwner")) != expected_owner:
        raise RecoveryError("existing proposal pull request has the wrong head repository owner")
    if pr.get("baseRefName") != expected_base:
        raise RecoveryError("existing proposal pull request targets the wrong base branch")
    if pr.get("headRefOid") != expected_head_oid:
        raise RecoveryError("existing proposal pull request does not point at the reviewed commit")
    return "reuse", url


def _cmd_compare(args: argparse.Namespace) -> int:
    compare_manifests(args.expected, args.observed)
    print("manifest-match")
    return 0


def _cmd_branch_action(args: argparse.Namespace) -> int:
    remote_exists = args.remote_tree is not None
    action = choose_branch_action(
        remote_exists=remote_exists,
        expected_tree=args.expected_tree,
        base_sha=args.base_sha,
        remote_tree=args.remote_tree,
        parent_sha=args.parent_sha,
        commit_count=args.commit_count,
    )
    print(action)
    return 0


def _cmd_pr_action(args: argparse.Namespace) -> int:
    payload = _load_json(args.prs_json)
    action, url = choose_pr_action(
        payload,
        expected_head_oid=args.expected_head,
        expected_owner=args.expected_owner,
        expected_base=args.expected_base,
    )
    print(json.dumps({"action": action, "url": url}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed helpers for Agent OS publication recovery")
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("compare-manifests")
    compare.add_argument("--expected", required=True)
    compare.add_argument("--observed", required=True)
    compare.set_defaults(handler=_cmd_compare)

    branch_action = sub.add_parser("branch-action")
    branch_action.add_argument("--expected-tree", required=True)
    branch_action.add_argument("--base-sha", required=True)
    branch_action.add_argument("--remote-tree")
    branch_action.add_argument("--parent-sha")
    branch_action.add_argument("--commit-count", type=int)
    branch_action.set_defaults(handler=_cmd_branch_action)

    pr_action = sub.add_parser("pr-action")
    pr_action.add_argument("--prs-json", required=True)
    pr_action.add_argument("--expected-head", required=True)
    pr_action.add_argument("--expected-owner", required=True)
    pr_action.add_argument("--expected-base", default="main")
    pr_action.set_defaults(handler=_cmd_pr_action)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except RecoveryError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
