from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


OWNER_LABELS = {
    "owner:backend": "backend",
    "owner:integrations": "integrations",
    "owner:research": "research-product",
    "owner:frontend": "frontend-ux",
    "owner:generalist": "generalist",
    "owner:security": "security-integrity",
}

AREA_LABELS = {
    "area:backend": "backend",
    "area:persistence": "backend",
    "area:api": "backend",
    "area:integrations": "integrations",
    "area:payments": "integrations",
    "area:settlement": "integrations",
    "area:reconciliation": "integrations",
    "area:research": "research-product",
    "area:product": "research-product",
    "area:frontend": "frontend-ux",
    "area:ux": "frontend-ux",
    "area:security": "security-integrity",
}

PRIORITY_LABELS = {
    "priority:p0": 0,
    "priority:p1": 1,
    "priority:p2": 2,
    "priority:p3": 3,
}

HIGH_IMPACT_LABELS = {
    "action:deploy",
    "action:delete",
    "action:publish",
    "action:purchase",
    "data:credentials",
    "data:live-financial",
    "permission:expand",
}

SECURITY_REVIEW_LABELS = {
    "area:auth",
    "area:security",
    "area:integrations",
    "area:payments",
    "area:settlement",
    "area:reconciliation",
    "data:financial",
    "data:credentials",
    "data:live-financial",
    "permission:expand",
}

NON_READY_LIFECYCLE_LABELS = {
    "agent:paused",
    "agent:claimed",
    "agent:working",
    "agent:awaiting-review",
    "agent:blocked",
    "needs:human",
}


@dataclass(frozen=True)
class DispatchPlan:
    issue_number: int
    title: str
    owner: str
    reviewers: tuple[str, ...]
    risk: str
    requires_human_approval: bool
    blocked_external_action: bool
    execution_scope: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _labels(issue: Mapping) -> set[str]:
    labels: set[str] = set()
    for raw in issue.get("labels", []) or []:
        if isinstance(raw, str):
            labels.add(raw)
        elif isinstance(raw, Mapping):
            name = raw.get("name")
            if isinstance(name, str):
                labels.add(name)
    return labels


def is_candidate(issue: Mapping) -> bool:
    if issue.get("state", "open") != "open":
        return False
    if issue.get("pull_request"):
        return False
    labels = _labels(issue)
    if "agent:ready" not in labels:
        return False
    if labels.intersection(NON_READY_LIFECYCLE_LABELS):
        return False
    return True


def _priority(issue: Mapping) -> tuple[int, int]:
    labels = _labels(issue)
    priority = min((value for label, value in PRIORITY_LABELS.items() if label in labels), default=2)
    number = int(issue.get("number", 0))
    return priority, number


def select_next_issue(issues: Sequence[Mapping]) -> Mapping | None:
    candidates = [issue for issue in issues if is_candidate(issue)]
    if not candidates:
        return None
    return min(candidates, key=_priority)


def _infer_owner(labels: set[str]) -> tuple[str, str]:
    explicit = [owner for label, owner in OWNER_LABELS.items() if label in labels]
    if len(explicit) == 1:
        return explicit[0], "explicit owner label"
    if len(explicit) > 1:
        return "generalist", "conflicting owner labels; route to generalist for triage"

    inferred = [owner for label, owner in AREA_LABELS.items() if label in labels]
    unique = sorted(set(inferred))
    if len(unique) == 1:
        return unique[0], "area label routing"
    if len(unique) > 1:
        return "generalist", "multiple specialist areas; route to generalist for triage"
    return "generalist", "no specialist label; safe fallback to generalist"


def _infer_risk(labels: set[str]) -> str:
    # High-impact external actions are never downgradeable by an issue label.
    if labels.intersection(HIGH_IMPACT_LABELS):
        return "high"
    explicit = [risk for risk in ("high", "medium", "low") if f"risk:{risk}" in labels]
    if explicit:
        return explicit[0]
    if labels.intersection(SECURITY_REVIEW_LABELS):
        return "medium"
    # Unknown/unclassified work must not fail open to low risk. A human can
    # explicitly apply risk:low after considering the task contract.
    return "medium"


def _reviewers(owner: str, labels: set[str], risk: str) -> tuple[str, ...]:
    reviewers: list[str] = ["qa-critic"]
    security_needed = (
        risk in {"medium", "high"}
        or owner == "integrations"
        or bool(labels.intersection(SECURITY_REVIEW_LABELS))
    )
    if security_needed and owner != "security-integrity":
        reviewers.append("security-integrity")
    return tuple(reviewers)


def build_dispatch_plan(issue: Mapping) -> DispatchPlan:
    if not is_candidate(issue):
        raise ValueError("issue is not eligible for agent dispatch")

    labels = _labels(issue)
    owner, reason = _infer_owner(labels)
    risk = _infer_risk(labels)
    blocked_external_action = bool(labels.intersection(HIGH_IMPACT_LABELS))
    requires_human_approval = risk == "high" or blocked_external_action
    execution_scope = "branch-only; external action blocked" if blocked_external_action else "branch-only"

    return DispatchPlan(
        issue_number=int(issue["number"]),
        title=str(issue.get("title", "")),
        owner=owner,
        reviewers=_reviewers(owner, labels, risk),
        risk=risk,
        requires_human_approval=requires_human_approval,
        blocked_external_action=blocked_external_action,
        execution_scope=execution_scope,
        reason=reason,
    )


def plan_next_issue(issues: Sequence[Mapping]) -> DispatchPlan | None:
    issue = select_next_issue(issues)
    return build_dispatch_plan(issue) if issue is not None else None
