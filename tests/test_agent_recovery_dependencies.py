import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / ".github" / "workflows" / "agent-publication-recovery.yml"


class AgentRecoveryDependencyTests(unittest.TestCase):
    def test_recovery_verifier_installs_trusted_dependencies_before_full_tests(self):
        text = RECOVERY.read_text(encoding="utf-8")
        verify = text.split("  verify-recovery-source:", 1)[1].split("  recover-publish-review:", 1)[0]

        self.assertIn("Install trusted base dependencies", verify)
        self.assertIn("python -m pip install -r requirements.txt", verify)
        install_index = verify.index("Install trusted base dependencies")
        test_index = verify.index("Run repository tests in read-only recovery verification job")
        self.assertLess(install_index, test_index)

    def test_dependency_install_stays_in_read_only_verification_job(self):
        text = RECOVERY.read_text(encoding="utf-8")
        verify = text.split("  verify-recovery-source:", 1)[1].split("  recover-publish-review:", 1)[0]

        self.assertIn("contents: read", verify)
        self.assertNotIn("contents: write", verify)
        self.assertNotIn("OPENAI_API_KEY", verify)
        self.assertIn("python -m pip install -r requirements.txt", verify)


if __name__ == "__main__":
    unittest.main()
