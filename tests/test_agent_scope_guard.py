import unittest

from agent_operator.scope_guard import MAX_CHANGED_FILES, validate_changed_paths


class AgentScopeGuardTests(unittest.TestCase):
    def test_normal_product_paths_are_allowed(self):
        self.assertEqual([], validate_changed_paths(["opportunity_radar/models.py", "tests/test_opportunity_radar.py"]))

    def test_agent_control_plane_paths_are_blocked(self):
        paths = [
            "agent_operator/core.py",
            "AGENTS.md",
            ".github/agents/backend.agent.md",
            ".github/skills/quality-gate/SKILL.md",
            ".github/workflows/agent-executor.yml",
            "docs/AGENT_OPERATOR.md",
        ]
        errors = validate_changed_paths(paths)
        self.assertEqual(len(paths), len(errors))
        self.assertTrue(all("protected" in error for error in errors))

    def test_large_autonomous_change_is_rejected(self):
        paths = [f"safe/file_{index}.py" for index in range(MAX_CHANGED_FILES + 1)]
        errors = validate_changed_paths(paths)
        self.assertTrue(any("limit" in error for error in errors))

    def test_duplicate_paths_do_not_inflate_file_limit(self):
        paths = ["safe/repeated.py"] * (MAX_CHANGED_FILES + 5)
        self.assertEqual([], validate_changed_paths(paths))


if __name__ == "__main__":
    unittest.main()
