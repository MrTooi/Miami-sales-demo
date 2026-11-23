"""The owner's job-cost answer (J1, the labor-gap plan v3 on issue #128), for tests about other rules.

A J1 answer counts only for the exact file, the exact words of its choice and the exact cost list MargenX shows,
which every other answer shapes. So it is given last, for the answers as they are then, the way the question screen
asks it last.
"""
from __future__ import annotations

import dataclasses

import quickbooks_figures as qf


def answer(report, answers: qf.OwnerAnswers, choice: str = qf.JOB_COSTS_ON_JOBS, *, costs: str | None = None,
           statement: str | None = None, file: str | None = None) -> qf.JobCostsAnswer:
    """The answer the owner would give now. costs, statement or file replace what it is bound to (stale answers)."""
    fingerprint = qf.report_fingerprint(report)
    now = qf.figures(report, dataclasses.replace(answers, report=fingerprint, job_costs=None))
    return qf.JobCostsAnswer(choice, statement if statement is not None else
                             qf.job_costs_statement(report, now.jobs_on, choice), fingerprint,
                             file if file is not None else report.file_digest,
                             costs if costs is not None else now.cost_digest)


def confirmed(report, answers: qf.OwnerAnswers, choice: str = qf.JOB_COSTS_ON_JOBS) -> qf.OwnerAnswers:
    """The answers bound to this report, with the owner's J1 answer for them, given last."""
    bound = dataclasses.replace(answers, report=qf.report_fingerprint(report))
    return dataclasses.replace(bound, job_costs=answer(report, bound, choice))
