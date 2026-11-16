"""Issue #128, step 6a: the owner's questions about a QuickBooks report (plan v7, step 6).

Made-up reports in the layouts seen (tests/quickbooks_fixtures.py), read end to end. The questions come
in a fixed order with their progress; each shows the line's row, date, Name and amount; only the choices
the rules allow are offered, none pre-selected, and "not sure" always leaves the question open.
"""
from decimal import Decimal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quickbooks_crosscheck as qc  # noqa: E402
import quickbooks_figures as qf  # noqa: E402
import quickbooks_fixtures as fx  # noqa: E402
import quickbooks_pnl as qp  # noqa: E402
import quickbooks_questions as qq  # noqa: E402
import quickbooks_sbcd as qs  # noqa: E402

D = Decimal
L, S = fx.line, fx.sale
X, Y = "Customer X (fictional)", "Customer Y (fictional)"


def read(sections):
    return qp.read_profit_and_loss_detail("pnl.xlsx", fx.xlsx(fx.report_rows(sections)))


def shop():
    """Job A for Customer X ($4,000 invoice, -$200 credit memo, $1,000 materials), a $700 invoice for Customer X with no
    job, a $50 Deposit, a $900 bill with only a vendor's name, and a $500 office expense."""
    return read({
        "Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                      L(3, "Invoice", "1002", X, D("700"), None),
                                      L(4, "Credit Memo", "1003", f"{X}:Job A", D("-200"), None),
                                      L(5, "Deposit", "", f"{X}:Job A", D("50"), None, "", "Checking")])],
        "Expenses": [("Job Materials", [L(5, "Bill", "B-1", f"{X}:Job A", D("1000"), None),
                                        L(6, "Bill", "B-2", "Garden Supply (fictional)", D("900"), None)]),
                     ("Office Supplies", [L(7, "Expense", "", "Office Depot (fictional)", D("500"), None)])]})


def first(questions, kind, contains=""):
    return next(q for q in questions.questions if q.kind == kind and contains in q.title)


class OrderAndShapeTests(unittest.TestCase):
    def test_questions_come_in_order_with_their_progress(self):
        questions = qq.open_questions(shop())
        kinds = [q.kind for q in questions.questions]
        self.assertEqual([qq.JOBS, qq.ACCOUNT, qq.ACCOUNT, qq.LINE], kinds)
        self.assertEqual(["Question 1 of 4", "Question 2 of 4", "Question 3 of 4", "Question 4 of 4"],
                         [q.progress for q in questions.questions])
        self.assertEqual("Do you use sub-customers in QuickBooks for jobs?", questions.questions[0].title)
        self.assertFalse(questions.done)

    def test_every_question_offers_not_sure_and_only_allowed_choices(self):
        for question in qq.open_questions(shop()).questions:
            with self.subTest(question.key):
                self.assertEqual(qq.NOT_SURE, question.choices[-1].value)
                self.assertEqual(len({c.value for c in question.choices}), len(question.choices))
        memo = first(qq.open_questions(shop()), qq.LINE, "-$200.00")
        # A negative line in Income can only be a reduction (never revenue); it isn't outside the period.
        self.assertEqual([qf.REDUCTION, qq.NOT_SURE], [c.value for c in memo.choices])
        self.assertIn("10/04/2026 · Credit Memo 1003", memo.details[0])
        self.assertIn("-$200.00", memo.details[1])
        self.assertIn("Row ", memo.small_print)

    def test_money_received_is_shown_as_held_never_asked(self):
        questions = qq.open_questions(shop())
        self.assertEqual(1, len(questions.held_lines))
        self.assertIn("money received or moved, so MargenX never counts it", questions.held_lines[0].reason)
        self.assertNotIn("$50.00", " ".join(q.title for q in questions.questions))

    def test_the_account_question_lists_every_entry(self):
        account = first(qq.open_questions(shop()), qq.ACCOUNT, "Job Materials")
        self.assertEqual(("Expenses", "Job Materials"), account.account)
        self.assertIn("2 entries, $1,900.00 in all:", account.details[0])
        self.assertEqual(3, len(account.details))
        self.assertTrue(account.details[1].startswith("Row "), account.details[1])
        self.assertIn("Bill B-1", account.details[1])

    def test_an_account_total_with_an_unreadable_amount_is_never_shown_as_complete(self):
        # The automated review of b3921fe. On a real file an unreadable amount keeps its whole section from being
        # checked, so this account is never asked about; the wording is guarded all the same.
        import dataclasses
        report = shop()
        bill = next(l for l in report.lines if l.num == "B-2")
        broken = dataclasses.replace(report, lines=tuple(dataclasses.replace(l, amount=None, outcome=qp.NOT_RESOLVED) if l is bill else l
                                                         for l in report.lines))
        account = first(qq.open_questions(broken), qq.ACCOUNT, "Job Materials")
        self.assertIn("$1,000.00 that MargenX can read, and 1 with an amount it can't read", account.details[0])
        self.assertNotIn("in all", account.details[0])
        self.assertEqual([qf.JOB_COSTS_ACCOUNT, qf.OVERHEAD_ACCOUNT, qf.MIXED_ACCOUNT, qq.NOT_SURE],
                         [c.value for c in account.choices])


class AnsweringTests(unittest.TestCase):
    def test_not_sure_and_skipping_leave_an_unanswered_question_open(self):
        report = shop()
        questions = qq.open_questions(report)
        same = qq.answer(report, None, questions.questions[0], qq.NOT_SURE)
        self.assertEqual([q.key for q in questions.questions], [q.key for q in qq.open_questions(report, same).questions])
        offered = qq.answer(report, None, questions.questions[0], "something not offered")
        self.assertEqual(4, len(qq.open_questions(report, offered).questions))

    def test_answering_never_changes_the_old_answers(self):
        report = shop()
        before = qf.OwnerAnswers(report=qf.report_fingerprint(report))
        after = qq.answer(report, before, qq.open_questions(report).questions[0], "yes")
        self.assertIsNone(before.sub_customers_are_jobs)
        self.assertTrue(after.sub_customers_are_jobs)

    def test_changing_an_answer_changes_whats_left(self):
        report = shop()
        jobs_question = qq.open_questions(report).questions[0]
        yes = qq.answer(report, None, jobs_question, "yes")
        left = qq.open_questions(report, yes)
        self.assertTrue(any("Which job is this $700.00 for?" == q.title for q in left.questions))
        no = qq.answer(report, yes, jobs_question, "no")  # going back and changing it
        self.assertFalse(any(q.title.startswith("Which job") for q in qq.open_questions(report, no).questions))

    def test_a_question_about_another_report_changes_nothing(self):
        # The automated review of 8370349: account and line questions from report A, answered against report B.
        report, other = shop(), read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("10"), None)])],
                                      "Expenses": [("Office Supplies", [L(7, "Expense", "", "Office Depot (fictional)",
                                                                          D("600"), None)])]})
        for question in (first(qq.open_questions(report), qq.ACCOUNT, "Office Supplies"),
                         first(qq.open_questions(report), qq.LINE, "-$200.00")):
            with self.subTest(question.key):
                choice = question.choices[0].value
                start = qf.OwnerAnswers(report=qf.report_fingerprint(other))
                self.assertEqual(start, qq.answer(other, start, question, choice))

    def test_not_sure_reopens_an_answered_question(self):
        # The automated review of 8370349: going back and choosing "Not sure yet" clears the earlier answer.
        report = shop()
        jobs = qq.open_questions(report).questions[0]
        answers = qq.answer(report, None, jobs, "yes")
        office = first(qq.open_questions(report, answers), qq.ACCOUNT, "Office Supplies")
        memo = first(qq.open_questions(report, answers), qq.LINE, "-$200.00")
        sale = first(qq.open_questions(report, answers), qq.LINE, "$700.00")
        answers = qq.answer(report, answers, office, qf.OVERHEAD_ACCOUNT)
        answers = qq.answer(report, answers, memo, qf.REDUCTION)
        answers = qq.answer(report, answers, sale, "no job")
        keys = {q.key for q in qq.open_questions(report, answers).questions}
        self.assertFalse({office.key, memo.key, sale.key} & keys)
        for question in (office, memo, sale, jobs):
            answers = qq.answer(report, answers, question, qq.NOT_SURE)
        keys = {q.key for q in qq.open_questions(report, answers).questions}
        self.assertTrue({office.key, memo.key, jobs.key} <= keys)  # the job question needs "yes" to jobs again
        self.assertEqual((None, {}, {}), (answers.sub_customers_are_jobs, dict(answers.accounts), dict(answers.lines)))
        figures = qf.figures(report, answers)
        self.assertEqual(qp.NEEDS_A_CHECK, figures.company["overhead"].status)

    def test_not_sure_on_the_job_keeps_what_the_line_is(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                                     L(3, "Journal Entry", "JE-1", X, D("-40"), None)])]})
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        entry = first(qq.open_questions(report, answers), qq.LINE, "-$40.00")
        answers = qq.answer(report, answers, entry, qf.REDUCTION)
        job = first(qq.open_questions(report, answers), qq.LINE, "Which job")
        answers = qq.answer(report, answers, job, "no job")
        answers = qq.answer(report, answers, job, qq.NOT_SURE)
        row = entry.row
        self.assertEqual((qf.REDUCTION, False), (answers.lines[row].kind, answers.lines[row].no_job))
        self.assertIn(job.key, {q.key for q in qq.open_questions(report, answers).questions})

    def test_no_filter_can_be_reopened(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])]})
        sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
            [(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)])])])))
        check = qc.cross_check(report, sales)
        answers = qq.answer(report, None, qq.open_questions(report, None, check).questions[0], "yes", cross_check=check)
        no_filter = first(qq.open_questions(report, answers, check), qq.NO_FILTER)
        answers = qq.answer(report, answers, no_filter, "yes", cross_check=check)
        answers = qq.answer(report, answers, no_filter, qq.NOT_SURE, cross_check=check)
        self.assertEqual("", answers.unfiltered_pair)
        self.assertIn(no_filter.key, {q.key for q in qq.open_questions(report, answers, check).questions})

    def test_no_filter_confirms_only_the_pair_it_was_asked_about(self):
        # The automated review of 872a31a: the second report is replaced before the question is answered.
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])]})

        def check(product):
            sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
                [(X, [], [("Job A", [S(2, "Invoice", "1001", product, 1, 4000)])])])))
            return qc.cross_check(report, sales)

        first_check, second_check = check("Design"), check("Design work")
        self.assertTrue(first_check.usable and second_check.usable)
        self.assertNotEqual(first_check.pair, second_check.pair)
        answers = qq.answer(report, None, qq.open_questions(report, None, first_check).questions[0], "yes",
                            cross_check=first_check)
        asked = first(qq.open_questions(report, answers, first_check), qq.NO_FILTER)
        self.assertEqual(answers, qq.answer(report, answers, asked, "yes", cross_check=second_check))
        self.assertEqual(first_check.pair,
                         qq.answer(report, answers, asked, "yes", cross_check=first_check).unfiltered_pair)

    def test_no_filter_is_only_asked_and_answered_for_a_cross_check_of_this_report(self):
        # PR #142 manual review, blocker 2: report A is current, but the cross-check passed in was made for report B.
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])]})
        other = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                                    L(3, "Invoice", "1002", f"{X}:Job A", D("1"), None)])]})
        sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
            [(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)])])])))
        own, stale = qc.cross_check(report, sales), qc.cross_check(other, sales)
        self.assertTrue(own.usable)
        if not stale.usable:  # make sure the guard, not "usable", is what's tested
            import dataclasses
            stale = dataclasses.replace(stale, usable=True, reasons=())
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        self.assertNotIn(qq.NO_FILTER, {q.kind for q in qq.open_questions(report, answers, stale).questions})
        asked = first(qq.open_questions(report, answers, own), qq.NO_FILTER)
        import dataclasses
        forged = dataclasses.replace(asked, pair=stale.pair)
        self.assertEqual(answers, qq.answer(report, answers, forged, "yes", cross_check=stale))

    def test_not_sure_on_an_old_no_filter_question_keeps_a_newer_pairs_confirmation(self):
        # PR #142 manual review, warning 1 (and the automated review of c909b95).
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])]})

        def check(product):
            sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
                [(X, [], [("Job A", [S(2, "Invoice", "1001", product, 1, 4000)])])])))
            return qc.cross_check(report, sales)

        a, b = check("Design"), check("Design work")
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        old = first(qq.open_questions(report, answers, a), qq.NO_FILTER)
        new = first(qq.open_questions(report, answers, b), qq.NO_FILTER)
        confirmed = qq.answer(report, answers, new, "yes", cross_check=b)
        self.assertEqual(b.pair, confirmed.unfiltered_pair)
        self.assertEqual(confirmed, qq.answer(report, confirmed, old, qq.NOT_SURE, cross_check=b))
        self.assertEqual("", qq.answer(report, confirmed, new, qq.NOT_SURE, cross_check=b).unfiltered_pair)

    def test_answers_for_another_report_are_never_carried_over(self):
        report, other = shop(), read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("10"), None)])]})
        theirs = qq.answer(other, None, qq.open_questions(other).questions[0], "yes")
        mine = qq.answer(report, theirs, first(qq.open_questions(report), qq.ACCOUNT, "Office"), qf.OVERHEAD_ACCOUNT)
        self.assertIsNone(mine.sub_customers_are_jobs)
        self.assertEqual(qf.report_fingerprint(report), mine.report)

    def test_overhead_records_the_exact_entries_and_asks_again_if_they_change(self):
        report = shop()
        office = first(qq.open_questions(report), qq.ACCOUNT, "Office Supplies")
        answers = qq.answer(report, None, office, qf.OVERHEAD_ACCOUNT)
        self.assertEqual(qf.entry_keys(report, ("Expenses", "Office Supplies")),
                         answers.accounts[("Expenses", "Office Supplies")].entries)
        self.assertFalse(any(q.key == office.key for q in qq.open_questions(report, answers).questions))
        stale = qf.OwnerAnswers(report=answers.report, accounts={("Expenses", "Office Supplies"): qf.AccountAnswer(
            qf.OVERHEAD_ACCOUNT, (("1", "x", "", "", "500"),))})
        self.assertTrue(any(q.key == office.key for q in qq.open_questions(report, stale).questions))

    def test_a_vendor_cost_can_go_to_any_job_or_overhead(self):
        report = shop()
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        answers = qq.answer(report, answers, first(qq.open_questions(report, answers), qq.ACCOUNT, "Job Materials"),
                            qf.JOB_COSTS_ACCOUNT)
        vendor = first(qq.open_questions(report, answers), qq.LINE, "$900.00")
        self.assertEqual(f"job:{X}{qq.SEPARATOR}Job A", vendor.choices[0].value)
        self.assertIn(qf.OVERHEAD, [c.value for c in vendor.choices])
        self.assertNotIn("outside job", [c.value for c in vendor.choices])  # no customer to name a job for
        assigned = qq.answer(report, answers, vendor, vendor.choices[0].value)
        figures = qf.figures(report, assigned)
        self.assertEqual(D("1900"), figures.jobs[(X, "Job A")]["job_costs"].amount)
        self.assertFalse(any(q.key == vendor.key for q in qq.open_questions(report, assigned).questions))

    def test_overhead_then_a_job_makes_it_a_job_cost_again(self):
        # The automated review of 872a31a: overhead first, then back to the same question and a job.
        report = shop()
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        answers = qq.answer(report, answers, first(qq.open_questions(report, answers), qq.ACCOUNT, "Job Materials"),
                            qf.JOB_COSTS_ACCOUNT)
        vendor = first(qq.open_questions(report, answers), qq.LINE, "$900.00")
        self.assertEqual(qf.JOB_COST, vendor.line_kind)
        overhead = qq.answer(report, answers, vendor, qf.OVERHEAD)
        self.assertEqual(qf.OVERHEAD, overhead.lines[vendor.row].kind)
        assigned = qq.answer(report, overhead, vendor, vendor.choices[0].value)
        self.assertEqual((qf.JOB_COST, "Job A"), (assigned.lines[vendor.row].kind, assigned.lines[vendor.row].job))
        figures = qf.figures(report, assigned)
        self.assertEqual((), figures.warnings)
        self.assertEqual(D("1900"), figures.jobs[(X, "Job A")]["job_costs"].amount)
        self.assertEqual(qf.figures(report, qq.answer(report, answers, vendor, vendor.choices[0].value)), figures)
        # And "Not sure yet" after overhead reopens it fully: nothing is left as overhead.
        reopened = qq.answer(report, overhead, vendor, qq.NOT_SURE)
        self.assertNotIn(vendor.row, reopened.lines)
        self.assertIn(vendor.key, {q.key for q in qq.open_questions(report, reopened).questions})

    def test_a_job_question_from_before_the_line_was_reopened_changes_nothing(self):
        # The owner said "revenue", was asked which job, then went back to "Not sure yet" on what the line is:
        # the old job question can't bring "revenue" back.
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                                     L(3, "Journal Entry", "JE-1", X, D("40"), None)])]})
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        entry = first(qq.open_questions(report, answers), qq.LINE, "$40.00")
        revenue = qq.answer(report, answers, entry, qf.REVENUE)
        job = first(qq.open_questions(report, revenue), qq.LINE, "Which job")
        reopened = qq.answer(report, revenue, entry, qq.NOT_SURE)
        self.assertNotIn(entry.row, reopened.lines)
        self.assertEqual(reopened, qq.answer(report, reopened, job, job.choices[0].value))

    def test_overhead_on_an_old_job_question_after_reopening_changes_nothing(self):
        # The automated review of bbee1be: a held entry called a job cost, its job question, the classification
        # reopened with "Not sure yet", then "overhead" on the old job question.
        report, entry, cost, job = self.held_cost_entry()
        reopened = qq.answer(report, cost, entry, qq.NOT_SURE)
        self.assertEqual(reopened, qq.answer(report, reopened, job, qf.OVERHEAD))

    def test_not_sure_after_overhead_on_the_job_question_keeps_the_owners_job_cost(self):
        # The automated review of bbee1be: only the job question's own answer is reopened.
        report, entry, cost, job = self.held_cost_entry()
        overhead = qq.answer(report, cost, job, qf.OVERHEAD)
        self.assertEqual(qf.OVERHEAD, overhead.lines[entry.row].kind)
        reopened = qq.answer(report, overhead, job, qq.NOT_SURE)
        self.assertEqual(cost, reopened)
        self.assertIn(job.key, {q.key for q in qq.open_questions(report, reopened).questions})

    def held_cost_entry(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])],
                       "Expenses": [("Job Materials", [L(5, "Journal Entry", "JE-1", "Vendor (fictional)", D("10"),
                                                         None)])]})
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        entry = first(qq.open_questions(report, answers), qq.LINE, "$10.00")
        cost = qq.answer(report, answers, entry, qf.JOB_COST)
        job = first(qq.open_questions(report, cost), qq.LINE, "Which job")
        self.assertIn(qf.OVERHEAD, [c.value for c in job.choices])
        return report, entry, cost, job

    def test_an_old_job_question_never_undoes_a_later_overhead(self):
        # PR #142 manual review, blocker 1: a job cost, its job question, then "overhead" on "What is this line?".
        # The old job question, answered with a job or with "Not sure yet", changes nothing.
        report, entry, cost, job = self.held_cost_entry()
        overhead = qq.answer(report, cost, entry, qf.OVERHEAD, answered_at="t2")
        self.assertNotIn("outside job", [c.value for c in job.choices])  # a vendor's line: no customer to name a job for
        for choice in (job.choices[0].value, qf.OVERHEAD, qq.NOT_SURE):
            with self.subTest(choice):
                self.assertEqual(overhead, qq.answer(report, overhead, job, choice))
        self.assertEqual((qf.OVERHEAD, "t2"), (overhead.lines[entry.row].kind, overhead.lines[entry.row].answered_at))
        self.assertNotIn(job.key, {q.key for q in qq.open_questions(report, overhead).questions})

    def test_a_job_answer_can_always_be_taken_back(self):
        # PR #142 manual review, round 2: Job Materials is "job costs", the $900 vendor bill is given Job A (or
        # overhead), then the account is changed to "mixed". "Not sure yet" on the job question still takes it back.
        report = shop()
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        materials = first(qq.open_questions(report, answers), qq.ACCOUNT, "Job Materials")
        answers = qq.answer(report, answers, materials, qf.JOB_COSTS_ACCOUNT)
        vendor = first(qq.open_questions(report, answers), qq.LINE, "$900.00")
        for choice in (vendor.choices[0].value, qf.OVERHEAD):
            with self.subTest(choice):
                given = qq.answer(report, answers, vendor, choice)
                mixed = qq.answer(report, given, materials, qf.MIXED_ACCOUNT)
                self.assertIn(vendor.row, mixed.lines)
                withdrawn = qq.answer(report, mixed, vendor, qq.NOT_SURE)
                self.assertNotIn(vendor.row, withdrawn.lines)
                figures = qf.figures(report, withdrawn)
                self.assertEqual(qp.NEEDS_A_CHECK, figures.jobs[(X, "Job A")]["job_costs"].status)
                # A new choice on the old question is still refused: the line is now an unsorted mixed entry.
                self.assertEqual(withdrawn, qq.answer(report, withdrawn, vendor, vendor.choices[0].value))

    def test_reopening_a_job_answer_puts_back_the_owners_own_answer_exactly(self):
        # PR #142 manual review, blocker 1: the classification comes back with its own time, never the job answer's.
        report, entry, _, _ = self.held_cost_entry()
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        cost = qq.answer(report, answers, entry, qf.JOB_COST, answered_at="t1")
        job = first(qq.open_questions(report, cost), qq.LINE, "Which job")
        for choice in (job.choices[0].value, qf.OVERHEAD):
            with self.subTest(choice):
                given = qq.answer(report, cost, job, choice, answered_at="t2")
                self.assertEqual("t2", given.lines[entry.row].answered_at)
                self.assertEqual(cost, qq.answer(report, given, job, qq.NOT_SURE))

    def test_no_job_question_for_a_customer_without_jobs(self):
        # Simpler questions (plan step 6): Customer Y has no jobs in the report, so its customer-only sale holds no job
        # back (S8) and isn't asked about; Customer X's is.
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                                     L(3, "Invoice", "1002", X, D("700"), None),
                                                     L(4, "Invoice", "1003", Y, D("300"), None)])]})
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        titles = [q.title for q in qq.open_questions(report, answers).questions]
        self.assertEqual(["Which job is this $700.00 for?"], titles)
        self.assertEqual(qp.COMPLETE, qf.figures(report, answers).customers[Y]["sales"].status)

    def test_an_outside_job_must_be_named(self):
        report = shop()
        answers = qq.answer(report, None, qq.open_questions(report).questions[0], "yes")
        sale = first(qq.open_questions(report, answers), qq.LINE, "$700.00")
        unchanged = qq.answer(report, answers, sale, "outside job", outside_job="  ")
        self.assertEqual(answers, unchanged)
        named = qq.answer(report, answers, sale, "outside job", outside_job="Old patio, 2025 (fictional)")
        self.assertFalse(any(q.key == sale.key for q in qq.open_questions(report, named).questions))

    def test_a_mixed_account_asks_entry_by_entry(self):
        report = shop()
        answers = qq.answer(report, None, first(qq.open_questions(report), qq.ACCOUNT, "Office"), qf.MIXED_ACCOUNT)
        entry = first(qq.open_questions(report, answers), qq.LINE, "Is this $500.00 entry a job cost or overhead?")
        self.assertEqual([qf.JOB_COST, qf.OVERHEAD, qq.NOT_SURE], [c.value for c in entry.choices])

    def test_a_deposit_outside_the_period_can_only_be_left_out(self):
        late = L(5, "Deposit", "", f"{X}:Job A", D("50"), None, "", "Checking")
        late[1] = "11/02/2026"
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None), late])]})
        question = first(qq.open_questions(report), qq.LINE, "$50.00")
        self.assertEqual([qf.OUTSIDE_PERIOD, qq.NOT_SURE], [c.value for c in question.choices])
        self.assertEqual((), qq.open_questions(report).held_lines)


class ConsistencyTests(unittest.TestCase):
    def test_every_choice_offered_is_one_the_rules_accept(self):
        # Whatever the owner picks among the choices shown, MargenX takes it (no "can't be used" warning): a
        # question never offers an answer the figures would refuse.
        late = L(5, "Deposit", "", f"{X}:Job A", D("50"), None, "", "Checking")
        late[1] = "11/02/2026"
        late_sale = L(6, "Invoice", "1009", f"{X}:Job A", D("80"), None)
        late_sale[1] = "11/03/2026"
        reports = [shop(), read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None),
                                                               late, late_sale,
                                                               L(7, "Journal Entry", "JE-1", Y, D("-30"), None)])],
                                 "Other Income": [("Interest Earned", [L(8, "Journal Entry", "JE-2", "Bank (fictional)",
                                                                         D("4"), None)])]})]
        for report in reports:
            for jobs in ("yes", "no"):
                base = qq.answer(report, None, qq.open_questions(report).questions[0], jobs)
                for question in qq.open_questions(report, base).questions:
                    for choice in question.choices:
                        if choice.value == qq.NOT_SURE:
                            continue
                        with self.subTest(report=report.layout.company, jobs=jobs, q=question.title, c=choice.value):
                            answered = qq.answer(report, base, question, choice.value, outside_job="Old job (fictional)")
                            self.assertEqual((), qf.figures(report, answered).warnings)
                            self.assertFalse(any(q.key == question.key for q in qq.open_questions(report, answered).questions)
                                             and question.kind != qq.ACCOUNT)

    def test_a_line_whose_date_cant_be_read_is_shown_held(self):
        odd = L(5, "Credit Memo", "1010", f"{X}:Job A", D("-20"), None)
        odd[1] = "2026-10-05"
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None), odd])]})
        questions = qq.open_questions(report)
        self.assertIn("can't be read, so no answer can count it", " ".join(h.reason for h in questions.held_lines))
        self.assertFalse(any("-$20.00" in q.title for q in questions.questions))


class CrossCheckAndProblemTests(unittest.TestCase):
    def test_the_no_filter_question_appears_only_with_a_usable_cross_check(self):
        report = read({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])]})
        sales = qs.read_sales_by_customer_detail("s.xlsx", fx.xlsx(fx.sbcd_rows(
            [(X, [], [("Job A", [S(2, "Invoice", "1001", "Design", 1, 4000)])])])))
        check = qc.cross_check(report, sales)
        self.assertNotIn(qq.NO_FILTER, [q.kind for q in qq.open_questions(report).questions])
        answers = qq.answer(report, None, qq.open_questions(report, None, check).questions[0], "yes", cross_check=check)
        question = first(qq.open_questions(report, answers, check), qq.NO_FILTER)
        answers = qq.answer(report, answers, question, "yes", cross_check=check)
        self.assertTrue(qq.open_questions(report, answers, check).done)
        self.assertEqual(qf.figures(report, answers, cross_check=check).jobs[(X, "Job A")]["profit_after_job_costs"].status,
                         qp.COMPLETE)

    def test_the_reports_own_problems_are_listed(self):
        rows = fx.report_rows({"Income": [("Design income", [L(2, "Invoice", "1001", f"{X}:Job A", D("4000"), None)])]})
        rows = [r if r[:1] != ["Total for Design income"] else fx.total("Total for Design income", D("4100")) for r in rows]
        report = qp.read_profit_and_loss_detail("t.xlsx", fx.xlsx(rows))
        problems = qq.open_questions(report).report_problems
        self.assertTrue(problems)
        self.assertIn("it says 4,100.00, but its lines add up to 4,000.00", " ".join(problems))


class WalkThroughTests(unittest.TestCase):
    def test_answering_every_question_leaves_only_what_can_never_be_counted(self):
        report = shop()
        answers = None
        script = {qq.JOBS: "yes", "Job Materials": qf.JOB_COSTS_ACCOUNT, "Office Supplies": qf.OVERHEAD_ACCOUNT,
                  "-$200.00": qf.REDUCTION, "$700.00": "no job", "$900.00": f"job:{X}{qq.SEPARATOR}Job A"}
        for _ in range(20):
            questions = qq.open_questions(report, answers)
            if questions.done:
                break
            question = questions.questions[0]
            choice = next(v for k, v in script.items() if k == question.kind or k in question.title)
            answers = qq.answer(report, answers, question, choice)
        self.assertTrue(qq.open_questions(report, answers).done)
        figures = qf.figures(report, answers)
        self.assertEqual((), figures.warnings)
        job = figures.jobs[(X, "Job A")]
        # $4,000 - $200 sales; $1,000 + $900 costs. The $50 Deposit is still held (never counted).
        self.assertEqual((D("3800"), D("1900")), (job["sales"].amount, job["job_costs"].amount))
        deposit = next(l.row for l in report.lines if l.transaction_type == "Deposit")
        self.assertEqual({deposit}, {h.row for h in job["sales"].holds if h.row is not None})
        self.assertEqual(D("500"), figures.company["overhead"].amount)


if __name__ == "__main__":
    unittest.main()
