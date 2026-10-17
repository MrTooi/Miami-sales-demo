import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / ".github/workflows/agent-final-readiness-core.yml"
CARRIER = ROOT / ".github/workflows/agent-operator.yml"
OLD_SCHEDULE = ROOT / ".github/workflows/agent-final-readiness-scheduled.yml"
PROBE = ROOT / ".github/workflows/agent-final-readiness-schedule-probe.yml"
CODEX_ACTION_SHA = "a8d8be6ee028bea4525bc722d16f36687b408c81"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
UPLOAD_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"


def core_text():
    return CORE.read_text(encoding="utf-8")


def carrier_text():
    return CARRIER.read_text(encoding="utf-8")


def job_block(name, next_name=None):
    data = core_text()
    marker = f"  {name}:\n"
    self_index = data.index(marker)
    if next_name is None:
        return data[self_index:]
    return data[self_index : data.index(f"  {next_name}:\n", self_index + len(marker))]


class ScheduledReadinessWorkflowTests(unittest.TestCase):
    def test_unreliable_native_schedule_and_probe_are_removed(self):
        self.assertTrue(CORE.exists())
        self.assertFalse(OLD_SCHEDULE.exists())
        self.assertFalse(PROBE.exists())

    def test_core_is_workflow_call_only_and_accepts_one_secret(self):
        data = core_text()
        header = data.split("permissions:", 1)[0]
        self.assertIn("on:\n  workflow_call:\n", header)
        self.assertIn("OPENAI_API_KEY:\n        required: true", header)
        for forbidden in (
            "schedule:",
            "workflow_dispatch:",
            "pull_request:",
            "push:",
            "issue_comment:",
            "repository_dispatch:",
        ):
            self.assertNotIn(forbidden, header)
        self.assertEqual(header.count("required: true"), 1)
        self.assertIn("permissions: {}", data)
        self.assertIn("group: agent-final-readiness-${{ github.repository }}", data)
        self.assertIn("cancel-in-progress: false", data)

    def test_registered_operator_schedule_is_the_only_carrier_and_manual_dispatch_cannot_call_readiness(self):
        data = carrier_text()
        header = data.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", header)
        self.assertIn("schedule:\n    - cron: '17,47 * * * *'", header)
        readiness = data.split("  final-readiness:\n", 1)[1]
        self.assertIn("if: github.event_name == 'schedule'", readiness)
        self.assertIn("uses: ./.github/workflows/agent-final-readiness-core.yml", readiness)
        self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}", readiness)
        self.assertNotIn("secrets: inherit", readiness)
        self.assertNotIn("workflow_dispatch", readiness)
        self.assertNotIn("openai/codex-action", readiness)
        planner = data.split("  plan-next-task:\n", 1)[1].split("  final-readiness:\n", 1)[0]
        self.assertIn("vars.LEDGER_AGENT_OPERATOR_ENABLED == 'true'", planner)
        self.assertIn("github.event_name == 'workflow_dispatch'", planner)

    def test_core_double_checks_real_schedule_provenance_and_blocks_reruns(self):
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("if: github.event_name == 'schedule'", prepare)
        self.assertIn("test \"$GITHUB_EVENT_NAME\" = 'schedule'", prepare)
        self.assertIn("CURRENT_ATTEMPT", prepare)
        self.assertIn("Manual reruns are blocked to prevent duplicate paid model calls.", prepare)

    def test_every_readiness_job_has_job_level_attempt_one_guard(self):
        jobs = [
            "prepare",
            "blind-pass",
            "validate-blind",
            "prepare-judge",
            "judge-pass",
            "validate-and-record",
        ]
        data = core_text()
        self.assertEqual(re.findall(r"^  ([a-z-]+):\n", data.split("\njobs:\n", 1)[1], re.M), jobs)
        for index, name in enumerate(jobs):
            block = job_block(name, jobs[index + 1] if index + 1 < len(jobs) else None)
            if_lines = re.findall(r"^    if: (.+)$", block, re.M)
            self.assertEqual(len(if_lines), 1, name)
            self.assertIn("github.run_attempt == 1", if_lines[0], name)
        for name, nxt in (("blind-pass", "validate-blind"), ("judge-pass", "validate-and-record")):
            block = job_block(name, nxt)
            self.assertIn("openai/codex-action", block)
            self.assertRegex(block, r"(?m)^    if: github\.run_attempt == 1 && ")
        self.assertIn(
            "if: github.event_name == 'schedule' && github.run_attempt == 1",
            job_block("prepare", "blind-pass"),
        )

    def test_model_calls_are_exactly_two_pinned_read_only_drop_sudo_calls(self):
        data = core_text()
        self.assertEqual(data.count(f"openai/codex-action@{CODEX_ACTION_SHA}"), 2)
        self.assertEqual(data.count("permission-profile: ':read-only'"), 2)
        self.assertEqual(data.count("safety-strategy: drop-sudo"), 2)
        self.assertEqual(data.count("allow-bots: true"), 2)
        self.assertEqual(data.count("openai-api-key: ${{ secrets.OPENAI_API_KEY }}"), 2)
        self.assertNotIn("permission-profile: ':workspace'", data)

    def test_readiness_jobs_have_stable_history_markers(self):
        data = core_text()
        for name in (
            "final-readiness-prepare",
            "final-readiness-blind-pass",
            "final-readiness-validate-blind",
            "final-readiness-prepare-judge",
            "final-readiness-judge-pass",
            "final-readiness-validate-and-record",
        ):
            self.assertIn(f"name: {name}", data)

    def test_history_selection_is_delegated_to_behavior_tested_module(self):
        # The previous inline shell classifier is now agent_evals/readiness_history.py;
        # its fixtures are executed in tests/test_readiness_history.py.
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("python -m agent_evals.readiness_history select", prepare)
        self.assertIn('--current-run-id "$CURRENT_RUN_ID"', prepare)
        self.assertIn('--current-sha "$CURRENT_SHA"', prepare)
        self.assertIn('--github-output "$GITHUB_OUTPUT"', prepare)
        self.assertIn("GH_TOKEN: ${{ github.token }}", prepare)
        self.assertNotIn("gh api", prepare, "history must not be re-implemented inline")
        refuse = prepare.index("Refuse non-schedule provenance and reruns before any work")
        checkout = prepare.index("Checkout exact scheduled commit without persisted credentials")
        setup = prepare.index("actions/setup-python@")
        select = prepare.index("Select next suite from verified carrier history and enforce retry barrier")
        gate = prepare.index("Require reviewed hardening change after a prior failed paid run")
        tests = prepare.index("Run deterministic readiness tests before model spend")
        bundle = prepare.index("Build blind-only input and freeze current suite hashes")
        self.assertLess(refuse, checkout)
        self.assertLess(checkout, setup)
        self.assertLess(setup, select)
        self.assertLess(select, gate)
        self.assertLess(gate, tests)
        self.assertLess(tests, bundle)
        self.assertIn("tests.test_readiness_history", prepare[tests:bundle],
                      "the history classifier must be tested before any model spend")

    def test_prepare_step_names_match_pre_model_infrastructure_classification(self):
        from agent_evals import readiness_history as rh

        prepare = job_block("prepare", "blind-pass")
        names = re.findall(r"^      - name: (.+)$", prepare, re.M)
        for step in rh.PRE_MODEL_INFRA_STEPS - {"Set up job"}:
            self.assertIn(step, names, "pre-model step list must match real prepare step names")
        for paid in ("Run deterministic readiness tests before model spend",
                     "Build blind-only input and freeze current suite hashes",
                     "Upload blind-only model input"):
            self.assertIn(paid, names)
            self.assertNotIn(paid, rh.PRE_MODEL_INFRA_STEPS)
        self.assertEqual(
            rh.THRESHOLD_FAILURE_STEP,
            "Fail closed when suite did not meet readiness threshold",
        )
        self.assertIn(f"name: {rh.THRESHOLD_FAILURE_STEP}", job_block("validate-and-record"))

    def test_prepare_creates_only_blind_input_before_validation(self):
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("build-blind --suite", prepare)
        self.assertIn("agent-final-readiness-blind-input", prepare)
        self.assertNotIn("build-judge", prepare)
        self.assertNotIn("agent-final-readiness-judge-input", prepare)
        self.assertIn("test ! -e \"$RUNNER_TEMP/blind-input/rubric.json\"", prepare)

    def test_prepare_judge_is_after_blind_validation_and_non_model(self):
        data = core_text()
        self.assertLess(data.index("  validate-blind:\n"), data.index("  prepare-judge:\n"))
        prepare_judge = job_block("prepare-judge", "judge-pass")
        self.assertIn("needs: [prepare, blind-pass, validate-blind]", prepare_judge)
        self.assertIn("build-judge --suite", prepare_judge)
        self.assertIn("agent-final-readiness-judge-input", prepare_judge)
        self.assertIn(f"actions/checkout@{CHECKOUT_SHA}", prepare_judge)
        self.assertIn("persist-credentials: false", prepare_judge)
        self.assertNotIn("openai/codex-action@", prepare_judge)

    def test_blind_and_judge_model_jobs_have_no_repository_checkout(self):
        blind = job_block("blind-pass", "validate-blind")
        judge = job_block("judge-pass", "validate-and-record")
        self.assertNotIn("actions/checkout@", blind)
        self.assertNotIn("actions/checkout@", judge)
        self.assertNotIn("agent-final-readiness-judge-input", blind)
        self.assertNotIn("build-judge", blind)
        self.assertIn("test ! -e \"$RUNNER_TEMP/blind/rubric.json\"", blind)
        self.assertIn("agent-final-readiness-blind-output", judge)
        self.assertIn("chmod a-w \"$RUNNER_TEMP/judge/blind.json\"", judge)

    def test_every_repository_checkout_is_pinned_and_non_model_jobs_only(self):
        data = core_text()
        checkouts = re.findall(r"uses: actions/checkout@([0-9a-f]+)", data)
        self.assertGreaterEqual(len(checkouts), 3)
        self.assertTrue(all(sha == CHECKOUT_SHA for sha in checkouts))
        for block in (
            job_block("prepare", "blind-pass"),
            job_block("validate-blind", "prepare-judge"),
            job_block("prepare-judge", "judge-pass"),
            job_block("validate-and-record"),
        ):
            if "actions/checkout@" in block:
                self.assertIn("persist-credentials: false", block)

    def test_artifact_actions_are_pinned_and_evidence_is_retained(self):
        data = core_text()
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

    def test_history_uses_registered_carrier_and_excludes_pre_migration_operator_runs(self):
        from agent_evals import readiness_history as rh

        source = (ROOT / "agent_evals/readiness_history.py").read_text(encoding="utf-8")
        self.assertEqual(rh.CARRIER_WORKFLOW, "agent-operator.yml")
        self.assertEqual(rh.CORE_PATH, ".github/workflows/agent-final-readiness-core.yml")
        self.assertIn("/actions/workflows/{CARRIER_WORKFLOW}/runs?event=schedule", source)
        self.assertIn("/contents/{CORE_PATH}?ref={sha}", source)
        self.assertIn('"HTTP 404" in proc.stderr', source)
        self.assertIn("refusing ambiguous history", source)

    def test_success_progression_requires_real_evidence_artifact(self):
        from agent_evals import readiness_history as rh

        self.assertEqual(rh.EVIDENCE_PREFIX, "agent-final-readiness-evidence-")
        self.assertEqual(rh.REQUIRED_SUCCESSES, 3)
        self.assertEqual(rh.SUITE_BY_SUCCESS_COUNT, {0: "a", 1: "b", 2: "c"})
        source = (ROOT / "agent_evals/readiness_history.py").read_text(encoding="utf-8")
        self.assertIn('a.get("expired") is False', source)
        self.assertIn("lacks exactly one valid evidence", source)

    def test_same_sha_retry_barrier_and_reviewed_change_gate_remain(self):
        from agent_evals import readiness_history as rh

        prepare = job_block("prepare", "blind-pass")
        self.assertEqual(
            rh.SAME_SHA_REFUSAL,
            "Most recent paid-relevant scheduled run failed on this exact commit; refusing a blind paid retry.",
        )
        self.assertIn("Require reviewed hardening change after a prior failed paid run", prepare)
        self.assertIn("if: steps.select.outputs.execute == 'true' && steps.select.outputs.failed_sha != ''", prepare)
        self.assertIn("python -m agent_evals.readiness_history hardening-gate", prepare)
        self.assertIn('--kind "$FAILURE_KIND"', prepare)
        self.assertIn("FAILURE_KIND: ${{ steps.select.outputs.failure_kind }}", prepare)
        self.assertIn('git cat-file -e "$FAILED_SHA^{commit}"', prepare)
        # Cadence-only carrier edits and unrelated tests can no longer unlock a paid retry.
        self.assertFalse(rh.hardening_allows_retry([".github/workflows/agent-operator.yml"], "behavioral"))
        self.assertFalse(rh.hardening_allows_retry([".github/workflows/agent-operator.yml"], "infrastructure"))

    def test_suite_c_finds_only_prior_valid_carrier_evidence_and_revalidates_it(self):
        final = job_block("validate-and-record")
        self.assertIn("/actions/workflows/agent-operator.yml/runs?event=schedule&status=success", final)
        self.assertIn(
            'select(.event == "schedule" and .conclusion == "success" and .run_attempt == 1)', final,
            "reruns must never be selected as prior A/B evidence",
        )
        self.assertIn("python -m agent_evals.scheduled_readiness verify-instruction-hashes", final)
        self.assertIn('"$RUNNER_TEMP/prior-a/metadata.json" "$RUNNER_TEMP/prior-b/metadata.json" "$RUNNER_TEMP/current-instructions.json"', final)
        self.assertNotIn("--allow-mixed", core_text())
        self.assertIn("agent-final-readiness-evidence-$RID", final)
        self.assertIn("mapfile -t IDS", final)
        self.assertIn('test "${#IDS[@]}" -eq 2', final)
        self.assertIn("EXPECTED_SUITES=(a b)", final)
        for required in (
            "test -s \"$DEST/hashes.sha256\"",
            "sha256sum -c hashes.sha256",
            "test -s \"$DEST/metadata.json\"",
            "test -s \"$DEST/blind.json\"",
            "test -s \"$DEST/judge.json\"",
            "gh api \"/repos/$GITHUB_REPOSITORY/actions/runs/$RID\" > \"$RUN_META\"",
            "'.event'",
            "'.repository'",
            "'.run_id'",
            "'.run_attempt'",
            "'.commit_sha'",
            "'.ref'",
            "'.blind_sha256'",
            "'.judge_sha256'",
            "'.deterministic_validation'",
            "'.suite'",
            "final_suite_${EXPECTED_SUITE}_prompts.json",
            "final_suite_${EXPECTED_SUITE}_rubric.json",
            "'.prompt_sha256'",
            "'.rubric_sha256'",
            "validate-blind --suite \"$EXPECTED_SUITE\"",
            "validate-judge --suite \"$EXPECTED_SUITE\"",
        ):
            self.assertIn(required, final)
        self.assertIn("= 'schedule'", final)
        self.assertIn("= '1'", final)
        self.assertIn("= 'refs/heads/main'", final)
        self.assertIn("= 'passed'", final)
        self.assertIn("BLIND_ACTUAL=", final)
        self.assertIn("JUDGE_ACTUAL=", final)

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

    def test_core_has_no_repository_mutation_or_deployment_permissions(self):
        data = core_text()
        folded = data.casefold()
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
            self.assertNotIn(forbidden, folded)
        permission_values = re.findall(r"^\s{6}(actions|contents):\s+(\w+)\s*$", data, flags=re.MULTILINE)
        self.assertTrue(permission_values)
        self.assertTrue(all(value == "read" for _, value in permission_values))

    def test_evidence_contains_required_runtime_provenance_and_reasserts_schedule(self):
        final = job_block("validate-and-record")
        for key in (
            "event",
            "repository",
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
            "agents_md_sha256",
            "copilot_instructions_sha256",
            "team_profiles_sha256",
            "deterministic_validation",
        ):
            self.assertIn(key, final)
        self.assertIn("test \"$(jq -r '.event' \"$RUNNER_TEMP/evidence/metadata.json\")\" = 'schedule'", final)
        self.assertIn('verify-instruction-hashes --metadata "$RUNNER_TEMP/evidence/metadata.json"', final)

    def test_instruction_hashes_are_taken_from_the_exact_blind_bundle_inputs(self):
        prepare = job_block("prepare", "blind-pass")
        for out in ("agents_md_sha256", "copilot_instructions_sha256", "team_profiles_sha256"):
            self.assertIn(f"{out}: ${{{{ steps.bundle.outputs.{out} }}}}", prepare)
        for bundled, repo in (
            ("blind-input/AGENTS.md", "AGENTS.md"),
            ("blind-input/copilot-instructions.md", ".github/copilot-instructions.md"),
            ("blind-input/team_profiles.json", "agent_evals/team_profiles.json"),
        ):
            self.assertIn(f'sha256sum "$RUNNER_TEMP/{bundled}"', prepare)
            self.assertIn(f"sha256sum {repo} |", prepare)


if __name__ == "__main__":
    unittest.main()
