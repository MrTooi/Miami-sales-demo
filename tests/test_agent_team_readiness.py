import json
import unittest
from pathlib import Path

from agent_evals.evaluate_team import evaluate, summary


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "agent_evals"


def load(name):
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


class AgentTeamReadinessTests(unittest.TestCase):
    def setUp(self):
        self.benchmark = load("benchmark_cases.json")
        self.baseline = load("baseline_manifest.json")
        self.hardened = load("team_manifest.json")

    def test_benchmark_has_representative_cases(self):
        cases = self.benchmark["cases"]
        ids = {case["id"] for case in cases}
        self.assertGreaterEqual(len(cases), 20)
        for required in {
            "finance_bug_fix",
            "square_oauth_integration",
            "mobile_ui_flow",
            "market_research",
            "ci_failure",
            "production_release",
            "security_incident",
            "prompt_injection",
            "unfamiliar_task",
        }:
            self.assertIn(required, ids)

    def test_baseline_benchmark_detects_real_coverage_gaps(self):
        report = summary(evaluate(self.baseline, self.benchmark))
        self.assertEqual(12, report["passed"])
        self.assertEqual(20, report["total"])
        self.assertIn("mobile_ui_flow", report["failed_cases"])
        self.assertIn("production_release", report["failed_cases"])
        self.assertIn("unfamiliar_task", report["failed_cases"])

    def test_hardened_team_covers_all_structural_benchmark_cases(self):
        report = summary(evaluate(self.hardened, self.benchmark))
        self.assertEqual(report["total"], report["passed"], report)
        self.assertEqual([], report["failed_cases"])

    def test_hardened_team_stays_small(self):
        # More agents are not automatically better. Keep specialization bounded.
        agents = self.hardened["agents"]
        self.assertLessEqual(len(agents), 8)

    def test_manifest_agent_profiles_exist(self):
        for agent in self.hardened["agents"]:
            with self.subTest(agent=agent["id"]):
                self.assertTrue((ROOT / agent["path"]).is_file(), agent["path"])

    def test_hardened_team_has_independent_qa_and_security(self):
        agents = self.hardened["agents"]
        reviewers = [agent for agent in agents if agent["independent_reviewer"]]
        caps = {cap for agent in reviewers for cap in agent["capabilities"]}
        self.assertIn("independent_review", caps)
        self.assertIn("security_review", caps)

    def test_universal_execution_and_eval_skills_exist(self):
        self.assertTrue(
            (ROOT / ".github" / "skills" / "universal-task-execution" / "SKILL.md").is_file()
        )
        self.assertTrue(
            (ROOT / ".github" / "skills" / "agent-evaluation" / "SKILL.md").is_file()
        )


if __name__ == "__main__":
    unittest.main()
