"""MargenX accuracy self-tests: random made-up shops with known answers, run through the whole app.

Each shop comes from tests/accuracy_shops.py, which works out the right answers in whole cents
without using any MargenX code. The shop is written as ordinary CSV files and read by MargenX
exactly as an upload would be (intake, profit engine, summary). Every job, customer and headline
figure, every status, and the prices at the usual margin must match. A second check renders the
results screen and reads the numbers back off it.

Run thousands of shops with: python scripts/accuracy_check.py 5000
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
import re
import unittest
from unittest import mock

import job_intake as ji
import job_profit as jp
import marginx_insights as mi
import marginx_ui as ui

from tests import accuracy_shops as shops

SHOPS_IN_CI = 400
CATEGORY = {"labor": "labor", "materials": "materials", "outsourced": "outsourced", "other": "other",
            "fees": "fees_overhead"}


def cents(amount: Decimal) -> int:
    value = amount * 100
    assert value == value.to_integral_value(), amount
    return int(value)


def run_margenx(shop: shops.Shop):
    """The shop's CSV files through MargenX, as an upload would go."""
    invoices, costs = shops.to_csv(shop)
    results = {}
    for data, kind in ((invoices, "invoices"), (costs, "costs")):
        headers, records = ji.read_csv(data)
        results[kind] = ji.intake(headers, records, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY")
    return results, jp.job_profit(results["invoices"], results["costs"])


def mismatches(seed: int) -> list[str]:
    """Every difference between MargenX and the known answers for one shop (empty = all correct)."""
    shop = shops.make_shop(seed)
    want = shops.answer(shop)
    results, report = run_margenx(shop)
    found: list[str] = []

    def check(what, got, expected):
        if got != expected:
            found.append(f"seed {seed}: {what}: MargenX {got!r}, expected {expected!r}")

    for kind, result in results.items():
        check(f"{kind} rows MargenX couldn't read", [r["reasons"] for r in result.rejected], [])
        check(f"{kind} rows read", len(result.accepted), len(shop.sales if kind == "invoices" else shop.costs))
    if found:
        return found
    jobs = {j.job_id: j for j in report.jobs}
    check("jobs", sorted(jobs), sorted(want.jobs))
    for job_id, expected in want.jobs.items():
        got = jobs.get(job_id)
        if got is None:
            continue
        check(f"{job_id} status", got.status, expected.status)
        check(f"{job_id} customers", got.customers, expected.customers)
        check(f"{job_id} sales", cents(got.sales), expected.sales)
        for mine, theirs in CATEGORY.items():
            check(f"{job_id} {theirs}", cents(got.costs[theirs]), expected.costs[mine])
        check(f"{job_id} figure", None if got.contribution is None else cents(got.contribution), expected.contribution)

    customers = {c.customer: c for c in report.customers}
    check("customers", sorted(customers), sorted(want.customers))
    for name, expected in want.customers.items():
        got = customers.get(name)
        if got is None:
            continue
        check(f"{name} status", got.status, expected.status)
        if expected.status != "unavailable":
            check(f"{name} sales", cents(got.sales), expected.sales)
            check(f"{name} figure", cents(got.contribution), expected.contribution)

    summary = mi.summarize(report)
    check("total sales", cents(summary.sales), want.total_sales)
    check("left after job costs", cents(summary.left_after_job_costs), want.left)
    check("jobs with a figure", summary.jobs_with_figure, want.jobs_with_figure)
    check("complete jobs", summary.complete_jobs, want.complete_jobs)
    check("jobs losing money", summary.losing_jobs, want.losing)
    check("possible losses", summary.possible_losses, want.possible_losses)
    check("sales with no job number", cents(summary.unlinked_sales), want.unlinked_sales)
    check("overhead", cents(summary.overhead_costs), want.overhead)
    check("costs with no job number", cents(summary.unassigned_job_costs), want.unassigned_job_costs)
    check("after overhead", None if summary.after_unlinked_costs is None else cents(summary.after_unlinked_costs),
          want.after_unlinked)
    check("usual margin given", summary.usual_margin is not None, want.usual_margin is not None)
    if summary.usual_margin is not None and want.usual_margin is not None:
        # MargenX divides with 28 significant digits; the shown percent and every price must agree exactly.
        check("usual margin shown", mi.percent(summary.usual_margin, Decimal(1)),
              shops.shown_percent(want.usual_margin.numerator, want.usual_margin.denominator))
        for job_id, expected in want.jobs.items():
            if expected.status == "complete" and expected.total_costs > 0 and Fraction(0) < want.usual_margin < 1:
                price = mi.pricing(jobs[job_id], summary.usual_margin)
                # Exact: a whole-dollar Decimal, so "1062.99" can never pass for 1062.
                got = None if not price else price["at_usual"]
                check(f"{job_id} price at usual margin", got,
                      Decimal(shops.price_at(expected.total_costs, want.usual_margin)))
    return found


def screen(report) -> str:
    """The results screen's HTML, as MargenX sends it to the browser (not a browser rendering)."""
    out: list[str] = []
    with mock.patch.object(ui, "_html", out.append):
        ui.results(report, mi.summarize(report), mi.attention(report), mi.period_text(report))
    return "".join(out)


def screen_mismatches(seed: int) -> list[str]:
    """The numbers a shop owner reads on the results screen, against the known answers."""
    shop = shops.make_shop(seed)
    _, report = run_margenx(shop)
    return screen_problems(screen(report), shops.answer(shop), seed)


def card(html: str, label: str) -> str | None:
    """The value shown on one headline card, read from that card only."""
    found = re.search(rf'<div class="mx-metric"><div class="l">{re.escape(label)}</div><div class="v [^"]*">([^<]*)</div>',
                      html)
    return found.group(1) if found else None


def screen_problems(html: str, want: shops.Answer, seed) -> list[str]:
    found: list[str] = []

    def expect(what, text):
        if text not in html:
            found.append(f"seed {seed}: on screen, {what}: expected to find {text!r}")

    def expect_card(label, value):
        if card(html, label) != value:
            found.append(f"seed {seed}: on screen, {label} card shows {card(html, label)!r}, expected {value!r}")

    expect_card("Sales", shops.shown_money(want.total_sales))
    # No figure at all, or no complete job: a dash on that card, never $0.
    expect_card("Left after job costs", shops.shown_money(want.left) if want.jobs_with_figure else "—")
    expect_card("Jobs losing money", f"{want.losing} of {want.complete_jobs}" if want.complete_jobs else "—")
    if want.overhead or want.unassigned_job_costs:
        if want.after_unlinked is None:
            expect("after-overhead total withheld", "A total after them isn't shown yet")
            if "these files leave" in html:
                found.append(f"seed {seed}: on screen, an after-overhead total is shown though it must be withheld")
        else:
            expect("after-overhead line", f"these files leave <b>{shops.shown_money(want.after_unlinked)}</b>")
    blocks = re.findall(r'<details class="mx-d">(.*?)</details>', html)
    for job_id, expected in want.jobs.items():
        block = next((b for b in blocks if f"· {job_id}</small>" in b), None)
        if block is None:
            found.append(f"seed {seed}: on screen, job {job_id} is missing")
            continue
        amount = re.search(r'<div class="a[^"]*">([^<]*)', block).group(1)
        figure = expected.contribution
        if amount != ("—" if figure is None else shops.shown_money(figure)):
            found.append(f"seed {seed}: on screen, job {job_id} shows {amount!r}, expected "
                         f"{'—' if figure is None else shops.shown_money(figure)!r}")
        if figure is not None and expected.sales > 0:
            share = shops.shown_percent(figure, expected.sales)
            margin = f"{share}% margin" + (" so far" if expected.status != "complete" else "")
            if f'<span class="p">{margin}</span>' not in block:
                found.append(f"seed {seed}: on screen, job {job_id} margin: expected {margin!r}")
        elif re.search(r'<span class="p">[^<]*% margin', block):  # no figure, or no positive sales: no margin shown
            found.append(f"seed {seed}: on screen, job {job_id} shows a margin it shouldn't")
        if expected.sales and (f'<td>Sold for</td><td class="r">{shops.shown_money(expected.sales)}</td>' not in block):
            found.append(f"seed {seed}: on screen, job {job_id} breakdown 'Sold for' doesn't match")
        label = {"complete": "Complete", "provisional": "Needs a check", "unavailable": "No figure yet"}[expected.status]
        if f'<span class="mx-tag {expected.status}">{label}</span>' not in block:
            found.append(f"seed {seed}: on screen, job {job_id} status: expected {label!r}")
    left_out = sorted(n for n, c in want.customers.items() if c.status == "unavailable")
    shown = any(c.status != "unavailable" for c in want.customers.values())
    if not shown and "Customers, by what they leave you" in html:
        found.append(f"seed {seed}: on screen, the customer list is shown though no customer has a figure")
    # The customer list (and its note) appears only when at least one customer has a figure.
    if shown and left_out and f"Not listed, no figure yet: {', '.join(left_out)}." not in html:
        found.append(f"seed {seed}: on screen, customers with no figure should be named: {left_out}")
    for name, expected in want.customers.items():
        if expected.status == "unavailable":
            if any(f'<div class="n">{name}<' in b for b in blocks):
                found.append(f"seed {seed}: on screen, customer {name} has no figure but is listed")
            continue
        block = next((b for b in blocks if f'<div class="n">{name}<' in b), None)
        if block is None:
            found.append(f"seed {seed}: on screen, customer {name} is missing")
            continue
        share = shops.shown_percent(expected.contribution, expected.sales)
        text = (f'<div class="a">{shops.shown_money(expected.contribution)}</div><div class="p">'
                + ("" if share is None else f"{share}% of ") + f"{shops.shown_money(expected.sales)}</div>")
        if text not in block:
            found.append(f"seed {seed}: on screen, customer {name}: expected {text!r}")
        if ("<small>Needs a check</small>" in block) != (expected.status == "provisional"):
            found.append(f"seed {seed}: on screen, customer {name} 'Needs a check' note doesn't match {expected.status}")
    return found


class AccuracyCheckScriptTests(unittest.TestCase):
    def test_script_refuses_to_check_no_shops(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "scripts" / "accuracy_check.py"
        spec = importlib.util.spec_from_file_location("accuracy_check", path)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        for bad in ("0", "-1", "lots"):
            self.assertEqual(2, script.main(["accuracy_check.py", bad]), bad)
        self.assertEqual(0, script.main(["accuracy_check.py", "3"]))


class AccuracyTests(unittest.TestCase):
    def test_random_shops_match_the_known_answers(self):
        problems = [p for seed in range(SHOPS_IN_CI) for p in mismatches(seed)]
        self.assertEqual([], problems[:20], f"{len(problems)} mismatches")

    def test_numbers_on_screen_match_the_known_answers(self):
        problems = [p for seed in range(SHOPS_IN_CI) for p in screen_mismatches(seed)]
        self.assertEqual([], problems[:20], f"{len(problems)} mismatches")

    def test_the_generator_covers_the_cases_that_matter(self):
        # The shops must exercise every status, losses, credits, overhead, unlinked costs and sales,
        # shared jobs and the usual-margin prices, or a pass would prove little.
        seen = set()
        for seed in range(SHOPS_IN_CI):
            shop = shops.make_shop(seed)
            want = shops.answer(shop)
            seen |= {j.status for j in want.jobs.values()}
            seen |= {"loss" for j in want.jobs.values() if j.contribution is not None and j.contribution < 0}
            seen |= {"credit" for s in shop.sales if s.cents < 0}
            seen |= {"shared" for j in want.jobs.values() if len(j.customers) > 1}
            seen |= {"overhead"} if want.overhead else set()
            seen |= {"unlinked cost"} if want.unassigned_job_costs else set()
            seen |= {"unlinked sale"} if want.unlinked_sales_lines else set()
            seen |= {"after overhead shown"} if want.after_unlinked is not None else set()
            seen |= {"usual margin"} if want.usual_margin is not None else set()
            seen |= {"$0 labor"} if any(c.kind == "Labor" and c.cents == 0 for c in shop.costs) else set()
            seen |= {"rent on a job"} if any(c.kind == "Rent" and c.job for c in shop.costs) else set()
            seen |= {"half percent"} if any(j.contribution is not None and j.sales > 0
                                            and (j.contribution * 200) % j.sales == 0
                                            and (j.contribution * 200 // j.sales) % 2 == 1
                                            for j in want.jobs.values()) else set()
        self.assertEqual({"complete", "provisional", "unavailable", "loss", "credit", "shared", "overhead",
                          "unlinked cost", "unlinked sale", "after overhead shown", "usual margin", "$0 labor",
                          "half percent", "rent on a job"}, seen)

    def test_empty_states_on_fixed_shops(self):
        L = shops.Line
        # No job has a figure: J-1 has sales but no costs. Rent has no job number.
        none = shops.Shop(1, sales=[L("I-1", 5, "A (fictional)", "J-1", "Banner", 50000)],
                          costs=[L("B-1", 5, "Landlord (fictional)", "", "Rent", 100000)])
        # No job is complete: J-2 has no labor, J-1 has no costs, so the total after rent is withheld too.
        incomplete = shops.Shop(2, sales=[L("I-1", 5, "A (fictional)", "J-1", "Banner", 50000),
                                          L("I-2", 6, "B (fictional)", "J-2", "Signs", 80000)],
                                costs=[L("B-1", 6, "Supply (fictional)", "J-2", "Materials", 30000),
                                       L("B-2", 7, "Landlord (fictional)", "", "Rent", 100000)])
        for shop in (none, incomplete):
            want = shops.answer(shop)
            html = screen(run_margenx(shop)[1])
            self.assertEqual([], screen_problems(html, want, shop.seed))
            self.assertEqual("—", card(html, "Jobs losing money"))
            self.assertNotIn("these files leave", html)
        self.assertEqual("—", card(screen(run_margenx(none)[1]), "Left after job costs"))
        self.assertEqual(("$500", 1, 0), (card(screen(run_margenx(incomplete)[1]), "Left after job costs"),
                                          shops.answer(incomplete).jobs_with_figure,
                                          shops.answer(incomplete).complete_jobs))

    def test_screen_check_catches_a_wrong_card_or_an_exposed_total(self):
        L = shops.Line
        shop = shops.Shop(3, sales=[L("I-1", 5, "A (fictional)", "J-1", "Banner", 50000),
                                    L("I-2", 6, "B (fictional)", "J-2", "Signs", 80000)],
                          costs=[L("B-1", 6, "Supply (fictional)", "J-2", "Materials", 30000),
                                 L("B-2", 7, "Landlord (fictional)", "", "Rent", 100000)])
        want = shops.answer(shop)
        html = screen(run_margenx(shop)[1])
        self.assertEqual([], screen_problems(html, want, 3))
        zero_card = re.sub(r'(<div class="l">Jobs losing money</div><div class="v [^"]*">)—(</div>)', r"\g<1>$0\2", html)
        self.assertNotEqual(html, zero_card)
        self.assertTrue(any("Jobs losing money card" in p for p in screen_problems(zero_card, want, 3)))
        exposed = html + '<div class="mx-after"><div>After the costs, these files leave <b>-$500</b></div></div>'
        self.assertTrue(any("must be withheld" in p for p in screen_problems(exposed, want, 3)))

    def test_demo_shop_matches_the_hand_worked_example(self):
        # The numbers worked out by hand in docs/ACCURACY.md, from the demo shop's CSV files.
        from pathlib import Path
        samples = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"
        results = {}
        for kind in ("invoices", "costs"):
            headers, records = ji.read_csv((samples / f"demo_sign_shop_{kind}.csv").read_bytes())
            results[kind] = ji.intake(headers, records, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY")
        report = jp.job_profit(results["invoices"], results["costs"])
        summary = mi.summarize(report)
        j105 = next(j for j in report.jobs if j.job_id == "J-105")
        self.assertEqual((60000, 34000, 28000, 12000, 0, 0, 0),
                         (cents(j105.sales), cents(j105.costs["materials"]), cents(j105.costs["outsourced"]),
                          cents(j105.costs["labor"]), cents(j105.costs["fees_overhead"]), cents(j105.costs["other"]),
                          cents(j105.costs["unknown"])))
        self.assertEqual((74000, -14000), (cents(j105.total_costs), cents(j105.contribution)))
        complete = [j for j in report.jobs if j.status == "complete"]
        self.assertEqual((7, 1030000, 312000), (len(complete), cents(sum(j.sales for j in complete)),
                                                cents(sum(j.contribution for j in complete))))
        self.assertEqual(-23, mi.percent(j105.contribution, j105.sales))
        self.assertEqual((1100000, 364000, 164000, 1, 7), (cents(summary.sales), cents(summary.left_after_job_costs),
                                                           cents(summary.after_unlinked_costs), summary.losing_jobs,
                                                           summary.complete_jobs))
        self.assertEqual(Fraction(312000, 1030000), summary.usual_margin)  # exact: 156/515
        self.assertEqual((30, Decimal("1062"), Decimal("740.00")),
                         (mi.percent(summary.usual_margin, Decimal(1)), mi.pricing(j105, summary.usual_margin)["at_usual"],
                          mi.pricing(j105, summary.usual_margin)["break_even"]))
        bayside = next(c for c in report.customers if c.customer.startswith("Bayside"))
        self.assertEqual((585000, 75000, 13), (cents(bayside.sales), cents(bayside.contribution),
                                               mi.percent(bayside.contribution, bayside.sales)))

    def test_the_independent_calculator_agrees_with_a_hand_count(self):
        # One tiny shop worked by hand, so the checker itself is checked.
        shop = shops.Shop(0, sales=[shops.Line("I-1", 5, "A (fictional)", "J-1", "Banner", 60000),
                                    shops.Line("I-2", 6, "A (fictional)", "J-1", "Banner", -5000)],
                          costs=[shops.Line("B-1", 5, "x", "J-1", "Labor", 12000),
                                 shops.Line("B-2", 5, "x", "J-1", "Materials", 34000),
                                 shops.Line("B-3", 5, "x", "", "Rent", 100000)])
        want = shops.answer(shop)
        # $600 - $50 credit = $550 sold; $120 labor + $340 materials = $460 costs; $90 left.
        self.assertEqual((55000, 46000, 9000, "complete"),
                         (want.jobs["J-1"].sales, want.jobs["J-1"].total_costs, want.jobs["J-1"].contribution,
                          want.jobs["J-1"].status))
        self.assertEqual(9000 - 100000, want.after_unlinked)  # $90 left minus $1,000 rent
        self.assertEqual(("$550", "-$910", "$12.50", 16), (shops.shown_money(55000), shops.shown_money(-91000),
                                                           shops.shown_money(1250), shops.shown_percent(9000, 55000)))


if __name__ == "__main__":
    unittest.main()
