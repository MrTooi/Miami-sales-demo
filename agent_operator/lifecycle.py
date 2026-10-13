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

MANAGED_LABELS = {
    "agent:ready": ("1d76db", "Approved for autonomous agent pickup"),
    "agent:claimed": ("fbca04", "Claimed by the background AI operator"),
    "agent:working": ("0e8a16", "Background AI execution is in progress"),
    "agent:awaiting-review": ("5319e7", "Agent work is ready for review"),
    "agent:blocked": ("d93f0b", "Agent execution stopped and needs intervention"),
    "needs:human": ("b60205", "Human approval or decision is required"),
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
