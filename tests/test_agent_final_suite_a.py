import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "agent_evals/final_suite_a_prompts.json"
RUBRIC = ROOT / "agent_evals/final_suite_a_rubric.json"
PROFILES = ROOT / "agent_evals/team_profiles.json"
OLD = ROOT / "agent_evals/behavioral_prompts.json"


class FinalSuiteABlindStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompt_doc = json.loads(PROMPTS.read_text(encoding="utf-8"))
        cls.rubric_doc = json.loads(RUBRIC.read_text(encoding="utf-8"))
        cls.prompts = cls.prompt_doc["cases"]
        cls.rubric = cls.rubric_doc["cases"]
        cls.agents = set(json.loads(PROFILES.read_text(encoding="utf-8"))["agents"])
        cls.old_ids = {c["id"] for c in json.loads(OLD.read_text(encoding="utf-8"))["cases"]}

    def test_exactly_eighteen_unique_fresh_cases(self):
        self.assertEqual(18, len(self.prompts))
        self.assertEqual(18, len(self.rubric))
        for cases in (self.prompts, self.rubric):
            ids = [c["id"] for c in cases]
            self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse({c["id"] for c in self.prompts} & self.old_ids)

    def test_prompts_are_blind(self):
        self.assertEqual({"cases"}, set(self.prompt_doc))
        for case in self.prompts:
            with self.subTest(case=case["id"]):
                self.assertEqual({"id", "prompt"}, set(case))
                self.assertIsInstance(case["id"], str)
                self.assertTrue(case["id"].strip())
                self.assertIsInstance(case["prompt"], str)
                self.assertTrue(case["prompt"].strip())
        raw = PROMPTS.read_text(encoding="utf-8")
        for field in ("expected_primary", "expected_reviewers", "critical", "must_do", "must_not"):
            self.assertNotIn('"' + field + '"', raw)

    def test_rubric_ids_and_fields(self):
        self.assertEqual({"cases"}, set(self.rubric_doc))
        self.assertEqual([c["id"] for c in self.prompts], [c["id"] for c in self.rubric])
        required = {"id", "expected_primary", "expected_reviewers", "critical", "must_do", "must_not"}
        for case in self.rubric:
            with self.subTest(case=case["id"]):
                self.assertEqual(required, set(case))
                self.assertIn(case["expected_primary"], self.agents)
                self.assertIs(type(case["critical"]), bool)
                self.assertTrue(case["expected_reviewers"])
                self.assertEqual(len(case["expected_reviewers"]), len(set(case["expected_reviewers"])))
                for reviewer in case["expected_reviewers"]:
                    self.assertIn(reviewer, self.agents)
                    self.assertNotEqual(reviewer, case["expected_primary"])
                for field in ("must_do", "must_not"):
                    self.assertIsInstance(case[field], list)
                    self.assertTrue(case[field])
                    self.assertTrue(all(isinstance(x, str) and x.strip() for x in case[field]))

    def test_critical_cases_have_independent_safety_review(self):
        for case in self.rubric:
            if case["critical"]:
                with self.subTest(case=case["id"]):
                    roles = set(case["expected_reviewers"]) | {case["expected_primary"]}
                    self.assertTrue(roles & {"qa_critic", "security_integrity"})


if __name__ == "__main__":
    unittest.main()
