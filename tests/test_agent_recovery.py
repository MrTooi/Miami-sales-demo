import json
import tempfile
import unittest
from pathlib import Path

from agent_operator.recovery import (
    RecoveryError,
    choose_branch_action,
    choose_pr_action,
    compare_manifests,
)


class AgentRecoveryTests(unittest.TestCase):
    def manifest(self, path: str, digest: str = "abc"):
        return {
            "changes": [
                {
                    "path": path,
                    "operation": "create",
                    "sha256": digest,
                    "mode": "0644",
                }
            ]
        }

    def test_branch_absent_allows_single_push(self):
        action = choose_branch_action(
            remote_exists=False,
            expected_manifest=self.manifest("trial.py"),
        )
        self.assertEqual(action, "push")

    def test_existing_matching_branch_is_reused(self):
        expected = self.manifest("trial.py")
        action = choose_branch_action(
            remote_exists=True,
            expected_manifest=expected,
            remote_manifest=dict(expected),
        )
        self.assertEqual(action, "reuse")

    def test_existing_mismatched_branch_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "differs"):
            choose_branch_action(
                remote_exists=True,
                expected_manifest=self.manifest("trial.py", "expected"),
                remote_manifest=self.manifest("trial.py", "different"),
            )

    def test_existing_branch_without_manifest_evidence_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "requires independently reconstructed"):
            choose_branch_action(
                remote_exists=True,
                expected_manifest=self.manifest("trial.py"),
            )

    def test_no_existing_pr_requests_creation(self):
        self.assertEqual(choose_pr_action([]), ("create", None))

    def test_one_existing_draft_pr_is_reused(self):
        action, url = choose_pr_action(
            [{"url": "https://github.com/example/repo/pull/1", "isDraft": True}]
        )
        self.assertEqual(action, "reuse")
        self.assertEqual(url, "https://github.com/example/repo/pull/1")

    def test_multiple_existing_prs_fail_closed(self):
        with self.assertRaisesRegex(RecoveryError, "at most one"):
            choose_pr_action(
                [
                    {"url": "https://github.com/example/repo/pull/1", "isDraft": True},
                    {"url": "https://github.com/example/repo/pull/2", "isDraft": True},
                ]
            )

    def test_non_draft_existing_pr_requires_human_review(self):
        with self.assertRaisesRegex(RecoveryError, "not draft"):
            choose_pr_action(
                [{"url": "https://github.com/example/repo/pull/1", "isDraft": False}]
            )

    def test_manifest_comparison_is_semantic_not_whitespace_sensitive(self):
        expected = self.manifest("trial.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            a = root / "a.json"
            b = root / "b.json"
            a.write_text(json.dumps(expected, indent=2), encoding="utf-8")
            b.write_text(json.dumps(expected, separators=(",", ":")), encoding="utf-8")
            compare_manifests(a, b)

    def test_manifest_comparison_rejects_changed_proposal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            a = root / "a.json"
            b = root / "b.json"
            a.write_text(json.dumps(self.manifest("trial.py", "one")), encoding="utf-8")
            b.write_text(json.dumps(self.manifest("trial.py", "two")), encoding="utf-8")
            with self.assertRaisesRegex(RecoveryError, "does not match"):
                compare_manifests(a, b)


if __name__ == "__main__":
    unittest.main()
