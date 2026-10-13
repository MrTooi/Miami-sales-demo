from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


LIFECYCLE_LABELS = {
    "agent:ready",
    "agent:claimed",
    "agent:working",
    "agent:awaiting-review",
    "agent:blocked",
    "needs:human",
}

# Labels the operator may rely on for queueing, routing, risk classification,
# and human gates. The executor bootstraps these before it reads the queue so a
# fresh repository cannot silently fall back to Generalist because a routing
# label was never created.
MANAGED_LABELS = {
    # Lifecycle
    "agent:ready": ("1d76db", "Approved for autonomous agent pickup"),
    "agent:claimed": ("fbca04", "Claimed by the background AI operator"),
    "agent:working": ("0e8a16", "Background AI execution is in progress"),
    "agent:awaiting-review": ("5319e7", "Agent work is ready for review"),
    "agent:blocked": ("d93f0b", "Agent execution stopped and needs intervention"),
    "agent:paused": ("cfd3d7", "Paused; autonomous agents must not pick up this task"),
    "needs:human": ("b60205", "Human approval or decision is required"),

    # Priority
    "priority:p0": ("b60205", "Highest-priority queued work"),
    "priority:p1": ("d93f0b", "High-priority queued work"),
    "priority:p2": ("fbca04", "Normal-priority queued work"),
    "priority:p3": ("cfd3d7", "Low-priority queued work"),

    # Explicit owners
    "owner:backend": ("0052cc", "Route primarily to Backend Engineer"),
    "owner:integrations": ("0052cc", "Route primarily to Integrations Engineer"),
    "owner:research": ("0052cc", "Route primarily to Research & Product Analyst"),
    "owner:frontend": ("0052cc", "Route primarily to Frontend & UX Engineer"),
    "owner:generalist": ("0052cc", "Route primarily to Generalist Operator"),
    "owner:security": ("0052cc", "Route primarily to Security & Data Integrity"),

    # Area routing
    "area:backend": ("0e8a16", "Backend/domain/service work"),
    "area:persistence": ("0e8a16", "Persistence/database work"),
    "area:api": ("0e8a16", "API/service-boundary work"),
    "area:integrations": ("0e8a16", "Third-party integration work"),
    "area:payments": ("0e8a16", "Payment-provider work"),
    "area:settlement": ("0e8a16", "Settlement/reconciliation work"),
    "area:reconciliation": ("0e8a16", "Cross-source reconciliation work"),
    "area:research": ("0e8a16", "Research/evidence work"),
    "area:product": ("0e8a16", "Product analysis/requirements work"),
    "area:frontend": ("0e8a16", "Frontend implementation work"),
    "area:ux": ("0e8a16", "UX/accessibility work"),
    "area:security": ("0e8a16", "Security/data-integrity work"),
    "area:auth": ("0e8a16", "Authentication/authorization work"),

    # Risk
    "risk:low": ("0e8a16", "Low-risk repository-scoped work"),
    "risk:medium": ("fbca04", "Medium-risk work requiring stronger review"),
    "risk:high": ("b60205", "High-risk work requiring human approval"),

    # Data / trust boundaries
    "data:financial": ("d93f0b", "Touches financial semantics or financial data handling"),
    "data:credentials": ("b60205", "Touches credentials/secrets; human-gated"),
    "data:live-financial": ("b60205", "Touches live financial/customer data; human-gated"),
    "permission:expand": ("b60205", "Expands tool/repository/system permissions; human-gated"),

    # External actions
    "action:deploy": ("b60205", "Deployment requested; human-gated"),
    "action:delete": ("b60205", "Destructive deletion requested; human-gated"),
    "action:publish": ("b60205", "External publication requested; human-gated"),
    "action:purchase": ("b60205", "Purchase/spend requested; human-gated"),
}


@dataclass(frozen=True)
class Transition:
    previous: frozenset[str]
    current: frozenset[str]
    target: str


def transition_labels(labels: Iterable[str], target: str) -> Transition:
    if target not in LIFECYCLE_LABELS:
        raise ValueError(f"unsupported lifecycle target: {target}")
    previous = frozenset(labels)
    current = frozenset((previous - LIFECYCLE_LABELS) | {target})
    return Transition(previous=previous, current=current, target=target)


def make_branch_name(issue_number: int, run_id: str) -> str:
    if issue_number <= 0:
        raise ValueError("issue_number must be positive")
    cleaned = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in {"-", "_"})
    if not cleaned:
        raise ValueError("run_id must contain at least one safe character")
    return f"agent/issue-{issue_number}-{cleaned}"
