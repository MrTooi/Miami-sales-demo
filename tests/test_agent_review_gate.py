import json
import tempfile
import unittest
from pathlib import Path

from agent_operator.review_gate import evaluate, load_review


class AgentReviewGateTests(unittest.TestCase):
    def _write(self, directory: str, name: str, payload) -> Path:
        path = Path(directory) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _pass_review(self, **overrides):
        payload = {
            "verdict": "pass",
            "summary": "ok",
            "findings": [],
            "tests": [],
        }
        payload.update(overrides)
        return payload

    def test_all_required_reviews_must_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            qa = self._write(directory, "qa.json", self._pass_review())
            security = self._write(directory, "security.json", self._pass_review())
            passed, reviews = evaluate([qa, security])
            self.assertTrue(passed)
            self.assertEqual(2, len(reviews))

    def test_fail_or_needs_human_blocks_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            qa = self._write(directory, "qa.json", self._pass_review())
            security = self._write(
                directory,
                "security.json",
                self._pass_review(verdict="needs-human", summary="ambiguous"),
            )
            passed, _ = evaluate([qa, security])
            self.assertFalse(passed)

    def test_pass_with_serious_finding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for severity in ("blocking", "important"):
                with self.subTest(severity=severity):
                    review = self._write(
                        directory,
                        f"{severity}.json",
                        self._pass_review(
                            summary="claimed pass",
                            findings=[
                                {
                                    "severity": severity,
                                    "title": "Serious issue",
                                    "evidence": "Concrete evidence",
                                }
                            ],
                        ),
                    )
                    passed, _ = evaluate([review])
                    self.assertFalse(passed)

    def test_pass_with_minor_finding_can_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            review = self._write(
                directory,
                "minor.json",
                self._pass_review(
                    summary="minor cleanup only",
                    findings=[
                        {
                            "severity": "minor",
                            "title": "Style note",
                            "evidence": "No correctness impact",
                        }
                    ],
                    tests=["python -m unittest (pass)"],
                ),
            )
            passed, _ = evaluate([review])
            self.assertTrue(passed)

    def test_missing_tests_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._pass_review()
            del payload["tests"]
            review = self._write(directory, "missing-tests.json", payload)
            with self.assertRaises(ValueError):
                load_review(review)

    def test_tests_must_be_list_of_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in ("pytest", [{"command": "pytest"}], ["pytest", 3]):
                with self.subTest(value=value):
                    review = self._write(
                        directory,
                        "bad-tests.json",
                        self._pass_review(tests=value),
                    )
                    with self.assertRaises(ValueError):
                        load_review(review)

    def test_unknown_top_level_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._pass_review()
            payload["counts"] = {"blocking": 0}
            review = self._write(directory, "extra-key.json", payload)
            with self.assertRaises(ValueError):
                load_review(review)

    def test_unknown_finding_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            review = self._write(
                directory,
                "extra-finding-key.json",
                self._pass_review(
                    findings=[
                        {
                            "severity": "minor",
                            "title": "Style note",
                            "evidence": "No correctness impact",
                            "detail": "unexpected",
                        }
                    ]
                ),
            )
            with self.assertRaises(ValueError):
                load_review(review)

    def test_malformed_or_unknown_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            unknown = self._write(
                directory,
                "unknown.json",
                self._pass_review(verdict="maybe", summary="unclear"),
            )
            with self.assertRaises(ValueError):
                load_review(unknown)

            malformed = self._write(
                directory,
                "malformed.json",
                {"verdict": "pass", "summary": "ok"},
            )
            with self.assertRaises(ValueError):
                load_review(malformed)

            malformed_finding = self._write(
                directory,
                "malformed-finding.json",
                self._pass_review(
                    findings=[
                        {
                            "severity": "critical",
                            "title": "bad",
                            "evidence": "bad",
                        }
                    ]
                ),
            )
            with self.assertRaises(ValueError):
                load_review(malformed_finding)


if __name__ == "__main__":
    unittest.main()
