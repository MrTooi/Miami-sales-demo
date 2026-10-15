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

    def test_trigger_is_owner_only_issue_comment_and_command_is_whole_body_exact(self):
        text = self.text()
        self.assertIn("issue_comment:", text)
        self.assertIn("permissions: {}", text)
        self.assertIn("github.event.issue.pull_request == null", text)
        self.assertIn("github.actor == github.repository_owner", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("startsWith(github.event.comment.body, '/agent-security-recover ')", text)
        self.assertIn("[[ \"$COMMENT_BODY\" =~ ^/agent-security-recover\\ [0-9]+\\ [0-9]+$ ]]", text)

    def test_permissions_are_read_only_except_issue_and_pr_evidence(self):
        text = self.text()
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertIn("issues: write", text)
        self.assertIn("pull-requests: write", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("actions: write", text)

    def test_recovery_requires_latest_exact_failed_security_stage_and_prior_successes(self):
        text = self.text()
        self.assertIn(".github/workflows/agent-executor.yml", text)
        self.assertIn("jobs?filter=latest", text)
        self.assertIn(".conclusion // empty", text)
        self.assertIn('"implement-task" and .conclusion == "success"', text)
        self.assertIn('"verify-task" and .conclusion == "success"', text)
        self.assertIn('"publish-review" and .conclusion == "failure"', text)
        self.assertIn("Run repository test command in no-write-token verification job", text)
        self.assertIn("Run read-only independent QA / Critic agent", text)
        self.assertIn("Verify QA reviewer left proposal unchanged", text)
        self.assertIn("Post QA review evidence", text)
        self.assertIn("Run read-only Security & Data Integrity reviewer", text)

    def test_actual_qa_json_is_recovered_and_gated_before_security(self):
        text = self.text()
        self.assertIn("qa-candidates.json", text)
        self.assertIn("github-actions[bot]", text)
        self.assertIn("fromjson?", text)
        self.assertIn('["findings","summary","tests","verdict"]', text)
        self.assertIn("test \"$(jq 'length' \"$RUNNER_TEMP/qa-candidates.json\")\" = '1'", text)
        self.assertIn('python -I -S "$RUNNER_TEMP/ledger-review-gate.py" "$QA_REVIEW_PATH"', text)
        self.assertLess(
            text.index('python -I -S "$RUNNER_TEMP/ledger-review-gate.py" "$QA_REVIEW_PATH"'),
            text.index("Run Security reviewer alone on a fresh hardened runner"),
        )

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

    def test_unvalidated_proposal_dependencies_are_not_installed(self):
        text = self.text()
        contract_index = text.index("Revalidate frozen contract, exact proposal, scope, QA verdict, and human authority")
        install_index = text.index("Install dependencies from validated source base")
        self.assertLess(contract_index, install_index)
        self.assertIn('python -m pip install -r "$RUNNER_TEMP/ledger-base-tree/requirements.txt"', text)
        before_contract = text[:contract_index]
        self.assertNotIn("pip install", before_contract)

    def test_security_reviewer_runs_once_with_schema_and_trusted_evidence_is_locked(self):
        text = self.text()
        self.assertEqual(text.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 1)
        self.assertEqual(text.count("permission-profile: ':read-only'"), 1)
        self.assertIn("Run Security reviewer alone on a fresh hardened runner", text)
        self.assertIn("output-schema-file: ${{ runner.temp }}/ledger-review-schema.json", text)
        self.assertIn("output-file: ${{ env.SECURITY_REVIEW_PATH }}", text)
        self.assertIn("ledger-recovery-evidence.sha256", text)
        self.assertIn("sudo chown -R root:root", text)
        self.assertIn("sudo chmod -R a-w", text)

    def test_integrity_must_pass_before_combined_gate_or_promotion(self):
        text = self.text()
        self.assertIn("id: integrity", text)
        self.assertIn("steps.source.outcome == 'success'", text)
        self.assertIn("steps.contract.outcome == 'success'", text)
        self.assertIn("steps.integrity.outcome == 'success'", text)
        self.assertIn("Evaluate combined QA and Security evidence with strict protected-main gate", text)
        self.assertIn('ledger-review-gate.py" "$QA_REVIEW_PATH" "$SECURITY_REVIEW_PATH"', text)
        promote = text.split("      - name: Promote preserved proposal to awaiting human review", 1)[1]
        promote = promote.split("      - name: Preserve blocked state", 1)[0]
        self.assertIn("steps.integrity.outcome == 'success'", promote)
        self.assertIn("steps.gate.outcome == 'success'", promote)

    def test_false_evidence_is_not_posted_after_validation_failure(self):
        text = self.text()
        evidence = text.split("      - name: Post validated Security recovery evidence", 1)[1]
        evidence = evidence.split("      - name: Promote preserved proposal", 1)[0]
        self.assertIn("steps.source.outcome == 'success'", evidence)
        self.assertIn("steps.contract.outcome == 'success'", evidence)
        self.assertIn("steps.integrity.outcome == 'success'", evidence)
        self.assertIn("actual QA verdict were revalidated successfully", evidence)

    def test_failed_integrity_or_gate_preserves_blocked_state(self):
        text = self.text()
        blocked = text.split("      - name: Preserve blocked state on failed validated recovery evidence", 1)[1]
        self.assertIn("always()", blocked)
        self.assertIn("steps.source.outcome == 'success'", blocked)
        self.assertIn("steps.contract.outcome == 'success'", blocked)
        self.assertIn("steps.integrity.outcome != 'success'", blocked)
        self.assertIn("steps.gate.outcome != 'success'", blocked)
        self.assertIn("agent:blocked", blocked)

    def test_recovery_rechecks_proposal_after_reviewer_and_never_merges_or_deploys(self):
        text = self.text()
        self.assertIn("Revalidate exact proposal and trusted evidence after Security attempt", text)
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
