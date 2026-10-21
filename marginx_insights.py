"""Plain-language summary of a MargenX profit report, for the results screen.

Turns job_profit.ProfitReport into the headline numbers and a short "what needs your
attention" list. Deterministic and exact: it only restates figures the report already
holds (Decimal), never estimates, allocates or hides an uncertain result. Shares of sales
(margins) are exact fractions (Fraction keeps 1/3 as exactly 1/3), so every comparison between
them is exact; percentages and "about $X" prices are rounded only for display.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from job_profit import ZERO, CustomerResult, JobResult, ProfitReport, format_money

# The "usual margin" (share kept across complete jobs) is only stated with at least this many.
MIN_JOBS_FOR_USUAL = 3
MAX_THIN_JOBS = 2
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
    jobs_with_figure: int        # jobs counted in left_after_job_costs
    sales_with_figure: Decimal   # the sales those jobs cover
    jobs_without_figure: int     # unavailable jobs: left out of the total, not counted as zero
    unlinked_sales: Decimal      # sales lines with no job number: in sales, not in any job's figure
    unlinked_sales_lines: int
    complete_jobs: int
    losing_jobs: int             # complete jobs that lost money: confirmed by complete records
    possible_losses: int         # jobs that need a check and show a loss so far: not confirmed
    jobs_to_check: int           # provisional or unavailable
    rejected_sales_lines: int    # rows that couldn't be read: not in sales or any total
    rejected_cost_lines: int
    figure_is_provisional: bool  # any job counted in the total isn't complete
    unlinked_costs: Decimal      # costs in the file not tied to any job
    overhead_costs: Decimal      # the part of unlinked_costs that is clear overhead or fees (rent...)
    unassigned_job_costs: Decimal  # the rest: costs with no job number that may belong to jobs
    # Sales minus every cost in these files, or None when some sales aren't in the job total
    # (jobs without a figure, sales without a job number) or some rows couldn't be read: a total
    # then could be wrong, so it's withheld.
    after_unlinked_costs: Decimal | None
    usual_margin: Fraction | None  # share kept across complete jobs, exact (3/10 = 30%), when there are enough

    @property
    def figure_is_partial(self) -> bool:
        """The job total leaves out some sales: jobs without a figure or sales without a job number."""
        return bool(self.jobs_without_figure or self.unlinked_sales_lines)


@dataclass(frozen=True)
class Insight:
    level: str   # "loss", "warn" or "info"
    title: str
    detail: str


def period_text(report: ProfitReport) -> str:
    """"Sales dated Oct 2 to Oct 23, 2026", from the imported sales lines' dates."""
    from datetime import date
    first, last = (date.fromisoformat(d) for d in report.invoice_dates)
    start = f"{first:%b} {first.day}" + ("" if first.year == last.year else f", {first.year}")
    return f"Sales dated {start} to {last:%b} {last.day}, {last.year}"


def money(amount: Decimal) -> str:
    """Exact dollars, without ".00" when there are no cents ("$1,300", "$12.50", "-$140")."""
    text = format_money(amount)
    return text[:-3] if text.endswith(".00") else text


def share_of(part: Decimal, whole: Decimal) -> Fraction:
    """part / whole exactly (whole must be positive). Margins are compared only as exact shares."""
    return Fraction(part) / Fraction(whole)


def _round_half_up(value: Fraction) -> int:
    """To a whole number, halves away from zero, computed exactly."""
    rounded = int(abs(value) + Fraction(1, 2))
    return rounded if value >= 0 else -rounded


def percent(part: Decimal | Fraction, whole: Decimal | Fraction | int) -> int | None:
    """Whole percent for display, or None when there's nothing to divide by."""
    if whole <= 0:
        return None
    return _round_half_up(Fraction(part) * 100 / Fraction(whole))


def job_name(job: JobResult) -> str:
    return f"{job.description} · {job.job_id}" if job.description else f"Job {job.job_id}"


def usual_margin(report: ProfitReport) -> Fraction | None:
    """The share of sales kept across complete jobs, as an exact fraction, or None with too few of them."""
    complete = [j for j in report.jobs if j.status == "complete" and j.sales > 0]
    sales = sum((j.sales for j in complete), ZERO)
    if len(complete) < MIN_JOBS_FOR_USUAL or sales <= 0:
        return None
    return share_of(sum((j.contribution for j in complete), ZERO), sales)


def pricing(job: JobResult, usual: Fraction | None) -> dict | None:
    """Break-even and "at your usual margin" prices for a complete job, from its own recorded costs.

    None for a job that isn't complete (its costs may be understated, so any price would be too
    low) or that has no costs. The target price is costs / (1 - usual margin), computed exactly and
    rounded to whole dollars (halves up) only for display, stated as "about".
    """
    if job.status != "complete" or job.total_costs <= 0:
        return None
    result = {"break_even": job.total_costs, "usual": None, "at_usual": None}
    if usual is not None and 0 < usual < 1:
        result["usual"] = percent(usual, 1)
        result["at_usual"] = Decimal(_round_half_up(Fraction(job.total_costs) / (1 - Fraction(usual))))
    return result


def _price_sentence(job: JobResult, usual: Fraction | None) -> str:
    """Break-even (for a losing job) and the price at the usual margin, when it's higher.

    Both come from the job's own recorded costs, before overhead (rent, fees) not tied to the job,
    so the break-even is worded as "cover its job costs", not as the business's break-even.
    """
    price = pricing(job, usual)
    if not price:
        return ""
    parts = []
    if job.contribution < 0:
        parts.append(f"To cover its job costs it needed {money(price['break_even'])}")
    if price["at_usual"] is not None and price["at_usual"] > job.sales:
        parts.append(f"at your usual {price['usual']}% margin, about {money(price['at_usual'])}")
    if not parts:
        return ""
    text = "; ".join(parts)
    return " " + text[0].upper() + text[1:] + "."


def summarize(report: ProfitReport) -> Summary:
    counted = [j for j in report.jobs if j.contribution is not None]
    counted_sales = sum((j.sales for j in counted), ZERO)
    left = sum((j.contribution for j in counted), ZERO)
    without_figure = len(report.jobs) - len(counted)
    partial = bool(without_figure or report.unlinked_sales_lines or not counted)
    unread = bool(report.rejected_sales_lines or report.rejected_cost_lines)
    return Summary(
        sales=sum((j.sales for j in report.jobs), ZERO) + report.unlinked_sales,
        left_after_job_costs=left,
        share_percent=percent(left, counted_sales),
        jobs=len(report.jobs),
        jobs_with_figure=len(counted),
        sales_with_figure=counted_sales,
        jobs_without_figure=without_figure,
        unlinked_sales=report.unlinked_sales,
        unlinked_sales_lines=report.unlinked_sales_lines,
        complete_jobs=sum(1 for j in counted if j.status == "complete"),
        losing_jobs=sum(1 for j in counted if j.status == "complete" and j.contribution < 0),
        possible_losses=sum(1 for j in counted if j.status != "complete" and j.contribution < 0),
        rejected_sales_lines=report.rejected_sales_lines,
        rejected_cost_lines=report.rejected_cost_lines,
        jobs_to_check=sum(1 for j in report.jobs if j.status != "complete"),
        figure_is_provisional=any(j.status != "complete" for j in counted),
        unlinked_costs=report.unlinked_costs,
        overhead_costs=report.unlinked_costs - report.unlinked_job_costs,
        unassigned_job_costs=report.unlinked_job_costs,
        after_unlinked_costs=None if partial or unread else left - report.unlinked_costs,
        usual_margin=usual_margin(report),
    )


def _thin_biggest_customer(report: ProfitReport) -> Insight | None:
    """The biggest customer by sales, when it keeps a much smaller share than the business.

    Only customers whose figures are complete are used, for both the biggest customer and the
    business-wide share it's compared with: missing costs elsewhere would inflate that benchmark and
    make a correctly costed customer look bad. When any customer or sale is left out (no figure,
    needs a check, billed to more than one customer, no job number), a bigger customer may be hidden,
    so the claim is worded as "of customers with complete figures" rather than "your biggest customer".
    """
    complete = [c for c in report.customers if c.status == "complete" and c.sales > 0]
    if len(complete) < 2:
        return None
    total_sales = sum((c.sales for c in complete), ZERO)
    biggest = max(complete, key=lambda c: (c.sales, c.customer))
    # The gap is measured on exact shares; only the percentages shown are rounded.
    gap_points = (share_of(sum((c.contribution for c in complete), ZERO), total_sales)
                  - share_of(biggest.contribution, biggest.sales)) * 100
    if gap_points < Fraction(THIN_GAP_POINTS):
        return None
    share = percent(biggest.contribution, biggest.sales)
    everything_complete = (not report.unlinked_sales_lines
                           and all(c.status == "complete" for c in report.customers)
                           and all(j.status == "complete" and len(j.customers) == 1 for j in report.jobs))
    others = [c for c in complete if c is not biggest]
    best = max(others, key=lambda c: (share_of(c.contribution, c.sales), c.customer))
    detail = (f"{money(biggest.sales)} in sales, {money(biggest.contribution)} left after job costs. "
              f"{best.customer} keeps {percent(best.contribution, best.sales)}%.")
    if everything_complete:
        title = f"{biggest.customer} is your biggest customer, but keeps only {share}%"
    else:
        title = f"Of customers with complete figures, {biggest.customer} is the biggest, but keeps only {share}%"
        detail += (" Customers whose figures still need a check aren't compared, so another customer may be "
                   "bigger.")
    return Insight("warn", title, detail)


def attention(report: ProfitReport) -> list[Insight]:
    """What needs the owner's attention, most important first."""
    items: list[Insight] = []
    usual = usual_margin(report)
    losing = [j for j in report.jobs if j.contribution is not None and j.contribution < 0]
    # A complete job's loss is confirmed by its records.
    for job in sorted((j for j in losing if j.status == "complete"), key=lambda j: (j.contribution, j.job_id)):
        detail = f"Sold for {money(job.sales)}, cost {money(job.total_costs)}." + _price_sentence(job, usual)
        items.append(Insight("loss", f"{job_name(job)} lost {money(-job.contribution)}", detail))
    # A job that needs a check only shows a loss so far: a missing sale or cost could change it either way.
    possible = sorted((j for j in losing if j.status != "complete"), key=lambda j: (j.contribution, j.job_id))
    for job in possible:
        why = " ".join(job.reasons) if job.reasons else "Some of its records are missing."
        items.append(Insight("warn", f"{job_name(job)} may have lost {money(-job.contribution)}",
                             f"The rows MargenX could read show sold for {money(job.sales)}, cost "
                             f"{money(job.total_costs)}. Not confirmed: {why}"))
    # Complete jobs that made money but kept less than half the usual margin.
    if usual is not None and usual > 0:
        thin_jobs = sorted((j for j in report.jobs if j.status == "complete" and j.sales > 0
                            and j.contribution >= 0 and share_of(j.contribution, j.sales) < usual / 2),
                           key=lambda j: (share_of(j.contribution, j.sales), j.job_id))
        for job in thin_jobs[:MAX_THIN_JOBS]:
            items.append(Insight("warn", f"{job_name(job)} kept only {percent(job.contribution, job.sales)}%",
                                 f"Sold for {money(job.sales)}, cost {money(job.total_costs)}."
                                 + _price_sentence(job, usual)))
    thin = _thin_biggest_customer(report)
    if thin:
        items.append(thin)
    to_check = [j for j in report.jobs if j.status == "provisional" and j not in possible]
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
                             ("They have no sales or no costs in these files, so no profit is shown for them and they "
                              "aren't in 'Left after job costs'." if len(missing) != 1 else
                              "It has no sales or no costs in these files, so no profit is shown for it and it "
                              "isn't in 'Left after job costs'.")))
    if report.unlinked_sales_lines:
        items.append(Insight("warn", f"{money(report.unlinked_sales)} of sales have no job number",
                             "They're in your sales but not in any job's figure. Add the job number in your "
                             "invoicing software to see what those jobs left you."))
    if report.unlinked_job_cost_lines:
        items.append(Insight("warn", f"{money(report.unlinked_job_costs)} of costs aren't linked to a job",
                             "If some belong to jobs, those jobs' figures are too high."))
    return items
