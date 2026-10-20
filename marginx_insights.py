"""Plain-language summary of a MarginX profit report, for the results screen.

Turns job_profit.ProfitReport into the headline numbers and a short "what needs your
attention" list. Deterministic and exact: it only restates figures the report already
holds (Decimal), never estimates, allocates or hides an uncertain result. Percentages are
rounded for display only.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from job_profit import ZERO, CustomerResult, JobResult, ProfitReport, format_money

# A customer counts as "thin" when its share left after job costs is at least this many
# percentage points below the business-wide share.
THIN_GAP_POINTS = Decimal("15")
MAX_CHECK_ITEMS = 3


@dataclass(frozen=True)
class Summary:
    sales: Decimal               # every imported sales line, with or without a job
    left_after_job_costs: Decimal  # sum of job contributions that have a figure
    share_percent: int | None    # left / sales of the jobs that have a figure, whole percent
    jobs: int
    losing_jobs: int
    jobs_to_check: int           # provisional or unavailable
    figure_is_provisional: bool  # any job counted in the total isn't complete


@dataclass(frozen=True)
class Insight:
    level: str   # "loss", "warn" or "info"
    title: str
    detail: str


def money(amount: Decimal) -> str:
    """Exact dollars, without ".00" when there are no cents ("$1,300", "$12.50", "-$140")."""
    text = format_money(amount)
    return text[:-3] if text.endswith(".00") else text


def percent(part: Decimal, whole: Decimal) -> int | None:
    """Whole percent for display, or None when there's nothing to divide by."""
    if whole <= 0:
        return None
    return int((part * 100 / whole).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def job_name(job: JobResult) -> str:
    return f"{job.description} · {job.job_id}" if job.description else f"Job {job.job_id}"


def summarize(report: ProfitReport) -> Summary:
    counted = [j for j in report.jobs if j.contribution is not None]
    counted_sales = sum((j.sales for j in counted), ZERO)
    left = sum((j.contribution for j in counted), ZERO)
    return Summary(
        sales=sum((j.sales for j in report.jobs), ZERO) + report.unlinked_sales,
        left_after_job_costs=left,
        share_percent=percent(left, counted_sales),
        jobs=len(report.jobs),
        losing_jobs=sum(1 for j in counted if j.contribution < 0),
        jobs_to_check=sum(1 for j in report.jobs if j.status != "complete"),
        figure_is_provisional=any(j.status != "complete" for j in counted),
    )


def _thin_biggest_customer(customers: list[CustomerResult]) -> Insight | None:
    """The biggest customer by sales, when it keeps a much smaller share than the business."""
    counted = [c for c in customers if c.contribution is not None and c.sales > 0]
    if len(counted) < 2:
        return None
    total_sales = sum((c.sales for c in counted), ZERO)
    overall = percent(sum((c.contribution for c in counted), ZERO), total_sales)
    biggest = max(counted, key=lambda c: (c.sales, c.customer))
    share = percent(biggest.contribution, biggest.sales)
    if overall is None or share is None or Decimal(overall - share) < THIN_GAP_POINTS:
        return None
    # The comparison uses a customer whose figures are complete, so it is never flattered by missing costs.
    others = [c for c in counted if c is not biggest and c.status == "complete"]
    detail = f"{money(biggest.sales)} in sales, {money(biggest.contribution)} left after job costs."
    if others:
        best = max(others, key=lambda c: (c.contribution / c.sales, c.customer))
        detail += f" {best.customer} keeps {percent(best.contribution, best.sales)}%."
    if biggest.status != "complete":
        detail += " Some of its jobs still need a check."
    return Insight("warn", f"{biggest.customer} is your biggest customer, but keeps only {share}%", detail)


def attention(report: ProfitReport) -> list[Insight]:
    """What needs the owner's attention, most important first."""
    items: list[Insight] = []
    for job in sorted((j for j in report.jobs if j.contribution is not None and j.contribution < 0),
                      key=lambda j: (j.contribution, j.job_id)):
        detail = f"Sold for {money(job.sales)}, cost {money(job.total_costs)}."
        if job.status != "complete":
            detail += " Some of its costs still need a check."
        items.append(Insight("loss", f"{job_name(job)} lost {money(-job.contribution)}", detail))
    thin = _thin_biggest_customer(report.customers)
    if thin:
        items.append(thin)
    to_check = [j for j in report.jobs if j.status == "provisional"]
    for job in to_check[:MAX_CHECK_ITEMS]:
        reason = job.reasons[0] if job.reasons else "Some of its costs are missing."
        items.append(Insight("warn", f"{job_name(job)} needs a check",
                             f"{reason} Its {money(job.contribution)} may not be the full picture."))
    if len(to_check) > MAX_CHECK_ITEMS:
        items.append(Insight("warn", f"{len(to_check) - MAX_CHECK_ITEMS} more jobs need a check",
                             "See the job list below for the reasons."))
    missing = [j for j in report.jobs if j.status == "unavailable"]
    if missing:
        items.append(Insight("info", f"{len(missing)} job{'s' if len(missing) != 1 else ''} without a figure yet",
                             "They have no sales or no costs in these files, so no profit is shown for them."))
    if report.unlinked_job_cost_lines:
        items.append(Insight("warn", f"{money(report.unlinked_job_costs)} of costs aren't linked to a job",
                             "If some belong to jobs, those jobs' figures are too high."))
    return items
