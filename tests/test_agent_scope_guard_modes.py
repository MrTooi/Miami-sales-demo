import tempfile
import unittest
from pathlib import Path

from agent_operator.scope_guard import apply_manifest, build_manifest, snapshot_tree


class AgentScopeGuardModeRegressionTests(unittest.TestCase):
    def test_read_only_lock_does_not_look_like_repository_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            source = root / "source"
            base.mkdir()
            source.mkdir()

            base_file = base / "safe.py"
            source_file = source / "safe.py"
            base_file.write_text("VALUE = 1\n", encoding="utf-8")
            source_file.write_text("VALUE = 1\n", encoding="utf-8")

            # The verifier intentionally makes its trusted copy read-only.
            # Git does not track ordinary read/write permission differences,
            # so this must not turn into a fake repository modification.
            base_file.chmod(0o444)
            source_file.chmod(0o644)

            manifest, errors = build_manifest(source, base)
            self.assertEqual([], manifest["changes"])
            self.assertEqual([], errors)
            self.assertEqual(0o644, snapshot_tree(base)["safe.py"]["mode"])
            self.assertEqual(0o644, snapshot_tree(source)["safe.py"]["mode"])

    def test_executable_bit_change_is_still_detected_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            source = root / "source"
            base.mkdir()
            source.mkdir()

            base_file = base / "safe.py"
            source_file = source / "safe.py"
            base_file.write_text("VALUE = 1\n", encoding="utf-8")
            source_file.write_text("VALUE = 1\n", encoding="utf-8")
            base_file.chmod(0o444)
            source_file.chmod(0o755)

            manifest, errors = build_manifest(source, base)
            self.assertEqual(1, len(manifest["changes"]))
            self.assertEqual("safe.py", manifest["changes"][0]["path"])
            self.assertTrue(any("executable-bit addition" in error for error in errors))
            self.assertEqual(0o644, manifest["changes"][0]["before"]["mode"])
            self.assertEqual(0o755, manifest["changes"][0]["after"]["mode"])

    def test_materialization_rejects_non_normalized_manifest_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()

            source_file = source / "safe.py"
            source_file.write_text("VALUE = 1\n", encoding="utf-8")
            source_file.chmod(0o644)
            after = snapshot_tree(source)["safe.py"]
            after = dict(after)
            after["mode"] = 0o4755
            manifest = {
                "version": 1,
                "changes": [
                    {
                        "path": "safe.py",
                        "operation": "add",
                        "before": None,
                        "after": after,
                    }
                ],
            }

            with self.assertRaisesRegex(ValueError, "unsupported normalized file mode"):
                apply_manifest(source, destination, manifest)
            self.assertFalse((destination / "safe.py").exists())


if __name__ == "__main__":
    unittest.main()
