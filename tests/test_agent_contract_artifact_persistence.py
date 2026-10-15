import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / ".github" / "workflows" / "agent-executor.yml"
CLAIM = ROOT / "agent_operator" / "claim.py"


class AgentContractArtifactPersistenceTests(unittest.TestCase):
    def test_executor_preserves_claim_written_recovery_metadata_in_contract_artifact(self):
        executor = EXECUTOR.read_text(encoding="utf-8")
        freeze = executor.split("      - name: Freeze immutable task contract", 1)[1].split(
            "      - name: Upload immutable task contract", 1
        )[0]
        upload = executor.split("      - name: Upload immutable task contract", 1)[1].split(
            "      - name: Mark task working", 1
        )[0]

        self.assertIn('mkdir -p "$RUNNER_TEMP/ledger-task-contract"', freeze)
        self.assertNotIn('rm -rf "$RUNNER_TEMP/ledger-task-contract"', freeze)
        self.assertNotIn('rm -r "$RUNNER_TEMP/ledger-task-contract"', freeze)
        self.assertIn('cp "$AGENT_TASK_PATH" "$RUNNER_TEMP/ledger-task-contract/task.json"', freeze)
        self.assertIn('cp "$AGENT_PROMPT_PATH" "$RUNNER_TEMP/ledger-task-contract/prompt.md"', freeze)
        self.assertIn("path: ${{ runner.temp }}/ledger-task-contract", upload)

    def test_claim_writes_metadata_into_the_same_uploaded_directory(self):
        claim = CLAIM.read_text(encoding="utf-8")
        self.assertIn('runner_temp / "ledger-task-contract" / "contract-metadata.json"', claim)
        self.assertIn('"base_sha": base_sha', claim)
        self.assertIn('"run_id": run_id', claim)
        self.assertIn('"run_attempt": run_attempt', claim)
        self.assertIn('"task_sha": hashlib.sha256(task_path.read_bytes()).hexdigest()', claim)
        self.assertIn('"prompt_sha": hashlib.sha256(prompt_path.read_bytes()).hexdigest()', claim)


if __name__ == "__main__":
    unittest.main()
