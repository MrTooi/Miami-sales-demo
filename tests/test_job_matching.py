"""Costs with no job number, matched to jobs only by the owner: never guessed, never more than asked."""
import unittest
from decimal import Decimal

import job_intake as ji
import job_matching as jm
import job_profit as jp

INVOICES = (b"Invoice,Date,Customer,Job,Description,Amount\n"
            b"I-1,10/31/2026,Gomez (fictional),J-1,Kitchen,1000.00\n"
            b"I-2,10/03/2026,Rivera (fictional),J-2,Bathroom,800.00\n")
COSTS = (b"Date,Vendor,Job,Type,Memo,Amount\n"
         b"10/30/2026,Crew (fictional),J-1,Labor,,300.00\n"
         b"10/01/2026,Crew (fictional),J-2,Labor,,200.00\n"
         b"10/01/2026,Paper Co (fictional),J-2,Materials,,100.00\n"
         b"10/29/2026,Tile Co (fictional),,Materials,Tile,400.00\n"   # row 5: no job number
         b"10/02/2026,Landlord (fictional),,Rent,,900.00\n"           # row 6: overhead, never asked
         b"10/15/2026,Shop Supply (fictional),,Supplies,,50.00\n")    # row 7: no job number


def read(data: bytes, kind: str) -> ji.IntakeResult:
    headers, rows = ji.read_csv(data)
    return ji.intake(headers, rows, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY")


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.invoices, self.costs = read(INVOICES, "invoices"), read(COSTS, "costs")
        self.jobs = jm.jobs(self.invoices, self.costs)

    def job(self, report, job_id):
        return next(j for j in report.jobs if j.job_id == job_id)

    def test_only_costs_that_may_belong_to_a_job_are_asked_about(self):
        self.assertEqual([5, 7], [line["row"] for line in jm.unmatched(self.costs)])  # rent isn't asked

    def test_jobs_around_the_cost_date_come_first_and_far_ones_are_not_marked(self):
        tile, supplies = jm.unmatched(self.costs)
        self.assertEqual(["J-1"], jm.nearby(tile, self.jobs))  # J-1 has dates Oct 30-31; J-2 ends Oct 3
        self.assertEqual([], jm.nearby(supplies, self.jobs))  # Oct 15: 12 days from J-2, 15 from J-1
        self.assertEqual(["J-2"], jm.nearby({**supplies, "date": "2026-10-10"}, self.jobs))  # 7 days, the edge
        self.assertEqual([], jm.nearby({**supplies, "date": "2026-10-11"}, self.jobs))  # 8 days: not marked

    def test_unanswered_costs_change_nothing(self):
        before = jp.job_profit(self.invoices, self.costs)
        after = jp.job_profit(self.invoices, jm.apply(self.costs, {}, self.jobs))
        self.assertEqual([(j.job_id, j.contribution, j.status) for j in before.jobs],
                         [(j.job_id, j.contribution, j.status) for j in after.jobs])
        self.assertTrue(all(j.status == "provisional" for j in after.jobs))  # $450 may belong to either job

    def test_answers_put_each_cost_on_exactly_the_chosen_job(self):
        answered = jm.apply(self.costs, {5: jm.job("J-1"), 7: jm.NOT_A_JOB}, self.jobs)
        report = jp.job_profit(self.invoices, answered)
        self.assertEqual((Decimal("300.00"), "complete"), (self.job(report, "J-1").contribution,
                                                           self.job(report, "J-1").status))  # 1000 - 300 - 400
        self.assertEqual((Decimal("500.00"), "complete"), (self.job(report, "J-2").contribution,
                                                           self.job(report, "J-2").status))
        # Nothing is lost: the supplies and rent are still costs, outside the jobs.
        self.assertEqual((Decimal("950.00"), Decimal("0")), (report.unlinked_costs, report.unlinked_job_costs))
        self.assertIn("1 cost line(s) worth $400.00 had no job number in the file; you said which job each was for.",
                      report.notes)
        self.assertIn("1 cost line(s) worth $50.00 had no job number in the file; you said they aren't for any job, "
                      "so they're counted with overhead.", report.notes)

    def test_the_original_file_result_is_never_changed(self):
        jm.apply(self.costs, {5: jm.job("J-1"), 7: jm.NOT_A_JOB}, self.jobs)
        self.assertEqual("", self.costs.accepted[3].get("job_id", ""))
        self.assertNotIn("not_for_a_job", self.costs.accepted[5])

    def test_a_job_that_is_not_in_the_files_is_refused(self):
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {5: jm.job("J-9")}, self.jobs)

    def test_a_cost_that_already_has_a_job_or_is_overhead_cannot_be_moved(self):
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {2: jm.job("J-2")}, self.jobs)  # row 2 is already J-1's labor
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {6: jm.job("J-1")}, self.jobs)  # row 6 is rent

    def test_a_plain_job_number_is_never_taken_as_an_answer(self):
        # Answers are tagged pairs: a bare string, even a real job number, is refused.
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {5: "J-1"}, self.jobs)

    def test_a_job_named_like_a_choice_still_gets_its_costs(self):
        # A job numbered "not_a_job" (or "not_sure") is a job like any other: picking it puts the
        # cost on that job, never in overhead.
        invoices = read(b"Invoice,Date,Customer,Job,Amount\nI-1,10/31/2026,Gomez (fictional),not_a_job,1000.00\n"
                        b"I-2,10/31/2026,Rivera (fictional),not_sure,500.00\n", "invoices")
        costs = read(b"Date,Vendor,Type,Amount\n10/30/2026,Crew (fictional),Labor,300.00\n"
                     b"10/30/2026,Tile Co (fictional),Materials,400.00\n", "costs")
        job_list = jm.jobs(invoices, costs)
        report = jp.job_profit(invoices, jm.apply(costs, {2: jm.job("not_a_job"), 3: jm.job("not_a_job")}, job_list))
        self.assertEqual((Decimal("300.00"), "complete"), (self.job(report, "not_a_job").contribution,
                                                           self.job(report, "not_a_job").status))
        self.assertEqual(Decimal("0"), report.unlinked_costs)  # nothing went to overhead
        self.assertNotEqual(jm.job("not_a_job"), jm.NOT_A_JOB)
        self.assertNotEqual(jm.job("not_sure"), jm.NOT_SURE)

    def test_a_costs_file_with_no_job_column_can_still_be_matched(self):
        costs = read(b"Date,Vendor,Type,Amount\n10/30/2026,Crew (fictional),Labor,300.00\n"
                     b"10/30/2026,Tile Co (fictional),Materials,400.00\n", "costs")
        self.assertFalse(jp.job_profit(self.invoices, costs).available)  # nothing to match on, as before
        job_list = jm.jobs(self.invoices, costs)
        report = jp.job_profit(self.invoices, jm.apply(costs, {2: jm.job("J-1"), 3: jm.job("J-1")}, job_list))
        self.assertEqual((Decimal("300.00"), "complete"), (self.job(report, "J-1").contribution,
                                                           self.job(report, "J-1").status))
        self.assertEqual("unavailable", self.job(report, "J-2").status)  # no costs were said to be J-2's


class SourceKeyTests(unittest.TestCase):
    def test_any_change_to_a_file_or_how_it_was_read_changes_its_key(self):
        reading = (0, "invoices", [("job_id", "Job")], "MM/DD/YYYY", None, [])
        key = jm.source_key("sales.csv", b"rows", reading)
        self.assertEqual(key, jm.source_key("sales.csv", b"rows", reading))  # the same file, read the same way
        self.assertNotEqual(key, jm.source_key("sales (2).csv", b"rows", reading))  # renamed
        self.assertNotEqual(key, jm.source_key("sales.csv", b"Shop B\nrows", reading))  # another title line
        self.assertNotEqual(key, jm.source_key("sales.csv", b"rows", (0, "invoices", [("job_id", "Project")],
                                                                      "MM/DD/YYYY", None, [])))  # another column
        self.assertNotEqual(key, jm.source_key("sales.csv", b"rows", (0, "invoices", [("job_id", "Job")],
                                                                      "DD/MM/YYYY", None, [])))  # another date answer


class AnswerChangeTests(unittest.TestCase):
    """Changing or taking back an answer gives exactly the figures of the new answer, never a mix."""

    def setUp(self):
        self.invoices, self.costs = read(INVOICES, "invoices"), read(COSTS, "costs")
        self.jobs = jm.jobs(self.invoices, self.costs)
        self.original = [dict(line) for line in self.costs.accepted]

    def figures(self, choices):
        report = jp.job_profit(self.invoices, jm.apply(self.costs, choices, self.jobs))
        self.assertEqual(self.original, self.costs.accepted)  # the file's own result is never changed
        jobs = {j.job_id: (j.contribution, j.status) for j in report.jobs}
        return jobs["J-1"], jobs["J-2"], report.unlinked_costs, report.unlinked_job_costs

    def test_every_answer_change_gives_the_new_answers_figures(self):
        d = Decimal
        unanswered = ((d("700.00"), "provisional"), (d("500.00"), "provisional"), d("1350.00"), d("450.00"))
        tile_j1 = ((d("300.00"), "complete"), (d("500.00"), "complete"), d("950.00"), d("0"))
        tile_not_a_job = ((d("700.00"), "provisional"), (d("500.00"), "complete"), d("1350.00"), d("0"))
        tile_j2 = ((d("700.00"), "provisional"), (d("100.00"), "complete"), d("950.00"), d("0"))
        supplies = {7: jm.NOT_A_JOB}
        steps = [  # J-1 -> Not sure, J-1 -> Not for a job, Not for a job -> J-2, Not for a job -> Not sure
            ({5: jm.job("J-1"), **supplies}, tile_j1), ({}, unanswered),
            ({5: jm.job("J-1"), **supplies}, tile_j1), ({5: jm.NOT_A_JOB, **supplies}, tile_not_a_job),
            ({5: jm.job("J-2"), **supplies}, tile_j2),
            ({5: jm.NOT_A_JOB, **supplies}, tile_not_a_job), ({5: jm.NOT_SURE, 7: jm.NOT_SURE}, unanswered),
        ]
        for choices, expected in steps:
            with self.subTest(choices=choices):
                self.assertEqual(expected, self.figures(choices))


if __name__ == "__main__":
    unittest.main()
