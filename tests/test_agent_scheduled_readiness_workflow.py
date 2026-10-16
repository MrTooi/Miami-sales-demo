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

    def test_suffix_prepare_marker_jq_filter_does_not_match_prepare_judge(self):
        jq = shutil.which("jq")
        self.assertIsNotNone(jq, "jq is required by the readiness workflow and its regression test")
        expression = '[.[] | select(.name | endswith("final-readiness-prepare"))] | length'
        for caller_prefix in ("final-readiness / ", "carrier-job / ", ""):
            with self.subTest(prefix=caller_prefix):
                jobs = [
                    {"name": caller_prefix + name, "started_at": "2026-10-16T00:00:00Z", "conclusion": "success"}
                    for name in (
                        "final-readiness-prepare",
                        "final-readiness-blind-pass",
                        "final-readiness-validate-blind",
                        "final-readiness-prepare-judge",
                        "final-readiness-judge-pass",
                        "final-readiness-validate-and-record",
                    )
                ]
                result = subprocess.run(
                    [jq, expression],
                    input=json.dumps(jobs),
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertEqual(result.stdout.strip(), "1")
        prepare = job_block("prepare", "blind-pass")
        self.assertIn(expression, prepare)
        self.assertNotIn('contains("final-readiness-prepare")', prepare)

    def test_zero_marker_case_is_handled_before_marker_fail_closed(self):
        prepare = job_block("prepare", "blind-pass")
        zero_marker = (
            "if [ \"$MARKERS\" = '0' ] && [ \"$READINESS_JOB_COUNT\" = '0' ] && "
            "[ \"$MODEL_STAGE_STARTED\" = '0' ] && [ \"$READINESS_ARTIFACT_COUNT\" = '0' ] && "
            "[ \"$CONCLUSION\" != 'success' ]; then"
        )
        marker_fail = "if [ \"$MARKERS\" != '1' ]; then"
        self.assertIn(zero_marker, prepare)
        self.assertIn(marker_fail, prepare)
        self.assertLess(prepare.index(zero_marker), prepare.index(marker_fail))
        self.assertIn("because no readiness job, model stage, or readiness artifact exists.", prepare)
        self.assertIn('.conclusion != "skipped"', prepare)
        self.assertIn('contains("final-readiness")', prepare)
        self.assertIn('startswith("agent-final-readiness-")', prepare)

    def _classify_history_run(self, conclusion, jobs, artifacts=()):
        """Run the workflow's real classification shell block against a fixture."""
        jq = shutil.which("jq")
        bash = shutil.which("bash")
        self.assertIsNotNone(jq, "jq is required")
        self.assertIsNotNone(bash, "bash is required")
        prepare = job_block("prepare", "blind-pass")
        start = prepare.index('MARKERS="$(jq')
        end = prepare.index("printf '%s\\n' \"$CANDIDATE\" >> \"$RELEVANT\"")
        snippet = "\n".join(line.strip() for line in prepare[start:end].splitlines())
        script = f'for _ in 1; do\n{snippet}\necho RELEVANT\ndone\n'
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "jobs.json"
            artifacts_path = Path(tmp) / "artifacts.json"
            jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
            artifacts_path.write_text(
                json.dumps({"artifacts": [{"name": n} for n in artifacts]}), encoding="utf-8"
            )
            env = dict(
                os.environ,
                JOBS=str(jobs_path),
                ARTIFACTS=str(artifacts_path),
                CONCLUSION=conclusion,
                RID="1",
            )
            result = subprocess.run(
                [bash, "-c", script], env=env, text=True, capture_output=True
            )
        if result.returncode != 0:
            return "fail-closed"
        return "relevant" if "RELEVANT" in result.stdout else "ignored"

    def test_history_classification_fixtures_for_zero_marker_runs(self):
        started = "2026-10-16T00:00:00Z"
        for conclusion in ("startup_failure", "failure", "cancelled"):
            with self.subTest(conclusion=conclusion, case="no jobs, no artifacts"):
                self.assertEqual(self._classify_history_run(conclusion, []), "ignored")
        self.assertEqual(self._classify_history_run("success", []), "fail-closed")
        # Unrelated artifacts do not block ignoring.
        self.assertEqual(self._classify_history_run("failure", [], ["unrelated"]), "ignored")

        for prefix in ("final-readiness / final-readiness-", "other-caller / final-readiness-"):
            # A started blind/judge stage fails closed under any caller prefix.
            for conclusion in ("success", "failure", "cancelled", "startup_failure", "timed_out"):
                for stage in ("blind-pass", "judge-pass"):
                    with self.subTest(prefix=prefix, conclusion=conclusion, started=stage):
                        jobs = [{"name": prefix + stage, "conclusion": "failure", "started_at": started}]
                        self.assertEqual(self._classify_history_run(conclusion, jobs), "fail-closed")

            # A skipped model stage is not paid-stage evidence, but it is still a
            # readiness-named job, so a zero-marker run is not ignored either.
            skipped = [{"name": prefix + "blind-pass", "conclusion": "skipped", "started_at": started}]
            for conclusion in ("cancelled", "failure", "success"):
                with self.subTest(prefix=prefix, conclusion=conclusion, case="skipped only"):
                    self.assertEqual(self._classify_history_run(conclusion, skipped), "fail-closed")

            # Exactly one prepare marker is relevant; duplicates fail closed.
            one = [{"name": prefix + "prepare", "conclusion": "success", "started_at": started}]
            self.assertEqual(self._classify_history_run("success", one), "relevant")
            self.assertEqual(self._classify_history_run("failure", one), "relevant")
            self.assertEqual(self._classify_history_run("failure", one + one), "fail-closed")

        # A readiness-named job with an unexpected name shape fails closed.
        odd = [{"name": "weird / final-readiness-prepare-v2", "conclusion": "failure", "started_at": started}]
        for conclusion in ("startup_failure", "failure", "cancelled"):
            self.assertEqual(self._classify_history_run(conclusion, odd), "fail-closed")

        # Any readiness artifact, even with no recognised jobs, fails closed.
        for conclusion in ("startup_failure", "failure", "cancelled"):
            for artifact in ("agent-final-readiness-blind-input-1", "agent-final-readiness-evidence-1"):
                with self.subTest(conclusion=conclusion, artifact=artifact):
                    self.assertEqual(self._classify_history_run(conclusion, [], [artifact]), "fail-closed")

    def test_skipped_model_stage_is_not_counted_as_started(self):
        jq = shutil.which("jq")
        self.assertIsNotNone(jq, "jq is required")
        expression = next(
            line.split("'")[1]
            for line in job_block("prepare", "blind-pass").splitlines()
            if line.strip().startswith("MODEL_STAGE_STARTED=\"$(jq")
        )
        for prefix in ("final-readiness / ", "other-caller / "):
            jobs = [
                {"name": prefix + "final-readiness-blind-pass", "conclusion": "skipped", "started_at": "2026-10-16T00:00:00Z"},
                {"name": prefix + "final-readiness-judge-pass", "conclusion": "skipped", "started_at": None},
            ]
            out = subprocess.run([jq, expression], input=json.dumps(jobs), text=True, capture_output=True, check=True)
            self.assertEqual(out.stdout.strip(), "0")
            jobs[0]["conclusion"] = "failure"
            out = subprocess.run([jq, expression], input=json.dumps(jobs), text=True, capture_output=True, check=True)
            self.assertEqual(out.stdout.strip(), "1")

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
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("/actions/workflows/agent-operator.yml/runs?event=schedule", prepare)
        self.assertIn("contents/.github/workflows/agent-final-readiness-core.yml?ref=$SHA", prepare)
        self.assertIn("if grep -q 'HTTP 404'", prepare)
        self.assertIn("continue", prepare)
        self.assertIn('select(.name | endswith("final-readiness-prepare"))', prepare)
        self.assertIn("MARKERS", prepare)
        self.assertIn("refusing ambiguous history", prepare)

    def test_success_progression_requires_real_evidence_artifact(self):
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("agent-final-readiness-evidence-$RID", prepare)
        self.assertIn(".expired == false", prepare)
        self.assertIn("SUCCESS_COUNT", prepare)
        self.assertIn("MISSING_SUCCESS_EVIDENCE", prepare)
        self.assertIn("successful carrier run lacks exactly one valid evidence artifact", prepare)
        self.assertIn("0) SUITE='a' ;;", prepare)
        self.assertIn("1) SUITE='b' ;;", prepare)
        self.assertIn("2) SUITE='c' ;;", prepare)
        self.assertIn("Three successful scheduled evidence runs already exist", prepare)

    def test_cancelled_attempts_are_ignored_only_when_no_model_job_or_artifact_started(self):
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("MODEL_STAGE_STARTED='unknown'", prepare)
        self.assertIn("READINESS_ARTIFACT_COUNT='unknown'", prepare)
        self.assertIn('endswith("final-readiness-blind-pass")', prepare)
        self.assertIn('endswith("final-readiness-judge-pass")', prepare)
        self.assertIn(".started_at != null", prepare)
        self.assertIn('.conclusion != "skipped"', prepare)
        ignore = "if [ \"$MODEL_STAGE_STARTED\" = '0' ] && [ \"$READINESS_ARTIFACT_COUNT\" = '0' ]; then"
        unknown = "if [ \"$MODEL_STAGE_STARTED\" = 'unknown' ] || [ \"$READINESS_ARTIFACT_COUNT\" = 'unknown' ]; then"
        self.assertIn(ignore, prepare)
        self.assertIn(unknown, prepare)
        self.assertLess(prepare.index(ignore), prepare.index(unknown))
        self.assertIn("Ignoring cancelled carrier run $RID because no model-stage job or readiness artifact started.", prepare)
        self.assertIn("Could not verify cancelled carrier run $RID job/artifact history; treating it as a paid-relevant failure.", prepare)
        self.assertIn("may have reached paid readiness work", prepare)

    def test_same_sha_retry_barrier_and_reviewed_change_gate_remain(self):
        prepare = job_block("prepare", "blind-pass")
        self.assertIn("Most recent paid-relevant scheduled run failed on this exact commit; refusing a blind paid retry.", prepare)
        self.assertIn("Require reviewed hardening change after a prior failed paid run", prepare)
        self.assertIn("agent-final-readiness-core\\.yml", prepare)
        self.assertIn("agent-operator\\.yml", prepare)

    def test_suite_c_finds_only_prior_valid_carrier_evidence_and_revalidates_it(self):
        final = job_block("validate-and-record")
        self.assertIn("/actions/workflows/agent-operator.yml/runs?event=schedule&status=success", final)
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
            "deterministic_validation",
        ):
            self.assertIn(key, final)
        self.assertIn("test \"$(jq -r '.event' \"$RUNNER_TEMP/evidence/metadata.json\")\" = 'schedule'", final)


if __name__ == "__main__":
    unittest.main()
