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
        answered = jm.apply(self.costs, {5: "J-1", 7: jm.NOT_A_JOB}, self.jobs)
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
        jm.apply(self.costs, {5: "J-1", 7: jm.NOT_A_JOB}, self.jobs)
        self.assertEqual("", self.costs.accepted[3].get("job_id", ""))
        self.assertNotIn("not_for_a_job", self.costs.accepted[5])

    def test_a_job_that_is_not_in_the_files_is_refused(self):
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {5: "J-9"}, self.jobs)

    def test_a_cost_that_already_has_a_job_or_is_overhead_cannot_be_moved(self):
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {2: "J-2"}, self.jobs)  # row 2 is already J-1's labor
        with self.assertRaises(ValueError):
            jm.apply(self.costs, {6: "J-1"}, self.jobs)  # row 6 is rent

    def test_a_costs_file_with_no_job_column_can_still_be_matched(self):
        costs = read(b"Date,Vendor,Type,Amount\n10/30/2026,Crew (fictional),Labor,300.00\n"
                     b"10/30/2026,Tile Co (fictional),Materials,400.00\n", "costs")
        self.assertFalse(jp.job_profit(self.invoices, costs).available)  # nothing to match on, as before
        job_list = jm.jobs(self.invoices, costs)
        report = jp.job_profit(self.invoices, jm.apply(costs, {2: "J-1", 3: "J-1"}, job_list))
        self.assertEqual((Decimal("300.00"), "complete"), (self.job(report, "J-1").contribution,
                                                           self.job(report, "J-1").status))
        self.assertEqual("unavailable", self.job(report, "J-2").status)  # no costs were said to be J-2's


if __name__ == "__main__":
    unittest.main()
