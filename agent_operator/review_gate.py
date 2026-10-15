from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_VERDICTS = {"pass", "fail", "needs-human"}
ALLOWED_SEVERITIES = {"blocking", "important", "minor"}
SERIOUS_SEVERITIES = {"blocking", "important"}
REQUIRED_REVIEW_KEYS = {"verdict", "summary", "findings", "tests"}
REQUIRED_FINDING_KEYS = {"severity", "title", "evidence"}


def load_review(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    if set(payload) != REQUIRED_REVIEW_KEYS:
        raise ValueError(
            f"{path} must contain exactly {sorted(REQUIRED_REVIEW_KEYS)!r}; "
            f"received {sorted(payload)!r}"
        )

    verdict = payload["verdict"]
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"{path} has unsupported verdict: {verdict!r}")
    if not isinstance(payload["summary"], str):
        raise ValueError(f"{path} is missing a string summary")

    tests = payload["tests"]
    if not isinstance(tests, list) or any(not isinstance(test, str) for test in tests):
        raise ValueError(f"{path} must contain a tests list of strings")

    findings = payload["findings"]
    if not isinstance(findings, list):
        raise ValueError(f"{path} is missing findings list")
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError(f"{path} contains a non-object finding")
        if set(finding) != REQUIRED_FINDING_KEYS:
            raise ValueError(
                f"{path} finding must contain exactly {sorted(REQUIRED_FINDING_KEYS)!r}; "
                f"received {sorted(finding)!r}"
            )
        severity = finding["severity"]
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"{path} has unsupported finding severity: {severity!r}")
        if not isinstance(finding["title"], str) or not isinstance(finding["evidence"], str):
            raise ValueError(f"{path} contains a malformed finding")
    return payload


def _review_passes(review: dict) -> bool:
    if review["verdict"] != "pass":
        return False
    return not any(
        finding.get("severity") in SERIOUS_SEVERITIES
        for finding in review.get("findings", [])
        if isinstance(finding, dict)
    )


def evaluate(paths: list[Path]) -> tuple[bool, list[dict]]:
    reviews = [load_review(path) for path in paths]
    return all(_review_passes(review) for review in reviews), reviews


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate structured AI reviewer outputs.")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    passed, reviews = evaluate(args.paths)
    for path, review in zip(args.paths, reviews):
        print(f"{path.name}: {review['verdict']} — {review['summary']}")
        for finding in review["findings"]:
            if isinstance(finding, dict):
                print(
                    f"  - {finding.get('severity', 'unknown')}: "
                    f"{finding.get('title', 'untitled')} — {finding.get('evidence', '')}"
                )
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
