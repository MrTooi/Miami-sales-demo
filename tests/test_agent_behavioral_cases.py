import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "agent_evals" / "behavioral_cases.json"
PROFILES_PATH = ROOT / "agent_evals" / "team_profiles.json"


class AgentBehavioralCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
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
                self.assertIn("security_integrity", case_map[case_id]["expected_reviewers"] + [case_map[case_id]["expected_primary"]])


if __name__ == "__main__":
    unittest.main()
