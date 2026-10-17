"""Pure status helpers for the read-only Ledger Command Center."""
from __future__ import annotations

from datetime import datetime, timedelta


def classify_schedule_slot(
    *,
    now: datetime,
    expected_slot: datetime | None,
    latest_run: dict | None,
    runs_error: bool,
    grace_minutes: int = 20,
) -> tuple[str, str]:
    """Classify scheduler health without treating event delivery as run success."""
    if runs_error:
        return "UNKNOWN", "Actions run history could not be retrieved; scheduler health is unknown."
    if expected_slot is None:
        return "UNKNOWN", "Current Operator cron could not be parsed; no fallback schedule is invented."

    created = None
    if latest_run and latest_run.get("created_at"):
        created = datetime.fromisoformat(str(latest_run["created_at"]).replace("Z", "+00:00"))
        if created.tzinfo is not None and expected_slot.tzinfo is not None:
            created = created.astimezone(expected_slot.tzinfo)

    if created is not None and created >= expected_slot:
        status = str(latest_run.get("status") or "").lower()
        conclusion = str(latest_run.get("conclusion") or "").lower()
        if status == "completed" and conclusion == "success":
            return "ON TRACK", "Scheduled Operator run completed successfully for the current slot."
        if status in {"queued", "in_progress", "waiting", "pending"} or not conclusion:
            return "WAITING", f"Scheduled Operator event is visible for the current slot; run is {status or 'still active'}."
        return "CHECK", f"Scheduled Operator event arrived for the current slot but concluded {conclusion or status or 'unsuccessfully'}."

    overdue = now - expected_slot
    if overdue > timedelta(minutes=grace_minutes):
        return "LATE / CHECK", f"No current-slot schedule event is visible after {grace_minutes}m delivery grace."
    return "WAITING", f"Within the {grace_minutes}m GitHub delivery grace for the current schedule slot."
