import unittest
from urllib.parse import unquote

from agent_operator.github_client import GitHubClient
from agent_operator.lifecycle import (
    HUMAN_STOP_LABELS,
    LIFECYCLE_LABELS,
    MANAGED_LABELS,
    make_branch_name,
    transition_labels,
)


class FakeLifecycleClient(GitHubClient):
    def __init__(self, labels, inject_after_target_post=None):
        self.repository = "owner/repo"
        self.token = "test"
        self.issue = {"number": 7, "labels": [{"name": label} for label in labels]}
        self.calls = []
        self.inject_after_target_post = inject_after_target_post
        self.injected = False

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
            if self.inject_after_target_post and not self.injected:
                self.issue["labels"].append({"name": self.inject_after_target_post})
                self.injected = True
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

    def test_human_stop_labels_block_autonomous_transition(self):
        for stop in sorted(HUMAN_STOP_LABELS):
            with self.subTest(stop=stop):
                with self.assertRaises(ValueError):
                    transition_labels({"agent:working", stop}, "agent:awaiting-review")

    def test_transition_to_needs_human_is_allowed(self):
        transition = transition_labels({"agent:ready", "agent:paused"}, "needs:human")
        self.assertIn("needs:human", transition.current)
        self.assertIn("agent:paused", transition.current)

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

    def test_claim_requires_ready_at_transition_time(self):
        client = FakeLifecycleClient({"priority:p1"})
        with self.assertRaisesRegex(RuntimeError, "no longer agent:ready"):
            client.set_lifecycle(7, "agent:claimed")
        self.assertNotIn("agent:claimed", client.label_names(client.issue))

    def test_human_stop_arriving_during_transition_wins_and_agent_target_is_rolled_back(self):
        client = FakeLifecycleClient(
            {"agent:ready", "priority:p1"},
            inject_after_target_post="needs:human",
        )
        with self.assertRaisesRegex(RuntimeError, "human stop arrived"):
            client.set_lifecycle(7, "agent:claimed")
        labels = client.label_names(client.issue)
        self.assertIn("needs:human", labels)
        self.assertIn("agent:ready", labels)
        self.assertNotIn("agent:claimed", labels)

    def test_pause_arriving_during_working_transition_is_preserved(self):
        client = FakeLifecycleClient(
            {"agent:claimed", "priority:p1"},
            inject_after_target_post="agent:paused",
        )
        with self.assertRaisesRegex(RuntimeError, "human stop arrived"):
            client.set_lifecycle(7, "agent:working")
        labels = client.label_names(client.issue)
        self.assertIn("agent:paused", labels)
        self.assertIn("agent:claimed", labels)
        self.assertNotIn("agent:working", labels)

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
