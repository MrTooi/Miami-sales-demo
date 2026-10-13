from __future__ import annotations

import argparse
import os

from .github_client import GitHubClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Transition a queued agent issue lifecycle state.")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--comment", default="")
    args = parser.parse_args()

    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    client = GitHubClient(repository, token)
    client.ensure_managed_labels()
    client.set_lifecycle(args.issue, args.state)
    if args.comment.strip():
        client.comment(args.issue, args.comment.strip())
    print(f"Issue #{args.issue} transitioned to {args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
