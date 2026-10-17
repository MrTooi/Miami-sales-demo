"""Behavior tests for agent_evals/readiness_history.py (Issue #87 / audit #86).

These execute the real selection logic the readiness core runs, instead of asserting
workflow text. Every ambiguity must fail closed (raise ReadinessHistoryError).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_evals import readiness_history as rh
from agent_evals import scheduled_readiness as sr

STARTED = "2026-10-16T00:00:00Z"
PREP = "final-readiness / final-readiness-prepare"
BLIND = "final-readiness / final-readiness-blind-pass"
VALIDATE_BLIND = "final-readiness / final-readiness-validate-blind"
PREP_JUDGE = "final-readiness / final-readiness-prepare-judge"
JUDGE = "final-readiness / final-readiness-judge-pass"
RECORD = "final-readiness / final-readiness-validate-and-record"
SELECT = "Select next suite from verified carrier history and enforce retry barrier"


def run(rid, conclusion="success", attempt=1, sha="sha-current", minute=None):
    return {
        "id": rid,
        "run_attempt": attempt,
        "conclusion": conclusion,
        "head_sha": sha,
        "event": "schedule",
        "status": "completed",
        "created_at": f"2026-10-17T00:{(minute if minute is not None else rid) % 60:02d}:00Z",
    }


def job(name, conclusion="success", started=STARTED, steps=None):
    data = {"name": name, "conclusion": conclusion, "started_at": started}
    if steps is not None:
        data["steps"] = steps
    return data


def prep(conclusion="success", failed_step=None):
    steps = [{"name": "Set up job", "conclusion": "success"}]
    if failed_step:
        steps.append({"name": failed_step, "conclusion": "failure"})
    return job(PREP, conclusion, steps=steps)


def evidence(rid, expired=False):
    return [{"name": f"{rh.EVIDENCE_PREFIX}{rid}", "expired": expired}]


def full_success_jobs():
    return [prep(), job(BLIND), job(VALIDATE_BLIND), job(PREP_JUDGE), job(JUDGE), job(RECORD)]


def threshold_failure_jobs():
    record = job(RECORD, "failure", steps=[{"name": rh.THRESHOLD_FAILURE_STEP, "conclusion": "failure"}])
    return [prep(), job(BLIND), job(VALIDATE_BLIND), job(PREP_JUDGE), job(JUDGE), record]


def attempt(rid, conclusion, jobs, artifacts=()):
    return rh.classify_attempt(rid, conclusion, jobs, list(artifacts))


class LegacyShellFixtureParityTests(unittest.TestCase):
    """The exact fixtures the previous shell classifier was tested with still hold."""

    def outcome(self, conclusion, jobs, artifacts=()):
        try:
            status = attempt(1, conclusion, jobs, [{"name": n} for n in artifacts])
        except rh.ReadinessHistoryError:
            return "fail-closed"
        return "ignored" if status == "ignore" else "relevant"

    def test_zero_marker_runs(self):
        for conclusion in ("startup_failure", "failure", "cancelled"):
            self.assertEqual(self.outcome(conclusion, []), "ignored")
        self.assertEqual(self.outcome("success", []), "fail-closed")
        self.assertEqual(self.outcome("failure", [], ["unrelated"]), "ignored")

        for prefix in ("final-readiness / final-readiness-", "other-caller / final-readiness-"):
            for conclusion in ("success", "failure", "cancelled", "startup_failure", "timed_out"):
                for stage in ("blind-pass", "judge-pass"):
                    with self.subTest(prefix=prefix, conclusion=conclusion, stage=stage):
                        jobs = [job(prefix + stage, "failure")]
                        self.assertEqual(self.outcome(conclusion, jobs), "fail-closed")
            skipped = [job(prefix + "blind-pass", "skipped")]
            for conclusion in ("cancelled", "failure", "success"):
                self.assertEqual(self.outcome(conclusion, skipped), "fail-closed")
            one = [job(prefix + "prepare")]
            self.assertEqual(self.outcome("success", one), "relevant")
            self.assertEqual(self.outcome("failure", one), "relevant")
            self.assertEqual(self.outcome("failure", one + one), "fail-closed")

        odd = [job("weird / final-readiness-prepare-v2", "failure")]
        for conclusion in ("startup_failure", "failure", "cancelled"):
            self.assertEqual(self.outcome(conclusion, odd), "fail-closed")
        for conclusion in ("startup_failure", "failure", "cancelled"):
            for artifact in ("agent-final-readiness-blind-input-1", "agent-final-readiness-evidence-1"):
                self.assertEqual(self.outcome(conclusion, [], [artifact]), "fail-closed")

    def test_prepare_marker_suffix_does_not_match_prepare_judge(self):
        for prefix in ("final-readiness / ", "carrier-job / ", ""):
            jobs = [job(prefix + "final-readiness-" + n) for n in (
                "prepare", "blind-pass", "validate-blind", "prepare-judge", "judge-pass", "validate-and-record")]
            self.assertEqual(len(rh._jobs_ending(jobs, "final-readiness-prepare")), 1)

    def test_skipped_model_stage_is_not_counted_as_started(self):
        for prefix in ("final-readiness / ", "other-caller / "):
            jobs = [job(prefix + "final-readiness-blind-pass", "skipped"),
                    job(prefix + "final-readiness-judge-pass", "skipped", started=None)]
            self.assertEqual(rh.model_stage_started(jobs), 0)
            jobs[0]["conclusion"] = "failure"
            self.assertEqual(rh.model_stage_started(jobs), 1)
            self.assertEqual(rh.model_stage_started([job(prefix + "final-readiness-judge-pass", "failure", started=None)]), 0)


class ClassifyAttemptTests(unittest.TestCase):
    def test_h1_prepare_infrastructure_failure_before_model_is_not_paid_relevant(self):
        for step in ("Set up job", "Refuse non-schedule provenance and reruns before any work",
                     "Checkout exact scheduled commit without persisted credentials", "Set up Python",
                     SELECT, "Require reviewed hardening change after a prior failed paid run"):
            with self.subTest(step=step):
                self.assertEqual(attempt(1, "failure", [prep("failure", step)]), "pre_model_failure")

    def test_deterministic_tests_bundle_or_upload_failure_stays_paid_relevant(self):
        for step in ("Run deterministic readiness tests before model spend",
                     "Build blind-only input and freeze current suite hashes",
                     "Upload blind-only model input", "Some unknown step"):
            with self.subTest(step=step):
                self.assertEqual(attempt(1, "failure", [prep("failure", step)]), "paid_relevant_failure")

    def test_prepare_failure_with_missing_steps_is_paid_relevant(self):
        self.assertEqual(attempt(1, "failure", [job(PREP, "failure")]), "paid_relevant_failure")
        self.assertEqual(attempt(1, "failure", [job(PREP, "failure", steps=[])]), "paid_relevant_failure")

    def test_any_readiness_artifact_keeps_infra_prepare_failure_paid_relevant(self):
        self.assertEqual(attempt(1, "failure", [prep("failure", SELECT)], evidence(1)), "paid_relevant_failure")
        blind_input = [{"name": f"{rh.BLIND_INPUT_PREFIX}1", "expired": False}]
        self.assertEqual(attempt(1, "failure", [prep("failure", SELECT)], blind_input), "paid_relevant_failure")

    def test_started_model_stage_is_paid_relevant(self):
        self.assertEqual(attempt(1, "failure", [prep(), job(BLIND, "failure")]), "paid_relevant_failure")
        self.assertEqual(attempt(1, "cancelled", [prep(), job(BLIND, "cancelled")]), "paid_relevant_failure")

    def test_cancelled_before_model_is_pre_model_even_with_blind_input_only(self):
        self.assertEqual(attempt(1, "cancelled", [prep("cancelled")]), "pre_model_failure")
        blind_input = [{"name": f"{rh.BLIND_INPUT_PREFIX}1", "expired": False}]
        queued_blind = job(BLIND, "cancelled", started=None)
        self.assertEqual(attempt(1, "cancelled", [prep(), queued_blind], blind_input), "pre_model_failure")
        self.assertEqual(attempt(1, "cancelled", [prep()], evidence(1)), "paid_relevant_failure")

    def test_prepare_success_then_run_failure_without_model_is_paid_relevant(self):
        self.assertEqual(attempt(1, "failure", [prep()]), "paid_relevant_failure")

    def test_success_requires_exactly_one_unexpired_evidence_artifact(self):
        self.assertEqual(attempt(1, "success", full_success_jobs(), evidence(1)), "success")
        self.assertEqual(attempt(1, "success", full_success_jobs(), []), "success_missing_evidence")
        self.assertEqual(attempt(1, "success", full_success_jobs(), evidence(1, expired=True)),
                         "success_missing_evidence")
        self.assertEqual(attempt(1, "success", full_success_jobs(), evidence(1) + evidence(1)),
                         "success_missing_evidence")
        self.assertEqual(attempt(1, "success", full_success_jobs(), evidence(2)), "success_missing_evidence")

    def test_unexpected_conclusion_fails_closed(self):
        for conclusion in ("neutral", "action_required", "stale", None):
            with self.assertRaises(rh.ReadinessHistoryError):
                attempt(1, conclusion, [prep()])


class FailureKindTests(unittest.TestCase):
    def test_threshold_failure_is_behavioral(self):
        self.assertEqual(rh.failure_kind(threshold_failure_jobs()), "behavioral")

    def test_blind_validation_failure_is_behavioral(self):
        jobs = [prep(), job(BLIND), job(VALIDATE_BLIND, "failure")]
        self.assertEqual(rh.failure_kind(jobs), "behavioral")

    def test_model_runtime_failure_before_recording_is_infrastructure(self):
        self.assertEqual(rh.failure_kind([prep(), job(BLIND, "failure")]), "infrastructure")
        jobs = [prep(), job(BLIND), job(VALIDATE_BLIND), job(PREP_JUDGE), job(JUDGE, "failure")]
        self.assertEqual(rh.failure_kind(jobs), "infrastructure")

    def test_recording_ran_or_unproven_is_behavioral(self):
        jobs = full_success_jobs()
        jobs[-1]["conclusion"] = "failure"
        self.assertEqual(rh.failure_kind(jobs), "behavioral")
        self.assertEqual(rh.failure_kind([prep()]), "behavioral")


class ClassifyRunAttemptProvenanceTests(unittest.TestCase):
    def test_m3_rerun_success_is_never_countable(self):
        rerun = run(5, "success", attempt=2)
        details = {"jobs": [], "artifacts": evidence(5),
                   "attempt1": {"run_attempt": 1, "status": "completed", "conclusion": "success"},
                   "attempt1_jobs": full_success_jobs()}
        self.assertEqual(rh.classify_run(rerun, details)["status"], "rerun_not_countable")

    def test_rerun_of_paid_failure_still_blocks(self):
        rerun = run(5, "success", attempt=2)
        details = {"jobs": [], "artifacts": evidence(5),
                   "attempt1": {"run_attempt": 1, "status": "completed", "conclusion": "failure"},
                   "attempt1_jobs": threshold_failure_jobs()}
        result = rh.classify_run(rerun, details)
        self.assertEqual(result["status"], "paid_relevant_failure")
        self.assertEqual(result["kind"], "behavioral")

    def test_unverifiable_attempt_one_fails_closed(self):
        rerun = run(5, "success", attempt=2)
        for details in (
            {"jobs": [], "artifacts": []},
            {"jobs": [], "artifacts": [], "attempt1": {"run_attempt": 2, "status": "completed"}, "attempt1_jobs": []},
            {"jobs": [], "artifacts": [], "attempt1": {"run_attempt": 1, "status": "in_progress"}, "attempt1_jobs": []},
            {"jobs": [], "artifacts": [], "attempt1": {"run_attempt": 1, "status": "completed"}},
        ):
            with self.assertRaises(rh.ReadinessHistoryError):
                rh.classify_run(rerun, details)
        for bad in (0, None, "1"):
            with self.assertRaises(rh.ReadinessHistoryError):
                rh.classify_run(run(6, attempt=bad), {"jobs": [], "artifacts": []})


class SelectSuiteTests(unittest.TestCase):
    def select(self, history, current_sha="sha-current", core=lambda sha: sha != "pre-core", max_runs=rh.MAX_RUNS_SCANNED):
        """history: newest-first list of (run, details)."""
        table = {r["id"]: d for r, d in history}
        calls = []

        def details(r):
            calls.append(r["id"])
            return table[r["id"]]

        result = rh.select_suite([r for r, _ in history], core, details, current_run_id=999,
                                 current_sha=current_sha, max_runs=max_runs)
        return result, calls

    def ok(self, rid, sha="sha-old"):
        return run(rid, "success", sha=sha), {"jobs": full_success_jobs(), "artifacts": evidence(rid)}

    def behavioral_fail(self, rid, sha="sha-old"):
        return run(rid, "failure", sha=sha), {"jobs": threshold_failure_jobs(), "artifacts": evidence(rid)}

    def infra_prepare_fail(self, rid, sha):
        return run(rid, "failure", sha=sha), {"jobs": [prep("failure", SELECT)], "artifacts": []}

    def test_empty_history_selects_a(self):
        self.assertEqual(self.select([])[0], {"execute": True, "suite": "a"})

    def test_progression_and_completion(self):
        self.assertEqual(self.select([self.ok(1)])[0]["suite"], "b")
        self.assertEqual(self.select([self.ok(2), self.ok(1)])[0]["suite"], "c")
        result, calls = self.select([self.ok(4), self.ok(3), self.ok(2), self.ok(1)])
        self.assertEqual(result, {"execute": False, "suite": "complete"})
        self.assertEqual(calls, [4, 3, 2], "scan must stop after three successes")

    def test_success_missing_evidence_fails_closed(self):
        missing = (run(2, "success"), {"jobs": full_success_jobs(), "artifacts": []})
        with self.assertRaisesRegex(rh.ReadinessHistoryError, "lacks exactly one valid evidence"):
            self.select([missing, self.ok(1)])

    def test_same_sha_paid_failure_refuses_blind_retry(self):
        with self.assertRaisesRegex(rh.ReadinessHistoryError, "refusing a blind paid retry"):
            self.select([self.behavioral_fail(1, sha="sha-current")])

    def test_failure_on_older_sha_requires_hardening_gate(self):
        result, _ = self.select([self.behavioral_fail(1, sha="sha-old")])
        self.assertEqual(result, {"execute": True, "suite": "a", "failed_sha": "sha-old", "failure_kind": "behavioral"})

    def test_h1_pre_model_failure_on_same_sha_does_not_become_latest_failure(self):
        result, _ = self.select([self.infra_prepare_fail(3, "sha-current"), self.ok(1)])
        self.assertEqual(result, {"execute": True, "suite": "b"})

    def test_h1_pre_model_failure_does_not_hide_older_paid_failure(self):
        history = [self.infra_prepare_fail(3, "sha-current"), self.behavioral_fail(2, sha="sha-current")]
        with self.assertRaisesRegex(rh.ReadinessHistoryError, "refusing a blind paid retry"):
            self.select(history)
        history = [self.infra_prepare_fail(3, "sha-current"), self.behavioral_fail(2, sha="sha-old")]
        self.assertEqual(self.select(history)[0]["failed_sha"], "sha-old")

    def test_success_after_failure_clears_the_barrier(self):
        result, _ = self.select([self.ok(3, sha="sha-current"), self.behavioral_fail(2, sha="sha-current")])
        self.assertEqual(result, {"execute": True, "suite": "b"})

    def test_h2_scan_stops_at_core_migration_boundary(self):
        pre = run(1, "success", sha="pre-core")
        history = [self.ok(3), (pre, None), self.ok(0)]
        result, calls = self.select(history)
        self.assertEqual(result["suite"], "b")
        self.assertEqual(calls, [3])

    def test_h2_scan_cap_fails_closed(self):
        history = [self.infra_prepare_fail(i, "sha-x") for i in range(10, 0, -1)]
        with self.assertRaisesRegex(rh.ReadinessHistoryError, "bounded history is insufficient"):
            self.select(history, max_runs=5)

    def test_current_incomplete_and_non_schedule_runs_are_skipped(self):
        current = dict(run(999, "failure", sha="sha-current"))
        in_progress = dict(run(8, None), status="in_progress")
        manual = dict(run(7, "failure", sha="sha-current"), event="workflow_dispatch")
        result, calls = self.select([(current, None), (in_progress, None), (manual, None)])
        self.assertEqual(result, {"execute": True, "suite": "a"})
        self.assertEqual(calls, [])

    def test_m3_rerun_of_success_does_not_count_and_does_not_block(self):
        rerun = (run(2, "success", attempt=2, sha="sha-current"), {
            "jobs": [], "artifacts": evidence(2),
            "attempt1": {"run_attempt": 1, "status": "completed", "conclusion": "success"},
            "attempt1_jobs": full_success_jobs()})
        self.assertEqual(self.select([rerun, self.ok(1)])[0], {"execute": True, "suite": "b"})

    def test_api_error_propagates(self):
        def boom(_run):
            raise rh.ReadinessHistoryError("GitHub API request failed")
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.select_suite([run(1)], lambda sha: True, boom, 999, "sha-current")
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.select_suite([run(1)], boom, boom, 999, "sha-current")


class HardeningGateTests(unittest.TestCase):
    def test_m1_behavioral_failure_unlocks_only_on_blind_instruction_inputs(self):
        for path in rh.BLIND_INSTRUCTION_INPUTS:
            self.assertTrue(rh.hardening_allows_retry([path], "behavioral"), path)
        for paths in (
            [".github/workflows/agent-operator.yml"],
            [".github/workflows/agent-final-readiness-core.yml"],
            ["tests/test_agent_routing.py", "tests/test_readiness_carrier_cadence.py"],
            [".github/agents/integrations.agent.md", ".github/skills/quality-gate/SKILL.md"],
            ["agent_evals/final_suite_a_rubric.json", "agent_evals/final_suite_a_prompts.json"],
            ["agent_evals/final_readiness.py", "agent_evals/scheduled_readiness.py"],
            ["docs/CURRENT_STATE.md", "CLAUDE.md"],
            [],
        ):
            with self.subTest(paths=paths):
                self.assertFalse(rh.hardening_allows_retry(paths, "behavioral"))

    def test_infrastructure_failure_unlocks_on_readiness_runtime_repair(self):
        for path in (".github/workflows/agent-final-readiness-core.yml",
                     "agent_evals/scheduled_readiness.py", "agent_evals/readiness_history.py", "AGENTS.md"):
            self.assertTrue(rh.hardening_allows_retry([path], "infrastructure"), path)
        for path in (".github/workflows/agent-operator.yml", "tests/test_readiness_history.py",
                     "agent_evals/final_suite_b_rubric.json", "docs/AGENT_OPERATOR.md"):
            self.assertFalse(rh.hardening_allows_retry([path], "infrastructure"), path)

    def test_unknown_kind_fails_closed(self):
        for kind in ("", "unknown", None):
            with self.assertRaises(rh.ReadinessHistoryError):
                rh.hardening_allows_retry(["AGENTS.md"], kind)

    def test_blind_instruction_inputs_match_blind_bundle_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "blind-input"
            sr.build_blind_bundle("a", bundle)
            names = sorted(p.name for p in bundle.iterdir())
        self.assertIn("AGENTS.md", names)
        self.assertIn("copilot-instructions.md", names)
        self.assertIn("team_profiles.json", names)
        self.assertEqual(sorted(sr.INSTRUCTION_INPUTS.values()), sorted(rh.BLIND_INSTRUCTION_INPUTS))


class CliTests(unittest.TestCase):
    def test_select_writes_outputs_and_same_sha_refusal_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.txt"
            with mock.patch.object(rh, "github_select", return_value={
                    "execute": True, "suite": "a", "failed_sha": "abc", "failure_kind": "behavioral"}):
                code = rh.main(["select", "--repo", "o/r", "--current-run-id", "1", "--current-sha", "s",
                                "--github-output", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(out.read_text().splitlines(),
                             ["execute=true", "suite=a", "failed_sha=abc", "failure_kind=behavioral"])
            out2 = Path(tmp) / "out2.txt"
            with mock.patch.object(rh, "github_select", side_effect=rh.ReadinessHistoryError(rh.SAME_SHA_REFUSAL)):
                code = rh.main(["select", "--repo", "o/r", "--current-run-id", "1", "--current-sha", "s",
                                "--github-output", str(out2)])
            self.assertEqual(code, 1)
            self.assertFalse(out2.exists(), "no outputs may be written when selection fails closed")

    def test_hardening_gate_cli(self):
        with mock.patch.object(rh, "_changed_paths", return_value=[".github/workflows/agent-operator.yml"]):
            self.assertEqual(rh.main(["hardening-gate", "--failed-sha", "a", "--current-sha", "b",
                                      "--kind", "behavioral"]), 1)
        with mock.patch.object(rh, "_changed_paths", return_value=["AGENTS.md"]):
            self.assertEqual(rh.main(["hardening-gate", "--failed-sha", "a", "--current-sha", "b",
                                      "--kind", "behavioral"]), 0)
        with mock.patch.object(rh, "_changed_paths", return_value=["AGENTS.md"]):
            self.assertEqual(rh.main(["hardening-gate", "--failed-sha", "a", "--current-sha", "b",
                                      "--kind", ""]), 1)

    def test_github_select_uses_read_only_gh_api_calls_and_caches_core_lookups(self):
        calls = []

        def fake_run(cmd, text, capture_output):
            calls.append(cmd)
            path = cmd[-1]
            if "/runs?event=schedule" in path:
                body = {"workflow_runs": [run(3, sha="s1"), run(2, sha="s1"), run(1, sha="pre-core")]}
            elif "/contents/" in path:
                if "pre-core" in path:
                    return mock.Mock(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")
                body = {}
            elif "/jobs" in path:
                body = [{"jobs": full_success_jobs()}]
            elif "/artifacts" in path:
                rid = path.split("/runs/")[1].split("/")[0]
                body = [{"artifacts": evidence(int(rid))}]
            else:
                raise AssertionError(path)
            return mock.Mock(returncode=0, stdout=json.dumps(body), stderr="")

        with mock.patch.object(rh.subprocess, "run", side_effect=fake_run):
            result = rh.github_select("o/r", 999, "s2")
        self.assertEqual(result, {"execute": True, "suite": "c"})
        for cmd in calls:
            self.assertEqual(cmd[:2], ["gh", "api"])
            for forbidden in ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"):
                self.assertNotIn(forbidden, cmd)
        self.assertEqual(sum(1 for c in calls if "/contents/" in c[-1] and "ref=s1" in c[-1]), 1)

    def test_github_select_api_failure_fails_closed(self):
        with mock.patch.object(rh.subprocess, "run",
                               return_value=mock.Mock(returncode=1, stdout="", stderr="HTTP 403 rate limit")):
            with self.assertRaises(rh.ReadinessHistoryError):
                rh.github_select("o/r", 999, "s")


class InstructionHashTests(unittest.TestCase):
    def test_instruction_hashes_cover_exact_blind_inputs(self):
        hashes = sr.instruction_hashes()
        self.assertEqual(set(hashes), {"agents_md_sha256", "copilot_instructions_sha256", "team_profiles_sha256"})
        for value in hashes.values():
            self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_verify_requires_identical_valid_hashes(self):
        good = sr.instruction_hashes()
        sr.verify_instruction_hashes([good, dict(good), dict(good)])
        for broken in ({}, {**good, "agents_md_sha256": ""}, {**good, "team_profiles_sha256": "X" * 64}):
            with self.assertRaises(ValueError):
                sr.verify_instruction_hashes([good, broken])
        mixed = {**good, "agents_md_sha256": "0" * 64}
        with self.assertRaises(ValueError):
            sr.verify_instruction_hashes([good, mixed])
        with self.assertRaises(ValueError):
            sr.verify_instruction_hashes([])

    def test_cli_has_no_mixed_version_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.json"
            b = Path(tmp) / "b.json"
            good = sr.instruction_hashes()
            a.write_text(json.dumps(good))
            b.write_text(json.dumps({**good, "agents_md_sha256": "0" * 64}))
            with mock.patch("sys.argv", ["sr", "verify-instruction-hashes", "--metadata", str(a), str(b), "--allow-mixed"]):
                with self.assertRaises(SystemExit):
                    sr.main()
            with mock.patch("sys.argv", ["sr", "verify-instruction-hashes", "--metadata", str(a), str(b)]):
                with self.assertRaises(ValueError):
                    sr.main()


if __name__ == "__main__":
    unittest.main()
