"""The made-up demo businesses shown to owners: one per kind of business we talk to.

Each must tell a clear story with no questions to answer: one job that lost money, a big customer who
barely makes money, one job missing labor (so it needs a check), and rent as overhead not tied to a
job. Every name is marked "(fictional)". The exact figures are checked so a change to the files is
always deliberate.
"""
from decimal import Decimal
import csv
import io
from pathlib import Path
import unittest

import job_intake as ji
import job_profit as jp
import marginx_insights as mi

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data" / "marginx"
SHOPS = ("sign_shop", "contractor", "custom_shop")


def read(shop):
    """(report, intake results) for a demo business, with every automatic choice, as the app makes them."""
    results = {}
    for kind in ("invoices", "costs"):
        data = (SAMPLES / f"demo_{shop}_{kind}.csv").read_bytes()
        headers, records = ji.read_csv(data)
        mapping = ji.suggest_mapping(headers, kind)
        assert ji.amount_scope_question(headers, records, mapping, kind) is None, (shop, kind)
        assert ji.subtotal_questions(headers, records, mapping, kind) == [], (shop, kind)
        date_format = ji.suggest_date_format(ji.column_values(headers, records, mapping["date"]))
        results[kind] = ji.intake(headers, records, mapping, kind, date_format)
    return jp.job_profit(results["invoices"], results["costs"]), results


class EveryDemoBusinessTests(unittest.TestCase):
    def test_reads_cleanly_with_nothing_to_answer(self):
        for shop in SHOPS:
            _, results = read(shop)
            for kind, result in results.items():
                self.assertEqual([], result.rejected, (shop, kind))

    def test_tells_the_same_kind_of_story(self):
        for shop in SHOPS:
            report, _ = read(shop)
            losing = [j for j in report.jobs if j.status == "complete" and j.contribution < 0]
            to_check = [j for j in report.jobs if j.status != "complete"]
            self.assertEqual(1, len(losing), shop)
            self.assertEqual(["No labor recorded."], [r for j in to_check for r in j.reasons], shop)
            titles = [i.title for i in mi.attention(report)]
            self.assertTrue(any("biggest, but keeps only" in t for t in titles), (shop, titles))
            # Rent is the one cost not tied to a job: overhead, kept out of every job's figure.
            self.assertTrue(any(n.startswith("1 overhead or fee line") for n in report.notes), shop)

    def test_every_name_is_marked_fictional(self):
        for shop in SHOPS:
            for kind, column in (("invoices", "Customer"), ("costs", "Vendor")):
                rows = csv.DictReader(io.StringIO((SAMPLES / f"demo_{shop}_{kind}.csv").read_text()))
                for row in rows:
                    self.assertTrue(row[column].endswith("(fictional)"), (shop, row[column]))


class ContractorDemoTests(unittest.TestCase):
    def test_exact_figures_and_findings(self):
        report, _ = read("contractor")
        summary = mi.summarize(report)
        self.assertEqual((Decimal("77400.00"), Decimal("18750.00"), 24), (summary.sales, summary.left_after_job_costs,
                                                                          summary.share_percent))
        self.assertEqual(Decimal("16250.00"), summary.after_unlinked_costs)  # after $2,500 of rent
        self.assertEqual([
            "Bathroom remodel · J-206 lost $650",
            "Pool deck tile · J-208 kept only 3%",
            "Lobby flooring · J-202 kept only 7%",
            "Of customers with complete figures, Ocean View Condos (fictional) is the biggest, but keeps only 6%",
            "Waiting room flooring · J-207 needs a check",
        ], [i.title for i in mi.attention(report)])


class CustomShopDemoTests(unittest.TestCase):
    def test_exact_figures_and_findings(self):
        report, _ = read("custom_shop")
        summary = mi.summarize(report)
        self.assertEqual((Decimal("64700.00"), Decimal("17350.00"), 27), (summary.sales, summary.left_after_job_costs,
                                                                          summary.share_percent))
        self.assertEqual(Decimal("14150.00"), summary.after_unlinked_costs)  # after $3,200 of rent
        self.assertEqual([
            "Store display (rush) · K-304 lost $350",
            "Stair railing · K-305 kept only 3%",
            "Entry gate · K-307 kept only 5%",
            "Of customers with complete figures, Harbor Builders (fictional) is the biggest, but keeps only 5%",
            "Vanity cabinets · K-308 needs a check",
        ], [i.title for i in mi.attention(report)])


if __name__ == "__main__":
    unittest.main()
