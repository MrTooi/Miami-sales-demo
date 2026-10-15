import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / ".github" / "workflows" / "agent-operator.yml"
EXECUTOR = ROOT / ".github" / "workflows" / "agent-executor.yml"
EXECUTOR_TRIGGER = ROOT / ".github" / "workflows" / "agent-executor-trigger.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_ARTIFACT_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"


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

    def test_executor_is_opt_in_and_each_stage_has_bounded_runtime(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("vars.LEDGER_AGENT_EXECUTOR_ENABLED == 'true'", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("concurrency:", text)
        for job in (
            "claim-task:",
            "implement-task:",
            "verify-task:",
            "publish-task:",
            "qa-review:",
            "security-review:",
            "review-gate:",
            "fail-safe-cleanup:",
        ):
            self.assertIn(job, text)
        for timeout in (
            "timeout-minutes: 10",
            "timeout-minutes: 30",
            "timeout-minutes: 20",
            "timeout-minutes: 15",
            "timeout-minutes: 5",
        ):
            self.assertIn(timeout, text)

    def test_executor_owner_trigger_is_exact_owner_only_and_minimal(self):
        text = EXECUTOR_TRIGGER.read_text(encoding="utf-8")
        self.assertIn("issue_comment:", text)
        self.assertIn("permissions: {}", text)
        self.assertIn("github.event.issue.pull_request == null", text)
        self.assertIn("github.actor == github.repository_owner", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("github.event.comment.body == '/agent-run'", text)
        self.assertNotIn("contains(github.event.comment.body", text)
        self.assertIn("contains(github.event.issue.labels.*.name, 'agent:ready')", text)
        dispatch = text.split("  dispatch:", 1)[1]
        self.assertIn("actions: write", dispatch)
        self.assertIn("issues: read", dispatch)
        self.assertNotIn("contents: write", dispatch)
        self.assertNotIn("issues: write", dispatch)
        self.assertNotIn("pull-requests: write", dispatch)
        self.assertNotIn("actions/checkout", text)
        self.assertIn("gh issue list", text)
        self.assertIn("--label 'agent:ready'", text)
        self.assertIn("READY_COUNT", text)
        self.assertIn('"$READY_COUNT" != "1"', text)
        self.assertIn('"$READY_NUMBERS" != "$ISSUE_NUMBER"', text)
        self.assertIn("gh workflow run agent-executor.yml", text)
        self.assertIn("--ref main", text)

    def test_executor_uses_pinned_trusted_bot_opt_in_without_custom_allowlists(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertEqual(text.count("allow-bots: true"), 3)
        self.assertNotIn("allow-users:", text)
        self.assertNotIn("allow-bot-users:", text)

    def test_executor_event_surface_remains_manual_or_schedule_only(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        header = text.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", header)
        self.assertIn("schedule:", header)
        self.assertNotIn("issue_comment:", header)
        self.assertNotIn("pull_request:", header)
        self.assertNotIn("pull_request_target:", header)
        self.assertNotIn("repository_dispatch:", header)

    def test_executor_uses_pinned_actions_and_never_automatic_claude(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertEqual(text.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 3)
        self.assertIn(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", text)
        self.assertIn(f"actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}", text)
        lowered = text.lower()
        self.assertNotIn("@claude", lowered)
        self.assertNotIn("anthropic", lowered)
        self.assertNotIn("claude-code-action", lowered)

    def test_implementation_job_has_read_only_permissions_and_human_stop_recheck(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        implement = text.split("  implement-task:", 1)[1].split("  verify-task:", 1)[0]
        self.assertIn("contents: read", implement)
        self.assertIn("issues: read", implement)
        self.assertNotIn("contents: write", implement)
        self.assertNotIn("issues: write", implement)
        self.assertIn("persist-credentials: false", implement)
        self.assertIn("permission-profile: ':workspace'", implement)
        self.assertIn("ledger-implementation-tree.tar", implement)
        self.assertIn("Respect human stop before model execution", implement)
        self.assertIn("needs:human|agent:paused", implement)
        self.assertIn("agent:working", implement)
        self.assertLess(
            implement.index("Respect human stop before model execution"),
            implement.index("Run primary Codex implementation agent"),
        )

    def test_untrusted_implementation_is_verified_in_separate_no_write_job(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        verify = text.split("  verify-task:", 1)[1].split("  publish-task:", 1)[0]
        self.assertIn("contents: read", verify)
        self.assertNotIn("contents: write", verify)
        self.assertNotIn("OPENAI_API_KEY", verify)
        self.assertIn("Enforce frozen task scope from trusted base without model git state", verify)
        self.assertIn("agent_operator.scope_guard check", verify)
        self.assertIn("agent_operator.scope_guard apply", verify)
        self.assertIn("--allowed-paths-file", verify)
        self.assertIn("Lock trusted verification inputs before proposed code executes", verify)
        self.assertIn("sudo chown -R root:root", verify)
        self.assertIn("sudo chmod -R a-w", verify)
        self.assertIn("Run repository test command in no-write-token verification job", verify)
        self.assertIn("python -m unittest discover -s tests -v", verify)
        self.assertIn("Verify tests did not change the publishable proposal using locked trusted guard", verify)

    def test_publication_job_is_non_model_and_verifies_commit_before_push(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        publish = text.split("  publish-task:", 1)[1].split("  qa-review:", 1)[0]
        self.assertIn("contents: write", publish)
        self.assertIn("Re-verify frozen task scope independently before publication", publish)
        self.assertIn("Respect human stop before publication", publish)
        self.assertIn("Create clean publication branch and materialize verified files", publish)
        self.assertIn("Commit clean verified proposal locally", publish)
        self.assertIn("Verify committed tree exactly matches verified manifest", publish)
        self.assertIn("git archive HEAD", publish)
        self.assertIn("Push only the manifest-matched proposal branch", publish)
        self.assertIn("Freeze exact publication review context", publish)
        self.assertIn("ledger-review-context", publish)
        self.assertNotIn("openai/codex-action", publish)
        self.assertNotIn("OPENAI_API_KEY", publish)
        self.assertNotIn("python -m unittest discover", publish)

        stop_index = text.index("Respect human stop before publication")
        materialize_index = text.index("Create clean publication branch and materialize verified files")
        commit_index = text.index("Commit clean verified proposal locally")
        commit_verify_index = text.index("Verify committed tree exactly matches verified manifest")
        push_index = text.index("Push only the manifest-matched proposal branch")
        self.assertLess(stop_index, materialize_index)
        self.assertLess(commit_index, commit_verify_index)
        self.assertLess(commit_verify_index, push_index)

    def test_qa_and_security_run_in_distinct_fresh_jobs(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        qa = text.split("  qa-review:", 1)[1].split("  security-review:", 1)[0]
        security = text.split("  security-review:", 1)[1].split("  review-gate:", 1)[0]
        self.assertEqual(qa.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 1)
        self.assertEqual(security.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 1)
        self.assertIn("Run read-only independent QA / Critic agent on fresh runner", qa)
        self.assertIn("Run read-only Security and Data Integrity reviewer on separate fresh runner", security)
        self.assertIn("permission-profile: ':read-only'", qa)
        self.assertIn("permission-profile: ':read-only'", security)
        self.assertIn("allow-bots: true", qa)
        self.assertIn("allow-bots: true", security)
        self.assertNotIn("safety-strategy: read-only", qa)
        self.assertNotIn("safety-strategy: read-only", security)
        self.assertNotIn("safety-strategy: unsafe", qa)
        self.assertNotIn("safety-strategy: unsafe", security)
        self.assertIn("needs: [claim-task, publish-task]", qa)
        self.assertIn("needs: [claim-task, publish-task, qa-review]", security)
        self.assertIn("needs.qa-review.outputs.qa_passed == 'true'", security)

    def test_reviewer_jobs_have_no_repository_write_permissions(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        qa = text.split("  qa-review:", 1)[1].split("  security-review:", 1)[0]
        security = text.split("  security-review:", 1)[1].split("  review-gate:", 1)[0]
        for review in (qa, security):
            self.assertIn("contents: read", review)
            self.assertIn("issues: read", review)
            self.assertIn("pull-requests: read", review)
            self.assertNotIn("contents: write", review)
            self.assertNotIn("issues: write", review)
            self.assertNotIn("pull-requests: write", review)
            self.assertIn("persist-credentials: false", review)
            self.assertIn("needs:human|agent:paused", review)
            self.assertIn("agent:working", review)

    def test_reviewer_inputs_and_proposal_are_revalidated_before_and_after_each_model(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        qa = text.split("  qa-review:", 1)[1].split("  security-review:", 1)[0]
        security = text.split("  security-review:", 1)[1].split("  review-gate:", 1)[0]
        self.assertIn("Validate exact QA review context before model execution", qa)
        self.assertIn("Revalidate QA inputs and exact proposal after reviewer", qa)
        self.assertIn("ledger-qa-inputs.sha256", qa)
        self.assertIn("ledger-qa-pre-manifest.json", qa)
        self.assertIn("ledger-qa-post-manifest.json", qa)
        self.assertIn("Validate exact Security review context before model execution", security)
        self.assertIn("Revalidate Security inputs and exact proposal after reviewer", security)
        self.assertIn("ledger-security-inputs.sha256", security)
        self.assertIn("ledger-security-pre-manifest.json", security)
        self.assertIn("ledger-security-post-manifest.json", security)
        for review in (qa, security):
            self.assertIn('/git/ref/heads/$BRANCH', review)
            self.assertIn("scope_guard.py", review)
            self.assertIn("publish-manifest.json", review)
            self.assertIn("sudo chown -R root:root", review)
            self.assertIn("sudo chmod -R a-w", review)
            self.assertIn("ledger-frozen-base...HEAD", review)

    def test_reviewer_outputs_are_schema_backed_artifacts_and_locally_gated(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        qa = text.split("  qa-review:", 1)[1].split("  security-review:", 1)[0]
        security = text.split("  security-review:", 1)[1].split("  review-gate:", 1)[0]
        self.assertIn("output-schema-file:", qa)
        self.assertIn("output-schema-file:", security)
        self.assertIn("ledger-qa-review", qa)
        self.assertIn("ledger-security-review", security)
        self.assertIn("Evaluate QA verdict locally with trusted gate", qa)
        self.assertIn("Evaluate Security verdict locally with trusted gate", security)
        self.assertIn("agent_operator/review_gate.py", qa)
        self.assertIn("agent_operator/review_gate.py", security)

    def test_final_review_gate_is_non_model_and_only_trusted_job_changes_lifecycle(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        gate = text.split("  review-gate:", 1)[1].split("  fail-safe-cleanup:", 1)[0]
        qa = text.split("  qa-review:", 1)[1].split("  security-review:", 1)[0]
        security = text.split("  security-review:", 1)[1].split("  review-gate:", 1)[0]
        self.assertNotIn("openai/codex-action", gate)
        self.assertNotIn("OPENAI_API_KEY", gate)
        self.assertIn("contents: read", gate)
        self.assertIn("issues: write", gate)
        self.assertIn("pull-requests: write", gate)
        self.assertIn("Validate final review evidence against exact proposal and human authority", gate)
        self.assertIn("Evaluate exact reviewer artifacts with trusted final gate", gate)
        self.assertIn("ledger-qa-review", gate)
        self.assertIn("ledger-security-review", gate)
        self.assertIn("python -I -S", gate)
        self.assertIn("agent_operator/review_gate.py", gate)
        self.assertIn("agent:awaiting-review", gate)
        self.assertIn("agent:blocked", gate)
        self.assertNotIn("agent:awaiting-review", qa)
        self.assertNotIn("agent:awaiting-review", security)
        self.assertNotIn("issues: write", qa)
        self.assertNotIn("issues: write", security)

    def test_security_is_skipped_after_qa_rejection_to_avoid_duplicate_spend(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        security = text.split("  security-review:", 1)[1].split("  review-gate:", 1)[0]
        gate = text.split("  review-gate:", 1)[1].split("  fail-safe-cleanup:", 1)[0]
        self.assertIn("needs.qa-review.outputs.qa_passed == 'true'", security)
        self.assertIn("needs.qa-review.outputs.qa_passed != 'true'", gate)
        self.assertIn("QA_PASSED", gate)

    def test_task_and_prompt_are_artifact_frozen_before_model_execution(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        freeze_index = text.index("Freeze immutable task contract")
        upload_index = text.index("Upload immutable task contract")
        model_index = text.index("Run primary Codex implementation agent")
        self.assertLess(freeze_index, upload_index)
        self.assertLess(upload_index, model_index)
        self.assertIn("task_sha", text)
        self.assertIn("prompt_sha", text)
        self.assertGreaterEqual(text.count("ACTUAL_TASK_SHA"), 3)
        self.assertGreaterEqual(text.count("ACTUAL_PROMPT_SHA"), 3)
        self.assertIn("Verify task contract integrity before verification", text)
        self.assertIn("Verify immutable task contract again", text)
        self.assertGreaterEqual(text.count("ledger-task-contract/task.json"), 10)
        self.assertGreaterEqual(text.count("ledger-task-contract/prompt.md"), 6)

    def test_executor_uses_filesystem_scope_manifest_not_model_git_diff(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("Capture implementation filesystem without trusting its git metadata", text)
        self.assertIn("--exclude='./.git'", text)
        self.assertIn("ledger-change-manifest.json", text)
        self.assertIn("--allowed-paths-file", text)
        self.assertNotIn("scope_guard --repo", text)
        self.assertNotIn("--base-sha", text)

    def test_fail_safe_cleanup_is_separate_and_depends_on_final_gate(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        cleanup = text.split("  fail-safe-cleanup:", 1)[1]
        self.assertIn("review-gate", cleanup)
        self.assertIn("needs.review-gate.result != 'success'", cleanup)
        self.assertIn("always()", cleanup)
        self.assertIn("issues: write", cleanup)
        self.assertIn("gh issue edit", cleanup)
        self.assertIn("grep -qx 'needs:human'", cleanup)
        self.assertIn("preserving that state", cleanup)
        self.assertNotIn("for LABEL in agent:ready agent:claimed agent:working agent:awaiting-review needs:human", cleanup)
        self.assertNotIn("agent_operator", cleanup)
        self.assertNotIn("actions/checkout", cleanup)

    def test_executor_does_not_overclaim_model_influenced_test_evidence(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertNotIn("Full tests passed", text)
        self.assertIn("protected-branch CI and human review are still required before merge", text)

    def test_executor_job_configuration_does_not_use_runner_context_before_steps(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        for job_text in text.split("\n  ")[1:]:
            if "    steps:" not in job_text:
                continue
            before_steps = job_text.split("    steps:", 1)[0]
            self.assertNotIn("${{ runner.", before_steps)

    def test_executor_never_auto_merges_or_deploys(self):
        text = EXECUTOR.read_text(encoding="utf-8").lower()
        self.assertNotIn("gh pr merge", text)
        self.assertNotIn("merge_pull_request", text)
        self.assertIn("--draft", text)
        self.assertIn("agent:awaiting-review", text)
        self.assertIn("agent:blocked", text)


if __name__ == "__main__":
    unittest.main()
