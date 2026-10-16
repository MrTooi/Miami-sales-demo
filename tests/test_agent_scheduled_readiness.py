import copy
import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.final_readiness import SUITES
from agent_evals.scheduled_readiness import (
    aggregate_judges,
    build_blind_bundle,
    build_judge_bundle,
    load_prompts,
    load_suite_rubric,
    score_suite_doc,
    validate_blind_doc,
    validate_judge_doc,
)


def valid_blind(suite):
    return {
        "results": [
            {
                "id": case["id"],
                "primary": "orchestrator",
                "reviewers": ["qa_critic"],
                "risk": "medium",
                "proposed_action": "Investigate safely and preserve evidence.",
                "verification_plan": "Verify the result with deterministic checks.",
                "approval_requirements": "Human approval if the action becomes high impact.",
                "uncertainty": "The synthetic prompt does not prove the outcome.",
                "refuses": ["Do not invent evidence or bypass safeguards."],
            }
            for case in load_prompts(suite)
        ]
    }


def judge_for_blind(suite, blind):
    rubric = load_suite_rubric(suite)
    return {
        "results": [
            {
                "id": blind_entry["id"],
                "primary": blind_entry["primary"],
                "reviewers": list(blind_entry["reviewers"]),
                "must_do_met": [False] * len(expected["must_do"]),
                "must_not_violated": [False] * len(expected["must_not"]),
            }
            for blind_entry, expected in zip(blind["results"], rubric)
        ]
    }


def perfect_judge(suite):
    return {
        "results": [
            {
                "id": case["id"],
                "primary": case["expected_primary"],
                "reviewers": list(case["expected_reviewers"]),
                "must_do_met": [True] * len(case["must_do"]),
                "must_not_violated": [False] * len(case["must_not"]),
            }
            for case in load_suite_rubric(suite)
        ]
    }


class BundleSeparationTests(unittest.TestCase):
    def test_blind_bundle_has_allowlisted_files_and_no_answer_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "blind"
            build_blind_bundle("a", out)
            self.assertEqual(
                {
                    "AGENTS.md",
                    "blind-prompt.md",
                    "blind-schema.json",
                    "copilot-instructions.md",
                    "prompts.json",
                    "team_profiles.json",
                },
                {p.name for p in out.iterdir()},
            )
            self.assertFalse(any("rubric" in p.name.casefold() for p in out.iterdir()))
            source = json.loads((Path(__file__).resolve().parents[1] / "agent_evals/final_suite_a_prompts.json").read_text())
            self.assertEqual(source, json.loads((out / "prompts.json").read_text()))

    def test_judge_bundle_contains_only_selected_hidden_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "judge"
            build_judge_bundle("b", out)
            self.assertEqual(
                {"judge-prompt.md", "judge-schema.json", "prompts.json", "rubric.json"},
                {p.name for p in out.iterdir()},
            )
            rubric = json.loads((out / "rubric.json").read_text())
            self.assertEqual(18, len(rubric["cases"]))
            self.assertTrue(all(case["id"].startswith("b") for case in rubric["cases"]))


class BlindValidationTests(unittest.TestCase):
    def test_valid_blind_document_passes_all_suites(self):
        for suite in SUITES:
            with self.subTest(suite=suite):
                validate_blind_doc(suite, valid_blind(suite))

    def test_missing_duplicate_and_reordered_ids_fail_closed(self):
        base = valid_blind("a")
        mutations = []
        missing = copy.deepcopy(base)
        missing["results"].pop()
        mutations.append(missing)
        duplicate = copy.deepcopy(base)
        duplicate["results"][1]["id"] = duplicate["results"][0]["id"]
        mutations.append(duplicate)
        reordered = copy.deepcopy(base)
        reordered["results"][0], reordered["results"][1] = reordered["results"][1], reordered["results"][0]
        mutations.append(reordered)
        for doc in mutations:
            with self.subTest():
                with self.assertRaises(ValueError):
                    validate_blind_doc("a", doc)

    def test_invalid_agent_self_review_and_malformed_fields_fail(self):
        for mutate in (
            lambda e: e.update(primary="not-an-agent"),
            lambda e: e.update(reviewers=[e["primary"]]),
            lambda e: e.update(reviewers=["qa_critic", "qa_critic"]),
            lambda e: e.update(risk="extreme"),
            lambda e: e.update(proposed_action=""),
            lambda e: e.update(refuses=[]),
            lambda e: e.update(extra="not allowed"),
        ):
            doc = valid_blind("a")
            mutate(doc["results"][0])
            with self.subTest():
                with self.assertRaises(ValueError):
                    validate_blind_doc("a", doc)


def _schema_keys(node):
    keys = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _schema_keys(value)
    elif isinstance(node, list):
        for value in node:
            keys |= _schema_keys(value)
    return keys


class StructuredOutputSchemaCompatibilityTests(unittest.TestCase):
    def test_generated_schemas_omit_unsupported_runtime_keywords(self):
        with tempfile.TemporaryDirectory() as tmp:
            blind_out = Path(tmp) / "blind"
            judge_out = Path(tmp) / "judge"
            build_blind_bundle("a", blind_out)
            build_judge_bundle("a", judge_out)
            for path in (blind_out / "blind-schema.json", judge_out / "judge-schema.json"):
                keys = _schema_keys(json.loads(path.read_text()))
                with self.subTest(schema=path.name):
                    self.assertNotIn("uniqueItems", keys)
                    self.assertNotIn("minLength", keys)
                    self.assertIn("additionalProperties", keys)
                    self.assertIn("minItems", keys)

    def test_local_validation_still_rejects_what_schema_no_longer_enforces(self):
        for mutate in (
            lambda e: e.update(reviewers=["qa_critic", "qa_critic"]),
            lambda e: e.update(id=""),
            lambda e: e.update(proposed_action="   "),
            lambda e: e.update(refuses=[" "]),
        ):
            doc = valid_blind("a")
            mutate(doc["results"][0])
            with self.subTest():
                with self.assertRaises(ValueError):
                    validate_blind_doc("a", doc)
        blind = valid_blind("a")
        judge = judge_for_blind("a", blind)
        judge["results"][0]["reviewers"] = ["qa_critic", "qa_critic"]
        with self.assertRaises(ValueError):
            validate_judge_doc("a", blind, judge)


class JudgeValidationTests(unittest.TestCase):
    def test_valid_judge_copies_frozen_routing(self):
        blind = valid_blind("a")
        judge = judge_for_blind("a", blind)
        validate_judge_doc("a", blind, judge)

    def test_judge_cannot_rewrite_id_primary_or_reviewers(self):
        blind = valid_blind("a")
        for mutate in (
            lambda e: e.update(id="a99-rewritten"),
            lambda e: e.update(primary="backend"),
            lambda e: e.update(reviewers=["security_integrity"]),
        ):
            judge = judge_for_blind("a", blind)
            mutate(judge["results"][0])
            with self.subTest():
                with self.assertRaises(ValueError):
                    validate_judge_doc("a", blind, judge)

    def test_judge_boolean_lengths_types_and_extra_fields_fail(self):
        blind = valid_blind("a")
        for mutate in (
            lambda e: e.update(must_do_met=e["must_do_met"][:-1]),
            lambda e: e.update(must_do_met=[1] * len(e["must_do_met"])),
            lambda e: e.update(must_not_violated=e["must_not_violated"] + [False]),
            lambda e: e.update(extra=True),
        ):
            judge = judge_for_blind("a", blind)
            mutate(judge["results"][0])
            with self.subTest():
                with self.assertRaises(ValueError):
                    validate_judge_doc("a", blind, judge)


class ScheduledScoringTests(unittest.TestCase):
    def test_perfect_suite_is_ready(self):
        for suite in SUITES:
            with self.subTest(suite=suite):
                report = score_suite_doc(suite, perfect_judge(suite))
                self.assertTrue(report["ready"])
                self.assertEqual((18, 18), (report["passed"], report["total"]))

    def test_one_noncritical_failure_is_17_of_18_and_below_threshold(self):
        for suite in SUITES:
            rubric = load_suite_rubric(suite)
            cid = next(case["id"] for case in rubric if not case["critical"])
            doc = perfect_judge(suite)
            next(entry for entry in doc["results"] if entry["id"] == cid)["must_do_met"][0] = False
            report = score_suite_doc(suite, doc)
            with self.subTest(suite=suite):
                self.assertFalse(report["ready"])
                self.assertEqual(17, report["passed"])

    def test_critical_violation_fails(self):
        rubric = load_suite_rubric("a")
        cid = next(case["id"] for case in rubric if case["critical"])
        doc = perfect_judge("a")
        next(entry for entry in doc["results"] if entry["id"] == cid)["must_not_violated"][0] = True
        report = score_suite_doc("a", doc)
        self.assertFalse(report["ready"])
        self.assertIn(cid, report["critical_failures"])
        self.assertIn(cid, report["critical_violations"])

    def test_perfect_three_suite_aggregate_uses_canonical_gate(self):
        report = aggregate_judges({suite: perfect_judge(suite) for suite in SUITES})
        self.assertTrue(report["ready"])
        self.assertEqual((54, 54), (report["passed"], report["total"]))
        self.assertEqual([["a", 18, 18], ["b", 18, 18], ["c", 18, 18]], report["suite_results"])


if __name__ == "__main__":
    unittest.main()
