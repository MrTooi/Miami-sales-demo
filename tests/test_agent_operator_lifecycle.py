import unittest

from agent_operator.lifecycle import (
    LIFECYCLE_LABELS,
    MANAGED_LABELS,
    make_branch_name,
    transition_labels,
)


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
