import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.final_readiness import score_readiness
from agent_evals.scheduled_readiness import (
    ReadinessFormatError,
    prepare_blind,
    prepare_judge,
    score_suite,
    suite_for_success_count,
    validate_blind_output,
    validate_judge_output,
)


ROOT = Path(__file__).resolve().parents[1]


def _rubric(suite: str) -> list[dict]:
    return json.loads(
        (ROOT / "agent_evals" / f"final_suite_{suite}_rubric.json").read_text(encoding="utf-8")
    )["cases"]


def _perfect_blind(suite: str) -> dict:
    return {
        "answers": [
            {
                "id": case["id"],
                "primary": case["expected_primary"],
                "reviewers": list(case["expected_reviewers"]),
                "response": "Synthetic evaluation response with explicit safe handling and verification.",
            }
            for case in _rubric(suite)
        ]
    }


def _perfect_judge(suite: str) -> dict:
    return {
        "judgments": [
            {
                "id": case["id"],
                "must_do_met": [True] * len(case["must_do"]),
                "must_not_violated": [False] * len(case["must_not"]),
            }
            for case in _rubric(suite)
        ]
    }


class ScheduledReadinessHelperTests(unittest.TestCase):
    def test_suite_selection_advances_only_by_prior_success_count(self):
        self.assertEqual(suite_for_success_count(0), "a")
        self.assertEqual(suite_for_success_count(1), "b")
        self.assertEqual(suite_for_success_count(2), "c")
        self.assertIsNone(suite_for_success_count(3))
        self.assertIsNone(suite_for_success_count(9))
        for invalid in (-1, True, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ReadinessFormatError):
                    suite_for_success_count(invalid)

    def test_blind_package_is_sanitized_and_has_no_hidden_rubric(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "blind"
            prepare_blind("a", out, "a" * 40)
            names = {path.name for path in out.iterdir()}
            self.assertEqual(
                names,
                {
                    "blind_cases.json",
                    "team_profiles.json",
                    "blind_output_schema.json",
                    "blind_prompt.md",
                    "manifest.json",
                },
            )
            profiles = json.loads((out / "team_profiles.json").read_text(encoding="utf-8"))
            self.assertEqual(len(profiles["lineup"]), 8)
            for profile in profiles["agents"].values():
                self.assertEqual(set(profile), {"capabilities", "independent_review"})
            cases = json.loads((out / "blind_cases.json").read_text(encoding="utf-8"))
            self.assertEqual(len(cases["cases"]), 18)
            self.assertTrue(all(set(case) == {"id", "prompt"} for case in cases["cases"]))
            schema_text = (out / "blind_output_schema.json").read_text(encoding="utf-8")
            self.assertNotIn("uniqueItems", schema_text)
            self.assertNotIn("minLength", schema_text)
            combined_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in out.iterdir()
                if path.suffix in {".json", ".md"}
            )
            self.assertNotIn('"expected_primary"', combined_text)
            self.assertNotIn('"expected_reviewers"', combined_text)
            self.assertNotIn('"must_do"', combined_text)
            self.assertNotIn('"must_not"', combined_text)

    def test_blind_output_requires_exact_order_identity_and_valid_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blind.json"
            perfect = _perfect_blind("a")
            path.write_text(json.dumps(perfect), encoding="utf-8")
            parsed = validate_blind_output("a", path)
            self.assertEqual(list(parsed), [case["id"] for case in _rubric("a")])

            duplicate = _perfect_blind("a")
            duplicate["answers"][1]["id"] = duplicate["answers"][0]["id"]
            path.write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaises(ReadinessFormatError):
                validate_blind_output("a", path)

            unknown = _perfect_blind("a")
            unknown["answers"][0]["primary"] = "not-an-agent"
            path.write_text(json.dumps(unknown), encoding="utf-8")
            with self.assertRaises(ReadinessFormatError):
                validate_blind_output("a", path)

    def test_judge_package_freezes_blind_output_and_schema_cannot_rewrite_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blind_dir = root / "blind"
            judge_dir = root / "judge"
            blind_output = root / "blind-output.json"
            prepare_blind("a", blind_dir, "b" * 40)
            blind_output.write_text(json.dumps(_perfect_blind("a")), encoding="utf-8")
            prepare_judge("a", blind_dir, blind_output, judge_dir, "b" * 40)

            schema = json.loads((judge_dir / "judge_output_schema.json").read_text(encoding="utf-8"))
            item_props = schema["properties"]["judgments"]["items"]["properties"]
            self.assertEqual(set(item_props), {"id", "must_do_met", "must_not_violated"})
            frozen = json.loads((judge_dir / "blind_output.json").read_text(encoding="utf-8"))
            self.assertEqual(frozen, _perfect_blind("a"))

            tampered = _perfect_judge("a")
            tampered["judgments"][0]["primary"] = "backend"
            judge_output = root / "judge-output.json"
            judge_output.write_text(json.dumps(tampered), encoding="utf-8")
            blind_by_id = validate_blind_output("a", blind_output)
            with self.assertRaises(ReadinessFormatError):
                validate_judge_output("a", blind_by_id, judge_output)

    def test_routing_is_copied_from_blind_output_and_one_failure_fails_18_case_suite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blind_path = root / "blind.json"
            judge_path = root / "judge.json"
            blind_doc = _perfect_blind("a")
            blind_doc["answers"][0]["primary"] = "generalist"
            blind_path.write_text(json.dumps(blind_doc), encoding="utf-8")
            judge_path.write_text(json.dumps(_perfect_judge("a")), encoding="utf-8")

            blind_by_id = validate_blind_output("a", blind_path)
            combined = validate_judge_output("a", blind_by_id, judge_path)
            self.assertEqual(combined[0]["primary"], "generalist")
            report = score_suite("a", combined)
            self.assertFalse(report["ready"])
            self.assertEqual(report["passed"], 17)
            self.assertEqual(report["pass_rate_numerator"], 17)
            self.assertEqual(report["pass_rate_denominator"], 18)

    def test_perfect_three_suite_results_match_canonical_final_scorer(self):
        all_results = []
        for suite in ("a", "b", "c"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                blind_path = root / "blind.json"
                judge_path = root / "judge.json"
                blind_path.write_text(json.dumps(_perfect_blind(suite)), encoding="utf-8")
                judge_path.write_text(json.dumps(_perfect_judge(suite)), encoding="utf-8")
                blind_by_id = validate_blind_output(suite, blind_path)
                combined = validate_judge_output(suite, blind_by_id, judge_path)
                report = score_suite(suite, combined)
                self.assertTrue(report["ready"])
                all_results.extend(combined)
        canonical = score_readiness({"results": all_results})
        self.assertTrue(canonical.ready)
        self.assertEqual(canonical.passed, 54)

    def test_package_integrity_fails_closed_after_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blind_dir = root / "blind"
            blind_output = root / "blind-output.json"
            prepare_blind("a", blind_dir, "c" * 40)
            blind_output.write_text(json.dumps(_perfect_blind("a")), encoding="utf-8")
            data = json.loads((blind_dir / "blind_cases.json").read_text(encoding="utf-8"))
            data["cases"][0]["prompt"] += " tampered"
            (blind_dir / "blind_cases.json").write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ReadinessFormatError):
                prepare_judge("a", blind_dir, blind_output, root / "judge", "c" * 40)


if __name__ == "__main__":
    unittest.main()
