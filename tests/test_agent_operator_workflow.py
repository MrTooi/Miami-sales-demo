import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / ".github" / "workflows" / "agent-operator.yml"
EXECUTOR = ROOT / ".github" / "workflows" / "agent-executor.yml"
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
        for job in ("claim-task:", "implement-task:", "verify-task:", "publish-review:", "fail-safe-cleanup:"):
            self.assertIn(job, text)
        for timeout in ("timeout-minutes: 10", "timeout-minutes: 30", "timeout-minutes: 20", "timeout-minutes: 25", "timeout-minutes: 5"):
            self.assertIn(timeout, text)

    def test_executor_uses_pinned_actions_and_never_automatic_claude(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn(f"openai/codex-action@{CODEX_ACTION_SHA}", text)
        self.assertIn(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", text)
        self.assertIn(f"actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}", text)
        lowered = text.lower()
        self.assertNotIn("@claude", lowered)
        self.assertNotIn("anthropic", lowered)
        self.assertNotIn("claude-code-action", lowered)

    def test_implementation_job_has_read_only_repository_permission_and_no_persisted_credentials(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        implement = text.split("  implement-task:", 1)[1].split("  verify-task:", 1)[0]
        self.assertIn("contents: read", implement)
        self.assertNotIn("contents: write", implement)
        self.assertNotIn("issues: write", implement)
        self.assertIn("persist-credentials: false", implement)
        self.assertIn("permission-profile: ':workspace'", implement)
        self.assertIn("ledger-implementation-tree.tar", implement)

    def test_untrusted_implementation_is_verified_in_separate_no_write_job(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        verify = text.split("  verify-task:", 1)[1].split("  publish-review:", 1)[0]
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

    def test_publish_job_rebuilds_commit_and_verifies_commit_tree_before_push(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        publish = text.split("  publish-review:", 1)[1].split("  fail-safe-cleanup:", 1)[0]
        self.assertIn("contents: write", publish)
        self.assertIn("Re-verify frozen task scope independently before publication", publish)
        self.assertIn("--allowed-paths-file", publish)
        self.assertIn("Create clean publication branch and materialize verified files", publish)
        self.assertIn("Commit clean verified proposal locally", publish)
        self.assertIn("Verify committed tree exactly matches verified manifest", publish)
        self.assertIn("git archive HEAD", publish)
        self.assertIn("ledger-commit-manifest.json", publish)
        self.assertIn("Push only the manifest-matched proposal branch", publish)
        self.assertIn("core.hooksPath=/dev/null", publish)
        self.assertNotIn("python -m unittest discover", publish)

        commit_index = text.index("Commit clean verified proposal locally")
        commit_verify_index = text.index("Verify committed tree exactly matches verified manifest")
        push_index = text.index("Push only the manifest-matched proposal branch")
        self.assertLess(commit_index, commit_verify_index)
        self.assertLess(commit_verify_index, push_index)

        verify_index = text.index("  verify-task:")
        publish_index = text.index("  publish-review:")
        self.assertLess(verify_index, publish_index)

    def test_reviewers_are_read_only_and_review_gate_uses_trusted_base(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("permission-profile: ':read-only'"), 2)
        self.assertGreaterEqual(text.count("working-directory: ${{ github.workspace }}"), 3)
        self.assertIn("Evaluate independent review gate from trusted base", text)
        self.assertIn('cd "$RUNNER_TEMP/ledger-base-tree"', text)
        self.assertIn("python -m agent_operator.review_gate", text)
        self.assertIn("Verify QA reviewer left proposal unchanged", text)
        self.assertIn("Verify Security reviewer left proposal unchanged", text)

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
        self.assertGreaterEqual(text.count("ledger-task-contract/task.json"), 8)
        self.assertGreaterEqual(text.count("ledger-task-contract/prompt.md"), 4)

    def test_executor_uses_filesystem_scope_manifest_not_model_git_diff(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("Capture implementation filesystem without trusting its git metadata", text)
        self.assertIn("--exclude='./.git'", text)
        self.assertIn("ledger-change-manifest.json", text)
        self.assertIn("--allowed-paths-file", text)
        self.assertNotIn("scope_guard --repo", text)
        self.assertNotIn("--base-sha", text)

    def test_fail_safe_cleanup_is_separate_and_preserves_human_intervention_state(self):
        text = EXECUTOR.read_text(encoding="utf-8")
        cleanup = text.split("  fail-safe-cleanup:", 1)[1]
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
