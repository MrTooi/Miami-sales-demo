import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / ".github" / "workflows" / "agent-publication-recovery.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
DOWNLOAD_ARTIFACT_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"


class AgentPublicationRecoveryWorkflowTests(unittest.TestCase):
    def text(self):
        return RECOVERY.read_text(encoding="utf-8")

    def test_recovery_is_manual_only_bounded_and_has_separate_verification(self):
        text = self.text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("source_run_id:", text)
        self.assertIn("issue_number:", text)
        self.assertIn("verify-recovery-source:", text)
        self.assertIn("recover-publish-review:", text)
        self.assertIn("fail-safe-recovery:", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_read_only_verification_job_has_no_write_or_model_secret(self):
        text = self.text()
        verify = text.split("  verify-recovery-source:", 1)[1].split("  recover-publish-review:", 1)[0]
        self.assertIn("contents: read", verify)
        self.assertIn("issues: read", verify)
        self.assertNotIn("contents: write", verify)
        self.assertNotIn("issues: write", verify)
        self.assertNotIn("OPENAI_API_KEY", verify)
        self.assertIn("Run repository tests in read-only recovery verification job", verify)
        self.assertIn("python -m unittest discover -s tests -v", verify)
        self.assertIn("git write-tree", verify)
        self.assertIn(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", verify)

    def test_recovery_never_invokes_primary_implementation_model(self):
        text = self.text()
        self.assertNotIn("permission-profile: ':workspace'", text)
        self.assertNotIn("Run primary Codex implementation agent", text)
        self.assertNotIn("ledger-implementation-result", text)
        self.assertEqual(text.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 2)
        self.assertEqual(text.count("permission-profile: ':read-only'"), 2)

    def test_recovery_runs_from_main_and_freezes_current_controls_by_sha(self):
        text = self.text()
        self.assertGreaterEqual(text.count("refs/heads/main"), 2)
        self.assertGreaterEqual(text.count("WORKFLOW_SHA: ${{ github.sha }}"), 2)
        for path in (
            "agent_operator/recovery.py",
            "agent_operator/scope_guard.py",
            "agent_operator/review_gate.py",
            "agent_operator/review_schema.json",
        ):
            self.assertIn(f"{path}?ref=$WORKFLOW_SHA", text)
        self.assertGreaterEqual(text.count("ledger-recovery-controls.sha256"), 4)
        self.assertGreaterEqual(text.count("sha256sum -c ledger-recovery-controls.sha256"), 3)

    def test_source_run_and_artifacts_are_strictly_validated(self):
        text = self.text()
        self.assertIn(".github/workflows/agent-executor.yml", text)
        self.assertIn("SOURCE_BRANCH", text)
        self.assertIn("SOURCE_STATUS", text)
        self.assertIn("workflow_dispatch", text)
        self.assertIn("schedule", text)
        self.assertIn('select(.name == "implement-task" and .conclusion == "success")', text)
        self.assertIn("exactly one unexpired task artifact and one implementation artifact", text)
        self.assertIn("task_artifact_id", text)
        self.assertIn("implementation_artifact_id", text)
        self.assertIn("task_artifact_digest", text)
        self.assertIn("implementation_artifact_digest", text)
        self.assertGreaterEqual(text.count(f"actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}"), 4)

    def test_contract_metadata_or_strict_legacy_branch_derives_base(self):
        text = self.text()
        self.assertIn("contract-metadata.json", text)
        self.assertIn("META_RUN", text)
        self.assertIn("META_BASE", text)
        self.assertIn("META_TASK", text)
        self.assertIn("META_PROMPT", text)
        self.assertIn("legacy source run has no base metadata", text)
        self.assertIn("legacy source proposal is not a single commit directly above source head", text)
        self.assertIn("git merge-base --is-ancestor", text)
        self.assertIn('EXPECTED_BRANCH="agent/issue-$REQUESTED_ISSUE-$SOURCE_RUN_ID"', text)

    def test_existing_branch_reuse_requires_exact_git_tree_and_base(self):
        text = self.text()
        self.assertIn("REMOTE_TREE", text)
        self.assertIn("PARENT_SHA", text)
        self.assertIn("COMMIT_COUNT", text)
        self.assertIn("branch-action", text)
        self.assertIn("--expected-tree", text)
        self.assertIn("--remote-tree", text)
        self.assertNotIn("--force", text)
        self.assertNotIn("push -f", text)

    def test_pr_reuse_is_same_repo_main_and_exact_reviewed_sha(self):
        text = self.text()
        for field in (
            "isCrossRepository",
            "headRepositoryOwner",
            "baseRefName",
            "headRefOid",
        ):
            self.assertIn(field, text)
        self.assertIn("--expected-head", text)
        self.assertIn("--expected-owner", text)
        self.assertIn("--expected-base main", text)
        self.assertIn("a previous PR for this proposal branch was closed", text)
        self.assertIn("gh pr create --draft", text)

    def test_remote_and_pr_sha_are_rechecked_around_reviews_and_promotion(self):
        text = self.text()
        self.assertGreaterEqual(text.count('git ls-remote origin "refs/heads/$BRANCH"'), 4)
        self.assertGreaterEqual(text.count("gh pr view \"$PR_URL\" --json headRefOid"), 4)
        self.assertGreaterEqual(text.count("REVIEWED_SHA"), 15)
        self.assertIn("Reviewed proposal commit", text)
        self.assertIn("Reviewed commit:", text)
        self.assertIn("exact commit", text)

    def test_recovery_always_runs_both_read_only_reviewers(self):
        text = self.text()
        self.assertIn("Run read-only independent QA recovery reviewer", text)
        self.assertIn("Run read-only Security & Data Integrity recovery reviewer", text)
        self.assertNotIn("SECURITY_REQUIRED", text)
        self.assertIn("Evaluate independent recovery review gate using frozen protected-main code", text)
        self.assertIn('"$QA_REVIEW_PATH" "$SECURITY_REVIEW_PATH"', text)

    def test_human_stop_is_checked_before_verification_publication_and_promotion(self):
        text = self.text()
        self.assertGreaterEqual(text.count("needs:human|agent:paused"), 5)
        self.assertIn("Respect human stop before recovery verification", text)
        self.assertIn("Respect human stop before branch publication", text)
        self.assertIn("Recheck human stop and exact remote/PR commit before reviewers", text)
        self.assertIn("Human stop raced lifecycle promotion", text)

    def test_fail_safe_only_mutates_a_validated_contract_issue(self):
        text = self.text()
        cleanup = text.split("  fail-safe-recovery:", 1)[1]
        self.assertIn("needs.verify-recovery-source.outputs.contract_valid == 'true'", cleanup)
        self.assertIn("needs.verify-recovery-source.outputs.issue_number", cleanup)
        self.assertIn("needs:human|agent:paused", cleanup)
        self.assertIn("agent:blocked", cleanup)
        self.assertNotIn("actions/checkout", cleanup)
        self.assertNotIn("agent_operator", cleanup)

    def test_recovery_never_merges_or_deploys(self):
        text = self.text().lower()
        self.assertNotIn("gh pr merge", text)
        self.assertNotIn("merge_pull_request", text)
        self.assertIn("--draft", text)
        self.assertIn("protected-branch ci and human merge review", text)


if __name__ == "__main__":
    unittest.main()
