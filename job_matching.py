"""Costs that don't say which job they were for, matched to jobs by the owner.

A receipt that just says "Tile, $1,200" can't be tied to a job from the files alone, and
MargenX never guesses: it asks the owner, one cost at a time. Jobs with sales or costs near
the cost's date are listed first to make answering quick, but nothing is ever chosen for the
owner. A cost the owner hasn't answered stays unlinked, exactly as before.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date

from job_intake import IntakeResult
from job_profit import cost_category

# An answer is a tagged pair, so a job number from a file can never be mistaken for one of
# MargenX's own choices (a job named "not_a_job" is still just a job).
NOT_SURE = ("not_sure", "")    # not answered yet: the cost stays unlinked and keeps jobs provisional
NOT_A_JOB = ("not_a_job", "")  # the owner says it's a general business cost, like overhead
NEAR_DAYS = 7            # "around that date": a job with a sale or cost this many days either side


@dataclass(frozen=True)
class Job:
    job_id: str
    description: str
    customers: tuple[str, ...]
    dates: tuple[str, ...]  # ISO dates of the job's sales and costs in these files


def job(job_id: str) -> tuple[str, str]:
    """The answer "this cost was for job job_id"."""
    return ("job", job_id)


def jobs(invoices: IntakeResult, costs: IntakeResult) -> list[Job]:
    """Every job number in the files, with what's needed to recognise it."""
    found: dict[str, dict] = {}
    for result in (invoices, costs):
        for line in result.accepted:
            job = line.get("job_id", "")
            if not job:
                continue
            info = found.setdefault(job, {"description": "", "customers": set(), "dates": set()})
            info["dates"].add(line["date"])
            if result is invoices:
                info["customers"].add(line["customer"])
                if line.get("description") and not info["description"]:
                    info["description"] = line["description"]
    return [Job(j, v["description"], tuple(sorted(v["customers"])), tuple(sorted(v["dates"])))
            for j, v in sorted(found.items())]


def unmatched(costs: IntakeResult) -> list[dict]:
    """Cost lines with no job number that may belong to a job, in file order.

    Every cost that may belong to a job is asked about, whether or not the file has a job number
    column; clear overhead and fees (rent, card fees) never are: they stay outside job figures.
    """
    typed = "cost_type" in costs.mapped_fields
    return [line for line in costs.accepted
            if not line.get("job_id") and not (typed and cost_category(line.get("cost_type")) == "fees_overhead")]


def nearby(line: dict, job_list: list[Job]) -> list[str]:
    """Job numbers with a sale or cost within NEAR_DAYS of this cost, closest first."""
    day = date.fromisoformat(line["date"])
    distances = []
    for job in job_list:
        gap = min(abs((date.fromisoformat(d) - day).days) for d in job.dates)
        if gap <= NEAR_DAYS:
            distances.append((gap, job.job_id))
    return [job_id for _, job_id in sorted(distances)]


def source_key(name: str, data: bytes, reading) -> str:
    """The identity of one file as read: its name, its exact bytes and every choice about how it was
    read (file type, columns, date format, amount meaning, subtotal answers).

    The owner's answers are kept under the keys of both files, so a different file, even one whose
    rows read the same (another report title, another name), or a different reading never reuses them.
    """
    return hashlib.sha256(repr((name, hashlib.sha256(data).hexdigest(), reading)).encode("utf-8")).hexdigest()


def apply(costs: IntakeResult, choices: dict[int, tuple[str, str]], job_list: list[Job]) -> IntakeResult:
    """The costs with the owner's answers applied, keyed by the cost's row in its file.

    job(id) sets that job number on the line (marked as the owner's answer); NOT_A_JOB marks it as a
    general business cost; NOT_SURE changes nothing. The original result is never changed.

    Every answer must be for a cost that is asked about: an answer for any other row (one not in the
    file, one that couldn't be read, a skipped total, a cost that already has a job, overhead) is
    refused, so no caller can believe an answer was applied when it wasn't.
    """
    known = {job.job_id for job in job_list}
    asked = {line["row"] for line in unmatched(costs)}
    others = sorted(set(choices) - asked, key=str)
    if others:
        raise ValueError(f"Row(s) {', '.join(map(str, others))} aren't costs asked about; no answer can apply to them.")
    accepted = []
    for line in costs.accepted:
        choice = choices.get(line["row"], NOT_SURE)
        if choice != NOT_SURE:
            if choice == NOT_A_JOB:
                line = {**line, "not_for_a_job": True}
            elif tuple(choice)[:1] == ("job",) and len(choice) == 2 and choice[1] in known:
                line = {**line, "job_id": choice[1], "job_from_owner": True}
            else:
                raise ValueError(f"Row {line['row']}: {choice!r} isn't a job in these files.")
        accepted.append(line)
    # Without a job number column, answered lines still need one for profit by job; unanswered
    # lines have none and stay unlinked.
    fields = costs.mapped_fields if "job_id" in costs.mapped_fields else (*costs.mapped_fields, "job_id")
    return replace(costs, accepted=accepted, mapped_fields=fields)
