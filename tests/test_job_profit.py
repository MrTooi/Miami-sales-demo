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
        # Outsourced work counts as the job's direct cost; the job is provisional only because Gym's
        # $40.00 rush fee has no job number and may belong to it.
        self.assertEqual(("provisional", ["Gym has 1 sales line(s) worth $40.00 with no job number that may belong "
                                          "to this job."]), (j2.status, j2.reasons))
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
        # A transfer row is rejected, but no money is missing.
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,10.00\n"
                             b"10/01/2026,Paper Co,J-1,Materials,10.00\n10/02/2026,Bank,J-1,Transfer,500.00\n")
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

    def test_mixed_labels_are_other_and_never_exempt(self):
        for text, category in (("Materials processing", "other"), ("Labor fees", "other"),
                               ("Outsourced install fee", "other"), ("Ink processing fee", "other"),
                               ("Processing fees", "fees_overhead"), ("Rent", "fees_overhead"),
                               ("Merchant fees", "fees_overhead"), ("Delivery fee", "other"),
                               ("Installation fee", "other"), ("Rush fee", "other"),
                               ("Cost of Goods Sold:Materials", "materials"), ("Job Labor", "labor")):
            self.assertEqual(category, jp.cost_category(text), text)
        # Unlinked "Materials processing" may belong to the job: it holds the job back.
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n"
                             b"B-3,10/02/2026,Paper Co,,Materials processing,40.00\n",
                             b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n")
        self.assertEqual(("provisional", Decimal("50.00")), (report.jobs[0].status, report.jobs[0].contribution))
        self.assertIn("worth $40.00 have no job number", " ".join(report.jobs[0].reasons))

    def test_negated_labels_never_confirm_materials_or_outsourced_work(self):
        for text in ("Non-material costs", "No materials", "Not outsourced", "Non-outsourced work", "No labor"):
            self.assertEqual("other", jp.cost_category(text), text)
            report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                                 b"B-2,10/01/2026,Shop,J-1," + text.encode() + b",30.00\n",
                                 b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n")
            job, customer = report.jobs[0], report.customers[0]
            self.assertEqual(("provisional", Decimal("50.00")), (job.status, job.contribution), text)  # still subtracted
            self.assertEqual("provisional", customer.status, text)

    def test_unlinked_delivery_or_installation_fees_hold_jobs_back(self):
        for fee in (b"Delivery fee", b"Installation fee"):
            with self.subTest(fee=fee):
                report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                                     b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n"
                                     b"B-3,10/02/2026,Courier,," + fee + b",40.00\n",
                                     b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n")
                self.assertEqual(("provisional", Decimal("50.00")),
                                 (report.jobs[0].status, report.jobs[0].contribution))

    def test_only_whole_overhead_types_are_exempt(self):
        for text in ("Rent", "Utilities", "Insurance", "Overhead", "Merchant fees", "Payment processing fees",
                     "Bank fees", "Office rent"):
            self.assertEqual("fees_overhead", jp.cost_category(text), text)
        for text in ("Equipment rent", "Job processing", "Installation insurance", "Rental", "Overhead crane"):
            self.assertEqual("other", jp.cost_category(text), text)
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
        invoices = b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
        for text in (b"Equipment rent", b"Job processing", b"Installation insurance"):
            with self.subTest(text=text):
                report = self.report(costs + b"B-3,10/02/2026,Lift Co,," + text + b",40.00\n", invoices)
                self.assertEqual(("provisional", Decimal("50.00")),
                                 (report.jobs[0].status, report.jobs[0].contribution))
                self.assertEqual(("provisional", Decimal("50.00")),
                                 (report.customers[0].status, report.customers[0].contribution))
                self.assertEqual(Decimal("40.00"), report.unlinked_costs)  # kept whole, never allocated
        # Clear overhead with no job number is outside the basis: the job can be complete.
        report = self.report(costs + b"B-3,10/31/2026,Landlord,,Rent,40.00\n", invoices)
        self.assertEqual(("complete", "complete"), (report.jobs[0].status, report.customers[0].status))

    def test_payment_processing_fees_are_costs_not_cash_movements(self):
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n"
                             b"B-3,10/01/2026,Square,J-1,Payment processing fees,2.90\n"
                             b"B-4,10/01/2026,Bank,J-1,Transfer fee,1.00\n",
                             b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n")
        job = report.jobs[0]
        self.assertEqual((Decimal("3.90"), Decimal("46.10"), "complete"),
                         (job.costs["fees_overhead"] + job.costs["other"], job.contribution, job.status))
        self.assertEqual(Decimal("2.90"), job.costs["fees_overhead"])

    def test_payout_net_of_fees_is_never_a_sale_or_a_cost(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                                    b"I-2,10/01/2026,Square,J-1,Payout net of fees,40.00\n")
        job = report.jobs[0]
        self.assertEqual((Decimal("100.00"), "provisional"), (job.sales, job.status))  # never $90 Complete
        report = self.report(costs + b"B-3,10/01/2026,Bank,J-1,Transfer less fees,40.00\n")
        job = report.jobs[0]
        self.assertEqual((Decimal("50.00"), "provisional"), (job.total_costs, job.status))

    def test_unrecognized_sales_row_types_never_inflate_a_complete_figure(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
        for row_type, amount in ((b"Payment processing fees", b"2.90"), (b"Bank Credit (ACH)", b"40.00"),
                                 (b"Estimate", b"500.00")):
            with self.subTest(row_type=row_type):
                report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Amount\n"
                                            b"I-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                                            b"I-2,10/01/2026,Bakery,J-1," + row_type + b"," + amount + b"\n")
                job = report.jobs[0]
                self.assertEqual((Decimal("100.00"), Decimal("50.00"), "provisional"),
                                 (job.sales, job.contribution, job.status))
                self.assertEqual("provisional", report.customers[0].status)
        # Recognized sale types still count.
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                                    b"I-2,10/01/2026,Bakery,J-1,Sales Receipt,25.00\n")
        self.assertEqual((Decimal("125.00"), "complete"), (report.jobs[0].sales, report.jobs[0].status))

    def test_bank_credit_variants_in_a_cost_file_are_never_costs(self):
        base = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
        invoices = b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
        for row_type in (b"Bank Credit (ACH)", b"ACH credit", b"Vendor refund"):
            with self.subTest(row_type=row_type):
                report = self.report(base + b"B-3,10/01/2026,Bank,J-1," + row_type + b",40.00\n", invoices)
                self.assertEqual((Decimal("50.00"), "provisional"),
                                 (report.jobs[0].total_costs, report.jobs[0].status))
        # Card charges and bank fees stay ordinary costs.
        report = self.report(base + b"B-3,10/01/2026,Sign Co,J-1,Credit Card Charge,5.00\n"
                                    b"B-4,10/01/2026,Bank,J-1,Bank service charges,1.00\n", invoices)
        self.assertEqual((Decimal("56.00"), "complete"), (report.jobs[0].total_costs, report.jobs[0].status))

    def test_estimates_and_purchase_orders_are_never_costs(self):
        invoices = b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
        # A transaction-type column next to the cost category.
        base = (b"Bill,Date,Vendor,Job,Transaction Type,Category,Amount\n"
                b"B-1,10/01/2026,Crew,J-1,Bill,Labor,20.00\nB-2,10/01/2026,Paper Co,J-1,Expense,Materials,30.00\n")
        for txn in (b"Estimate", b"Purchase Order", b"Quote", b"Something else"):
            with self.subTest(txn=txn):
                report = self.report(base + b"B-3,10/01/2026,Paper Co,J-1," + txn + b",Materials,40.00\n", invoices)
                job = report.jobs[0]
                self.assertEqual((Decimal("50.00"), "provisional"), (job.contribution, job.status))
                self.assertEqual("provisional", report.customers[0].status)
        report = self.report(base + b"B-3,10/01/2026,Sign Co,J-1,Check,Delivery,5.00\n", invoices)
        self.assertEqual((Decimal("45.00"), "complete"), (report.jobs[0].contribution, report.jobs[0].status))
        # Only a cost category column: any real category counts, but not an estimate or order.
        cat = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
               b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
        for category in (b"Estimate", b"Purchase order", b"Materials quote"):
            with self.subTest(category=category):
                report = self.report(cat + b"B-3,10/01/2026,Paper Co,J-1," + category + b",40.00\n", invoices)
                self.assertEqual((Decimal("50.00"), "provisional"), (report.jobs[0].contribution, report.jobs[0].status))
        for category in (b"Delivery", b"Permits", b"Equipment rental"):
            with self.subTest(category=category):
                report = self.report(cat + b"B-3,10/01/2026,Sign Co,J-1," + category + b",5.00\n", invoices)
                self.assertEqual((Decimal("45.00"), "complete"), (report.jobs[0].contribution, report.jobs[0].status))

    def test_blank_transaction_types_are_unresolved(self):
        invoices = b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
        report = self.report(b"Bill,Date,Vendor,Job,Transaction Type,Category,Amount\n"
                             b"B-1,10/01/2026,Crew,J-1,,Labor,20.00\nB-2,10/01/2026,Paper Co,J-1,,Materials,30.00\n",
                             invoices)
        # No row is a posted cost, so no cost lines were imported and no figure is shown at all.
        self.assertFalse(report.available)
        self.assertEqual([], report.jobs)
        self.assertIn("No cost lines were imported", " ".join(report.reasons))
        report = self.report(b"Bill,Date,Vendor,Job,Transaction Type,Category,Amount\n"
                             b"B-1,10/01/2026,Crew,J-1,Bill,Labor,20.00\nB-2,10/01/2026,Paper Co,J-1,Bill,Materials,30.00\n"
                             b"B-3,10/01/2026,Ink Co,J-1,,Materials,40.00\n", invoices)
        self.assertEqual((Decimal("50.00"), "provisional"), (report.jobs[0].contribution, report.jobs[0].status))
        self.assertEqual("provisional", report.customers[0].status)
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n",
                             b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                             b"I-2,10/01/2026,Bakery,J-1,,40.00\n")
        self.assertEqual((Decimal("100.00"), "provisional"), (report.jobs[0].sales, report.jobs[0].status))
        # A file with only a cost category column may leave it blank: that is just an untyped cost.
        report = self.report(b"Bill,Date,Vendor,Job,Category,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\nB-3,10/01/2026,Ink Co,J-1,,5.00\n", invoices)
        self.assertEqual(Decimal("55.00"), report.jobs[0].total_costs)

    def test_conflicting_type_columns_are_unresolved(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Transaction Type,Amount\n"
                                    b"I-1,10/01/2026,Bakery,J-1,Invoice,Invoice,100.00\n"
                                    b"I-2,10/01/2026,Bakery,J-1,Invoice,Payment,40.00\n")
        self.assertEqual((Decimal("100.00"), "provisional"), (report.jobs[0].sales, report.jobs[0].status))
        self.assertEqual("provisional", report.customers[0].status)
        # Both columns saying payment is plainly a payment: left out, nothing missing.
        report = self.report(costs, b"Invoice,Date,Customer,Job,Type,Transaction Type,Amount\n"
                                    b"I-1,10/01/2026,Bakery,J-1,Invoice,Invoice,100.00\n"
                                    b"I-2,10/01/2026,Bakery,J-1,Payment,Payment,40.00\n")
        self.assertEqual("complete", report.jobs[0].status)
        # Costs file: a "Payment" transaction on a "Materials" category row is unresolved.
        report = self.report(b"Bill,Date,Vendor,Job,Transaction Type,Category,Amount\n"
                             b"B-1,10/01/2026,Crew,J-1,Bill,Labor,20.00\nB-2,10/01/2026,Paper Co,J-1,Bill,Materials,30.00\n"
                             b"B-3,10/01/2026,Paper Co,J-1,Payment,Materials,40.00\n",
                             b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n")
        self.assertEqual((Decimal("50.00"), "provisional"), (report.jobs[0].contribution, report.jobs[0].status))

    LINKED = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
              b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n")
    SALES = b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"

    def assert_job(self, report, sales, contribution, status):
        job = report.jobs[0]
        self.assertEqual((sales, contribution, status), (job.sales, job.contribution, job.status))
        self.assertEqual(status, report.customers[0].status)

    def test_credit_memo_signs_singular_and_plural(self):
        for label in (b"Credit Memo", b"Credit Memos", b"Credit Note", b"Credit Notes"):
            with self.subTest(label=label):
                invoices = (b"Invoice,Date,Customer,Job,Type,Amount\nI-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                            b"I-2,10/01/2026,Bakery,J-1," + label + b",")
                self.assert_job(self.report(self.LINKED, invoices + b"20.00\n"),
                                Decimal("100.00"), Decimal("50.00"), "provisional")  # never $70 Complete
                self.assert_job(self.report(self.LINKED, invoices + b"-20.00\n"),
                                Decimal("80.00"), Decimal("30.00"), "complete")

    def test_payment_with_a_blank_transaction_type_is_unresolved(self):
        invoices = (b"Invoice,Date,Customer,Job,Type,Transaction Type,Amount\n"
                    b"I-1,10/01/2026,Bakery,J-1,Invoice,Invoice,100.00\nI-2,10/01/2026,Bakery,J-1,Payment,,40.00\n")
        self.assert_job(self.report(self.LINKED, invoices), Decimal("100.00"), Decimal("50.00"), "provisional")
        costs = (b"Bill,Date,Vendor,Job,Txn Type,Transaction Type,Category,Amount\n"
                 b"B-1,10/01/2026,Crew,J-1,Bill,Bill,Labor,20.00\nB-2,10/01/2026,Paper Co,J-1,Bill,Bill,Materials,30.00\n"
                 b"B-3,10/01/2026,Bank,J-1,Payment,,,40.00\n")
        self.assert_job(self.report(costs, self.SALES), Decimal("100.00"), Decimal("50.00"), "provisional")
        # Every column saying payment: plainly a payment, left out, nothing missing.
        self.assert_job(self.report(costs.replace(b"Payment,,,40.00", b"Payment,Payment,,40.00"), self.SALES),
                        Decimal("100.00"), Decimal("50.00"), "complete")

    def test_sales_labels_are_not_cost_categories(self):
        for label in (b"Invoice", b"Sale", b"Sales Receipt", b"Revenue"):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1," + label + b",40.00\n", self.SALES)
                self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")  # never $10 Complete
        for label in (b"Delivery", b"Permits", b"Equipment rental"):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Sign Co,J-1," + label + b",5.00\n", self.SALES)
                self.assert_job(report, Decimal("100.00"), Decimal("45.00"), "complete")

    def test_overhead_names_under_a_job_account_are_not_exempt(self):
        for label, status in ((b"Job Costs:Rent", "provisional"), (b"Cost of Goods Sold:Insurance", "provisional"),
                              (b"Office rent", "complete"), (b"Overhead:Rent", "complete"),
                              (b"Operating Expenses:Utilities", "complete")):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/31/2026,Landlord,," + label + b",40.00\n", self.SALES)
                self.assert_job(report, Decimal("100.00"), Decimal("50.00"), status)
                self.assertEqual(Decimal("40.00"), report.unlinked_costs)  # disclosed whole, never allocated
        self.assertEqual("other", jp.cost_category("Job Costs:Rent"))
        self.assertEqual("fees_overhead", jp.cost_category("Overhead:Rent"))
        self.assertEqual("materials", jp.cost_category("Cost of Goods Sold:Materials"))

    def test_account_paths_in_cost_categories(self):
        for label in (b"Income:Revenue", b"Income:Sales", b"Sales:Signs"):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1," + label + b",40.00\n", self.SALES)
                self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")  # never $10 Complete
        report = self.report(self.LINKED + b"B-3,10/01/2026,Square,J-1,Operating Expenses:Payment processing fees,2.90\n",
                             self.SALES)
        self.assert_job(report, Decimal("100.00"), Decimal("47.10"), "complete")
        self.assertEqual(Decimal("2.90"), report.jobs[0].costs["fees_overhead"])
        report = self.report(self.LINKED + b"B-3,10/01/2026,Sign Co,J-1,Job Costs:Delivery,5.00\n", self.SALES)
        self.assert_job(report, Decimal("100.00"), Decimal("45.00"), "complete")

    def test_identical_lines_are_counted_once_but_keep_the_job_provisional(self):
        report = self.report(b"Date,Vendor,Job,Type,Amount\n10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"10/01/2026,Crew,J-1,Labor,20.00\n10/02/2026,Paper Co,J-1,Materials,30.00\n",
                             self.SALES)
        self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")  # never $30, never Complete
        report = self.report(self.LINKED, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
                                          b"I-1,10/01/2026,Bakery,J-1,100.00\n")
        self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")
        # Lines that differ in any column (here the bill number) are both real and count.
        report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Crew,J-1,Labor,20.00\nB-3,10/02/2026,Paper Co,J-1,Materials,30.00\n",
                             self.SALES)
        self.assert_job(report, Decimal("100.00"), Decimal("30.00"), "complete")

    def test_summary_rows_in_a_category_column_are_never_costs(self):
        for label in (b"Grand Total", b"Subtotal", b"Totals:Grand Total"):
            with self.subTest(label=label):
                report = self.report(b"Bill,Date,Vendor,Job,Category,Line Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                                     b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\n"
                                     b"B-3,10/01/2026,Paper Co,J-1," + label + b",50.00\n", self.SALES)
                # Never subtracted again ($0); its meaning is unconfirmed, so the job is provisional.
                self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")
        report = self.report(b"Bill,Date,Vendor,Job,Category,Line Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                             b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\nB-3,10/01/2026,Sign Co,J-1,Permits,5.00\n",
                             self.SALES)
        self.assert_job(report, Decimal("100.00"), Decimal("45.00"), "complete")

    def test_look_alike_customers_and_jobs_are_never_complete(self):
        costs = (b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor,20.00\n"
                 b"B-2,10/01/2026,Paper Co,J-1,Materials,30.00\nB-3,10/01/2026,Crew,J-2,Labor,20.00\n"
                 b"B-4,10/01/2026,Paper Co,J-2,Materials,30.00\n")
        report = self.report(costs, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
                                    b"I-2,10/01/2026,bakery,J-2,150.00\n")
        self.assertEqual(["complete", "complete"], [j.status for j in report.jobs])  # the jobs themselves are fine
        self.assertEqual([("Bakery", Decimal("50.00"), "provisional"), ("bakery", Decimal("100.00"), "provisional")],
                         [(c.customer, c.contribution, c.status) for c in report.customers])  # kept apart, never merged
        self.assertIn("look alike", " ".join(report.notes))
        report = self.report(costs.replace(b"J-2", b"j 1"), b"Invoice,Date,Customer,Job,Amount\n"
                                                           b"I-1,10/01/2026,Bakery,J-1,100.00\nI-2,10/01/2026,Bakery,j 1,150.00\n")
        self.assertEqual({"J-1": "provisional", "j 1": "provisional"}, {j.job_id: j.status for j in report.jobs})
        self.assertEqual("provisional", report.customers[0].status)
        # Distinct names stay complete.
        report = self.report(costs, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
                                    b"I-2,10/01/2026,Gym,J-2,150.00\n")
        self.assertEqual(["complete", "complete"], [c.status for c in report.customers])

    def test_income_account_names_are_never_costs(self):
        for label in (b"Sales of Product Income", b"Sales of Product Income:Printing", b"Services Income",
                      b"Income:Revenue"):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1," + label + b",40.00\n", self.SALES)
                self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")
                self.assertEqual(Decimal("50.00"), report.jobs[0].total_costs)  # the $40 is never subtracted
        for label, contribution in ((b"Cost of Goods Sold:Materials", Decimal("10.00")),
                                    (b"Sales commissions", Decimal("10.00")), (b"Income tax", Decimal("10.00"))):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1," + label + b",40.00\n", self.SALES)
                self.assertEqual(contribution, report.jobs[0].contribution)
        self.assert_job(self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1,Cost of Goods Sold:Materials,40.00\n",
                                    self.SALES), Decimal("100.00"), Decimal("10.00"), "complete")

    def test_zero_dollar_cost_lines_never_make_a_job_complete(self):
        cases = ((b"0.00", b"30.00", ["Labor recorded only as $0.00."]),
                 (b"20.00", b"0.00", ["Materials or outsourced work recorded only as $0.00."]),
                 (b"0.00", b"0.00", ["Labor recorded only as $0.00.",
                                     "Materials or outsourced work recorded only as $0.00."]))
        for labor, materials, reasons in cases:
            with self.subTest(labor=labor, materials=materials):
                report = self.report(b"Bill,Date,Vendor,Job,Type,Amount\nB-1,10/01/2026,Crew,J-1,Labor," + labor + b"\n"
                                     b"B-2,10/01/2026,Paper Co,J-1,Materials," + materials + b"\n", self.SALES)
                job = report.jobs[0]
                self.assertEqual(("provisional", reasons), (job.status, job.reasons))
                self.assertEqual("provisional", report.customers[0].status)
                self.assertEqual(Decimal("100.00") - Decimal(labor.decode()) - Decimal(materials.decode()),
                                 job.contribution)  # zero rows are kept, nothing invented
        self.assert_job(self.report(self.LINKED, self.SALES), Decimal("100.00"), Decimal("50.00"), "complete")

    def test_a_customers_sales_without_a_job_keep_their_jobs_provisional(self):
        costs = self.LINKED + (b"B-3,10/01/2026,Crew,J-2,Labor,20.00\nB-4,10/01/2026,Paper Co,J-2,Materials,30.00\n")
        for amount in (b"40.00", b"-15.00"):  # a rush charge, or a credit
            with self.subTest(amount=amount):
                report = self.report(costs, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
                                            b"I-2,10/01/2026,Gym,J-2,100.00\nI-3,10/01/2026,Bakery,," + amount + b"\n")
                jobs = {j.job_id: j for j in report.jobs}
                self.assertEqual((Decimal("50.00"), "provisional"), (jobs["J-1"].contribution, jobs["J-1"].status))
                self.assertIn("Bakery has 1 sales line(s) worth", " ".join(jobs["J-1"].reasons))
                self.assertEqual("complete", jobs["J-2"].status)  # another customer's job is unaffected
                customers = {c.customer: c.status for c in report.customers}
                self.assertEqual({"Bakery": "provisional", "Gym": "complete"}, customers)
                self.assertEqual(Decimal(amount.decode()), report.unlinked_sales)  # disclosed in full, never spread

    def test_credit_only_jobs_are_never_complete(self):
        report = self.report(self.LINKED, b"Invoice,Date,Customer,Job,Type,Amount\n"
                                          b"I-1,10/01/2026,Bakery,J-1,Credit Memo,-20.00\n")
        self.assert_job(report, Decimal("-20.00"), Decimal("-70.00"), "provisional")  # exact figure kept
        self.assertIn("Only credits were found", " ".join(report.jobs[0].reasons))
        report = self.report(self.LINKED, b"Invoice,Date,Customer,Job,Type,Amount\n"
                                          b"I-1,10/01/2026,Bakery,J-1,Invoice,100.00\n"
                                          b"I-2,10/01/2026,Bakery,J-1,Credit Memo,-20.00\n")
        self.assert_job(report, Decimal("80.00"), Decimal("30.00"), "complete")

    def test_revenue_balance_sheet_and_order_accounts_are_never_costs(self):
        for label in (b"Product Sales", b"Sales Revenue", b"Income:Product Sales", b"Sales Discounts",
                      b"Inventory Asset", b"Sales Tax Payable", b"Accounts Payable", b"Undeposited Funds",
                      b"Prepaid Expenses", b"Purchase Order:Materials", b"Estimate:Labor"):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1," + label + b",40.00\n", self.SALES)
                self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "provisional")  # never $10 Complete
                self.assertEqual(Decimal("50.00"), report.jobs[0].total_costs)
        for label in (b"Cost of Goods Sold:Materials", b"Equipment rental", b"Sales commissions",
                      b"Sales tax expense", b"Cost of sales", b"Inventory"):
            with self.subTest(label=label):
                report = self.report(self.LINKED + b"B-3,10/01/2026,Paper Co,J-1," + label + b",40.00\n", self.SALES)
                self.assertEqual(Decimal("90.00"), report.jobs[0].total_costs)  # a real cost, subtracted

    def test_descriptions_are_text_not_account_paths(self):
        report = self.report(self.LINKED, b"Invoice,Date,Customer,Job,Description,Line Amount\n"
                                          b"I-1,10/01/2026,Bakery,J-1,Signs,60.00\nI-1,10/01/2026,Bakery,J-1,Service: Total,40.00\n")
        self.assert_job(report, Decimal("100.00"), Decimal("50.00"), "complete")  # "Service: Total" is a real line

    def test_unlinked_sales_under_a_look_alike_name_keep_jobs_provisional(self):
        for name in (b"bakery", b"BAKERY", b"Bakery ", b"Bak-ery"):
            with self.subTest(name=name):
                report = self.report(self.LINKED, b"Invoice,Date,Customer,Job,Amount\nI-1,10/01/2026,Bakery,J-1,100.00\n"
                                                  b"I-2,10/01/2026," + name + b",,-20.00\n")
                job = {j.job_id: j for j in report.jobs}["J-1"]
                self.assertEqual(("provisional", Decimal("50.00")), (job.status, job.contribution))  # never Complete
                self.assertIn("with no job number that may belong to this job", " ".join(job.reasons))
                self.assertEqual(Decimal("-20.00"), report.unlinked_sales)  # disclosed, never merged or allocated

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
        self.assertEqual("other", jp.cost_category("Non-labor fees"))  # a plain fee may be a job cost
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
