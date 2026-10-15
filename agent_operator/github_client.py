from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .lifecycle import HUMAN_STOP_LABELS, LIFECYCLE_LABELS, MANAGED_LABELS, transition_labels


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

    def _delete_label(self, issue_number: int, label: str) -> None:
        encoded = quote(label, safe="")
        try:
            self._request(
                "DELETE",
                f"/repos/{self.repository}/issues/{issue_number}/labels/{encoded}",
            )
        except HTTPError as exc:
            if exc.code != 404:
                raise

    def set_lifecycle(self, issue_number: int, target: str) -> dict:
        issue = self.get_issue(issue_number)
        current = self.label_names(issue)

        # Human stop labels always outrank automation. This validation also
        # catches a stop that landed after an earlier queue read.
        transition_labels(current, target)
        if target == "agent:claimed" and "agent:ready" not in current:
            raise RuntimeError(
                f"issue #{issue_number} is no longer agent:ready; refusing autonomous claim"
            )

        # Add the target before removing the previous lifecycle label. For a
        # claim this gives us a second observation point where agent:ready must
        # still exist; a human removing it before claim completion fails closed.
        self._request(
            "POST",
            f"/repos/{self.repository}/issues/{issue_number}/labels",
            {"labels": [target]},
        )
        after_add = self.get_issue(issue_number)
        after_add_labels = self.label_names(after_add)
        active_stops = after_add_labels.intersection(HUMAN_STOP_LABELS)
        if target != "needs:human" and active_stops:
            if target not in current:
                self._delete_label(issue_number, target)
            raise RuntimeError(
                f"human stop arrived during lifecycle transition for issue #{issue_number}: "
                f"{sorted(active_stops)}"
            )
        if target == "agent:claimed" and "agent:ready" not in after_add_labels:
            if target not in current:
                self._delete_label(issue_number, target)
            raise RuntimeError(
                f"agent:ready was removed while claiming issue #{issue_number}; claim aborted"
            )

        # Remove only lifecycle labels that were present in our initial read.
        # A human stop label added after that read is never deleted here.
        for label in sorted((current & LIFECYCLE_LABELS) - {target}):
            self._delete_label(issue_number, label)

        updated = self.get_issue(issue_number)
        updated_labels = self.label_names(updated)
        final_stops = updated_labels.intersection(HUMAN_STOP_LABELS)
        if target != "needs:human" and final_stops:
            if target not in current:
                self._delete_label(issue_number, target)
            raise RuntimeError(
                f"human stop won lifecycle race for issue #{issue_number}: {sorted(final_stops)}"
            )

        lifecycle = updated_labels.intersection(LIFECYCLE_LABELS)
        if lifecycle != {target}:
            raise RuntimeError(
                f"lifecycle transition race detected for issue #{issue_number}: {sorted(lifecycle)}"
            )
        return updated

    def comment(self, issue_number: int, body: str) -> None:
        if not body.strip():
            return
        self._request(
            "POST",
            f"/repos/{self.repository}/issues/{issue_number}/comments",
            {"body": body},
        )
