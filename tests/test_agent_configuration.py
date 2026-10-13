import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".github" / "agents"
SKILL_DIR = ROOT / ".github" / "skills"

EXPECTED_AGENTS = {
    "orchestrator.agent.md",
    "backend.agent.md",
    "integrations.agent.md",
    "qa-critic.agent.md",
    "security-integrity.agent.md",
    "research-product.agent.md",
    "frontend-ux.agent.md",
    "generalist.agent.md",
}

EXPECTED_SKILLS = {
    "ai-team-orchestration",
    "financial-integrity",
    "opportunity-validation",
    "quality-gate",
    "agent-governance",
    "general-task-execution",
    "agent-evaluation",
}


def frontmatter(text: str) -> str:
    match = re.search(r"(?:^|\n)---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def frontmatter_value(block: str, key: str):
    match = re.search(rf"^{re.escape(key)}:\s*['\"]?(.*?)['\"]?\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else None


class AgentConfigurationTests(unittest.TestCase):
    def test_durable_ai_context_files_exist(self):
        self.assertTrue((ROOT / "AGENTS.md").is_file())
        self.assertTrue((ROOT / "PROJECT_BRIEF.md").is_file())
        self.assertTrue((ROOT / ".github" / "copilot-instructions.md").is_file())

    def test_expected_agent_profiles_exist(self):
        names = {path.name for path in AGENT_DIR.glob("*.agent.md")}
        self.assertTrue(EXPECTED_AGENTS.issubset(names), EXPECTED_AGENTS - names)

    def test_agent_profiles_have_name_and_description(self):
        for path in AGENT_DIR.glob("*.agent.md"):
            with self.subTest(agent=path.name):
                block = frontmatter(path.read_text(encoding="utf-8"))
                self.assertTrue(block, f"{path} is missing YAML frontmatter")
                self.assertTrue(frontmatter_value(block, "name"), f"{path} is missing name")
                self.assertTrue(frontmatter_value(block, "description"), f"{path} is missing description")

    def test_expected_skills_exist_and_are_well_formed(self):
        for skill_name in EXPECTED_SKILLS:
            with self.subTest(skill=skill_name):
                skill_file = SKILL_DIR / skill_name / "SKILL.md"
                self.assertTrue(skill_file.is_file(), f"Missing {skill_file}")
                block = frontmatter(skill_file.read_text(encoding="utf-8"))
                self.assertTrue(block, f"{skill_file} is missing YAML frontmatter")
                self.assertEqual(skill_name, frontmatter_value(block, "name"))
                self.assertTrue(frontmatter_value(block, "description"))

    def test_agent_benchmark_assets_exist(self):
        self.assertTrue((ROOT / "agent_evals" / "team_profiles.json").is_file())
        self.assertTrue((ROOT / "agent_evals" / "scenarios.json").is_file())
        self.assertTrue((ROOT / "agent_evals" / "benchmark.py").is_file())

    def test_cross_source_settlement_routes_to_integrations_primary(self):
        instructions = (ROOT / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        integration_profile = (AGENT_DIR / "integrations.agent.md").read_text(encoding="utf-8")
        self.assertIn("Integrations Engineer as primary", instructions)
        self.assertIn("Cross-source payment-provider settlement and reconciliation", instructions)
        self.assertIn("payment sale -> provider fee -> provider payout -> bank deposit", integration_profile)
        self.assertIn("Integrations is the **primary owner**", integration_profile)


if __name__ == "__main__":
    unittest.main()
