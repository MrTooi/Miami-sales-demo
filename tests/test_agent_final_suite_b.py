import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((ROOT / "agent_evals" / name).read_text(encoding="utf-8"))["cases"]

class SuiteBStructureTests(unittest.TestCase):
    def test_blind_separation_and_matching_ids(self):
        blind = load("final_suite_b_prompts.json")
        judge = load("final_suite_b_rubric.json")
        self.assertEqual(len(blind), len(judge))
        self.assertEqual(len(blind), 18)
        ids = [x["id"] for x in blind]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {x["id"] for x in judge})
        for case in blind:
            self.assertEqual(set(case), {"id", "prompt"})
            self.assertTrue(case["prompt"].strip())
            for key in ("expected_primary", "expected_reviewers", "critical", "must_do", "must_not"):
                self.assertNotIn('"' + key + '"', case["prompt"])

    def test_rubric_structure_and_agents(self):
        judge = load("final_suite_b_rubric.json")
        agents = json.loads((ROOT / "agent_evals/team_profiles.json").read_text())["agents"]
        expected = {"id", "expected_primary", "expected_reviewers", "critical", "must_do", "must_not"}
        for case in judge:
            self.assertEqual(set(case), expected)
            self.assertIn(case["expected_primary"], agents)
            self.assertIs(type(case["critical"]), bool)
            self.assertTrue(case["must_do"] and case["must_not"])
            self.assertTrue(case["expected_reviewers"])
            self.assertNotIn(case["expected_primary"], case["expected_reviewers"])
            for reviewer in case["expected_reviewers"]:
                self.assertIn(reviewer, agents)
            if case["critical"]:
                self.assertIn("security_integrity", [case["expected_primary"], *case["expected_reviewers"]])

    def test_not_prior_suite_copies(self):
        prior = load("behavioral_prompts.json")
        current = load("final_suite_b_prompts.json")
        self.assertFalse({x["id"] for x in prior} & {x["id"] for x in current})
        old = {x["prompt"].casefold() for x in prior}
        self.assertTrue(all(x["prompt"].casefold() not in old for x in current))
