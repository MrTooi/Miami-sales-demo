import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / ".github" / "workflows" / "agent-operator.yml"
EXECUTOR = ROOT / ".github" / "workflows" / "agent-executor.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"


class AgentOperatorWorkflowTests(unittest.TestCase):
    def test_workflow_is_scheduled_but_disabled_by_default(self):
        text = PLANNER.read_text(encoding="utf-8")
        self.assertIn("schedule:", text)
        self.assertIn("vars.LEDGER_AGENT_OPERATOR_ENABLED == 'true'", text)
        self.assertIn("workflow_dispatch:", text)

    def test_foundation_workflow_is_read_only(self):
        text = PLANNER.read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("issues: read", text)
        self.assertIn("pull-requests: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("issues: write", text)
        self.assertNotIn("pull-requests: write", text)

    def test_foundation_workflow_invokes_no_model_provider(self):
        text = PLANNER.read_text(encoding="utf-8").lower()
        self.assertNotIn("@claude", text)
        self.assertNotIn("anthropic", text)
        self.assertNotIn("openai_api_key", text)
        self.assertNotIn("codex", text)

    def test_scheduler_prevents_overlapping_runs_and_has_timeout(self):
        text = PLANNER.read_text(encoding="utf-8")
        self.assertIn("concurrency:", text)
        self.assertIn("group: ledger-agent-operator-${{ github.repository }}", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("timeout-minutes: 10", text)

    def test_executor_is_opt_in_and_has_bounded_runtime(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("vars.LEDGER_AGENT_EXECUTOR_ENABLED == 'true'", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("concurrency:", text)
        self.assertIn("timeout-minutes: 45", text)

    def test_executor_uses_pinned_codex_and_never_automatic_claude(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn(f"openai/codex-action@{CODEX_ACTION_SHA}", text)
        lowered = text.lower()
        self.assertNotIn("@claude", lowered)
        self.assertNotIn("anthropic", lowered)
        self.assertNotIn("claude-code-action", lowered)

    def test_executor_does_not_persist_checkout_credentials_into_model_workspace(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("persist-credentials: false", text)
        self.assertIn("permission-profile: ':workspace'", text)

    def test_executor_requires_scope_tests_and_independent_review_gate(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("python -m agent_operator.scope_guard", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("agent_operator/review_schema.json", text)
        self.assertIn("python -m agent_operator.review_gate", text)
        self.assertIn("agent:awaiting-review", text)
        self.assertIn("agent:blocked", text)

    def test_executor_never_auto_merges_or_deploys(self):
        text = EXECUTOR.read_text(encoding="utf-8").lower()
        self.assertNotIn("gh pr merge", text)
        self.assertNotIn("merge_pull_request", text)
        self.assertNotIn("deploy", "\n".join(line for line in text.splitlines() if line.strip().startswith("run:")))
        self.assertIn("--draft", text)


if __name__ == "__main__":
    unittest.main()
