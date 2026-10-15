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


BASE = "a" * 40
EXPECTED_TREE = "b" * 40
REMOTE_TREE = EXPECTED_TREE
HEAD = "c" * 40
OWNER = "MrTooi"


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

    def pr(self, **overrides):
        payload = {
            "url": "https://github.com/MrTooi/Miami-sales-demo/pull/39",
            "isDraft": True,
            "isCrossRepository": False,
            "headRepositoryOwner": {"login": OWNER},
            "baseRefName": "main",
            "headRefOid": HEAD,
        }
        payload.update(overrides)
        return payload

    def test_branch_absent_allows_single_push(self):
        action = choose_branch_action(
            remote_exists=False,
            expected_tree=EXPECTED_TREE,
            base_sha=BASE,
        )
        self.assertEqual(action, "push")

    def test_existing_exact_git_tree_is_reused(self):
        action = choose_branch_action(
            remote_exists=True,
            expected_tree=EXPECTED_TREE,
            base_sha=BASE,
            remote_tree=REMOTE_TREE,
            parent_sha=BASE,
            commit_count=1,
        )
        self.assertEqual(action, "reuse")

    def test_existing_tree_with_extra_tracked_cache_file_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "Git tree differs"):
            choose_branch_action(
                remote_exists=True,
                expected_tree=EXPECTED_TREE,
                base_sha=BASE,
                remote_tree="d" * 40,
                parent_sha=BASE,
                commit_count=1,
            )

    def test_existing_branch_wrong_parent_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "parent"):
            choose_branch_action(
                remote_exists=True,
                expected_tree=EXPECTED_TREE,
                base_sha=BASE,
                remote_tree=EXPECTED_TREE,
                parent_sha="e" * 40,
                commit_count=1,
            )

    def test_existing_branch_multiple_commits_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "exactly one commit"):
            choose_branch_action(
                remote_exists=True,
                expected_tree=EXPECTED_TREE,
                base_sha=BASE,
                remote_tree=EXPECTED_TREE,
                parent_sha=BASE,
                commit_count=2,
            )

    def test_existing_branch_without_identity_evidence_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "requires tree"):
            choose_branch_action(
                remote_exists=True,
                expected_tree=EXPECTED_TREE,
                base_sha=BASE,
            )

    def test_no_existing_pr_requests_creation(self):
        self.assertEqual(
            choose_pr_action(
                [],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
            ),
            ("create", None),
        )

    def test_one_same_repo_exact_head_draft_pr_is_reused(self):
        action, url = choose_pr_action(
            [self.pr()],
            expected_head_oid=HEAD,
            expected_owner=OWNER,
        )
        self.assertEqual(action, "reuse")
        self.assertEqual(url, "https://github.com/MrTooi/Miami-sales-demo/pull/39")

    def test_cross_repository_pr_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "cross-repository"):
            choose_pr_action(
                [self.pr(isCrossRepository=True)],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
            )

    def test_wrong_head_repository_owner_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "wrong head repository owner"):
            choose_pr_action(
                [self.pr(headRepositoryOwner={"login": "attacker"})],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
            )

    def test_wrong_base_branch_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "wrong base branch"):
            choose_pr_action(
                [self.pr(baseRefName="other")],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
            )

    def test_wrong_reviewed_head_oid_fails_closed(self):
        with self.assertRaisesRegex(RecoveryError, "reviewed commit"):
            choose_pr_action(
                [self.pr(headRefOid="f" * 40)],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
            )

    def test_multiple_existing_prs_fail_closed(self):
        with self.assertRaisesRegex(RecoveryError, "at most one"):
            choose_pr_action(
                [self.pr(), self.pr(url="https://github.com/MrTooi/Miami-sales-demo/pull/40")],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
            )

    def test_non_draft_existing_pr_requires_human_review(self):
        with self.assertRaisesRegex(RecoveryError, "not draft"):
            choose_pr_action(
                [self.pr(isDraft=False)],
                expected_head_oid=HEAD,
                expected_owner=OWNER,
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
