import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / ".github" / "workflows" / "agent-publication-recovery.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
DOWNLOAD_ARTIFACT_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"


class AgentPublicationRecoveryWorkflowTests(unittest.TestCase):
    def text(self):
        return RECOVERY.read_text(encoding="utf-8")

    def test_recovery_is_manual_only_and_bounded(self):
        text = self.text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("source_run_id:", text)
        self.assertIn("issue_number:", text)
        self.assertIn("timeout-minutes: 25", text)
        self.assertIn("concurrency:", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_recovery_never_invokes_primary_implementation_model(self):
        text = self.text()
        self.assertNotIn("permission-profile: ':workspace'", text)
        self.assertNotIn("Run primary Codex implementation agent", text)
        self.assertNotIn("ledger-implementation-result", text)
        self.assertEqual(text.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 2)
        self.assertEqual(text.count("permission-profile: ':read-only'"), 2)

    def test_recovery_runs_only_from_protected_main_and_freezes_current_controls(self):
        text = self.text()
        self.assertIn("Publication recovery must be dispatched from protected main", text)
        self.assertIn("refs/heads/main", text)
        self.assertIn("WORKFLOW_SHA: ${{ github.sha }}", text)
        self.assertIn("agent_operator/recovery.py?ref=$WORKFLOW_SHA", text)
        self.assertIn("agent_operator/scope_guard.py?ref=$WORKFLOW_SHA", text)
        self.assertIn("agent_operator/review_gate.py?ref=$WORKFLOW_SHA", text)
        self.assertIn("agent_operator/review_schema.json?ref=$WORKFLOW_SHA", text)
        self.assertIn("ledger-recovery.py", text)
        self.assertIn("ledger-scope-guard.py", text)
        self.assertIn("ledger-review-gate.py", text)
        self.assertIn("ledger-review-schema.json", text)

    def test_recovery_requires_successful_source_implementation_and_verification(self):
        text = self.text()
        self.assertIn(".github/workflows/agent-executor.yml", text)
        self.assertIn('select(.name == "implement-task" and .conclusion == "success")', text)
        self.assertIn('select(.name == "verify-task" and .conclusion == "success")', text)
        self.assertIn("source run lacks successful implementation and verification evidence", text)
        self.assertIn("exactly one unexpired task artifact and one implementation artifact", text)
        self.assertGreaterEqual(text.count(f"actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}"), 2)
        self.assertGreaterEqual(text.count("run-id: ${{ inputs.source_run_id }}"), 2)
        self.assertGreaterEqual(text.count("github-token: ${{ github.token }}"), 2)

    def test_recovery_derives_branch_from_frozen_contract(self):
        text = self.text()
        self.assertIn('EXPECTED_BRANCH="agent/issue-$REQUESTED_ISSUE-$SOURCE_RUN_ID"', text)
        self.assertIn("frozen task branch does not match deterministic source-run branch", text)
        self.assertIn("ledger-task-contract/task.json", text)

    def test_current_trusted_scope_guard_rechecks_frozen_proposal(self):
        text = self.text()
        self.assertIn("Independently reconstruct expected verified manifest with current trusted guard", text)
        self.assertGreaterEqual(text.count('python -I -S "$RUNNER_TEMP/ledger-scope-guard.py"'), 5)
        self.assertNotIn("python -m agent_operator.scope_guard", text)

    def test_existing_branch_is_reused_only_after_exact_manifest_match(self):
        text = self.text()
        self.assertIn("git ls-remote --exit-code --heads", text)
        self.assertIn("COMMIT_COUNT", text)
        self.assertIn("PARENT_SHA", text)
        self.assertIn("ledger-remote-manifest.json", text)
        self.assertIn('python -I -S "$RUNNER_TEMP/ledger-recovery.py" compare-manifests', text)
        self.assertIn('echo "action=reuse"', text)
        self.assertIn('echo "action=push"', text)
        self.assertNotIn("--force", text)
        self.assertNotIn("push -f", text)

    def test_existing_draft_pr_is_reused_instead_of_duplicated(self):
        text = self.text()
        self.assertIn("gh pr list", text)
        self.assertIn('python -I -S "$RUNNER_TEMP/ledger-recovery.py" pr-action', text)
        self.assertIn("if [ \"$ACTION\" = 'create' ]", text)
        self.assertIn("gh pr create --draft", text)

    def test_human_stop_is_checked_before_recovery_reviewers_and_promotion(self):
        text = self.text()
        self.assertGreaterEqual(text.count("needs:human|agent:paused"), 4)
        self.assertGreaterEqual(text.count("agent:working"), 2)
        self.assertLess(
            text.index("Respect human stop before recovery"),
            text.index("Reuse matching proposal branch or publish once when absent"),
        )
        self.assertLess(
            text.index("Respect human stop before reviewer model calls"),
            text.index("Run read-only independent QA recovery reviewer"),
        )
        self.assertIn("Human stop became active; refusing lifecycle promotion", text)

    def test_reviewers_are_read_only_and_current_review_gate_remains_human_gated(self):
        text = self.text()
        self.assertIn("Run read-only independent QA recovery reviewer", text)
        self.assertIn("Run read-only Security & Data Integrity recovery reviewer", text)
        self.assertIn("Evaluate independent recovery review gate using current protected-main code", text)
        self.assertIn('python -I -S "$RUNNER_TEMP/ledger-review-gate.py"', text)
        self.assertIn("agent:awaiting-review", text)
        self.assertIn("agent:blocked", text)
        self.assertNotIn("gh pr merge", text)
        self.assertNotIn("merge_pull_request", text)

    def test_fail_safe_recovery_preserves_human_intervention(self):
        text = self.text()
        cleanup = text.split("  fail-safe-recovery:", 1)[1]
        self.assertIn("always()", cleanup)
        self.assertIn("needs:human|agent:paused", cleanup)
        self.assertIn("agent:blocked", cleanup)
        self.assertNotIn("actions/checkout", cleanup)
        self.assertNotIn("agent_operator", cleanup)


if __name__ == "__main__":
    unittest.main()
