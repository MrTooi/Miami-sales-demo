from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .lifecycle import MANAGED_LABELS, transition_labels


API_ROOT = "https://api.github.com"


class GitHubClient:
    def __init__(self, repository: str, token: str) -> None:
        if not repository:
            raise ValueError("repository is required")
        if not token:
            raise ValueError("token is required")
        self.repository = repository
        self.token = token

    def _request(self, method: str, path: str, payload: dict | None = None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{API_ROOT}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ledger-agent-operator",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None

    def get_issue(self, issue_number: int) -> dict:
        payload = self._request("GET", f"/repos/{self.repository}/issues/{issue_number}")
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub issue response was not an object")
        return payload

    def ensure_managed_labels(self) -> None:
        for name, (color, description) in MANAGED_LABELS.items():
            encoded = quote(name, safe="")
            try:
                self._request("GET", f"/repos/{self.repository}/labels/{encoded}")
            except HTTPError as exc:
                if exc.code != 404:
                    raise
                self._request(
                    "POST",
                    f"/repos/{self.repository}/labels",
                    {"name": name, "color": color, "description": description},
                )

    @staticmethod
    def label_names(issue: dict) -> set[str]:
        result: set[str] = set()
        for raw in issue.get("labels", []) or []:
            if isinstance(raw, str):
                result.add(raw)
            elif isinstance(raw, dict) and isinstance(raw.get("name"), str):
                result.add(raw["name"])
        return result

    def set_lifecycle(self, issue_number: int, target: str) -> dict:
        issue = self.get_issue(issue_number)
        transition = transition_labels(self.label_names(issue), target)
        payload = self._request(
            "PATCH",
            f"/repos/{self.repository}/issues/{issue_number}",
            {"labels": sorted(transition.current)},
        )
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub update response was not an object")
        return payload

    def comment(self, issue_number: int, body: str) -> None:
        if not body.strip():
            return
        self._request(
            "POST",
            f"/repos/{self.repository}/issues/{issue_number}/comments",
            {"body": body},
        )
