"""Issue #128: every job cost on its job before a QuickBooks job's profit is Complete (labor-gap plan v3, J1-J4).

The gap: once the file checks passed, a job with materials but no labor showed Complete with its profit too high,
and a job with a sale and no costs showed Complete at 100%. A file can't show that a job's costs are all on the job
(crew pay run as overhead, materials booked to overhead, a bill not entered yet), and a line check can't prove it
either. So the owner confirms MargenX's cost list for this exact file (J1), every job-cost figure holds until then
(J2), a job or customer with sales and no costs holds even after "yes" (J3), and the company's profit after overhead
is built from its own parts (J4).

One test per row of the plan's test list (issue #128, plan v3), the round-3 review's two warnings, and the
limitation test: a wrong "yes" can still give Complete figures. Every company, customer, vendor and amount here is
made up; every report is built in the layout seen (tests/quickbooks_fixtures.py) and read end to end from Excel bytes.
"""
import dataclasses
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_questions as qq  # noqa: E402
import quickbooks_results as qr  # noqa: E402
import qbo_job_costs as jc  # noqa: E402
import test_quickbooks_coverage as t  # noqa: E402

L = fx.line
X, Y, KITCHEN, PATIO = t.X, t.Y, t.KITCHEN, t.PATIO
Z = "Customer Z (fictional)"
ON, OVERHEAD_TOO = qf.JOB_COSTS_ON_JOBS, qf.JOB_COSTS_SOME_OVERHEAD
JOB_COSTS_TITLE = "Is every job cost for these dates in this report, on its job?"


def row_of(report, num: str) -> int:
    return next(line.row for line in report.lines if line.num == num)


def overhead(report, *names) -> dict:
    """Each named Expenses account answered overhead, every entry confirmed."""
    return {("Expenses", name): qf.AccountAnswer(qf.OVERHEAD_ACCOUNT, qf.entry_keys(report, ("Expenses", name)))
            for name in names}


def ready(report, *, check=None, overhead_accounts=(), accounts=None, lines=None, jobs=True) -> qf.OwnerAnswers:
    """Every answer but J1: jobs, every cost account job costs (some overhead), the no-filter answer when there's a
    cross-check, the given line answers, and the coverage "yes", as the screens record them."""
    answers = t.base(report, check=check, accounts=accounts, job_costs=False)
    accounts = {**answers.accounts, **overhead(report, *overhead_accounts)}
    answers = dataclasses.replace(answers, accounts=accounts, lines=lines or {}, sub_customers_are_jobs=jobs)
    return t.say(report, answers, qf.COVERAGE_YES, check)


def with_check(report):
    return qc.cross_check(report, t.sales_report())


def j2(figure: qf.Figure) -> list[str]:
    return [h.reason for h in figure.holds if h.kind == qf.JOB_COSTS_HOLD]


def j3(figure: qf.Figure) -> list[str]:
    return [h.reason for h in figure.holds if h.kind == qf.NO_JOB_COSTS_HOLD]


def partial_labor():
    """Patio: $1,200 of sales, $800 of materials and an $80 labor bill on the job; $450 of crew pay for it run through
    payroll as overhead (round-1 blocker 1)."""
    return t.pnl({"Income": [("Design income", t.income())],
                  "Expenses": [("Job Materials", t.materials()),
                               ("Labor", [*t.labor(), L(8, "Bill", "B-4", f"{Y}:Patio", D("80"), None)]),
                               ("Payroll Expenses", [L(9, "Check", "C-1", "Crew pay (fictional)", D("450"), None)])]})


def materials_in_overhead():
    """Patio: $80 of labor on the job, its $800 of materials booked to an overhead account (round-1 blocker 2)."""
    return t.pnl({"Income": [("Design income", t.income())],
                  "Expenses": [("Job Materials", t.materials(y_too=False)),
                               ("Labor", [*t.labor(), L(8, "Bill", "B-4", f"{Y}:Patio", D("80"), None)]),
                               ("Supplies", [L(9, "Check", "C-2", "Supplier (fictional)", D("800"), None)])]})


class PartialCostsTests(unittest.TestCase):
    """Plan tests 1, 2 and 4: costs partly on the job, the rest in overhead or not in the report at all."""

    def check_outcomes(self, report, overhead_account, patio_profit):
        check = with_check(report)
        answers = ready(report, check=check, overhead_accounts=(overhead_account,))
        after_overhead = D("5700") - sum(l.amount for l in report.lines if l.section == "Expenses")

        some = qf.figures(report, jc.confirmed(report, answers, OVERHEAD_TOO), cross_check=check)
        self.assertEqual(OVERHEAD_TOO, some.job_costs)
        for group in (some.jobs[PATIO], some.jobs[KITCHEN], some.customers[X], some.customers[Y]):
            for name in ("job_costs", "profit_after_job_costs"):
                self.assertEqual(qp.NEEDS_A_CHECK, group[name].status)
                self.assertEqual(1, len(j2(group[name])), name)
        for name in ("job_costs", "profit_after_job_costs", "overhead"):
            self.assertEqual(1, len(j2(some.company[name])), name)
        # Every job cost is in this report: profit after overhead includes them, so J2 doesn't hold it (J4).
        self.assertEqual((after_overhead, qp.COMPLETE), (some.company["after_overhead"].amount,
                                                         some.company["after_overhead"].status))
        self.assertEqual(patio_profit, some.jobs[PATIO]["profit_after_job_costs"].amount)  # never changed

        unanswered = qf.figures(report, answers, cross_check=check)
        self.assertEqual(qf.JOB_COSTS_NOT_CONFIRMED, unanswered.job_costs)
        self.assertEqual((after_overhead, qp.NEEDS_A_CHECK), (unanswered.company["after_overhead"].amount,
                                                              unanswered.company["after_overhead"].status))
        self.assertEqual(1, len(j2(unanswered.company["after_overhead"])))

        # The limitation: a wrong "yes" gives Complete figures, exact to the cent and still overstated.
        wrong = qf.figures(report, jc.confirmed(report, answers, ON), cross_check=check)
        self.assertEqual({qp.COMPLETE}, t.statuses(wrong))
        self.assertEqual(patio_profit, wrong.jobs[PATIO]["profit_after_job_costs"].amount)
        self.assertEqual(after_overhead, wrong.company["after_overhead"].amount)

    def test_partial_labor(self):
        self.check_outcomes(partial_labor(), "Payroll Expenses", D("320"))  # $1,200 - $800 - $80

    def test_materials_in_overhead(self):
        self.check_outcomes(materials_in_overhead(), "Supplies", D("1120"))  # $1,200 - $80

    def test_only_yes_or_all_in_the_report_leave_profit_after_overhead_alone(self):
        # Round-1 blocker 4: $100 in overhead and $450 never posted can't truthfully be "all in this report", so the
        # owner answers "Not sure"; no answer, "not sure", or an answer that no longer applies all hold it.
        report = partial_labor()
        answers = ready(report, overhead_accounts=("Payroll Expenses",))
        given = jc.confirmed(report, answers, ON)
        question = next(q for q in qq.open_questions(report, answers).questions if q.kind == qq.JOB_COSTS)
        cases = {"none": answers,
                 "not sure": qq.answer(report, given, question, qq.NOT_SURE),
                 "another list": dataclasses.replace(given, job_costs=jc.answer(report, answers, costs="0" * 64)),
                 "another workbook": dataclasses.replace(given, job_costs=jc.answer(report, answers, file="f" * 64)),
                 "other words": dataclasses.replace(given, job_costs=jc.answer(
                     report, answers, statement="All my job costs are on my jobs.")),
                 "unknown choice": dataclasses.replace(given, job_costs=jc.answer(report, answers, "maybe"))}
        for name, case in cases.items():
            with self.subTest(name):
                result = qf.figures(report, case)
                self.assertEqual(qf.JOB_COSTS_NOT_CONFIRMED, result.job_costs)
                self.assertEqual(qp.NEEDS_A_CHECK, result.company["after_overhead"].status)
                self.assertEqual(1, len(j2(result.company["after_overhead"])))
                if name != "none" and name != "not sure":
                    self.assertTrue(result.warnings, name)  # never silently dropped
        for choice in (ON, OVERHEAD_TOO):
            self.assertEqual([], j2(qf.figures(report, jc.confirmed(report, answers, choice)).company["after_overhead"]))


class NoCostsTests(unittest.TestCase):
    """J3, plan tests 3, 6 (credit-only), 7 and 8: sales activity with no counted job cost holds, even after "yes"."""

    def test_an_exact_refund_still_needs_costs(self):
        # Round-1 blocker 3: an invoice and a matching credit memo net to $0 of sales, with $0 of costs.
        report = t.pnl({"Income": [("Design income", [*t.income(),
                                                      L(4, "Credit Memo", "CM-1", f"{Y}:Patio", D("-1200"), None)])],
                        "Expenses": [("Job Materials", t.materials(y_too=False)), ("Labor", t.labor())]})
        lines = {row_of(report, "CM-1"): qf.LineAnswer(qf.REDUCTION)}
        result = qf.figures(report, jc.confirmed(report, ready(report, lines=lines)))
        self.assertEqual(ON, result.job_costs)
        self.assertEqual((D("0"), D("0")), (result.jobs[PATIO]["sales"].amount, result.jobs[PATIO]["job_costs"].amount))
        for figure in (result.jobs[PATIO]["job_costs"], result.jobs[PATIO]["profit_after_job_costs"],
                       result.customers[Y]["profit_after_job_costs"]):
            self.assertEqual(qp.NEEDS_A_CHECK, figure.status)
            self.assertTrue(j3(figure))
        self.assertIn("Customer Y (fictional) › Patio: no job costs are counted for this job in this report yet, or "
                      "they add up to $0 or less (credits included)", j3(result.jobs[PATIO]["profit_after_job_costs"])[0])
        self.assertEqual([], j3(result.jobs[KITCHEN]["profit_after_job_costs"]))
        self.assertEqual(qp.COMPLETE, result.company["profit_after_job_costs"].status)  # J3 never holds the company

    def test_case_b_no_costs_holds_the_job_and_its_customer_after_yes(self):
        check_report = t.pnl({"Income": [("Design income", t.income())],
                              "Expenses": [("Job Materials", t.materials(y_too=False)), ("Labor", t.labor())]})
        check = with_check(check_report)
        result = qf.figures(check_report, jc.confirmed(check_report, ready(check_report, check=check)),
                            cross_check=check)
        self.assertEqual((D("1200"), qp.NEEDS_A_CHECK), (result.jobs[PATIO]["profit_after_job_costs"].amount,
                                                         result.jobs[PATIO]["profit_after_job_costs"].status))
        self.assertEqual(qp.NEEDS_A_CHECK, result.customers[Y]["profit_after_job_costs"].status)
        self.assertEqual(qp.COMPLETE, result.jobs[KITCHEN]["profit_after_job_costs"].status)
        self.assertEqual(qp.COMPLETE, result.customers[X]["profit_after_job_costs"].status)
        self.assertEqual((D("4200"), qp.COMPLETE), (result.company["profit_after_job_costs"].amount,
                                                    result.company["profit_after_job_costs"].status))

    def test_case_a_with_yes_is_complete_the_documented_limit(self):
        report = t.full_export()  # Patio has materials and no labor: the owner's yes covers it
        check = with_check(report)
        result = qf.figures(report, jc.confirmed(report, ready(report, check=check)), cross_check=check)
        self.assertEqual({qp.COMPLETE}, t.statuses(result))
        self.assertEqual({"company": D("3400"), X: D("3000"), Y: D("400"), KITCHEN: D("3000"), PATIO: D("400")},
                         t.profits(result))
        self.assertIn("your confirmation that every job cost for these dates is in this report and on its job",
                      result.scope)

    def test_another_jobs_costs_never_count_for_a_job_with_none(self):
        # Patio has a sale and no costs; Customer Y's Deck job, and a bill for Y's outside job "Garage", have costs.
        report = t.pnl({"Income": [("Design income", [*t.income(), L(4, "Invoice", "1004", f"{Y}:Deck", D("500"),
                                                                     None)])],
                        "Expenses": [("Job Materials", [*t.materials(y_too=False),
                                                        L(6, "Bill", "B-6", f"{Y}:Deck", D("300"), None),
                                                        L(9, "Bill", "B-9", "Garage supplier (fictional)", D("450"),
                                                          None)]),
                                     ("Labor", t.labor())]})
        lines = {row_of(report, "B-9"): qf.LineAnswer(qf.JOB_COST, customer=Y, outside_job="Garage")}
        result = qf.figures(report, jc.confirmed(report, ready(report, lines=lines)))
        self.assertEqual(D("750"), result.customers[Y]["job_costs"].amount)
        self.assertTrue(j3(result.jobs[PATIO]["profit_after_job_costs"]))
        self.assertEqual([], j3(result.jobs[(Y, "Deck")]["profit_after_job_costs"]))
        self.assertTrue(j3(result.customers[Y]["profit_after_job_costs"]))  # through Patio

    def test_a_credit_only_job_holds(self):
        report = t.pnl({"Income": [("Design income", t.income())],
                        "Expenses": [("Job Materials", [*t.materials(y_too=False),
                                                        L(6, "Vendor Credit", "VC-1", f"{Y}:Patio", D("-100"), None)]),
                                     ("Labor", t.labor())]})
        lines = {row_of(report, "VC-1"): qf.LineAnswer(qf.JOB_COST)}
        result = qf.figures(report, jc.confirmed(report, ready(report, lines=lines)))
        self.assertEqual(D("-100"), result.jobs[PATIO]["job_costs"].amount)
        self.assertTrue(j3(result.jobs[PATIO]["job_costs"]))
        self.assertTrue(j3(result.customers[Y]["profit_after_job_costs"]))

    def test_with_jobs_off_each_customer_is_checked(self):
        report = t.pnl({"Income": [("Design income", t.income())],
                        "Expenses": [("Job Materials", t.materials(y_too=False)), ("Labor", t.labor())]})
        result = qf.figures(report, jc.confirmed(report, ready(report, jobs=False)))
        self.assertFalse(result.jobs_on)
        self.assertIn("Customer Y (fictional): no job costs are counted for this customer",
                      j3(result.customers[Y]["profit_after_job_costs"])[0])
        self.assertEqual(qp.COMPLETE, result.customers[X]["profit_after_job_costs"].status)

    def test_customer_only_sales_always_hold_their_customer(self):
        # Round-2 blocker 3: a $450 bill for the outside job "Garage" can't stand in for the costs of an unrelated
        # $1,000 sale that isn't on a job.
        report = t.pnl({"Income": [("Design income", [*t.income(), L(4, "Invoice", "1003", Z, D("1000"), None)])],
                        "Expenses": [("Job Materials", [*t.materials(),
                                                        L(9, "Bill", "B-9", "Garage supplier (fictional)", D("450"),
                                                          None)]),
                                     ("Labor", t.labor())]})
        lines = {row_of(report, "B-9"): qf.LineAnswer(qf.JOB_COST, customer=Z, outside_job="Garage")}
        result = qf.figures(report, jc.confirmed(report, ready(report, lines=lines)))
        self.assertEqual(D("450"), result.customers[Z]["job_costs"].amount)  # counted for Z, on no job in this report
        reasons = j3(result.customers[Z]["profit_after_job_costs"])
        self.assertEqual(["Some of Customer Z (fictional)'s sales aren't on a job in this report, so MargenX can't "
                          "tell which costs go with them, and this customer's profit may be misstated."], reasons)
        for key in (KITCHEN, PATIO):
            self.assertEqual([], j3(result.jobs[key]["profit_after_job_costs"]))  # judged on their own lines
        self.assertEqual([], j3(result.customers[X]["profit_after_job_costs"]))


def reclassified():
    """Patio's $450 supplier bill in a mixed account (round-2 blocker 1): on Patio, Patio's profit is -$50."""
    return t.pnl({"Income": [("Design income", t.income())],
                  "Expenses": [("Job Materials", t.materials()), ("Labor", t.labor()),
                               ("Supplies", [L(9, "Bill", "B-9", "Supplier (fictional)", D("450"), None)])]})


class BindingTests(unittest.TestCase):
    """Plan tests 5 and 9, and the round-3 review's first warning: the answer is bound to the exact file, the words
    of its choice, and the exact cost list shown."""

    def setUp(self):
        self.report = reclassified()
        self.row = row_of(self.report, "B-9")
        self.accounts = {**t.base(self.report).accounts,
                         ("Expenses", "Supplies"): qf.AccountAnswer(qf.MIXED_ACCOUNT)}

    def answers(self, line: qf.LineAnswer, **kw) -> qf.OwnerAnswers:
        return ready(self.report, accounts=self.accounts, lines={self.row: line}, **kw)

    def assert_reopened(self, before: qf.OwnerAnswers, after: qf.OwnerAnswers,
                        warning: str = "How MargenX counts your costs has changed"):
        """The answer given for before's list isn't used for after's: held, with a warning, and asked again."""
        given = jc.confirmed(self.report, before)
        moved = dataclasses.replace(after, job_costs=given.job_costs)
        result = qf.figures(self.report, moved)
        self.assertNotEqual(qf.figures(self.report, before).cost_digest, result.cost_digest)
        self.assertEqual(qf.JOB_COSTS_NOT_CONFIRMED, result.job_costs)
        self.assertTrue(any(warning in w for w in result.warnings), result.warnings)
        self.assertEqual(qq.JOB_COSTS, qq.open_questions(self.report, moved).questions[-1].kind)
        return result

    def test_moving_a_bill_to_overhead_reopens_the_question(self):
        on_patio = self.answers(qf.LineAnswer(qf.JOB_COST, customer=Y, job="Patio"))
        check = with_check(self.report)
        on_patio_s3 = dataclasses.replace(on_patio, unfiltered_pair=check.pair)
        confirmed = qf.figures(self.report, jc.confirmed(self.report, on_patio_s3), cross_check=check)
        self.assertEqual((D("-50"), qp.COMPLETE), (confirmed.jobs[PATIO]["profit_after_job_costs"].amount,
                                                   confirmed.jobs[PATIO]["profit_after_job_costs"].status))
        result = self.assert_reopened(on_patio, self.answers(qf.LineAnswer(qf.OVERHEAD)))
        self.assertEqual((D("400"), qp.NEEDS_A_CHECK), (result.jobs[PATIO]["profit_after_job_costs"].amount,
                                                        result.jobs[PATIO]["profit_after_job_costs"].status))

    def test_moving_a_bill_between_outside_jobs_reopens_the_question(self):
        # The round-3 review's warning: Garage and Shed both give job=None; the list shows where it went.
        self.assert_reopened(self.answers(qf.LineAnswer(qf.JOB_COST, customer=Y, outside_job="Garage")),
                             self.answers(qf.LineAnswer(qf.JOB_COST, customer=Y, outside_job="Shed")))
        listing = qf.figures(self.report, self.answers(qf.LineAnswer(qf.JOB_COST, customer=Y,
                                                                      outside_job="Shed"))).cost_list
        self.assertIn('Customer Y (fictional), the job "Shed", which isn\'t in this report: sales $0.00, job costs '
                      "$450.00", listing)

    def test_moving_a_bill_to_another_job_or_turning_jobs_off_reopens_the_question(self):
        self.assert_reopened(self.answers(qf.LineAnswer(qf.JOB_COST, customer=Y, job="Patio")),
                             self.answers(qf.LineAnswer(qf.JOB_COST, customer=X, job="Kitchen")))
        # Jobs off changes the words too ("customer" for "job"), which is caught first.
        self.assert_reopened(self.answers(qf.LineAnswer(qf.OVERHEAD)),
                             self.answers(qf.LineAnswer(qf.OVERHEAD), jobs=False), "for other words")

    def test_swapping_two_equal_bills_between_outside_jobs_reopens_the_question(self):
        # The list's totals are the same both ways ($450 for Garage, $450 for Shed), so only each line's own outside
        # job, kept in the digest, shows the change.
        report = t.pnl({"Income": [("Design income", t.income())],
                        "Expenses": [("Job Materials", t.materials()), ("Labor", t.labor()),
                                     ("Supplies", [L(9, "Bill", "B-9", "Supplier (fictional)", D("450"), None),
                                                   L(10, "Bill", "B-10", "Supplier (fictional)", D("450"), None)])]})
        first, second = row_of(report, "B-9"), row_of(report, "B-10")
        accounts = {**t.base(report).accounts, ("Expenses", "Supplies"): qf.AccountAnswer(qf.MIXED_ACCOUNT)}

        def where(a, b):
            return ready(report, accounts=accounts,
                         lines={first: qf.LineAnswer(qf.JOB_COST, customer=Y, outside_job=a),
                                second: qf.LineAnswer(qf.JOB_COST, customer=Y, outside_job=b)})

        before, after = where("Garage", "Shed"), where("Shed", "Garage")
        self.assertEqual(qf.figures(report, before).cost_list, qf.figures(report, after).cost_list)
        moved = dataclasses.replace(after, job_costs=jc.confirmed(report, before).job_costs)
        self.assertEqual(qf.JOB_COSTS_NOT_CONFIRMED, qf.figures(report, moved).job_costs)

    def test_a_question_shown_before_the_list_changed_confirms_nothing(self):
        before = self.answers(qf.LineAnswer(qf.JOB_COST, customer=Y, job="Patio"))
        stale = next(q for q in qq.open_questions(self.report, before).questions if q.kind == qq.JOB_COSTS)
        after = self.answers(qf.LineAnswer(qf.OVERHEAD))
        self.assertEqual(after, qq.answer(self.report, after, stale, ON))
        fresh = next(q for q in qq.open_questions(self.report, after).questions if q.kind == qq.JOB_COSTS)
        self.assertEqual(ON, qf.figures(self.report, qq.answer(self.report, after, fresh, ON)).job_costs)

    def test_another_workbook_that_reads_the_same_needs_its_own_answer(self):
        first, second = t.full_export(), t.full_export(saved_at="2026-11-17T09:00:00Z")
        answers = jc.confirmed(first, ready(first))
        self.assertEqual(ON, qf.figures(first, answers).job_costs)
        result = qf.figures(second, dataclasses.replace(answers, coverage=None))
        self.assertEqual(qf.JOB_COSTS_NOT_CONFIRMED, result.job_costs)
        self.assertTrue(any("another file" in w for w in result.warnings))
        # "Not sure" asked about the second workbook never withdraws the first one's answer.
        question = next(q for q in qq.open_questions(second, answers).questions if q.kind == qq.JOB_COSTS)
        self.assertEqual(answers.job_costs, qq.answer(second, answers, question, qq.NOT_SURE).job_costs)


class QuestionTests(unittest.TestCase):
    """J1 on the question list: asked last, with the list and the words; only that question records it."""

    def test_it_is_asked_last_with_the_list_and_the_words_of_each_choice(self):
        report = partial_labor()
        answers = ready(report, overhead_accounts=("Payroll Expenses",))
        questions = qq.open_questions(report, answers).questions
        self.assertEqual([qq.JOB_COSTS], [q.kind for q in questions])
        question = questions[0]
        self.assertEqual(JOB_COSTS_TITLE, question.title)
        self.assertEqual(["Yes, I checked", "All of them are in this report, but some are booked to overhead, not to "
                          "their jobs", "Not sure, or some may be missing (not entered yet, or not in QuickBooks)"],
                         [c.label for c in question.choices])
        for line in ("Customer X (fictional) › Kitchen: sales $4,500.00, job costs $1,500.00",
                     "Customer Y (fictional) › Patio: sales $1,200.00, job costs $880.00", "Overhead: $450.00",
                     "How MargenX counted your costs for January 1-October 26, 2026:"):
            self.assertIn(line, question.details)
        yes = qf.job_costs_statement(report, True, ON)
        self.assertIn("belongs in this accrual reporting period (January 1-October 26, 2026)", yes)
        self.assertIn("including jobs with no sale yet, and for work for a customer that isn't on a job", yes)
        self.assertIn("including jobs with no sale yet", qf.job_costs_statement(report, True, OVERHEAD_TOO))
        self.assertIn("But some of them are booked to overhead, not to their jobs.",
                      qf.job_costs_statement(report, True, OVERHEAD_TOO))
        self.assertIn("including customers with no sale yet", qf.job_costs_statement(report, False, ON))
        self.assertIn(f"\"Yes, I checked\" means: \"{yes}\"", question.details)

    def test_no_other_answer_or_report_records_it(self):
        report = t.full_export()
        check = with_check(report)
        answers = None
        picks = {qq.JOBS: "yes", qq.NO_FILTER: "yes", qq.COVERAGE: qf.COVERAGE_YES}
        while True:
            question = qq.open_questions(report, answers, check).questions[0]
            if question.kind == qq.JOB_COSTS:
                break
            answers = qq.answer(report, answers, question, picks.get(question.kind, qf.JOB_COSTS_ACCOUNT),
                                cross_check=check)
        self.assertIsNone(answers.job_costs)
        self.assertEqual(qf.JOB_COSTS_NOT_CONFIRMED, qf.figures(report, answers, check).job_costs)
        question = qq.open_questions(report, answers, check).questions[-1]
        done = qq.answer(report, answers, question, ON, cross_check=check)
        self.assertTrue(qq.open_questions(report, done, check).done)
        self.assertEqual({qp.COMPLETE}, t.statuses(qf.figures(report, done, cross_check=check)))
        # Yes, then "not sure": every status updates at once, amounts don't move, coverage and S3 stay.
        back = qq.answer(report, done, question, qq.NOT_SURE)
        self.assertIsNone(back.job_costs)
        result = qf.figures(report, back, cross_check=check)
        self.assertEqual(t.profits(qf.figures(report, done, cross_check=check)), t.profits(result))
        for _, group in t.every_figure(result):
            self.assertEqual(qp.NEEDS_A_CHECK, group["profit_after_job_costs"].status)
        self.assertEqual(qf.CONFIRMED, result.coverage)

    def test_only_the_job_cost_question_ever_records_a_job_cost_answer(self):
        # A guard on the product code: the only place that builds a JobCostsAnswer is quickbooks_questions.answer,
        # under the job-cost question. No upload, other answer or step can record one.
        root = Path(__file__).resolve().parents[1]
        builders = sorted(p.name for p in root.glob("*.py") if "JobCostsAnswer(" in p.read_text(encoding="utf-8"))
        self.assertEqual(["quickbooks_questions.py"], builders)
        source = (root / "quickbooks_questions.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("JobCostsAnswer("))
        answer = source[source.index("\ndef answer("):]
        answer = answer[:answer.index("\ndef ", 1)]
        self.assertIn("if question.kind == JOB_COSTS:", answer[:answer.index("qf.JobCostsAnswer(choice")])

    def test_coverage_and_s3_still_hold_on_their_own(self):
        report = t.full_export()
        check = with_check(report)
        answers = jc.confirmed(report, dataclasses.replace(t.base(report, check=check), unfiltered_pair=""))
        result = qf.figures(report, answers, cross_check=check)
        self.assertEqual(ON, result.job_costs)
        self.assertTrue(t.coverage_held(result))  # no coverage answer
        covered = qf.figures(report, jc.confirmed(report, t.say(report, t.base(report), qf.COVERAGE_YES)))
        self.assertEqual([qf.ONE_REPORT], [h.reason for h in covered.jobs[PATIO]["profit_after_job_costs"].holds])


class ScreenTests(unittest.TestCase):
    """Plan test 12 (screen): J1 is asked last; after a later answer changes the list, its old answer is shown apart,
    never counted, and the question comes back."""

    def test_a_changed_list_puts_the_old_answer_apart_and_asks_again(self):
        def page():
            import sys
            from pathlib import Path
            for folder in (Path.cwd(), Path.cwd() / "tests"):
                sys.path.insert(0, str(folder))
            import quickbooks_results as qresults
            import quickbooks_screens as qscreens
            import test_quickbooks_coverage as t
            report = t.full_export()
            qresults.results_screen(report, qscreens.question_screen(report, key="j1"))

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_function(page, default_timeout=30)
        at.run()
        save = t.ScreenTests.save
        save(at, "Yes, each sub-customer is a job")
        for _ in range(2):
            save(at, "Job costs: what's in it is spent on specific jobs")
        save(at, "Yes, I checked")  # coverage
        self.assertEqual(JOB_COSTS_TITLE, at.subheader[0].value)
        texts = [m.value.replace("\\$", "$") for m in at.markdown]
        self.assertIn("Customer Y (fictional) › Patio: sales $1,200.00, job costs $800.00", texts)
        save(at, "Yes, I checked")  # job costs
        self.assertIn(qf.JOB_COSTS_CONFIRMED, [s.value for s in at.success])
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (5)"), review.label)
        self.assertIn(f"{JOB_COSTS_TITLE} → Yes, I checked", [m.value for m in review.markdown])

        # The first account changed to "mixed": its entries are no longer counted as job costs, so the list changes.
        [b for b in review.button if b.label == "Change"][1].click().run()
        save(at, "Mixed: some entries are for jobs, some are overhead (I'll answer them one by one)")
        self.assertNotIn(qf.JOB_COSTS_CONFIRMED, [s.value for s in at.success])
        review = next(e for e in at.expander if e.label.startswith("Your answers"))
        self.assertTrue(review.label.startswith("Your answers (4)"), review.label)  # the old J1 answer isn't counted
        listed = [m.value for m in review.markdown]
        apart = listed[listed.index(next(m for m in listed if m.startswith("**Earlier answers that don't apply now**"))):]
        self.assertIn(f"{JOB_COSTS_TITLE} → Yes, I checked", apart)
        self.assertEqual(4, len([b for b in review.button if b.label == "Change"]))
        self.assertIn(JOB_COSTS_TITLE, listed[listed.index("**Still to answer**"):])


class AfterOverheadTests(unittest.TestCase):
    """J4: profit after overhead is built from its own parts, so it keeps exactly the holds it has today."""

    def test_its_other_holds_still_reach_it_and_its_amount_is_unchanged(self):
        report = t.pnl({"Income": [("Design income", t.income())],
                        "Expenses": [("Job Materials", t.materials()), ("Labor", t.labor()),
                                     ("Office", [L(9, "Expense", "E-1", "Office shop (fictional)", D("70"), None)])]})
        accounts = {**t.base(report).accounts, ("Expenses", "Office"): qf.AccountAnswer(qf.NOT_SURE_ACCOUNT)}
        result = qf.figures(report, jc.confirmed(report, ready(report, accounts=accounts), OVERHEAD_TOO))
        company = result.company
        held = [h for h in company["after_overhead"].holds]
        self.assertEqual(D("3400"), company["after_overhead"].amount)  # the open $70 isn't counted: it holds instead
        self.assertTrue(any(h.row == row_of(report, "E-1") for h in held))  # the open line still holds it
        self.assertEqual([], j2(company["after_overhead"]))
        expected = tuple(dict.fromkeys(h for name in ("sales", "job_costs", "overhead", "other")
                                       for h in company[name].holds if h.kind != qf.JOB_COSTS_HOLD))
        self.assertEqual(expected, company["after_overhead"].holds)


class ResultsTests(unittest.TestCase):
    """Plan test 12 (words): the headline, the cells and What's missing say why, once, with no amount invented."""

    def test_the_results_say_why_without_an_amount(self):
        report = t.pnl({"Income": [("Design income", t.income())],
                        "Expenses": [("Job Materials", t.materials(y_too=False)), ("Labor", t.labor())]})
        unanswered = qf.figures(report, ready(report))
        self.assertIn("you haven't confirmed yet that every job cost for these dates is in this report and on its job "
                      "(job costs may be misstated)", qr.headline(report, unanswered))
        self.assertEqual("$4,200.00 · Needs a check (job costs may be misstated)",
                         qr.cell(unanswered.company["profit_after_job_costs"]))
        reasons = qr.missing(unanswered)
        self.assertEqual(1, sum("haven't confirmed that every job cost" in r for r in reasons))
        some = qf.figures(report, jc.confirmed(report, ready(report), OVERHEAD_TOO))
        self.assertIn("you said some job costs are booked to overhead, not to their jobs", qr.headline(report, some))
        confirmed = qf.figures(report, jc.confirmed(report, ready(report)))
        self.assertIn("This figure is Complete for this report.", qr.headline(report, confirmed))
        self.assertEqual("$1,200.00 · Needs a check (job costs may be misstated)",
                         qr.cell(confirmed.jobs[PATIO]["profit_after_job_costs"]))
        self.assertIn("Customer Y (fictional) › Patio: no job costs are counted for this job in this report yet, or "
                      "they add up to $0 or less (credits included), so its profit may be misstated.",
                      qr.missing(confirmed))
        # D-011: each figure keeps its own amount (as with every hold), and the note beside it never gives a dollar
        # amount for what may be missing or misplaced: no held amount, never $0.
        for result in (unanswered, some, confirmed):
            for _, group in t.every_figure(result):
                for figure in group.values():
                    text = qr.cell(figure)
                    if qf.MAY_BE_MISSTATED in text:
                        self.assertTrue(text.startswith(qr.money(figure.amount) + " · Needs a check ("), text)
                        self.assertNotIn("$", text.split(" · Needs a check (", 1)[1], text)


if __name__ == "__main__":
    unittest.main()
