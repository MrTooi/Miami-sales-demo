import copy
import json
import unittest
from fractions import Fraction
from pathlib import Path

from agent_evals.final_readiness import SUITES, load_rubric, score_readiness

ROOT = Path(__file__).resolve().parents[1]
AGENTS = json.loads((ROOT / "agent_evals/team_profiles.json").read_text(encoding="utf-8"))["agents"]
RUBRIC_FIELDS = ("expected_primary", "expected_reviewers", "critical", "must_do", "must_not")


def load(suite, kind):
    return json.loads((ROOT / f"agent_evals/final_suite_{suite}_{kind}.json").read_text(encoding="utf-8"))["cases"]


def perfect_doc(rubric):
    return {"results": [
        {"id": cid, "primary": c["expected_primary"], "reviewers": list(c["expected_reviewers"]),
         "must_do_met": [True] * len(c["must_do"]), "must_not_violated": [False] * len(c["must_not"])}
        for cid, c in rubric.items()
    ]}


class CrossSuiteTests(unittest.TestCase):
    def test_ids_and_prompts_unique_across_suites_and_old_suite(self):
        ids, prompts = [], []
        for suite in SUITES:
            self.assertEqual(18, len(load(suite, "prompts")))
            self.assertEqual([c["id"] for c in load(suite, "prompts")], [c["id"] for c in load(suite, "rubric")])
            ids += [c["id"] for c in load(suite, "prompts")]
            prompts += [c["prompt"].strip().casefold() for c in load(suite, "prompts")]
        self.assertEqual(54, len(set(ids)))
        self.assertEqual(54, len(set(prompts)))
        old = json.loads((ROOT / "agent_evals/behavioral_prompts.json").read_text(encoding="utf-8"))["cases"]
        self.assertFalse(set(ids) & {c["id"] for c in old})
        self.assertFalse(set(prompts) & {c["prompt"].strip().casefold() for c in old})

    def test_blind_prompts_leak_no_rubric_data(self):
        for suite in SUITES:
            raw = (ROOT / f"agent_evals/final_suite_{suite}_prompts.json").read_text(encoding="utf-8")
            for key in RUBRIC_FIELDS:
                self.assertNotIn(f'"{key}"', raw)
            rubric = {c["id"]: c for c in load(suite, "rubric")}
            for case in load(suite, "prompts"):
                self.assertEqual({"id", "prompt"}, set(case))
                text = case["prompt"].casefold()
                for agent in ("qa_critic", "security_integrity", "research_product", "frontend_ux"):
                    self.assertNotIn(agent, text)
                for phrase in rubric[case["id"]]["must_do"] + rubric[case["id"]]["must_not"]:
                    self.assertNotIn(phrase.casefold(), text)

    def test_rubrics_use_valid_agents_and_have_no_self_review(self):
        repo_agents = {k for k, v in AGENTS.items() if v["source"] == "repo"}
        for suite in SUITES:
            for case in load(suite, "rubric"):
                with self.subTest(case=case["id"]):
                    self.assertTrue({"id", *RUBRIC_FIELDS} <= set(case))
                    self.assertIn(case["expected_primary"], repo_agents)
                    self.assertTrue(case["expected_reviewers"])
                    self.assertEqual(len(case["expected_reviewers"]), len(set(case["expected_reviewers"])))
                    self.assertNotIn(case["expected_primary"], case["expected_reviewers"])
                    self.assertTrue(set(case["expected_reviewers"]) <= repo_agents)
                    self.assertIs(type(case["critical"]), bool)
                    for key in ("must_do", "must_not"):
                        self.assertTrue(case[key])
                        self.assertTrue(all(isinstance(x, str) and x.strip() for x in case[key]))

    def test_critical_cases_have_independent_reviewer_and_security_coverage(self):
        for suite in SUITES:
            for case in load(suite, "rubric"):
                if not case["critical"]:
                    continue
                with self.subTest(case=case["id"]):
                    reviewers = set(case["expected_reviewers"])
                    self.assertTrue(any(AGENTS[r]["independent_review"] for r in reviewers))
                    self.assertIn("security_integrity", reviewers | {case["expected_primary"]})

    def test_suite_c_rubric_covers_all_blind_prompts(self):
        self.assertEqual(18, len(load("c", "rubric")))


class ReadinessScorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rubric = load_rubric()
        cls.perfect = perfect_doc(cls.rubric)

    def score(self, doc):
        return score_readiness(doc, self.rubric)

    def test_perfect_results_are_ready(self):
        report = self.score(self.perfect)
        self.assertTrue(report.ready)
        self.assertEqual((54, 54), (report.passed, report.total))
        self.assertEqual(Fraction(1), report.pass_rate)

    def test_empty_and_malformed_documents_fail_closed(self):
        for doc in (None, [], {}, {"results": []}, {"results": "x"}, {"results": [], "extra": 1}):
            with self.subTest(doc=doc):
                self.assertFalse(self.score(doc).ready)

    def test_missing_duplicate_unknown_cases_fail_closed(self):
        missing = copy.deepcopy(self.perfect)
        missing["results"].pop()
        self.assertFalse(self.score(missing).ready)
        dup = copy.deepcopy(self.perfect)
        dup["results"].append(copy.deepcopy(dup["results"][0]))
        self.assertFalse(self.score(dup).ready)
        unknown = copy.deepcopy(self.perfect)
        unknown["results"][0]["id"] = "zz-unknown"
        self.assertFalse(self.score(unknown).ready)

    def test_malformed_entry_fields_fail_closed(self):
        for mutate in (
            lambda e: e.pop("reviewers"),
            lambda e: e.update(must_do_met=e["must_do_met"][:-1]),
            lambda e: e.update(must_do_met=[1] * len(e["must_do_met"])),
            lambda e: e.update(must_not_violated=None),
            lambda e: e.update(extra=True),
        ):
            doc = copy.deepcopy(self.perfect)
            mutate(doc["results"][0])
            with self.subTest():
                report = self.score(doc)
                self.assertFalse(report.ready)
                self.assertTrue(report.errors)

    def test_critical_failure_blocks_even_above_threshold(self):
        cid = next(c for c, v in self.rubric.items() if v["critical"])
        doc = copy.deepcopy(self.perfect)
        entry = next(e for e in doc["results"] if e["id"] == cid)
        entry["must_not_violated"][0] = True
        report = self.score(doc)
        self.assertFalse(report.ready)
        self.assertEqual((cid,), report.critical_failures)
        self.assertGreaterEqual(report.pass_rate, Fraction(95, 100))

    def test_wrong_primary_and_missing_reviewer_fail_case(self):
        cid = next(iter(self.rubric))
        for mutate in (lambda e: e.update(primary="orchestrator" if e["primary"] != "orchestrator" else "backend"),
                       lambda e: e.update(reviewers=[])):
            doc = copy.deepcopy(self.perfect)
            mutate(next(e for e in doc["results"] if e["id"] == cid))
            self.assertIn(cid, self.score(doc).failed_cases)

    def test_noncritical_failures_use_exact_95_percent_threshold(self):
        noncritical = [c for c, v in self.rubric.items() if not v["critical"]]
        self.assertGreaterEqual(len(noncritical), 3)
        doc = copy.deepcopy(self.perfect)
        for e in doc["results"]:
            if e["id"] == noncritical[0]:
                e["must_do_met"][0] = False
        report = self.score(doc)
        self.assertEqual(53, report.passed)
        self.assertTrue(report.ready)  # 53/54 ~ 98.1% >= 95%
        for e in doc["results"]:
            if e["id"] in noncritical[:3]:
                e["must_do_met"][0] = False
        report = self.score(doc)
        self.assertEqual(51, report.passed)  # 51/54 ~ 94.4% < 95%
        self.assertFalse(report.ready)


if __name__ == "__main__":
    unittest.main()
