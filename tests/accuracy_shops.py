"""Made-up shops with known answers, for MargenX's accuracy self-tests.

Independent of MargenX on purpose: this file imports nothing from the product. A shop is generated
from a seed, its right answers are worked out here in whole cents (integers, never floats) from the
shop itself, and the shop is written out as ordinary sales and cost CSV files. The tests then run
those files through all of MargenX (intake, profit engine, summary, screen) and compare.

The rules below are MargenX's written rules (job_profit's module docstring and docs/MVP_SPEC.md),
re-implemented from the text, not copied from the code:
- A job's figure is its sales minus every cost recorded against it ("direct job contribution").
- A job has no figure (unavailable) without sales or without costs.
- A job is complete only with a positive sale, labor above $0, materials or outsourced work above
  $0, one customer, no unlinked cost that could be a job cost (rent and other clear overhead are
  fine), and no sales without a job number for its customer. Otherwise it needs a check.
- A customer's figure covers its own single-customer jobs that have a figure.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from fractions import Fraction

CUSTOMERS = ["Biscayne Bakery (fictional)", "Wynwood Gym (fictional)", "Coral Way Dental (fictional)",
             "Little River Cafe (fictional)", "Doral Realty (fictional)", "Brickell Law (fictional)",
             "Hialeah Auto (fictional)", "Kendall School (fictional)"]
JOBS = ["Storefront signs", "Yard signs", "Event banners", "Vehicle wrap", "Window graphics", "Menu boards",
        "Team shirts", "Rush banner", "Trade show booth", "Business cards"]
# Cost types the generator uses, and what each one is under MargenX's written rules.
COST_TYPES = {"Labor": "labor", "Materials": "materials", "Vinyl": "materials", "Outsourced work": "outsourced",
              "Subcontractor": "outsourced", "Shipping": "other", "Equipment rent": "other",
              "Merchant fees": "fees", "Rent": "overhead", "Utilities": "overhead"}
JOB_COST_TYPES = ["Labor", "Materials", "Vinyl", "Outsourced work", "Subcontractor", "Shipping", "Equipment rent",
                  "Merchant fees"]
OVERHEAD_TYPES = ["Rent", "Utilities"]


@dataclass
class Line:
    number: str
    day: int
    party: str          # customer (sales) or vendor (costs)
    job: str            # "" = no job number
    kind: str           # description (sales) or cost type (costs)
    cents: int


@dataclass
class Shop:
    seed: int
    sales: list[Line] = field(default_factory=list)
    costs: list[Line] = field(default_factory=list)


def make_shop(seed: int) -> Shop:
    rng = random.Random(seed)
    shop = Shop(seed)
    customers = rng.sample(CUSTOMERS, rng.randint(2, len(CUSTOMERS)))
    n_jobs = rng.randint(3, 18)
    numbers = iter(range(1000, 100000))

    def sale(job, customer, cents, what):
        shop.sales.append(Line(f"INV-{next(numbers)}", rng.randint(1, 28), customer, job, what, cents))

    def cost(job, cost_type, cents):
        shop.costs.append(Line(f"B-{next(numbers)}", rng.randint(1, 28), f"{cost_type} supplier (fictional)", job,
                               cost_type, cents))

    for j in range(n_jobs):
        job = f"J-{100 + j}"
        what = rng.choice(JOBS)
        customer = rng.choice(customers)
        shape = rng.random()
        if rng.random() < 0.12:  # a margin of exactly x.5%: tests how halves are rounded on screen
            m, n = rng.randint(1, 20), rng.randint(-20, 99)
            sold, left = 20000 * m, 100 * m * (2 * n + 1)  # left / sold = (2n + 1) / 200, a half percent
            sale(job, customer, sold, what)
            cost(job, "Labor", (sold - left) // 3)
            cost(job, "Materials", sold - left - (sold - left) // 3)
            continue
        if shape < 0.06:  # costs but no sales: no figure
            pass
        elif shape < 0.09:  # only a credit: needs a check
            sale(job, customer, -rng.randint(500, 20000), what)
        else:
            for _ in range(rng.randint(1, 3)):
                sale(job, customer, rng.randint(5000, 800000), what)
            if rng.random() < 0.12:  # a refund or credit on the job
                sale(job, customer, -rng.randint(100, 20000), what)
            if rng.random() < 0.05:  # billed to a second customer too
                sale(job, rng.choice([c for c in customers if c != customer] or customers),
                     rng.randint(5000, 100000), what)
        if rng.random() < 0.06 and shape >= 0.06:  # sales but no costs: no figure
            continue
        if rng.random() < 0.85:
            for _ in range(rng.randint(1, 2)):
                cost(job, "Labor", rng.randint(2000, 300000))
        elif rng.random() < 0.3:
            cost(job, "Labor", 0)  # a $0.00 placeholder proves nothing was spent
        if rng.random() < 0.85:
            for _ in range(rng.randint(1, 3)):
                cost(job, rng.choice(["Materials", "Vinyl", "Outsourced work", "Subcontractor"]),
                     rng.randint(1000, 400000))
        for _ in range(rng.choice([0, 0, 0, 1, 2])):
            cost(job, rng.choice(["Shipping", "Equipment rent", "Merchant fees"]), rng.randint(100, 50000))
        if shape < 0.06 and not any(c.job == job for c in shop.costs):
            cost(job, "Materials", rng.randint(1000, 50000))
    for _ in range(rng.choice([0, 1, 1, 2, 3])):  # rent and utilities: overhead, never a job's cost
        cost("", rng.choice(OVERHEAD_TYPES), rng.randint(50000, 400000))
    if rng.random() < 0.15:  # a cost with no job number that could be a job's cost
        cost("", rng.choice(["Materials", "Shipping"]), rng.randint(1000, 90000))
    if rng.random() < 0.15:  # a sale with no job number
        sale("", rng.choice(customers), rng.randint(5000, 200000), "Misc")
    return shop


# ---- Writing the shop as CSV files, the way a shop's export might look ----

def money_text(cents: int, rng: random.Random) -> str:
    """Plain ("1234.50") or with a dollar sign and commas ("$1,234.50"), and a minus for credits."""
    sign, cents = ("-" if cents < 0 else ""), abs(cents)
    dollars, rest = divmod(cents, 100)
    if rng.random() < 0.5:
        return f"{sign}{dollars}.{rest:02d}"
    return f"{sign}${dollars:,}.{rest:02d}"


def to_csv(shop: Shop) -> tuple[bytes, bytes]:
    rng = random.Random(shop.seed * 7919)
    sales = ["Invoice,Date,Customer,Job,Description,Amount"]
    for s in shop.sales:
        sales.append(f'{s.number},10/{s.day:02d}/2026,"{s.party}",{s.job},"{s.kind}",{_quote(money_text(s.cents, rng))}')
    costs = ["Bill,Date,Vendor,Job,Type,Amount"]
    for c in shop.costs:
        costs.append(f'{c.number},10/{c.day:02d}/2026,"{c.party}",{c.job},{c.kind},{_quote(money_text(c.cents, rng))}')
    return ("\n".join(sales) + "\n").encode(), ("\n".join(costs) + "\n").encode()


def _quote(text: str) -> str:
    return f'"{text}"' if "," in text else text


# ---- The right answers, worked out from the shop itself in whole cents ----

@dataclass
class JobAnswer:
    sales: int
    costs: dict[str, int]
    status: str            # complete, provisional, unavailable
    customers: tuple[str, ...]

    @property
    def total_costs(self) -> int:
        return sum(self.costs.values())

    @property
    def contribution(self) -> int | None:
        return None if self.status == "unavailable" else self.sales - self.total_costs


@dataclass
class CustomerAnswer:
    sales: int
    costs: int
    status: str

    @property
    def contribution(self) -> int | None:
        return None if self.status == "unavailable" else self.sales - self.costs


@dataclass
class Answer:
    jobs: dict[str, JobAnswer]
    customers: dict[str, CustomerAnswer]
    total_sales: int
    left: int                     # sum of job figures that exist
    jobs_with_figure: int
    complete_jobs: int
    losing: int                   # complete jobs below zero
    possible_losses: int          # jobs that need a check and are below zero so far
    unlinked_sales: int
    unlinked_sales_lines: int
    overhead: int
    unassigned_job_costs: int
    after_unlinked: int | None    # None = withheld
    usual_margin: Fraction | None


def answer(shop: Shop) -> Answer:
    job_ids = sorted({s.job for s in shop.sales if s.job} | {c.job for c in shop.costs if c.job})
    unlinked_job_like = [c for c in shop.costs if not c.job and COST_TYPES[c.kind] != "overhead"]
    unlinked_sales = [s for s in shop.sales if not s.job]
    customers_with_unlinked_sales = {s.party for s in unlinked_sales}
    jobs: dict[str, JobAnswer] = {}
    for job in job_ids:
        sales_lines = [s for s in shop.sales if s.job == job]
        cost_lines = [c for c in shop.costs if c.job == job]
        costs = {k: 0 for k in ("labor", "materials", "outsourced", "other", "fees")}
        for c in cost_lines:
            costs[COST_TYPES[c.kind]] += c.cents
        customers = tuple(sorted({s.party for s in sales_lines}))
        if not sales_lines or not cost_lines:
            status = "unavailable"
        else:
            complete = (any(s.cents > 0 for s in sales_lines) and costs["labor"] > 0
                        and (costs["materials"] > 0 or costs["outsourced"] > 0) and len(customers) == 1
                        and not unlinked_job_like and not (set(customers) & customers_with_unlinked_sales))
            status = "complete" if complete else "provisional"
        jobs[job] = JobAnswer(sum(s.cents for s in sales_lines), costs, status, customers)

    customers: dict[str, CustomerAnswer] = {}
    names = ({c for j in jobs.values() for c in j.customers} | customers_with_unlinked_sales)
    for name in names:
        own = [j for j in jobs.values() if j.customers == (name,)]
        counted = [j for j in own if j.status != "unavailable"]
        shared = any(name in j.customers and len(j.customers) > 1 for j in jobs.values())
        held_back = (any(j.status == "unavailable" for j in own) or shared or name in customers_with_unlinked_sales
                     or any(j.status == "provisional" for j in counted))
        status = "unavailable" if not counted else ("provisional" if held_back else "complete")
        customers[name] = CustomerAnswer(sum(j.sales for j in counted), sum(j.total_costs for j in counted), status)

    with_figure = [j for j in jobs.values() if j.status != "unavailable"]
    complete = [j for j in with_figure if j.status == "complete"]
    left = sum(j.contribution for j in with_figure)
    unlinked_costs = sum(c.cents for c in shop.costs if not c.job)
    unassigned = sum(c.cents for c in unlinked_job_like)
    partial = len(with_figure) < len(jobs) or bool(unlinked_sales) or not with_figure
    usual_jobs = [j for j in complete if j.sales > 0]
    usual = (Fraction(sum(j.contribution for j in usual_jobs), sum(j.sales for j in usual_jobs))
             if len(usual_jobs) >= 3 and sum(j.sales for j in usual_jobs) > 0 else None)
    return Answer(
        jobs=jobs, customers=customers,
        total_sales=sum(s.cents for s in shop.sales), left=left,
        jobs_with_figure=len(with_figure), complete_jobs=len(complete),
        losing=sum(1 for j in complete if j.contribution < 0),
        possible_losses=sum(1 for j in with_figure if j.status == "provisional" and j.contribution < 0),
        unlinked_sales=sum(s.cents for s in unlinked_sales), unlinked_sales_lines=len(unlinked_sales),
        overhead=unlinked_costs - unassigned, unassigned_job_costs=unassigned,
        after_unlinked=None if partial else left - unlinked_costs,
        usual_margin=usual,
    )


# ---- How the right answers should read on screen ----

def shown_money(cents: int) -> str:
    """"$1,300", "$12.50", "-$140": whole dollars drop ".00"."""
    sign, cents = ("-" if cents < 0 else ""), abs(cents)
    dollars, rest = divmod(cents, 100)
    return f"{sign}${dollars:,}" + ("" if rest == 0 else f".{rest:02d}")


def shown_percent(part: int, whole: int) -> int | None:
    """Whole percent, halves rounded away from zero; None when there's nothing to divide by."""
    if whole <= 0:
        return None
    value = Fraction(part * 100, whole)
    rounded = int(abs(value) + Fraction(1, 2))
    return rounded if value >= 0 else -rounded


def price_at(costs_cents: int, margin: Fraction) -> int:
    """Whole dollars at a margin: costs / (1 - margin), halves rounded up."""
    dollars = Fraction(costs_cents, 100) / (1 - margin)
    return int(dollars + Fraction(1, 2))
