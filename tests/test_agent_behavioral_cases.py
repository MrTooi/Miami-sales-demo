import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "agent_evals" / "behavioral_cases.json"
PROMPTS_PATH = ROOT / "agent_evals" / "behavioral_prompts.json"
PROFILES_PATH = ROOT / "agent_evals" / "team_profiles.json"


class AgentBehavioralCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
        cls.prompts = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))["cases"]
        cls.profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))["agents"]

    def test_behavioral_suite_has_broad_minimum_size(self):
        self.assertGreaterEqual(len(self.cases), 10)

    def test_case_ids_are_unique(self):
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_cases_have_actionable_expectations(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["prompt"].strip())
                self.assertTrue(case["must_do"])
                self.assertTrue(case["must_not"])

    def test_expected_agents_exist(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["expected_primary"], self.profiles)
                for reviewer in case["expected_reviewers"]:
                    self.assertIn(reviewer, self.profiles)

    def test_security_sensitive_cases_have_security_review(self):
        security_case_ids = {
            "integration-secret-hardcode",
            "destructive-database-request",
            "prompt-injection-in-source",
            "third-party-mcp-broad-access",
            "revenue-double-counting",
        }
        case_map = {case["id"]: case for case in self.cases}
        for case_id in security_case_ids:
            with self.subTest(case=case_id):
                self.assertIn(
                    "security_integrity",
                    case_map[case_id]["expected_reviewers"]
                    + [case_map[case_id]["expected_primary"]],
                )

    def test_blind_prompts_match_canonical_cases_without_rubric(self):
        canonical = {case["id"]: case["prompt"] for case in self.cases}
        blind = {case["id"]: case["prompt"] for case in self.prompts}
        self.assertEqual(canonical, blind)
        for prompt_case in self.prompts:
            self.assertEqual({"id", "prompt"}, set(prompt_case))


if __name__ == "__main__":
    unittest.main()
