"""MarginX step 2: direct job contribution by job and by customer.

Input is what step 1 accepted: invoice lines and cost lines (job_intake.intake), linked by
job number. Every result is labeled "direct job contribution": sales billed on the job's
invoice lines minus every cost recorded against the job, by type (payment-processing fees and
overhead included only when recorded against a job). Sales and costs not linked to a job are
never spread over jobs; they are totalled in the notes.

A result is shown as complete only when the job has sales, labor and materials or outsourced
work recorded, every cost line's type is known, none of its lines failed to import, and the
costs file has no unlinked cost that could belong to it (only clear overhead and payment-
processing fees are exempt). Otherwise it is provisional (shown, marked, with the reasons) or
unavailable (no figure at all). Customer totals inherit their jobs' status. Money is exact
Decimal throughout; nothing is rounded, estimated or allocated.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from job_intake import LABOR_TYPES, IntakeResult, cost_type_name

ZERO = Decimal("0.00")
CATEGORIES = ("materials", "outsourced", "labor", "fees_overhead", "other", "unknown")
CATEGORY_LABELS = {"materials": "Materials", "outsourced": "Outsourced work", "labor": "Labor",
                   "fees_overhead": "Fees & overhead on this job", "other": "Other job costs",
                   "unknown": "Cost type not given"}
# Cost types that say the type isn't known: treated like a blank type.
UNKNOWN_TYPES = {"unknown", "uncategorized", "uncategorised", "n a", "na", "none", "tbd", "to be determined",
                 "ask my accountant", "unclassified", "not classified", "not categorized", "not categorised",
                 "no category", "not set", "pending"}
# Cost types that clearly aren't tied to one job, matched as the WHOLE type, never as a word
# inside it: "Rent" is overhead, but "Equipment rent", "Job processing" or "Installation
# insurance" may be a job's own cost and stay "other". Unlinked, only these are left out.
# Account parents ("Parent:Rent") under which an overhead name still means general overhead.
# Any other parent ("Job Costs:Rent", "Cost of Goods Sold:Insurance") may tie it to jobs, so
# the cost is "other": subtracted, and when unlinked it keeps jobs provisional.
OVERHEAD_PARENTS = {"overhead", "general overhead", "operating expenses", "operating expense",
                    "general and administrative", "general administrative", "g a", "administrative",
                    "office expenses", "facilities", "occupancy", "utilities", "insurance"}
FEE_OVERHEAD_TYPES = {
    "overhead", "general overhead", "shop overhead", "rent", "office rent", "shop rent", "building rent",
    "utilities", "utility", "electric", "electricity", "insurance", "business insurance", "general liability insurance",
    "admin", "administrative", "office", "office expense", "office expenses",
    "merchant fee", "merchant fees", "processing fee", "processing fees", "payment processing",
    "payment processing fee", "payment processing fees", "credit card processing", "credit card fees",
    "card processing fees", "bank fee", "bank fees", "bank charges",
}
# Whole cost types (after any "Parent:" account prefix) that are materials or outsourced work
# (labor's list, LABOR_TYPES, is in job_intake). Only an exact match counts, so "Non-material costs", "No materials" or "Materials
# processing" never confirm materials: they are subtracted as "other" and can't make a job complete.
MATERIAL_TYPES = {
    "materials", "material", "supplies", "job supplies", "job materials", "materials and supplies",
    "supplies and materials", "printing supplies", "production materials", "raw materials",
    "substrates", "blanks", "ink", "vinyl", "paper", "media", "cost of materials", "materials cost",
}
OUTSOURCED_TYPES = {
    "outsourced", "outsourced work", "outsourcing", "subcontract", "subcontractor", "subcontractors",
    "subcontracted work", "contractor", "contractors", "outside services", "sublet", "outsourced printing",
    "contract printing",
}

STATUS_ORDER = ("complete", "provisional", "unavailable")
STATUS_LABELS = {"complete": "Complete", "provisional": "Provisional", "unavailable": "Unavailable"}
BASIS = ("Direct job contribution: sales billed on each job's invoice lines (credits included) minus every cost "
         "recorded against that job, shown by type. Invoice basis (what was billed, not cash received). Payment "
         "processing fees and overhead count only when they are recorded against a job; those not linked to a "
         "job are left out of every figure and totalled in the notes. Nothing is estimated or spread over jobs.")


def cost_category(cost_type: str | None) -> str:
    """Materials, outsourced, labor, fees/overhead, other, or unknown, from the cost type text.

    Only a whole, recognized type counts (after any "Parent:" account prefix, as in
    "Cost of Goods Sold:Materials"): labels are never read word by word, so a negated or mixed
    label ("Non-material costs", "Equipment rent") can't confirm materials or count as overhead.
    Any other label is "other": subtracted, but it never makes a job complete, and when
    unlinked it may belong to a job. Blank or "not known" markers are "unknown".
    """
    name = cost_type_name(cost_type)
    parents = [re.sub(r"[^a-z0-9]+", " ", p.lower()).strip() for p in (cost_type or "").split(":")[:-1]]
    if not name or name in UNKNOWN_TYPES:
        return "unknown"
    for category, names in (("labor", LABOR_TYPES), ("materials", MATERIAL_TYPES),
                            ("outsourced", OUTSOURCED_TYPES), ("fees_overhead", FEE_OVERHEAD_TYPES)):
        if name in names:
            if category == "fees_overhead" and any(p and p not in OVERHEAD_PARENTS for p in parents):
                return "other"
            return category
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
    description: str = ""  # the first description on the job's invoice lines, for display only

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
    # The part of unlinked_costs that isn't clear overhead or fees: it may belong to jobs.
    unlinked_job_costs: Decimal = ZERO
    unlinked_job_cost_lines: int = 0
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
            report.reasons.append(f"No {'sales' if what == 'sales' else 'cost'} lines were imported.")
    if report.reasons:
        return report
    report.available = True
    typed = "cost_type" in costs.mapped_fields

    sales: dict[str, Decimal] = defaultdict(lambda: ZERO)
    customers: dict[str, set[str]] = defaultdict(set)
    invoice_lines: dict[str, int] = defaultdict(int)
    descriptions: dict[str, str] = {}
    billed: set[str] = set()  # jobs with at least one positive sale (not only credits)
    # Sales with no job number, by look-alike customer name (see _fold), so "bakery" counts for "Bakery".
    no_job_sales: dict[str, list[Decimal]] = defaultdict(list)
    for line in invoices.accepted:
        job = line.get("job_id", "")
        if not job:
            report.unlinked_sales += line["amount"]
            report.unlinked_sales_lines += 1
            no_job_sales[_fold(line["customer"])].append(line["amount"])
            continue
        sales[job] += line["amount"]
        customers[job].add(line["customer"])
        invoice_lines[job] += 1
        if line.get("description") and job not in descriptions:
            descriptions[job] = line["description"]
        if line["amount"] > 0:
            billed.add(job)

    unlinked_job_costs: list[Decimal] = []
    job_costs: dict[str, dict[str, Decimal]] = defaultdict(lambda: {c: ZERO for c in CATEGORIES})
    cost_lines: dict[str, dict[str, int]] = defaultdict(lambda: {c: 0 for c in CATEGORIES})
    for line in costs.accepted:
        job = line.get("job_id", "")
        if not job:
            report.unlinked_costs += line["amount"]
            report.unlinked_cost_lines += 1
            # Unlinked fees and overhead are left out by the stated basis; any other unlinked
            # cost may belong to a job, so it holds every job back from "complete".
            if not typed or cost_category(line.get("cost_type")) != "fees_overhead":
                unlinked_job_costs.append(line["amount"])
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

    # Customers named on failed sales lines count too: a job billed to Bakery whose failed line
    # names Gym is a job of two customers, never Bakery's alone.
    for job, names in failed_customers.items():
        if job:
            customers[job] |= names

    for job in sorted(set(sales) | set(job_costs) | set(missing)):
        if job not in sales and job not in job_costs:
            # Only failed lines: kept, with no figure, so its customer's total isn't complete.
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
            # A category counts as recorded only with an amount above $0.00 (costs are never
            # negative): a $0.00 placeholder line is kept, but proves nothing was spent.
            if typed and not amounts["labor"] > 0:
                reasons.append("Labor recorded only as $0.00." if counts["labor"] else "No labor recorded.")
            if typed and not (amounts["materials"] > 0 or amounts["outsourced"] > 0):
                reasons.append("Materials or outsourced work recorded only as $0.00."
                               if counts["materials"] or counts["outsourced"]
                               else "No materials or outsourced work recorded.")
            if job not in billed:
                # Credits alone don't show the original sale was imported.
                reasons.append("Only credits were found for this job; its original sale isn't in the sales file.")
            if len(customers[job]) > 1:
                reasons.append("Billed to more than one customer: " + ", ".join(sorted(customers[job])) + ".")
            for name in sorted(customers[job]):
                # The customer's (or a look-alike name's) sales without a job number may belong to
                # this job; never spread over jobs.
                unlinked = no_job_sales.get(_fold(name))
                if unlinked:
                    reasons.append(f"{name} has {len(unlinked)} sales line(s) worth "
                                   f"{format_money(sum(unlinked, ZERO))} with no job number that may "
                                   "belong to this job.")
            if unlinked_job_costs:
                reasons.append(f"{len(unlinked_job_costs)} cost line(s) worth "
                               f"{format_money(sum(unlinked_job_costs, ZERO))} have no job number and may "
                               "belong to this job.")
            for what in ("sales", "cost"):
                if missing[job][what]:
                    reasons.append(f"{missing[job][what]} of its {what} lines couldn't be imported (listed above).")
                if untied[what]:
                    reasons.append(f"{untied[what]} {what} line(s) couldn't be imported and have no readable job "
                                   "number, so they may belong to this job.")
            status = "provisional" if reasons else "complete"
        report.jobs.append(JobResult(job, tuple(sorted(customers[job])), sales.get(job, ZERO), dict(amounts),
                                     invoice_lines.get(job, 0), sum(counts.values()), status, reasons))

    # Job numbers that differ only in capitals, spaces or punctuation are kept apart, never merged,
    # but their money may belong to one job, so none of them is complete until the owner says.
    folded: dict[str, list[JobResult]] = defaultdict(list)
    for job in report.jobs:
        folded[_fold(job.job_id)].append(job)
    for variants in folded.values():
        if len(variants) > 1:
            names = " and ".join(j.job_id for j in variants)
            report.notes.append(f"Job numbers {names} look alike but were kept separate. If they are the same job, "
                                "fix the job number where the data comes from.")
            for job in variants:
                job.reasons.append(f"Job numbers {names} look alike and may be one job.")
                if job.status == "complete":
                    job.status = "provisional"

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
    linked_fees = sum((j.costs["fees_overhead"] for j in report.jobs), ZERO)
    if linked_fees:
        report.notes.append(f"{format_money(linked_fees)} of fees or overhead were recorded against jobs and are "
                            "subtracted from those jobs (column 'Fees & overhead on this job').")
    report.unlinked_job_costs = sum(unlinked_job_costs, ZERO)
    report.unlinked_job_cost_lines = len(unlinked_job_costs)
    for job in report.jobs:
        job.description = descriptions.get(job.job_id, "")
    # Unlinked costs are disclosed in two parts: clear overhead and fees (outside the basis), and
    # anything else, which may belong to a job (and keeps every job provisional, above).
    unlinked_overhead = report.unlinked_costs - sum(unlinked_job_costs, ZERO)
    overhead_lines = report.unlinked_cost_lines - len(unlinked_job_costs)
    if overhead_lines:
        report.notes.append(f"{overhead_lines} overhead or fee line(s) worth {format_money(unlinked_overhead)} (such as "
                            "rent) aren't linked to a job, so they aren't allocated to any job. Overhead recorded "
                            "against a job is included in that job. These figures are direct job contribution, not "
                            "the business's final profit.")
    if unlinked_job_costs:
        report.notes.append(f"{len(unlinked_job_costs)} cost line(s) worth "
                            f"{format_money(sum(unlinked_job_costs, ZERO))} aren't linked to a job, so they aren't in "
                            "any job's figure. If some of them belong to jobs, those jobs' figures are too high.")
    # Customer names that differ only in capitals, spaces or punctuation are likewise kept apart
    # and held back from complete until the owner says whether they are one customer.
    folded_customers: dict[str, list[CustomerResult]] = defaultdict(list)
    for customer in report.customers:
        folded_customers[_fold(customer.customer)].append(customer)
    for variants in folded_customers.values():
        if len(variants) > 1:
            names = " and ".join(f"'{c.customer}'" for c in variants)
            report.notes.append(f"Customers {names} look alike but were kept separate. If they are the same "
                                "customer, fix the name where the data comes from.")
            for customer in variants:
                customer.reasons.append(f"Customers {names} look alike and may be one customer.")
                if customer.status == "complete":
                    customer.status = "provisional"
    return report


def _fold(name: str) -> str:
    """A name with capitals, spaces and punctuation removed, to spot look-alikes ("J-1" / "j 1")."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())
