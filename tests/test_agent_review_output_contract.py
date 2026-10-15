import json
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "agent_operator" / "review_schema.json"
EXECUTOR_PATH = ROOT / ".github" / "workflows" / "agent-executor.yml"
RECOVERY_PATH = ROOT / ".github" / "workflows" / "agent-publication-recovery.yml"
PROMPT_CONTRACT = (
    "Top-level keys must be exactly verdict, summary, findings, and tests; all four are required. "
    "Use an empty tests array when there is no test evidence; do not add any other top-level keys."
)


class AgentReviewOutputContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_schema_accepts_string_test_evidence(self):
        jsonschema.validate(
            {
                "verdict": "pass",
                "summary": "No blocking findings.",
                "findings": [],
                "tests": [
                    "python -m unittest tests.test_agent_workbench_trial_finance -v (pass)",
                    "python -m unittest discover -s tests -v (pass)",
                ],
            },
            self.schema,
        )

    def test_schema_accepts_empty_tests_array(self):
        jsonschema.validate(
            {
                "verdict": "pass",
                "summary": "No test evidence was available.",
                "findings": [],
                "tests": [],
            },
            self.schema,
        )

    def test_schema_requires_tests_key(self):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(
                {
                    "verdict": "pass",
                    "summary": "Missing required tests evidence key.",
                    "findings": [],
                },
                self.schema,
            )

    def test_schema_still_rejects_unknown_top_level_fields(self):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(
                {
                    "verdict": "pass",
                    "summary": "No blocking findings.",
                    "findings": [],
                    "tests": [],
                    "unexpected": "must remain forbidden",
                },
                self.schema,
            )

    def test_schema_rejects_non_string_test_evidence(self):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(
                {
                    "verdict": "pass",
                    "summary": "No blocking findings.",
                    "findings": [],
                    "tests": [{"command": "python -m unittest", "result": "pass"}],
                },
                self.schema,
            )

    def test_schema_keeps_strict_top_level_contract(self):
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(
            self.schema["required"],
            ["verdict", "summary", "findings", "tests"],
        )
        self.assertEqual(set(self.schema["required"]), set(self.schema["properties"]))

    def test_executor_reviewer_prompts_state_exact_required_keys(self):
        text = EXECUTOR_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count(PROMPT_CONTRACT), 2)

    def test_recovery_reviewer_prompts_state_exact_required_keys(self):
        text = RECOVERY_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count(PROMPT_CONTRACT), 2)


if __name__ == "__main__":
    unittest.main()
