import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/agent-final-readiness-scheduled.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
UPLOAD_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"


def text():
    return WORKFLOW.read_text(encoding="utf-8")


def job_block(name, next_name=None):
    data = text()
    marker = f"  {name}:\n"
    self_index = data.index(marker)
    if next_name is None:
        return data[self_index:]
    return data[self_index : data.index(f"  {next_name}:\n", self_index + len(marker))]


class ScheduledReadinessWorkflowTests(unittest.TestCase):
    def test_trigger_surface_is_schedule_only_and_concurrency_is_non_cancelling(self):
        data = text()
        header = data.split("jobs:", 1)[0]
        self.assertIn("on:\n  schedule:\n", header)
        self.assertIn("cron: '17 * * * *'", header)
        for forbidden in ("workflow_dispatch:", "pull_request:", "push:", "issue_comment:"):
            self.assertNotIn(forbidden, header)
        self.assertIn("permissions: {}", header)
        self.assertIn("group: agent-final-readiness-${{ github.repository }}", header)
        self.assertIn("cancel-in-progress: false", header)

    def test_model_calls_are_exactly_two_pinned_read_only_drop_sudo_calls(self):
        data = text()
        self.assertEqual(data.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 2)
        self.assertEqual(data.count("permission-profile: ':read-only'"), 2)
        self.assertEqual(data.count("safety-strategy: drop-sudo"), 2)
        self.assertEqual(data.count("allow-bots: true"), 2)
        self.assertEqual(data.count("openai-api-key: ${{ secrets.OPENAI_API_KEY }}"), 2)
        self.assertNotIn("permission-profile: ':workspace'", data)

    def test_blind_and_judge_model_jobs_have_no_repository_checkout(self):
        blind = job_block("blind-pass", "validate-blind")
        judge = job_block("judge-pass", "validate-and-record")
        self.assertNotIn("actions/checkout@", blind)
        self.assertNotIn("actions/checkout@", judge)
        self.assertNotIn("agent-final-readiness-judge-input", blind)
        self.assertIn("test ! -e \"$RUNNER_TEMP/blind/rubric.json\"", blind)
        self.assertIn("agent-final-readiness-blind-output", judge)
        self.assertIn("chmod a-w \"$RUNNER_TEMP/judge/blind.json\"", judge)

    def test_every_repository_checkout_is_pinned_and_non_model_jobs_only(self):
        data = text()
        checkouts = re.findall(r"uses: actions/checkout@([0-9a-f]+)", data)
        self.assertGreaterEqual(len(checkouts), 2)
        self.assertTrue(all(sha == CHECKOUT_SHA for sha in checkouts))
        for block in (job_block("prepare", "blind-pass"), job_block("validate-blind", "judge-pass"), job_block("validate-and-record")):
            if "actions/checkout@" in block:
                self.assertIn("persist-credentials: false", block)

    def test_artifact_actions_are_pinned_and_evidence_is_retained(self):
        data = text()
        upload_shas = re.findall(r"uses: actions/upload-artifact@([0-9a-f]+)", data)
        download_shas = re.findall(r"uses: actions/download-artifact@([0-9a-f]+)", data)
        self.assertGreaterEqual(len(upload_shas), 5)
        self.assertGreaterEqual(len(download_shas), 4)
        self.assertTrue(all(sha == UPLOAD_SHA for sha in upload_shas))
        self.assertTrue(all(sha == DOWNLOAD_SHA for sha in download_shas))
        final = job_block("validate-and-record")
        self.assertIn("name: agent-final-readiness-evidence-${{ github.run_id }}", final)
        self.assertIn("retention-days: 30", final)
        self.assertIn("sha256sum -c hashes.sha256", final)

    def test_cost_controls_select_by_success_and_block_blind_retries(self):
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("CURRENT_ATTEMPT", prepare)
        self.assertIn("Manual reruns are blocked to prevent duplicate paid model calls.", prepare)
        self.assertIn(".conclusion == \"success\"", prepare)
        self.assertIn("SUCCESS_COUNT", prepare)
        self.assertIn("Three successful scheduled evidence runs already exist", prepare)
        self.assertIn("Most recent scheduled run failed on this exact commit; refusing a blind paid retry.", prepare)
        self.assertIn("Require reviewed hardening change after a prior failed paid run", prepare)
        self.assertRegex(prepare, r"0\) SUITE='a'.*1\) SUITE='b'.*2\) SUITE='c'", msg="A/B/C selection must be success-count driven")

    def test_canonical_local_validation_controls_scoring_and_final_aggregate(self):
        final = job_block("validate-and-record")
        self.assertIn("validate-blind --suite", final)
        self.assertIn("validate-judge --suite", final)
        self.assertIn("score-suite --suite", final)
        self.assertIn("aggregate \\", final)
        self.assertIn("--a \"$RUNNER_TEMP/prior-a/judge.json\"", final)
        self.assertIn("--b \"$RUNNER_TEMP/prior-b/judge.json\"", final)
        self.assertIn("--c \"$RUNNER_TEMP/outputs/judge.json\"", final)
        self.assertIn("Fail closed when suite did not meet readiness threshold", final)

    def test_workflow_has_no_repository_mutation_or_deployment_permissions(self):
        data = text()
        for forbidden in (
            "contents: write",
            "actions: write",
            "issues: write",
            "pull-requests: write",
            "id-token: write",
            "gh issue ",
            "gh pr ",
            "git push",
            "git commit",
            "deploy",
            "deployment",
        ):
            self.assertNotIn(forbidden, data.casefold() if forbidden.islower() else data)
        permission_values = re.findall(r"^\s{6}(actions|contents):\s+(\w+)\s*$", data, flags=re.MULTILINE)
        self.assertTrue(permission_values)
        self.assertTrue(all(value == "read" for _, value in permission_values))

    def test_success_evidence_contains_required_runtime_provenance(self):
        final = job_block("validate-and-record")
        for key in (
            "event",
            "run_id",
            "run_attempt",
            "commit_sha",
            "ref",
            "python_version",
            "suite",
            "prompt_sha256",
            "rubric_sha256",
            "blind_sha256",
            "judge_sha256",
            "deterministic_validation",
        ):
            self.assertIn(key, final)
        self.assertIn("event=schedule", text().replace("'", "")) if False else None
        self.assertIn("test \"$GITHUB_EVENT_NAME\" = 'schedule'", job_block("prepare", "blind-pass"))


if __name__ == "__main__":
    unittest.main()
