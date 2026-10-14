import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_operator.scope_guard import (
    MAX_CHANGED_FILES,
    evaluate_repository,
    validate_changed_paths,
)


class AgentScopeGuardTests(unittest.TestCase):
    def test_normal_product_paths_are_allowed(self):
        self.assertEqual([], validate_changed_paths(["opportunity_radar/models.py", "tests/test_new_feature.py"]))

    def test_agent_control_plane_and_high_trust_paths_are_blocked(self):
        paths = [
            "agent_operator/core.py",
            "AGENTS.md",
            "requirements.txt",
            ".gitignore",
            ".github/agents/backend.agent.md",
            ".github/skills/quality-gate/SKILL.md",
            ".github/workflows/agent-executor.yml",
            ".github/copilot-instructions.md",
            "docs/AGENT_OPERATOR.md",
            "agent_evals/scenarios.json",
            "finance_engine.py",
            "transaction_integrity.py",
            "ledger_store.py",
            "app_ledger.py",
            "opportunity_radar/scoring.py",
            "tests/test_agent_review_gate.py",
        ]
        errors = validate_changed_paths(paths)
        self.assertEqual(len(paths), len(errors))
        self.assertTrue(all("protected" in error for error in errors))

    def test_generated_python_cache_does_not_trigger_scope_failure(self):
        paths = [
            "agent_operator/__pycache__/core.cpython-311.pyc",
            "tests/__pycache__/test_example.cpython-311.pyc",
            ".pytest_cache/v/cache/nodeids",
        ]
        self.assertEqual([], validate_changed_paths(paths))

    def test_large_autonomous_change_is_rejected(self):
        paths = [f"safe/file_{index}.py" for index in range(MAX_CHANGED_FILES + 1)]
        errors = validate_changed_paths(paths)
        self.assertTrue(any("limit" in error for error in errors))

    def test_duplicate_paths_do_not_inflate_file_limit(self):
        paths = ["safe/repeated.py"] * (MAX_CHANGED_FILES + 5)
        self.assertEqual([], validate_changed_paths(paths))

    def _repo(self, directory: str) -> tuple[Path, str]:
        repo = Path(directory)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Scope Guard Test"], check=True)
        (repo / "tests").mkdir()
        (repo / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
        (repo / "tests" / "test_existing.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
        base = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        return repo, base

    def test_existing_tests_cannot_be_modified_autonomously(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self._repo(directory)
            (repo / "tests" / "test_existing.py").write_text("VALUE = 2\n", encoding="utf-8")
            paths, errors = evaluate_repository(repo, base)
            self.assertIn("tests/test_existing.py", paths)
            self.assertTrue(any("existing test changed" in error for error in errors))

    def test_commit_cannot_hide_changes_from_base_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self._repo(directory)
            (repo / "safe.py").write_text("VALUE = 2\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "safe.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "agent commit"], check=True)
            paths, errors = evaluate_repository(repo, base)
            self.assertIn("safe.py", paths)
            self.assertTrue(any("HEAD changed" in error for error in errors))

    def test_only_generated_cache_is_ignored_by_repository_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, base = self._repo(directory)
            cache = repo / "agent_operator" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "core.cpython-311.pyc").write_bytes(b"cache")
            _, errors = evaluate_repository(repo, base)
            self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
