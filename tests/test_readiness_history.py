import tempfile
import unittest
from pathlib import Path

from agent_evals import readiness_history as rh
from agent_evals import scheduled_readiness as sr

PREP = "Caller / final-readiness-prepare"
BLIND = "Caller / final-readiness-blind-pass"
RECORD = "Caller / final-readiness-validate-and-record"
SELECT = "Select next suite from verified carrier history and enforce retry barrier"


def run(rid, conclusion="success", attempt=1, sha="s", created=None):
    return {"id": rid, "run_attempt": attempt, "conclusion": conclusion, "head_sha": sha,
            "event": "schedule", "status": "completed", "created_at": created or f"2026-01-01T00:{rid:02d}:00Z"}


def prep(conclusion="success", failed_step=None):
    steps = [{"name": "Set up job", "conclusion": "success"}]
    if failed_step:
        steps.append({"name": failed_step, "conclusion": "failure"})
    return {"name": PREP, "conclusion": conclusion, "started_at": "t", "steps": steps}


def model(name=BLIND, conclusion="failure"):
    return {"name": name, "conclusion": conclusion, "started_at": "t"}


def evidence(rid):
    return [{"name": f"{rh.EVIDENCE_PREFIX}{rid}", "expired": False}]


class ClassifyRunTests(unittest.TestCase):
    def test_transient_prepare_api_failure_before_model_is_not_paid_relevant(self):
        self.assertEqual("pre_model_failure",
                         rh.classify_run(run(1, "failure"), [prep("failure", SELECT)], []))

    def test_prepare_cancelled_before_model_is_pre_model(self):
        self.assertEqual("pre_model_failure", rh.classify_run(run(1, "cancelled"), [prep("cancelled")], []))

    def test_blind_input_artifact_alone_does_not_make_failure_paid_relevant(self):
        arts = [{"name": f"{rh.BLIND_INPUT_PREFIX}1", "expired": False}]
        self.assertEqual("pre_model_failure",
                         rh.classify_run(run(1, "failure"), [prep("failure", "Upload blind-only model input")], arts))

    def test_deterministic_test_or_bundle_failure_stays_paid_relevant(self):
        for step in ("Run deterministic readiness tests before model spend",
                     "Build blind-only input and freeze current suite hashes"):
            self.assertEqual("paid_relevant_failure",
                             rh.classify_run(run(1, "failure"), [prep("failure", step)], []), step)

    def test_unknown_failed_step_or_missing_steps_fail_closed_to_paid_relevant(self):
        bare = {"name": PREP, "conclusion": "failure", "started_at": "t"}
        self.assertEqual("paid_relevant_failure", rh.classify_run(run(1, "failure"), [bare], []))

    def test_started_model_stage_is_paid_relevant(self):
        self.assertEqual("paid_relevant_failure",
                         rh.classify_run(run(1, "failure"), [prep(), model()], []))
        self.assertEqual("paid_relevant_failure",
                         rh.classify_run(run(1, "cancelled"), [prep(), model(conclusion="cancelled")], []))

    def test_evidence_artifact_makes_failure_paid_relevant(self):
        self.assertEqual("paid_relevant_failure",
                         rh.classify_run(run(1, "failure"), [prep("failure", SELECT)], evidence(1)))

    def test_prepare_success_then_failure_without_model_is_paid_relevant(self):
        self.assertEqual("paid_relevant_failure", rh.classify_run(run(1, "failure"), [prep()], []))

    def test_no_readiness_work_ignored_but_success_without_marker_is_ambiguous(self):
        self.assertEqual("ignore", rh.classify_run(run(1, "failure"), [{"name": "other"}], []))
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.classify_run(run(1, "success"), [{"name": "other"}], [])

    def test_success_needs_exactly_one_unexpired_evidence(self):
        self.assertEqual("success", rh.classify_run(run(1), [prep()], evidence(1)))
        self.assertEqual("success_missing_evidence", rh.classify_run(run(1), [prep()], []))
        expired = [{"name": f"{rh.EVIDENCE_PREFIX}1", "expired": True}]
        self.assertEqual("success_missing_evidence", rh.classify_run(run(1), [prep()], expired))

    def test_failure_kind_distinguishes_threshold_from_infrastructure(self):
        record = {"name": RECORD, "conclusion": "failure", "started_at": "t",
                  "steps": [{"name": rh.THRESHOLD_FAILURE_STEP, "conclusion": "failure"}]}
        self.assertEqual("behavioral", rh.failure_kind([prep(), model(conclusion="success"), record]))
        self.assertEqual("infrastructure", rh.failure_kind([prep(), model()]))
        self.assertEqual("behavioral", rh.failure_kind([prep()]))


class AttemptProvenanceTests(unittest.TestCase):
    def test_attempt_two_cannot_influence_selection(self):
        for attempt in (2, 3, None):
            with self.assertRaises(rh.ReadinessHistoryError):
                rh.classify_run(run(1, attempt=attempt), [prep()], evidence(1))

    def test_attempt_two_success_is_never_counted_in_selection(self):
        runs = [run(1), run(2, attempt=2)]
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.select_suite(runs, lambda r: {"has_core": True, "jobs": [prep()], "artifacts": evidence(r["id"])},
                            99, "cur", True)


class HardeningGateTests(unittest.TestCase):
    def test_cadence_or_unrelated_test_change_does_not_unlock_behavioral_retry(self):
        for paths in ([".github/workflows/agent-operator.yml"],
                      ["tests/test_agent_scope_guard.py"],
                      ["tests/test_readiness_carrier_cadence.py", ".github/workflows/agent-operator.yml"],
                      [".github/workflows/agent-final-readiness-core.yml"],
                      ["agent_evals/scheduled_readiness.py"]):
            self.assertFalse(rh.hardening_allows_retry(paths, "behavioral"), paths)

    def test_instruction_change_unlocks_behavioral_retry(self):
        for path in ("AGENTS.md", ".github/copilot-instructions.md", ".github/agents/qa.agent.md",
                     ".github/skills/x/SKILL.md", "agent_evals/team_profiles.json"):
            self.assertTrue(rh.hardening_allows_retry([path], "behavioral"), path)

    def test_infrastructure_repair_unlocks_only_infrastructure_failures(self):
        paths = [".github/workflows/agent-final-readiness-core.yml", "tests/test_agent_scheduled_readiness.py"]
        self.assertTrue(rh.hardening_allows_retry(paths, "infrastructure"))
        self.assertFalse(rh.hardening_allows_retry(paths, "behavioral"))
        self.assertFalse(rh.hardening_allows_retry(["tests/test_agent_scope_guard.py"], "infrastructure"))

    def test_unknown_kind_and_empty_diff_fail_closed(self):
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.hardening_allows_retry(["AGENTS.md"], "other")
        self.assertFalse(rh.hardening_allows_retry([], "infrastructure"))


class SelectSuiteTests(unittest.TestCase):
    def details_for(self, table, calls=None):
        def fn(r):
            if calls is not None:
                calls.append(r["id"])
            return table[r["id"]]
        return fn

    def ok(self, rid):
        return {"has_core": True, "jobs": [prep()], "artifacts": evidence(rid)}

    def test_sequence_a_b_c_from_successes(self):
        table = {1: self.ok(1), 2: self.ok(2)}
        self.assertEqual({"execute": True, "suite": "a"},
                         rh.select_suite([], self.details_for(table), 99, "cur", True))
        self.assertEqual("b", rh.select_suite([run(1)], self.details_for(table), 99, "cur", True)["suite"])
        self.assertEqual("c", rh.select_suite([run(1), run(2)], self.details_for(table), 99, "cur", True)["suite"])

    def test_pre_model_failure_does_not_block_same_sha(self):
        table = {1: self.ok(1), 2: {"has_core": True, "jobs": [prep("failure", SELECT)], "artifacts": []}}
        out = rh.select_suite([run(1), run(2, "failure", sha="cur")], self.details_for(table), 99, "cur", True)
        self.assertEqual({"execute": True, "suite": "b"}, out)

    def test_paid_relevant_failure_blocks_same_sha_and_flags_other_sha(self):
        table = {1: {"has_core": True, "jobs": [prep(), model()], "artifacts": []}}
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.select_suite([run(1, "failure", sha="cur")], self.details_for(table), 99, "cur", True)
        out = rh.select_suite([run(1, "failure", sha="old")], self.details_for(table), 99, "cur", True)
        self.assertEqual(("a", "old", "infrastructure"), (out["suite"], out["failed_sha"], out["failure_kind"]))

    def test_three_successes_complete_and_scan_stops_early(self):
        table = {i: self.ok(i) for i in range(1, 60)}
        calls = []
        runs = [run(i) for i in range(1, 60)]
        out = rh.select_suite(runs, self.details_for(table, calls), 999, "cur", False)
        self.assertEqual({"execute": False, "suite": "complete"}, out)
        self.assertEqual(3, len(calls))  # bounded API pressure: newest three only

    def test_truncated_window_without_boundary_fails_closed(self):
        table = {1: self.ok(1)}
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.select_suite([run(1)], self.details_for(table), 99, "cur", False)

    def test_truncated_window_with_pre_core_boundary_is_sufficient(self):
        table = {2: self.ok(2), 1: {"has_core": False, "jobs": [], "artifacts": []}}
        out = rh.select_suite([run(1), run(2)], self.details_for(table), 99, "cur", False)
        self.assertEqual("b", out["suite"])

    def test_api_error_propagates_fail_closed(self):
        def boom(_):
            raise RuntimeError("HTTP 502")
        with self.assertRaises(RuntimeError):
            rh.select_suite([run(1)], boom, 99, "cur", True)

    def test_success_missing_evidence_refuses(self):
        table = {1: {"has_core": True, "jobs": [prep()], "artifacts": []}}
        with self.assertRaises(rh.ReadinessHistoryError):
            rh.select_suite([run(1)], self.details_for(table), 99, "cur", True)


class InstructionHashTests(unittest.TestCase):
    def test_hashes_cover_exact_blind_bundle_inputs(self):
        hashes = sr.instruction_hashes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            sr.build_blind_bundle("a", out)
            self.assertEqual(hashes["agents_md_sha256"], sr.sha256_file(out / "AGENTS.md"))
            self.assertEqual(hashes["copilot_instructions_sha256"], sr.sha256_file(out / "copilot-instructions.md"))
            self.assertEqual(hashes["team_profiles_sha256"], sr.sha256_file(out / "team_profiles.json"))

    def test_mixed_instruction_versions_rejected_unless_explicit(self):
        base = sr.instruction_hashes()
        other = dict(base, agents_md_sha256="0" * 64)
        sr.verify_instruction_hashes([base, dict(base), dict(base)])
        with self.assertRaises(ValueError):
            sr.verify_instruction_hashes([base, other, base])
        sr.verify_instruction_hashes([base, other, base], allow_mixed=True)

    def test_missing_or_malformed_hash_rejected_even_when_mixed_allowed(self):
        base = sr.instruction_hashes()
        legacy = {k: v for k, v in base.items() if k != "team_profiles_sha256"}
        for bad in (legacy, dict(base, agents_md_sha256="xyz"), {}):
            with self.assertRaises(ValueError):
                sr.verify_instruction_hashes([base, bad], allow_mixed=True)
        with self.assertRaises(ValueError):
            sr.verify_instruction_hashes([])


if __name__ == "__main__":
    unittest.main()
