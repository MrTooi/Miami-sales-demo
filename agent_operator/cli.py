from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from .core import plan_next_issue


API_ROOT = "https://api.github.com"


def _github_get(url: str, token: str) -> object:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ledger-agent-operator",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_ready_issues(repository: str, token: str) -> list[dict]:
    encoded_label = quote("agent:ready")
    url = f"{API_ROOT}/repos/{repository}/issues?state=open&labels={encoded_label}&per_page=100"
    payload = _github_get(url, token)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub issues response was not a list")
    return [item for item in payload if isinstance(item, dict)]


def _write_summary(plan: dict | None, summary_path: str | None) -> None:
    if not summary_path:
        return
    path = Path(summary_path)
    if plan is None:
        text = "## LEDGER AI Team Operator\n\nNo eligible `agent:ready` issue was found.\n"
    else:
        reviewers = ", ".join(plan["reviewers"]) or "none"
        text = (
            "## LEDGER AI Team Operator\n\n"
            f"Planned issue **#{plan['issue_number']} — {plan['title']}**\n\n"
            f"- Owner: `{plan['owner']}`\n"
            f"- Reviewers: `{reviewers}`\n"
            f"- Risk: `{plan['risk']}`\n"
            f"- Human approval required: `{str(plan['requires_human_approval']).lower()}`\n"
            f"- Execution scope: `{plan['execution_scope']}`\n"
            f"- Routing reason: {plan['reason']}\n\n"
            "This foundation workflow plans work only. It does not invoke an AI model, mutate issues, create branches, merge code, or perform external actions.\n"
        )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    output_path = Path(os.environ.get("AGENT_OPERATOR_OUTPUT", "agent_operator_plan.json"))

    if not repository:
        raise SystemExit("GITHUB_REPOSITORY is required")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    issues = fetch_ready_issues(repository, token)
    plan = plan_next_issue(issues)
    serialized = plan.to_dict() if plan is not None else None
    output_path.write_text(json.dumps(serialized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_summary(serialized, os.environ.get("GITHUB_STEP_SUMMARY"))
    print(json.dumps(serialized, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
