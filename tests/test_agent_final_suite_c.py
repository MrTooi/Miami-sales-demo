import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLIND = ROOT / "agent_evals/final_suite_c_prompts.json"
RUBRIC = ROOT / "agent_evals/final_suite_c_rubric.json"
PROFILES = ROOT / "agent_evals/team_profiles.json"

class SuiteCStructuralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompts = json.loads(BLIND.read_text())["cases"]
        cls.rubric = json.loads(RUBRIC.read_text())["cases"]
        cls.agents = json.loads(PROFILES.read_text())["agents"]

    def test_exactly_eighteen_unique_cases(self):
        for cases in (self.prompts, self.rubric):
            ids = [c["id"] for c in cases]
            self.assertEqual(18, len(ids))
            self.assertEqual(18, len(set(ids)))

    def test_matching_ids(self):
        self.assertEqual({c["id"] for c in self.prompts},
                         {c["id"] for c in self.rubric})

    def test_blind_has_no_rubric_fields(self):
        for case in self.prompts:
            self.assertEqual({"id", "prompt"}, set(case))
            self.assertTrue(case["prompt"].strip())

    def test_rubric_complete_and_valid(self):
        expected = {"id", "expected_primary", "expected_reviewers",
                    "critical", "must_do", "must_not"}
        for case in self.rubric:
            self.assertEqual(expected, set(case))
            self.assertIn(case["expected_primary"], self.agents)
            self.assertIs(type(case["critical"]), bool)
            self.assertTrue(case["must_do"])
            self.assertTrue(case["must_not"])
            self.assertNotIn(case["expected_primary"], case["expected_reviewers"])
            for reviewer in case["expected_reviewers"]:
                self.assertIn(reviewer, self.agents)

if __name__ == "__main__":
    unittest.main()
