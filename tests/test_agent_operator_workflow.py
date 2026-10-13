import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-operator.yml"


class AgentOperatorWorkflowTests(unittest.TestCase):
    def test_workflow_is_scheduled_but_disabled_by_default(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("schedule:", text)
        self.assertIn("vars.LEDGER_AGENT_OPERATOR_ENABLED == 'true'", text)
        self.assertIn("workflow_dispatch:", text)

    def test_foundation_workflow_is_read_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("issues: read", text)
        self.assertIn("pull-requests: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("issues: write", text)
        self.assertNotIn("pull-requests: write", text)

    def test_foundation_workflow_invokes_no_model_provider(self):
        text = WORKFLOW.read_text(encoding="utf-8").lower()
        self.assertNotIn("@claude", text)
        self.assertNotIn("anthropic", text)
        self.assertNotIn("openai_api_key", text)
        self.assertNotIn("codex", text)


if __name__ == "__main__":
    unittest.main()
