import unittest
from urllib.parse import unquote

from agent_operator.github_client import GitHubClient
from agent_operator.lifecycle import (
    LIFECYCLE_LABELS,
    MANAGED_LABELS,
    make_branch_name,
    transition_labels,
)


class FakeLifecycleClient(GitHubClient):
    def __init__(self, labels):
        self.repository = "owner/repo"
        self.token = "test"
        self.issue = {"number": 7, "labels": [{"name": label} for label in labels]}
        self.calls = []

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.endswith("/issues/7"):
            return {
                "number": 7,
                "labels": [dict(label) for label in self.issue["labels"]],
            }
        if method == "DELETE" and "/issues/7/labels/" in path:
            encoded = path.rsplit("/", 1)[-1]
            label = unquote(encoded)
            self.issue["labels"] = [item for item in self.issue["labels"] if item["name"] != label]
            return None
        if method == "POST" and path.endswith("/issues/7/labels"):
            current = {item["name"] for item in self.issue["labels"]}
            for label in payload["labels"]:
                if label not in current:
                    self.issue["labels"].append({"name": label})
            return {"labels": self.issue["labels"]}
        raise AssertionError(f"Unexpected request: {method} {path} {payload}")


class AgentOperatorLifecycleTests(unittest.TestCase):
    def test_transition_preserves_non_lifecycle_labels_and_replaces_state(self):
        transition = transition_labels(
            {"agent:ready", "priority:p1", "area:backend", "agent:claimed"},
            "agent:working",
        )
        self.assertEqual(
            frozenset({"priority:p1", "area:backend", "agent:working"}),
            transition.current,
        )
        self.assertEqual(1, len(transition.current.intersection(LIFECYCLE_LABELS)))

    def test_github_transition_mutates_only_lifecycle_labels(self):
        client = FakeLifecycleClient(
            {"agent:ready", "agent:claimed", "priority:p1", "data:financial"}
        )
        updated = client.set_lifecycle(7, "agent:working")
        labels = client.label_names(updated)
        self.assertEqual(
            {"agent:working", "priority:p1", "data:financial"},
            labels,
        )
        self.assertFalse(any(method == "PATCH" for method, _, _ in client.calls))
        self.assertEqual({"agent:working"}, labels & LIFECYCLE_LABELS)

    def test_unknown_lifecycle_target_is_rejected(self):
        with self.assertRaises(ValueError):
            transition_labels({"agent:ready"}, "agent:magic")

    def test_branch_name_is_deterministic_and_safe(self):
        self.assertEqual("agent/issue-42-123_abc", make_branch_name(42, "123_abc"))
        self.assertEqual("agent/issue-42-123abc", make_branch_name(42, "123 abc!"))

    def test_branch_name_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            make_branch_name(0, "123")
        with self.assertRaises(ValueError):
            make_branch_name(2, "!!!")

    def test_managed_labels_cover_queue_routing_risk_and_human_gates(self):
        expected = {
            "agent:ready",
            "agent:paused",
            "agent:claimed",
            "priority:p0",
            "priority:p1",
            "priority:p2",
            "priority:p3",
            "owner:backend",
            "owner:integrations",
            "owner:research",
            "owner:frontend",
            "owner:generalist",
            "owner:security",
            "area:backend",
            "area:integrations",
            "area:settlement",
            "area:research",
            "area:frontend",
            "area:security",
            "area:auth",
            "risk:low",
            "risk:medium",
            "risk:high",
            "data:financial",
            "data:credentials",
            "data:live-financial",
            "permission:expand",
            "action:deploy",
            "action:delete",
            "action:publish",
            "action:purchase",
        }
        self.assertTrue(expected.issubset(MANAGED_LABELS), expected - set(MANAGED_LABELS))

    def test_every_managed_label_has_valid_color_and_description(self):
        for name, (color, description) in MANAGED_LABELS.items():
            with self.subTest(label=name):
                self.assertEqual(6, len(color))
                self.assertTrue(all(ch in "0123456789abcdef" for ch in color.lower()))
                self.assertTrue(description.strip())


if __name__ == "__main__":
    unittest.main()
