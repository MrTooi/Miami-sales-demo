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

    def test_all_required_reviews_must_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            qa = self._write(
                directory,
                "qa.json",
                {"verdict": "pass", "summary": "ok", "findings": []},
            )
            security = self._write(
                directory,
                "security.json",
                {"verdict": "pass", "summary": "ok", "findings": []},
            )
            passed, reviews = evaluate([qa, security])
            self.assertTrue(passed)
            self.assertEqual(2, len(reviews))

    def test_fail_or_needs_human_blocks_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            qa = self._write(
                directory,
                "qa.json",
                {"verdict": "pass", "summary": "ok", "findings": []},
            )
            security = self._write(
                directory,
                "security.json",
                {"verdict": "needs-human", "summary": "ambiguous", "findings": []},
            )
            passed, _ = evaluate([qa, security])
            self.assertFalse(passed)

    def test_malformed_or_unknown_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            unknown = self._write(
                directory,
                "unknown.json",
                {"verdict": "maybe", "summary": "unclear", "findings": []},
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


if __name__ == "__main__":
    unittest.main()
