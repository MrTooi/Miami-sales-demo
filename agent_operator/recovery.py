from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class RecoveryError(RuntimeError):
    """Raised when a publication recovery cannot be proven safe."""


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
        raise RecoveryError("existing proposal does not match the frozen verified manifest")


def choose_branch_action(
    *,
    remote_exists: bool,
    expected_manifest: dict[str, Any],
    remote_manifest: dict[str, Any] | None = None,
) -> str:
    """Return push/reuse while failing closed on an unexpected remote proposal."""

    if not remote_exists:
        return "push"
    if remote_manifest is None:
        raise RecoveryError("existing branch requires independently reconstructed manifest evidence")
    if expected_manifest != remote_manifest:
        raise RecoveryError("existing branch differs from the frozen verified proposal")
    return "reuse"


def choose_pr_action(open_prs: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Reuse one existing draft PR, create when absent, and reject ambiguity."""

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
    return "reuse", url


def _cmd_compare(args: argparse.Namespace) -> int:
    compare_manifests(args.expected, args.observed)
    print("manifest-match")
    return 0


def _cmd_pr_action(args: argparse.Namespace) -> int:
    payload = _load_json(args.prs_json)
    action, url = choose_pr_action(payload)
    print(json.dumps({"action": action, "url": url}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed helpers for Agent OS publication recovery")
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("compare-manifests")
    compare.add_argument("--expected", required=True)
    compare.add_argument("--observed", required=True)
    compare.set_defaults(handler=_cmd_compare)

    pr_action = sub.add_parser("pr-action")
    pr_action.add_argument("--prs-json", required=True)
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
