from decimal import Decimal
from pathlib import Path
import unittest

import job_intake as ji
import job_profit as jp

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"


def intake(csv_bytes, kind, scope=None):
    headers, rows = ji.read_csv(csv_bytes)
    return ji.intake(headers, rows, ji.suggest_mapping(headers, kind), kind, "MM/DD/YYYY", scope)


INVOICES = (b"Invoice,Date,Customer,Job,Description,Line Amount\n"
            b"I-1,10/01/2026,Bakery,J-1,Signs,1000.00\n"
            b"I-1,10/01/2026,Bakery,J-1,Reprint credit,-50.00\n"
            b"I-2,10/02/2026,Gym,J-2,Banner,300.00\n"
            b"I-3,10/03/2026,Bakery,J-3,Decals,200.00\n"
            b"I-4,10/04/2026,Gym,,Rush fee,40.00\n")
COSTS = (b"Bill,Date,Vendor,Job,Type,Amount\n"
         b"B-1,10/01/2026,Paper Co,J-1,Materials,300.00\n"
         b"B-2,10/01/2026,Crew,J-1,Labor,200.10\n"
         b"B-3,10/02/2026,Print Partner,J-2,Outsourced,350.00\n"
         b"B-4,10/02/2026,Crew,J-2,Labor,25.00\n"
         b"B-5,10/05/2026,Electric Co,,Overhead,230.00\n"
         b"B-6,10/06/2026,Paper Co,J-9,Materials,60.00\n")


class JobProfitTests(unittest.TestCase):
    def setUp(self):
        self.report = jp.job_profit(intake(INVOICES, "invoices"), intake(COSTS, "costs"))
        self.jobs = {j.job_id: j for j in self.report.jobs}
        self.customers = {c.customer: c for c in self.report.customers}

    def test_complete_job_is_exact_and_includes_credits(self):
        j1 = self.jobs["J-1"]
        self.assertEqual("complete", j1.status)
        self.assertEqual(Decimal("950.00"), j1.sales)  # 1000 - 50 credit
        self.assertEqual(Decimal("500.10"), j1.total_costs)
        self.assertEqual(Decimal("449.90"), j1.contribution)
        self.assertIsInstance(j1.contribution, Decimal)

    def test_loss_making_job_is_shown_as_a_negative_contribution(self):
        j2 = self.jobs["J-2"]
        self.assertEqual("complete", j2.status)  # outsourced work counts as the job's direct cost
        self.assertEqual(Decimal("-75.00"), j2.contribution)

    def test_jobs_missing_sales_or_costs_get_no_figure(self):
        self.assertEqual("unavailable", self.jobs["J-3"].status)
        self.assertIsNone(self.jobs["J-3"].contribution)
        self.assertIn("No costs recorded", " ".join(self.jobs["J-3"].reasons))
        self.assertEqual("unavailable", self.jobs["J-9"].status)
        self.assertIn("No sales", " ".join(self.jobs["J-9"].reasons))

    def test_unlinked_sales_and_costs_are_reported_never_spread_over_jobs(self):
        self.assertEqual((Decimal("40.00"), 1), (self.report.unlinked_sales, self.report.unlinked_sales_lines))
        self.assertEqual((Decimal("230.00"), 1), (self.report.unlinked_costs, self.report.unlinked_cost_lines))
        notes = " ".join(self.report.notes)
        self.assertIn("$40.00", notes)
        self.assertIn("$230.00", notes)

    def test_customer_totals_inherit_their_jobs_status(self):
        bakery = self.customers["Bakery"]
        self.assertEqual(("J-1", "J-3"), bakery.jobs)
        self.assertEqual(Decimal("449.90"), bakery.contribution)  # only J-1 has a figure
        self.assertEqual("provisional", bakery.status)
        self.assertIn("J-3", " ".join(bakery.reasons))
        gym = self.customers["Gym"]
        self.assertEqual("provisional", gym.status)  # its rush fee has no job
        self.assertIn("no job number", " ".join(gym.reasons))

    def test_basis_and_dates_are_stated(self):
        self.assertIn("Direct job contribution", self.report.basis)
        self.assertIn("not cash received", self.report.basis)
        self.assertEqual(("2026-10-01", "2026-10-04"), self.report.invoice_dates)
        self.assertEqual(("2026-10-01", "2026-10-06"), self.report.cost_dates)


class CompletenessTests(unittest.TestCase):
    def report(self, costs, invoices=b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,500.00\n"):
        return jp.job_profit(intake(invoices, "invoices"), intake(costs, "costs"))

    def test_missing_labor_or_materials_makes_a_job_provisional(self):
        job = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Paper Co,J-1,Materials,100.00\n").jobs[0]
        self.assertEqual(("provisional", ["No labor recorded."]), (job.status, job.reasons))
        self.assertEqual(Decimal("400.00"), job.contribution)
        job = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,100.00\n").jobs[0]
        self.assertEqual(["No materials or outsourced work recorded."], job.reasons)

    def test_unknown_cost_types_make_a_job_provisional(self):
        job = self.report(b"Date,Vendor,Job,Amount\n10/01/2026,Paper Co,J-1,100.00\n").jobs[0]
        self.assertEqual("provisional", job.status)
        self.assertIn("no cost type column", " ".join(job.reasons))
        job = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,100.00\n"
                          b"10/01/2026,Paper Co,J-1,Materials,50.00\n10/01/2026,Ink Co,J-1,,20.00\n").jobs[0]
        self.assertEqual(["1 of its cost lines have no cost type."], job.reasons)
        self.assertEqual(Decimal("170.00"), job.total_costs)

    def test_job_billed_to_two_customers_is_kept_out_of_customer_totals(self):
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"10/01/2026,Paper Co,J-1,Materials,10.00\n",
                             b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,50.00\n"
                             b"I-2,10/01/2026,Gym,J-1,50.00\n")
        self.assertEqual("provisional", report.jobs[0].status)
        # Each customer stays listed, with no figure and the left-out job named.
        self.assertEqual(["Bakery", "Gym"], [c.customer for c in report.customers])
        for customer in report.customers:
            self.assertEqual("unavailable", customer.status)
            self.assertIsNone(customer.contribution)
            self.assertIn("Left out, billed to more than one customer: J-1", " ".join(customer.reasons))
        self.assertIn("more than one customer", " ".join(report.notes))

    def test_customer_with_a_complete_job_and_a_shared_job_is_not_complete(self):
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\nB-3,10/01/2026,Crew,J-2,Labor,5.00\n"
                             b"B-4,10/01/2026,Paper Co,J-2,Materials,5.00\n",
                             b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,50.00\n"
                             b"I-2,10/01/2026,Bakery,J-2,30.00\nI-3,10/01/2026,Gym,J-2,30.00\n")
        bakery = {c.customer: c for c in report.customers}["Bakery"]
        self.assertEqual(("provisional", Decimal("30.00")), (bakery.status, bakery.contribution))  # J-1 only
        self.assertIn("J-2", " ".join(bakery.reasons))

    def test_a_cost_line_that_failed_to_import_keeps_its_job_from_being_complete(self):
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"10/01/2026,Paper Co,J-1,Materials,10.00\n10/01/2026,Ink Co,J-1,Materials,12.345\n")
        job = report.jobs[0]
        self.assertEqual("provisional", job.status)
        self.assertIn("1 of its cost lines couldn't be imported", " ".join(job.reasons))
        self.assertEqual("provisional", report.customers[0].status)

    def test_failed_lines_without_a_job_number_hold_back_every_job(self):
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"10/01/2026,Paper Co,J-1,Materials,10.00\n10/01/2026,Ink Co,,Materials,oops\n"
                             b"10/01/2026,Paper Co,J-1\n")
        job = report.jobs[0]
        self.assertEqual("provisional", job.status)
        self.assertIn("2 cost line(s) couldn't be imported and have no readable job number", " ".join(job.reasons))

    def test_rows_that_are_not_lines_do_not_hold_a_job_back(self):
        # A duplicate row and a transfer row are rejected, but no money is missing.
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"10/01/2026,Crew,J-1,Labor,10.00\n10/01/2026,Paper Co,J-1,Materials,10.00\n"
                             b"10/01/2026,Bank,J-1,Transfer,500.00\n")
        self.assertEqual(("complete", []), (report.jobs[0].status, report.jobs[0].reasons))

    def test_job_whose_only_lines_failed_keeps_its_customer_from_being_complete(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,50.00\n"
                                    b"I-2,10/01/2026,Bakery,J-2,oops\n")
        jobs = {j.job_id: j for j in report.jobs}
        self.assertEqual("complete", jobs["J-1"].status)
        self.assertEqual(("unavailable", ("Bakery",)), (jobs["J-2"].status, jobs["J-2"].customers))
        bakery = report.customers[0]
        self.assertEqual(("provisional", Decimal("30.00")), (bakery.status, bakery.contribution))
        self.assertIn("J-2", " ".join(bakery.reasons))
        # A failed sales line whose customer can't be read holds back every customer.
        report = self.report(costs, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,50.00\n"
                                    b"I-2,10/01/2026,,J-2,20.00\n")
        self.assertEqual("provisional", report.customers[0].status)
        self.assertIn("no readable customer", " ".join(report.customers[0].reasons))

    def test_unclear_credits_are_never_treated_as_harmless(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\nB-3,10/01/2026,Paper Co,J-1,Vendor Credit,5.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Amount\n"
                                    b"I-1,10/01/2026,Bakery,J-1,Invoice,50.00\nI-2,10/01/2026,Bakery,J-1,Credit,10.00\n")
        job = report.jobs[0]
        self.assertEqual("provisional", job.status)  # a supplier credit and a customer credit may be missing
        self.assertIn("1 of its sales lines couldn't be imported", " ".join(job.reasons))
        self.assertIn("1 of its cost lines couldn't be imported", " ".join(job.reasons))
        # An explicit bank credit is a cash movement: rejected, and nothing is missing.
        report = self.report(costs.replace(b"Vendor Credit", b"Materials"),
                             b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,50.00\n"
                             b"I-2,10/01/2026,Bank,J-1,Bank Credit,10.00\n")
        self.assertEqual("complete", report.jobs[0].status)

    def test_failed_lines_naming_another_customer_make_the_job_shared(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\nB-3,10/01/2026,Paper Co,J-3,Materials,10.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,50.00\n"
                                    b"I-2,10/01/2026,Gym,J-1,oops\nI-3,10/01/2026,Cafe,J-3,oops\n")
        jobs = {j.job_id: j for j in report.jobs}
        self.assertEqual(("Bakery", "Gym"), jobs["J-1"].customers)
        self.assertEqual("provisional", jobs["J-1"].status)
        customers = {c.customer: c for c in report.customers}
        for name in ("Bakery", "Gym"):  # J-1 is in neither total, and both say so
            self.assertIn("Left out, billed to more than one customer: J-1", " ".join(customers[name].reasons))
            self.assertNotEqual("complete", customers[name].status)
        # A cost-only job whose failed invoice names its customer is that customer's, with no figure.
        self.assertEqual(("Cafe",), jobs["J-3"].customers)
        self.assertEqual("unavailable", customers["Cafe"].status)
        self.assertIn("J-3", " ".join(customers["Cafe"].reasons))

    def test_fees_and_overhead_recorded_against_a_job_are_shown_and_subtracted(self):
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\n"
                             b"B-3,10/01/2026,Square,J-1,Processing fees,1.50\nB-4,10/01/2026,Landlord,J-1,Overhead,5.00\n"
                             b"B-5,10/01/2026,Square,,Merchant fees,9.00\n")
        job = report.jobs[0]
        self.assertEqual(Decimal("6.50"), job.costs["fees_overhead"])
        self.assertEqual(Decimal("473.50"), job.contribution)  # 500 - 10 - 10 - 1.50 - 5
        notes = " ".join(report.notes)
        self.assertIn("$6.50 of fees or overhead were recorded against jobs", notes)
        self.assertIn("1 cost line(s) worth $9.00 aren't linked to a job", notes)
        self.assertIn("count only when they are recorded against a job", report.basis)
        self.assertEqual("fees_overhead", jp.cost_category("Merchant fees"))

    def test_unknown_type_markers_keep_a_job_provisional(self):
        for marker in (b"Unknown", b"Uncategorized", b"N/A", b"Not classified", b"Ask My Accountant"):
            with self.subTest(marker=marker):
                job = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                                  b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\nB-3,10/01/2026,Ink Co,J-1," + marker
                                  + b",5.00\n").jobs[0]
                self.assertEqual(("provisional", Decimal("5.00")), (job.status, job.costs["unknown"]))
        self.assertEqual("other", jp.cost_category("Delivery"))

    def test_credit_memo_signs(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,10.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,10.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                                    b"I-2,10/01/2026,Bakery,J-1,Credit Memo,-20.00\n")
        self.assertEqual(("complete", Decimal("80.00")), (report.jobs[0].status, report.jobs[0].sales))
        # A positive credit memo is never added to sales; the job can't be complete.
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                                    b"I-2,10/01/2026,Bakery,J-1,Credit Memo,20.00\n")
        self.assertEqual(("provisional", Decimal("100.00")), (report.jobs[0].status, report.jobs[0].sales))
        # Supplier credits: a positive one is unclear, a negative one is a negative cost; neither is imported.
        for amount in (b"5.00", b"-5.00"):
            report = self.report(costs + b"B-3,10/01/2026,Paper Co,J-1,Vendor Credit," + amount + b"\n")
            self.assertEqual(("provisional", Decimal("20.00")), (report.jobs[0].status, report.jobs[0].total_costs))

    def test_unlinked_costs_keep_jobs_provisional_but_are_never_allocated(self):
        invoices = b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\nB-3,10/02/2026,Paper Co,,Materials,40.00\n",
                             invoices)
        job = report.jobs[0]
        self.assertEqual(("provisional", Decimal("50.00")), (job.status, job.contribution))  # figure kept, not $10
        self.assertIn("1 cost line(s) worth $40.00 have no job number and may belong to this job", " ".join(job.reasons))
        self.assertEqual("provisional", report.customers[0].status)
        # Unlinked overhead or fees are outside the stated basis and don't hold jobs back.
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\nB-3,10/31/2026,Electric Co,,Overhead,90.00\n",
                             invoices)
        self.assertEqual(("complete", Decimal("50.00")), (report.jobs[0].status, report.jobs[0].contribution))
        self.assertIn("$90.00 aren't linked to a job", " ".join(report.notes))

    def test_money_is_never_shown_rounded(self):
        self.assertEqual("$1,250.50", jp.format_money(Decimal("1250.5")))
        self.assertEqual("-$45.00", jp.format_money(Decimal("-45.00")))
        with self.assertRaises(ValueError):
            jp.format_money(Decimal("12.345"))

    def test_look_alike_job_numbers_are_never_merged(self):
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Paper Co,j-1,Materials,100.00\n")
        self.assertEqual(["J-1", "j-1"], sorted(j.job_id for j in report.jobs))
        self.assertIn("look alike", " ".join(report.notes))

    def test_no_job_column_means_no_figures_at_all(self):
        report = self.report(b"Date,Vendor,Type,Amount\n10/01/2026,Paper Co,Materials,100.00\n")
        self.assertFalse(report.available)
        self.assertEqual([], report.jobs)
        self.assertIn("costs file has no job number column", " ".join(report.reasons))

    def test_cost_categories(self):
        self.assertEqual("labor", jp.cost_category("Contract labor"))
        self.assertEqual("outsourced", jp.cost_category("Subcontractor"))
        self.assertEqual("materials", jp.cost_category("COGS:Materials"))
        self.assertEqual("other", jp.cost_category("Delivery"))
        self.assertEqual("fees_overhead", jp.cost_category("Non-labor fees"))
        self.assertEqual("unknown", jp.cost_category("  "))

    def test_wrong_kinds_are_refused(self):
        inv = intake(b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,500.00\n", "invoices")
        with self.assertRaises(ValueError):
            jp.job_profit(inv, inv)


class SampleFileTests(unittest.TestCase):
    def test_sample_files(self):
        headers, rows = ji.read_csv((SAMPLES / "fictional_invoices.csv").read_bytes())
        inv = ji.intake(headers, rows, ji.suggest_mapping(headers, "invoices"), "invoices", "MM/DD/YYYY", "line")
        headers, rows = ji.read_csv((SAMPLES / "fictional_costs.csv").read_bytes())
        cst = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        jobs = {j.job_id: j for j in jp.job_profit(inv, cst).jobs}
        self.assertEqual((Decimal("840.00"), "provisional"), (jobs["J-501"].contribution, jobs["J-501"].status))
        self.assertEqual(Decimal("475.00"), jobs["J-502"].contribution)  # 640 + 120 - 190 - 95


if __name__ == "__main__":
    unittest.main()
