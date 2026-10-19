"""MarginX step 2: direct job contribution by job and by customer.

Input is what step 1 accepted: invoice lines and cost lines (job_intake.intake), linked by
job number. Every result is labeled "direct job contribution": sales billed on the job's
invoice lines minus the costs recorded against the job. Processor fees, overhead and costs
not linked to a job are never included, and the result says so.

A result is shown as complete only when the job has sales, labor and materials or outsourced
work recorded, with every cost line's type known. Otherwise it is provisional (shown, marked,
with the reasons) or unavailable (no figure at all). Customer totals inherit their jobs'
status. Money is exact Decimal throughout; nothing is rounded, estimated or allocated.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from job_intake import IntakeResult, is_labor

ZERO = Decimal("0.00")
CATEGORIES = ("materials", "outsourced", "labor", "other", "unknown")
CATEGORY_LABELS = {"materials": "Materials", "outsourced": "Outsourced work", "labor": "Labor",
                   "other": "Other job costs", "unknown": "Cost type not given"}
MATERIAL_WORDS = {"material", "materials", "supplies", "supply", "inventory", "stock", "substrate", "substrates",
                  "blanks", "media", "ink", "vinyl", "paper"}
OUTSOURCED_WORDS = {"outsourced", "outsource", "outsourcing", "subcontract", "subcontractor", "subcontractors",
                    "subcontracted", "contractor", "contractors"}

STATUS_ORDER = ("complete", "provisional", "unavailable")
STATUS_LABELS = {"complete": "Complete", "provisional": "Provisional", "unavailable": "Unavailable"}
BASIS = ("Direct job contribution: sales billed on each job's invoice lines (credits included) minus the costs "
         "recorded against that job. Invoice basis (what was billed, not cash received). Not included: "
         "payment processing fees, overhead, and costs not linked to a job.")


def cost_category(cost_type: str | None) -> str:
    """Materials, outsourced, labor, other, or unknown (blank), from the cost type text."""
    text = (cost_type or "").strip()
    if not text:
        return "unknown"
    if is_labor(text):
        return "labor"
    words = set(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
    if words & OUTSOURCED_WORDS:
        return "outsourced"
    if words & MATERIAL_WORDS:
        return "materials"
    return "other"


@dataclass
class JobResult:
    job_id: str
    customers: tuple[str, ...]
    sales: Decimal
    costs: dict[str, Decimal]
    invoice_lines: int
    cost_lines: int
    status: str
    reasons: list[str] = field(default_factory=list)

    @property
    def total_costs(self) -> Decimal:
        return sum(self.costs.values(), ZERO)

    @property
    def contribution(self) -> Decimal | None:
        """None when unavailable: no figure is shown at all."""
        return None if self.status == "unavailable" else self.sales - self.total_costs


@dataclass
class CustomerResult:
    customer: str
    jobs: tuple[str, ...]
    sales: Decimal
    total_costs: Decimal
    status: str
    reasons: list[str] = field(default_factory=list)

    @property
    def contribution(self) -> Decimal | None:
        return None if self.status == "unavailable" else self.sales - self.total_costs


@dataclass
class ProfitReport:
    available: bool
    reasons: list[str] = field(default_factory=list)  # why nothing could be calculated
    jobs: list[JobResult] = field(default_factory=list)
    customers: list[CustomerResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unlinked_sales: Decimal = ZERO
    unlinked_sales_lines: int = 0
    unlinked_costs: Decimal = ZERO
    unlinked_cost_lines: int = 0
    invoice_dates: tuple[str, str] | None = None
    cost_dates: tuple[str, str] | None = None
    basis: str = BASIS


def _worst(statuses) -> str:
    return max(statuses, key=STATUS_ORDER.index, default="unavailable")


def _dates(records: list[dict]) -> tuple[str, str] | None:
    days = sorted(r["date"] for r in records)
    return (days[0], days[-1]) if days else None


def format_money(amount: Decimal) -> str:
    """Dollars with two decimals. Amounts always have at most two (intake refuses more), so
    nothing is rounded; anything else is refused rather than shown rounded."""
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError(f"Amount with more than two decimals: {amount}")
    return f"-${-amount:,.2f}" if amount < 0 else f"${amount:,.2f}"


def job_profit(invoices: IntakeResult, costs: IntakeResult) -> ProfitReport:
    """Direct job contribution per job and per customer, from one invoice file and one cost file."""
    if invoices.kind != "invoices" or costs.kind != "costs":
        raise ValueError("Pass one invoices result and one costs result.")
    report = ProfitReport(available=False, invoice_dates=_dates(invoices.accepted), cost_dates=_dates(costs.accepted))
    for result, what in ((invoices, "sales"), (costs, "costs")):
        if "job_id" not in result.mapped_fields:
            report.reasons.append(f"The {what} file has no job number column, so its lines can't be matched to jobs.")
        elif not result.accepted:
            report.reasons.append(f"No {what} lines were imported.")
    if report.reasons:
        return report
    report.available = True
    typed = "cost_type" in costs.mapped_fields

    sales: dict[str, Decimal] = defaultdict(lambda: ZERO)
    customers: dict[str, set[str]] = defaultdict(set)
    invoice_lines: dict[str, int] = defaultdict(int)
    for line in invoices.accepted:
        job = line.get("job_id", "")
        if not job:
            report.unlinked_sales += line["amount"]
            report.unlinked_sales_lines += 1
            continue
        sales[job] += line["amount"]
        customers[job].add(line["customer"])
        invoice_lines[job] += 1

    job_costs: dict[str, dict[str, Decimal]] = defaultdict(lambda: {c: ZERO for c in CATEGORIES})
    cost_lines: dict[str, dict[str, int]] = defaultdict(lambda: {c: 0 for c in CATEGORIES})
    for line in costs.accepted:
        job = line.get("job_id", "")
        if not job:
            report.unlinked_costs += line["amount"]
            report.unlinked_cost_lines += 1
            continue
        category = cost_category(line.get("cost_type")) if typed else "unknown"
        job_costs[job][category] += line["amount"]
        cost_lines[job][category] += 1

    # Lines that couldn't be imported may hold this job's money: a job with any of them is
    # never complete, and lines that can't be tied to a job hold back every job.
    missing: dict[str, dict[str, int]] = defaultdict(lambda: {"sales": 0, "cost": 0})
    untied = {"sales": 0, "cost": 0}
    failed_customers: dict[str, set[str]] = defaultdict(set)  # customers named on failed sales lines
    unknown_customer_lines = 0  # failed sales lines whose customer can't be read
    for result, what in ((invoices, "sales"), (costs, "cost")):
        for row in result.rejected:
            if not row.get("money_missing", True):
                continue
            values = row.get("values") or {}
            job = values.get("job_id", "")
            if job:
                missing[job][what] += 1
            else:
                untied[what] += 1
            if what == "sales":
                if values.get("customer"):
                    failed_customers[job].add(values["customer"])
                else:
                    unknown_customer_lines += 1

    for job in sorted(set(sales) | set(job_costs) | set(missing)):
        if job not in sales and job not in job_costs:
            # Only failed lines: kept, with no figure, so its customer's total isn't complete.
            customers[job] = set(failed_customers[job])
            report.jobs.append(JobResult(job, tuple(sorted(customers[job])), ZERO, {c: ZERO for c in CATEGORIES},
                                         0, 0, "unavailable",
                                         [f"Its only lines couldn't be imported ({missing[job]['sales']} sales, "
                                          f"{missing[job]['cost']} cost; listed above)."]))
            continue
        counts = cost_lines[job] if job in cost_lines else {c: 0 for c in CATEGORIES}
        amounts = job_costs[job] if job in job_costs else {c: ZERO for c in CATEGORIES}
        reasons = []
        if job not in sales:
            status = "unavailable"
            reasons.append("No sales for this job in the sales file.")
        elif not sum(counts.values()):
            status = "unavailable"
            reasons.append("No costs recorded for this job.")
        else:
            if not typed:
                reasons.append("The costs file has no cost type column, so labor and materials can't be checked.")
            elif counts["unknown"]:
                reasons.append(f"{counts['unknown']} of its cost lines have no cost type.")
            if typed and not counts["labor"]:
                reasons.append("No labor recorded.")
            if typed and not (counts["materials"] or counts["outsourced"]):
                reasons.append("No materials or outsourced work recorded.")
            if len(customers[job]) > 1:
                reasons.append("Billed to more than one customer: " + ", ".join(sorted(customers[job])) + ".")
            for what in ("sales", "cost"):
                if missing[job][what]:
                    reasons.append(f"{missing[job][what]} of its {what} lines couldn't be imported (listed above).")
                if untied[what]:
                    reasons.append(f"{untied[what]} {what} line(s) couldn't be imported and have no readable job "
                                   "number, so they may belong to this job.")
            status = "provisional" if reasons else "complete"
        report.jobs.append(JobResult(job, tuple(sorted(customers[job])), sales.get(job, ZERO), dict(amounts),
                                     invoice_lines.get(job, 0), sum(counts.values()), status, reasons))

    by_customer: dict[str, list[JobResult]] = defaultdict(list)
    shared_by_customer: dict[str, list[str]] = defaultdict(list)
    shared = []
    for job in report.jobs:
        if len(job.customers) == 1:
            by_customer[job.customers[0]].append(job)
        elif len(job.customers) > 1:
            shared.append(job.job_id)
            for customer in job.customers:
                shared_by_customer[customer].append(job.job_id)
    no_job_lines: dict[str, int] = defaultdict(int)
    for line in invoices.accepted:
        if not line.get("job_id"):
            no_job_lines[line["customer"]] += 1
    for customer in sorted(set(by_customer) | set(no_job_lines) | set(shared_by_customer) | failed_customers.get("", set())):
        jobs = by_customer.get(customer, [])
        counted = [j for j in jobs if j.status != "unavailable"]
        reasons = []
        left_out = [j.job_id for j in jobs if j.status == "unavailable"]
        if left_out:
            reasons.append(f"Left out, no figure yet: {', '.join(left_out)}.")
        if any(j.status == "provisional" for j in counted):
            reasons.append("Includes provisional jobs: "
                           + ", ".join(j.job_id for j in counted if j.status == "provisional") + ".")
        if shared_by_customer.get(customer):
            reasons.append("Left out, billed to more than one customer: "
                           + ", ".join(shared_by_customer[customer]) + ".")
        if unknown_customer_lines:
            reasons.append(f"{unknown_customer_lines} sales line(s) couldn't be imported and have no readable "
                           "customer, so they may belong to this customer.")
        if customer in failed_customers.get("", set()):
            reasons.append("Some of its sales lines without a job number couldn't be imported.")
        if no_job_lines.get(customer):
            reasons.append(f"{no_job_lines[customer]} invoice line(s) have no job number and are left out.")
        if not counted:
            status = "unavailable"
        else:
            status = _worst([j.status for j in counted] + (["provisional"] if reasons else []))
        report.customers.append(CustomerResult(customer, tuple(j.job_id for j in jobs) + tuple(shared_by_customer[customer]),
                                               sum((j.sales for j in counted), ZERO),
                                               sum((j.total_costs for j in counted), ZERO), status, reasons))

    if shared:
        report.notes.append(f"Jobs billed to more than one customer aren't in any customer's total: {', '.join(shared)}.")
    if report.unlinked_sales_lines:
        report.notes.append(f"{report.unlinked_sales_lines} invoice line(s) worth {format_money(report.unlinked_sales)} have "
                            "no job number, so they aren't in any job's figure.")
    if report.unlinked_cost_lines:
        report.notes.append(f"{report.unlinked_cost_lines} cost line(s) worth {format_money(report.unlinked_costs)} aren't "
                            "linked to a job, so they aren't in any job's figure. If some of them belong to "
                            "jobs, those jobs' figures are too high.")
    # Job numbers that differ only in capitals or spaces are kept apart, never merged silently.
    folded: dict[str, list[str]] = defaultdict(list)
    for job in report.jobs:
        folded[re.sub(r"\s+", "", job.job_id.lower())].append(job.job_id)
    for variants in folded.values():
        if len(variants) > 1:
            report.notes.append(f"Job numbers {' and '.join(variants)} look alike but were kept separate. "
                                "If they are the same job, fix the job number where the data comes from.")
    return report
