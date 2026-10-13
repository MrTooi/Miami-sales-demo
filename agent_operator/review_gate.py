from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_VERDICTS = {"pass", "fail", "needs-human"}


def load_review(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    verdict = payload.get("verdict")
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"{path} has unsupported verdict: {verdict!r}")
    if not isinstance(payload.get("summary"), str):
        raise ValueError(f"{path} is missing a string summary")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError(f"{path} is missing findings list")
    return payload


def evaluate(paths: list[Path]) -> tuple[bool, list[dict]]:
    reviews = [load_review(path) for path in paths]
    return all(review["verdict"] == "pass" for review in reviews), reviews


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
