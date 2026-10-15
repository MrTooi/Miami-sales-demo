import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-readiness-scheduled-evidence.yml"

CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"


class ScheduledReadinessWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_is_schedule_only_and_capped_at_three_evidence_runs(self):
        self.assertIn("schedule:", self.text)
        self.assertIn("cron: '*/5 * * * *'", self.text)
        self.assertNotIn("workflow_dispatch:", self.text)
        self.assertIn("github.event_name == 'schedule' && github.run_number <= 3", self.text)

    def test_has_read_only_repository_permissions(self):
        self.assertIn("permissions:\n  contents: read", self.text)
        for forbidden in (
            "contents: write",
            "issues: write",
            "pull-requests: write",
            "actions: write",
            "id-token: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_never_uses_model_tokens_or_repository_secrets(self):
        lowered = self.text.lower()
        for forbidden in (
            "openai_api_key",
            "anthropic",
            "codex-action",
            "@claude",
            "secrets.",
            "agent-executor.yml",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_runs_agent_readiness_tests_and_fails_before_evidence_on_failure(self):
        command = "python -m unittest discover -s tests -p 'test_agent_*.py' -v"
        self.assertIn(command, self.text)
        self.assertLess(
            self.text.index("Run deterministic Agent OS readiness tests"),
            self.text.index("Build immutable run evidence"),
        )
        self.assertLess(
            self.text.index("Build immutable run evidence"),
            self.text.index("Upload scheduled readiness evidence"),
        )

    def test_uses_pinned_actions_and_fail_closed_artifact_upload(self):
        self.assertIn(f"actions/checkout@{CHECKOUT_SHA}", self.text)
        self.assertIn(f"actions/setup-python@{SETUP_PYTHON_SHA}", self.text)
        self.assertIn(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", self.text)
        self.assertIn("if-no-files-found: error", self.text)
        self.assertIn("retention-days: 7", self.text)

    def test_evidence_binds_run_to_commit_and_event(self):
        for field in (
            '"event": "GITHUB_EVENT_NAME"',
            '"run_id": "GITHUB_RUN_ID"',
            '"run_attempt": "GITHUB_RUN_ATTEMPT"',
            '"run_number": "GITHUB_RUN_NUMBER"',
            '"sha": "GITHUB_SHA"',
            '"ref": "GITHUB_REF"',
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.text)


if __name__ == "__main__":
    unittest.main()
