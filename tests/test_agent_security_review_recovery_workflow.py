import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-security-review-recovery.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
DOWNLOAD_ARTIFACT_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"


class AgentSecurityReviewRecoveryWorkflowTests(unittest.TestCase):
    def text(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_trigger_is_owner_only_issue_comment_and_not_pr(self):
        text = self.text()
        self.assertIn("issue_comment:", text)
        self.assertIn("permissions: {}", text)
        self.assertIn("github.event.issue.pull_request == null", text)
        self.assertIn("github.actor == github.repository_owner", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("startsWith(github.event.comment.body, '/agent-security-recover ')", text)
        self.assertIn("^/agent-security-recover [0-9]+ [0-9]+$", text)

    def test_permissions_are_read_only_except_issue_and_pr_evidence(self):
        text = self.text()
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertIn("issues: write", text)
        self.assertIn("pull-requests: write", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("actions: write", text)

    def test_recovery_requires_exact_failed_security_stage_and_prior_successes(self):
        text = self.text()
        self.assertIn(".github/workflows/agent-executor.yml", text)
        self.assertIn('"implement-task" and .conclusion == "success"', text)
        self.assertIn('"verify-task" and .conclusion == "success"', text)
        self.assertIn("Run repository test command in no-write-token verification job", text)
        self.assertIn("Run read-only independent QA / Critic agent", text)
        self.assertIn("Verify QA reviewer left proposal unchanged", text)
        self.assertIn("Post QA review evidence", text)
        self.assertIn("Run read-only Security & Data Integrity reviewer", text)
        self.assertIn('.conclusion == "failure"', text)

    def test_frozen_contract_and_exact_draft_proposal_are_revalidated(self):
        text = self.text()
        self.assertIn(f"actions/checkout@{CHECKOUT_SHA}", text)
        self.assertIn(f"actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}", text)
        self.assertIn("ledger-task-contract", text)
        self.assertIn('test "$(git rev-parse HEAD^)" = "$SOURCE_HEAD"', text)
        self.assertIn('test "$BRANCH" = "agent/issue-$ISSUE_NUMBER-$SOURCE_RUN_ID"', text)
        self.assertIn("ledger-scope-guard.py", text)
        self.assertIn("--allowed-paths-file", text)
        self.assertIn("ledger-preserved-manifest.json", text)
        self.assertIn("isDraft", text)
        self.assertIn("agent:blocked", text)
        self.assertIn("needs:human|agent:paused", text)

    def test_security_reviewer_runs_once_on_fresh_job_with_schema(self):
        text = self.text()
        self.assertEqual(text.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 1)
        self.assertEqual(text.count("permission-profile: ':read-only'"), 1)
        self.assertIn("Run Security reviewer alone on a fresh hardened runner", text)
        self.assertIn("output-schema-file: ${{ runner.temp }}/ledger-review-schema.json", text)
        self.assertIn("output-file: ${{ env.SECURITY_REVIEW_PATH }}", text)
        self.assertIn("Evaluate Security evidence with strict protected-main gate", text)
        self.assertIn("ledger-review-gate.py", text)

    def test_recovery_rechecks_proposal_after_reviewer_and_never_merges(self):
        text = self.text()
        self.assertIn("Revalidate exact proposal and trusted controls after Security attempt", text)
        self.assertIn("ledger-after-security.json", text)
        self.assertIn("cmp -s", text)
        self.assertIn("agent:awaiting-review", text)
        self.assertIn("Draft PR #$PR_NUMBER remains unmerged", text)
        lowered = text.lower()
        self.assertNotIn("gh pr merge", lowered)
        self.assertNotIn("merge_pull_request", lowered)
        self.assertNotIn("deploy", lowered)


if __name__ == "__main__":
    unittest.main()
