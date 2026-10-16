import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-final-readiness-scheduled.yml"

CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_ARTIFACT_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"


class FinalScheduledReadinessWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_only_and_no_manual_or_product_trigger(self):
        self.assertIn("schedule:", self.text)
        self.assertIn("cron: '43 * * * *'", self.text)
        self.assertNotIn("workflow_dispatch:", self.text)
        self.assertNotIn("issue_comment:", self.text)
        self.assertNotIn("pull_request:", self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_selects_a_b_c_from_prior_successes_not_run_number(self):
        self.assertIn("status=success", self.text)
        self.assertIn("SUCCESS_COUNT", self.text)
        self.assertIn('0) SUITE="a"', self.text)
        self.assertIn('1) SUITE="b"', self.text)
        self.assertIn('2) SUITE="c"', self.text)
        self.assertNotIn("github.run_number <=", self.text)
        self.assertIn("refusing blind retry on unchanged failed state", self.text)

    def test_permissions_are_read_only_and_no_repo_write_permission_exists(self):
        self.assertIn("permissions: {}", self.text)
        for forbidden in (
            "contents: write",
            "issues: write",
            "pull-requests: write",
            "actions: write",
            "id-token: write",
            "deployments: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)
        self.assertIn("actions: read", self.text)
        self.assertIn("contents: read", self.text)

    def test_exactly_two_read_only_model_calls_and_no_untrusted_retry_loop(self):
        self.assertEqual(self.text.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 2)
        self.assertEqual(self.text.count("permission-profile: ':read-only'"), 2)
        self.assertEqual(self.text.count("safety-strategy: drop-sudo"), 2)
        self.assertEqual(self.text.count("allow-bots: true"), 2)
        self.assertNotIn("continue-on-error: true", self.text)
        self.assertNotIn("max-attempts", self.text)
        self.assertNotIn("rerun", self.text.lower())

    def test_blind_and_judge_model_jobs_never_checkout_repository(self):
        blind_start = self.text.index("  blind-pass:")
        judge_prep_start = self.text.index("  prepare-judge:")
        judge_start = self.text.index("  judge-pass:")
        final_start = self.text.index("  finalize-evidence:")
        blind_section = self.text[blind_start:judge_prep_start]
        judge_section = self.text[judge_start:final_start]
        self.assertNotIn("actions/checkout@", blind_section)
        self.assertNotIn("actions/checkout@", judge_section)
        self.assertIn("agent-final-blind-input-", blind_section)
        self.assertIn("agent-final-judge-input-", judge_section)

    def test_codex_is_last_step_in_each_model_job(self):
        blind_start = self.text.index("  blind-pass:")
        judge_prep_start = self.text.index("  prepare-judge:")
        judge_start = self.text.index("  judge-pass:")
        final_start = self.text.index("  finalize-evidence:")
        blind_section = self.text[blind_start:judge_prep_start]
        judge_section = self.text[judge_start:final_start]
        self.assertTrue(blind_section.rstrip().endswith("model: ${{ vars.LEDGER_CODEX_MODEL }}"))
        self.assertTrue(judge_section.rstrip().endswith("model: ${{ vars.LEDGER_CODEX_MODEL }}"))

    def test_judge_is_separate_and_finalization_is_deterministic(self):
        self.assertIn("scheduled_readiness prepare-judge", self.text)
        self.assertIn("judge_output_schema.json", self.text)
        self.assertIn("scheduled_readiness finalize", self.text)
        self.assertLess(self.text.index("  blind-pass:"), self.text.index("  prepare-judge:"))
        self.assertLess(self.text.index("  prepare-judge:"), self.text.index("  judge-pass:"))

    def test_evidence_is_bound_and_uploaded_fail_closed(self):
        for token in (
            "GITHUB_EVENT_NAME",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_REF",
            "GITHUB_SHA",
            "source_prompts_sha256",
            "source_rubric_sha256",
            "blind_output_sha256",
            "judge_output_sha256",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text)
        self.assertIn("if-no-files-found: error", self.text)
        self.assertIn("Enforce suite readiness after evidence upload", self.text)

    def test_pinned_actions(self):
        for action, sha in (
            ("actions/checkout", CHECKOUT_SHA),
            ("actions/setup-python", SETUP_PYTHON_SHA),
            ("actions/upload-artifact", UPLOAD_ARTIFACT_SHA),
            ("actions/download-artifact", DOWNLOAD_ARTIFACT_SHA),
        ):
            with self.subTest(action=action):
                self.assertIn(f"{action}@{sha}", self.text)


if __name__ == "__main__":
    unittest.main()
