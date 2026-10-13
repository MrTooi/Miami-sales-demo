import unittest

from agent_operator.lifecycle import LIFECYCLE_LABELS, make_branch_name, transition_labels


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


if __name__ == "__main__":
    unittest.main()
