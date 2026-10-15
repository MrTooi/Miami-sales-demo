import os
import tempfile
import unittest
from pathlib import Path

from agent_operator.scope_guard import (
    MAX_CHANGED_FILES,
    apply_manifest,
    build_manifest,
    snapshot_tree,
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
            ".gitattributes",
            "pyproject.toml",
            "conftest.py",
            ".github/agents/backend.agent.md",
            ".github/workflows/agent-executor.yml",
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

    def test_protected_top_level_modules_cannot_be_shadowed_by_new_packages(self):
        paths = [
            "finance_engine/__init__.py",
            "transaction_integrity/helpers.py",
            "ledger_store/__init__.py",
            "app_ledger/routes.py",
            "opportunity_radar/scoring/__init__.py",
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

    def _trees(self, directory: str) -> tuple[Path, Path]:
        root = Path(directory)
        base = root / "base"
        source = root / "source"
        base.mkdir()
        source.mkdir()
        return base, source

    def test_frozen_task_allowlist_rejects_any_extra_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (source / "allowed.py").write_text("ALLOWED = True\n", encoding="utf-8")
            (source / "surprise.py").write_text("SURPRISE = True\n", encoding="utf-8")

            manifest, errors = build_manifest(
                source,
                base,
                allowed_paths=("allowed.py",),
            )
            self.assertEqual({"allowed.py", "surprise.py"}, {entry["path"] for entry in manifest["changes"]})
            self.assertTrue(any("outside the frozen task allowlist: surprise.py" in error for error in errors))
            self.assertFalse(any("outside the frozen task allowlist: allowed.py" in error for error in errors))

    def test_renaming_protected_file_cannot_hide_original_path(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (base / "finance_engine.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "x.py").write_text("VALUE = 1\n", encoding="utf-8")

            manifest, errors = build_manifest(source, base)
            paths = {(entry["operation"], entry["path"]) for entry in manifest["changes"]}
            self.assertIn(("delete", "finance_engine.py"), paths)
            self.assertIn(("add", "x.py"), paths)
            self.assertTrue(any("protected" in error and "finance_engine.py" in error for error in errors))
            self.assertTrue(any("deletion" in error and "finance_engine.py" in error for error in errors))

    def test_renaming_existing_test_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (base / "tests").mkdir()
            (source / "tests").mkdir()
            (base / "tests" / "test_finance_engine.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "tests" / "test_new.py").write_text("VALUE = 1\n", encoding="utf-8")

            manifest, errors = build_manifest(source, base)
            self.assertTrue(any("existing test changed" in error for error in errors))
            self.assertTrue(any("deletion" in error for error in errors))
            self.assertEqual(
                {"tests/test_finance_engine.py", "tests/test_new.py"},
                {entry["path"] for entry in manifest["changes"]},
            )

    def test_new_generated_cache_is_ignored_because_it_is_never_published(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (base / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
            cache = source / "agent_operator" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "core.cpython-311.pyc").write_bytes(b"cache")

            manifest, errors = build_manifest(source, base)
            self.assertEqual([], manifest["changes"])
            self.assertEqual([], errors)

    def test_base_tracked_cache_change_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            base_cache = base / "agent_operator" / "__pycache__"
            source_cache = source / "agent_operator" / "__pycache__"
            base_cache.mkdir(parents=True)
            source_cache.mkdir(parents=True)
            (base_cache / "core.cpython-311.pyc").write_bytes(b"old")
            (source_cache / "core.cpython-311.pyc").write_bytes(b"new")

            manifest, errors = build_manifest(source, base)
            self.assertEqual(1, len(manifest["changes"]))
            self.assertTrue(any("protected" in error for error in errors))

    def test_existing_test_modification_is_blocked_but_new_test_module_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (base / "tests").mkdir()
            (source / "tests").mkdir()
            (base / "tests" / "test_existing.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "tests" / "test_existing.py").write_text("VALUE = 2\n", encoding="utf-8")
            (source / "tests" / "test_feature.py").write_text("VALUE = 1\n", encoding="utf-8")

            _, errors = build_manifest(source, base)
            self.assertTrue(any("existing test changed" in error for error in errors))
            self.assertFalse(any("test_feature.py" in error for error in errors))

    def test_new_non_test_python_under_tests_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (source / "tests").mkdir()
            (source / "tests" / "sitecustomize.py").write_text("VALUE = 1\n", encoding="utf-8")

            _, errors = build_manifest(source, base)
            self.assertTrue(any("not an allowed test module" in error for error in errors))

    def test_symlink_and_new_executable_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            target = source / "target.txt"
            target.write_text("ok\n", encoding="utf-8")
            os.symlink("target.txt", source / "link.txt")
            executable = source / "tool.py"
            executable.write_text("print('x')\n", encoding="utf-8")
            executable.chmod(0o755)

            _, errors = build_manifest(source, base)
            self.assertTrue(any("non-regular" in error and "link.txt" in error for error in errors))
            self.assertTrue(any("executable-bit" in error and "tool.py" in error for error in errors))

    def test_replacing_base_symlink_with_regular_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = self._trees(directory)
            (base / "target.txt").write_text("target\n", encoding="utf-8")
            os.symlink("target.txt", base / "link.txt")
            (source / "target.txt").write_text("target\n", encoding="utf-8")
            (source / "link.txt").write_text("replacement\n", encoding="utf-8")

            _, errors = build_manifest(source, base)
            self.assertTrue(any("non-regular base entry" in error and "link.txt" in error for error in errors))

    def test_materialization_refuses_symlink_destination_even_for_verified_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            source = root / "source"
            destination = root / "destination"
            for path in (base, source, destination):
                path.mkdir()

            (base / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "safe.py").write_text("VALUE = 2\n", encoding="utf-8")
            (destination / "target.py").write_text("TARGET = True\n", encoding="utf-8")
            os.symlink("target.py", destination / "safe.py")

            manifest, errors = build_manifest(source, base)
            self.assertEqual([], errors)
            with self.assertRaisesRegex(ValueError, "symlink"):
                apply_manifest(source, destination, manifest)

    def test_verified_manifest_materializes_into_clean_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            source = root / "source"
            destination = root / "destination"
            for path in (base, source, destination):
                path.mkdir()

            (base / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
            (destination / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "safe.py").write_text("VALUE = 2\n", encoding="utf-8")
            (source / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")

            manifest, errors = build_manifest(source, base)
            self.assertEqual([], errors)
            apply_manifest(source, destination, manifest)

            rebuilt, rebuilt_errors = build_manifest(destination, base)
            self.assertEqual([], rebuilt_errors)
            self.assertEqual(manifest, rebuilt)
            self.assertEqual(snapshot_tree(source), snapshot_tree(destination))


if __name__ == "__main__":
    unittest.main()
