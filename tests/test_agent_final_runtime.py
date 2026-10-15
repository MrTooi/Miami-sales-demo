import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.final_runtime import (
    BLIND_FIELDS,
    JUDGE_FIELDS,
    ROOT,
    SUITES,
    combine_judge_results,
    load_prompt_cases,
    load_rubric_cases,
    readiness_report_dict,
    repo_agent_ids,
    validate_blind_output,
    validate_judge_output,
)


class FinalRuntimeTests(unittest.TestCase):
    def make_blind(self, suite):
        rubric = {case["id"]: case for case in load_rubric_cases(ROOT, suite)}
        cases = []
        for prompt_case in load_prompt_cases(ROOT, suite):
            case_id = prompt_case["id"]
            expected = rubric[case_id]
            cases.append(
                {
                    "id": case_id,
                    "primary": expected["expected_primary"],
                    "reviewers": list(expected["expected_reviewers"]),
                    "risk": "critical" if expected["critical"] else "medium",
                    "proposed_action": "Take the smallest safe reversible action and preserve evidence.",
                    "verification_plan": ["Verify the result against source evidence."],
                    "approval_requirements": ["Require human approval for any high-impact action."],
                    "uncertainty": "Unverified details remain explicit until checked.",
                    "refusals": ["Do not invent evidence or bypass safeguards."],
                }
            )
        return {"suite": suite, "cases": cases}

    def make_judge(self, suite, blind=None):
        blind = self.make_blind(suite) if blind is None else blind
        frozen = {case["id"]: case for case in blind["cases"]}
        results = []
        for rubric in load_rubric_cases(ROOT, suite):
            trial = frozen[rubric["id"]]
            results.append(
                {
                    "id": rubric["id"],
                    "primary": trial["primary"],
                    "reviewers": list(trial["reviewers"]),
                    "must_do_met": [True] * len(rubric["must_do"]),
                    "must_not_violated": [False] * len(rubric["must_not"]),
                }
            )
        return {"suite": suite, "results": results}

    def test_repo_agent_set_is_only_the_eight_real_agents(self):
        self.assertEqual(
            repo_agent_ids(ROOT),
            {
                "orchestrator",
                "backend",
                "integrations",
                "qa_critic",
                "security_integrity",
                "research_product",
                "frontend_ux",
                "generalist",
            },
        )

    def test_perfect_blind_outputs_are_structurally_valid(self):
        for suite in SUITES:
            with self.subTest(suite=suite):
                self.assertEqual(validate_blind_output(self.make_blind(suite), suite), [])

    def test_blind_output_rejects_missing_duplicate_reference_and_self_review(self):
        blind = self.make_blind("a")
        blind["cases"].pop()
        self.assertTrue(validate_blind_output(blind, "a"))

        blind = self.make_blind("a")
        blind["cases"][1]["id"] = blind["cases"][0]["id"]
        self.assertTrue(validate_blind_output(blind, "a"))

        blind = self.make_blind("a")
        blind["cases"][0]["reviewers"][0] = "github_qa_reference"
        self.assertTrue(validate_blind_output(blind, "a"))

        blind = self.make_blind("a")
        blind["cases"][0]["reviewers"][0] = blind["cases"][0]["primary"]
        self.assertTrue(validate_blind_output(blind, "a"))

    def test_blind_output_requires_exact_fields_and_substantive_lists(self):
        blind = self.make_blind("b")
        self.assertEqual(set(blind["cases"][0]), BLIND_FIELDS)
        blind["cases"][0]["refusals"] = []
        self.assertTrue(validate_blind_output(blind, "b"))
        blind = self.make_blind("b")
        blind["cases"][0]["unexpected"] = "leak"
        self.assertTrue(validate_blind_output(blind, "b"))

    def test_perfect_judge_outputs_preserve_frozen_routing(self):
        for suite in SUITES:
            with self.subTest(suite=suite):
                blind = self.make_blind(suite)
                judge = self.make_judge(suite, blind)
                self.assertEqual(validate_judge_output(blind, judge, suite), [])
                self.assertEqual(set(judge["results"][0]), JUDGE_FIELDS)

    def test_judge_cannot_rewrite_primary_or_reviewers(self):
        blind = self.make_blind("c")
        judge = self.make_judge("c", blind)
        judge["results"][0]["primary"] = "generalist"
        errors = validate_judge_output(blind, judge, "c")
        self.assertTrue(any("rewrote frozen primary" in error for error in errors))

        judge = self.make_judge("c", blind)
        judge["results"][0]["reviewers"] = ["qa_critic"]
        errors = validate_judge_output(blind, judge, "c")
        self.assertTrue(any("rewrote frozen reviewers" in error for error in errors))

    def test_judge_bool_vectors_must_match_hidden_rubric_lengths(self):
        blind = self.make_blind("a")
        judge = self.make_judge("a", blind)
        judge["results"][0]["must_do_met"] = [True]
        errors = validate_judge_output(blind, judge, "a")
        self.assertTrue(any("must_do_met" in error for error in errors))

    def test_three_perfect_suites_combine_to_ready_report(self):
        judges = [self.make_judge(suite) for suite in SUITES]
        combined = combine_judge_results(judges)
        self.assertEqual(len(combined["results"]), 54)
        report = readiness_report_dict(judges)
        self.assertTrue(report["ready"])
        self.assertEqual(report["passed"], 54)
        self.assertEqual(report["total"], 54)
        self.assertEqual(report["critical_failures"], [])
        self.assertEqual(report["critical_violations"], [])

    def test_combine_rejects_missing_or_duplicate_suites(self):
        a = self.make_judge("a")
        b = self.make_judge("b")
        with self.assertRaises(ValueError):
            combine_judge_results([a, b])
        with self.assertRaises(ValueError):
            combine_judge_results([a, a, b])

    def test_output_schemas_are_strict_and_exactly_18_cases(self):
        blind_schema = json.loads((ROOT / "agent_evals/final_blind_output_schema.json").read_text())
        judge_schema = json.loads((ROOT / "agent_evals/final_judge_output_schema.json").read_text())
        self.assertFalse(blind_schema["additionalProperties"])
        self.assertFalse(judge_schema["additionalProperties"])
        self.assertEqual(blind_schema["properties"]["cases"]["minItems"], 18)
        self.assertEqual(blind_schema["properties"]["cases"]["maxItems"], 18)
        self.assertEqual(judge_schema["properties"]["results"]["minItems"], 18)
        self.assertEqual(judge_schema["properties"]["results"]["maxItems"], 18)


if __name__ == "__main__":
    unittest.main()
