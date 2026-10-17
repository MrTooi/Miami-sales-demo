"""Pure status helpers for the read-only Ledger Command Center."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

_CRON_LINE = re.compile(r"^\s*-?\s*cron:\s*(.*?)\s*$")
_HOURLY_MINUTES = re.compile(r"^(\d{1,2}(?:,\d{1,2})*) \* \* \* \*$")


def parse_cron_minutes(workflow_text: str | None) -> list[int] | None:
    """Return every minute-of-hour scheduled by a workflow's ``cron:`` lines.

    Only the shape ``M[,M...] * * * *`` is understood. If there is no cron line, or
    any cron line has another shape or an out-of-range minute, return ``None`` so the
    dashboard shows UNKNOWN instead of a partial or invented schedule.
    """
    if not workflow_text:
        return None
    minutes: set[int] = set()
    found = False
    for line in workflow_text.splitlines():
        match = _CRON_LINE.match(line)
        if not match:
            continue
        found = True
        expr = match.group(1)
        if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "'\"":
            expr = expr[1:-1]
        expr = expr.strip()
        shape = _HOURLY_MINUTES.match(expr)
        if not shape:
            return None
        for part in shape.group(1).split(","):
            value = int(part)
            if not 0 <= value <= 59:
                return None
            minutes.add(value)
    return sorted(minutes) if found and minutes else None


def previous_slot(now: datetime, minutes: list[int] | None) -> datetime | None:
    """Most recent scheduled slot at or before ``now`` (None when the schedule is unknown)."""
    if not minutes:
        return None
    base = now.replace(second=0, microsecond=0)
    candidates = [
        (base + timedelta(hours=offset)).replace(minute=minute)
        for offset in (-1, 0)
        for minute in minutes
    ]
    eligible = [c for c in candidates if c <= now]
    return max(eligible) if eligible else None


def next_slot(now: datetime, minutes: list[int] | None) -> datetime | None:
    """First scheduled slot strictly after ``now`` (None when the schedule is unknown)."""
    if not minutes:
        return None
    base = now.replace(second=0, microsecond=0)
    candidates = [
        (base + timedelta(hours=offset)).replace(minute=minute)
        for offset in (0, 1)
        for minute in minutes
    ]
    later = [c for c in candidates if c > now]
    return min(later) if later else None


def latest_run_display(latest_run: dict | None) -> tuple[str, str, str]:
    """(value, tone, note) for any 'latest scheduled run' status shown to the owner.

    Only an attempt-1 run may show its own conclusion. A rerun (or a run whose attempt
    is unknown) shows RERUN / CHECK so a manual re-run can never display SUCCESS as
    schedule health. Tone is never "ok": a historical run says nothing about the
    current slot.
    """
    if not latest_run:
        return "UNKNOWN", "warn", "No Operator schedule event is visible in the current API window."
    attempt = latest_run.get("run_attempt")
    if attempt != 1:
        return (
            "RERUN / CHECK",
            "warn",
            f"Attempt {attempt!r}: a manual rerun or unknown attempt is not schedule-health evidence.",
        )
    state = str(latest_run.get("conclusion") or latest_run.get("status") or "unknown").lower()
    return state.upper(), ("info" if state == "success" else "warn"), "Attempt 1."


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
        if latest_run.get("run_attempt") != 1:
            return "CHECK", (
                f"The latest scheduled Operator run is attempt {latest_run.get('run_attempt')!r}, not an attempt-1 "
                "schedule delivery; a rerun or unknown attempt is not evidence of schedule health."
            )
        if status == "completed" and conclusion == "success":
            return "ON TRACK", (
                "A scheduled Operator run created since the last expected slot completed successfully. "
                "GitHub cron is best-effort: this does not prove exact-time delivery of every slot."
            )
        if status in {"queued", "in_progress", "waiting", "pending"} or not conclusion:
            return "WAITING", f"Scheduled Operator event is visible for the current slot; run is {status or 'still active'}."
        return "CHECK", f"Scheduled Operator event arrived for the current slot but concluded {conclusion or status or 'unsuccessfully'}."

    overdue = now - expected_slot
    if overdue > timedelta(minutes=grace_minutes):
        return "LATE / CHECK", f"No current-slot schedule event is visible after {grace_minutes}m delivery grace."
    return "WAITING", f"Within the {grace_minutes}m GitHub delivery grace for the current schedule slot."
