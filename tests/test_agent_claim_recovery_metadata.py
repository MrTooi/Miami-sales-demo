import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_operator.claim import _current_git_head, _write_contract_metadata


class AgentClaimRecoveryMetadataTests(unittest.TestCase):
    def test_current_git_head_is_full_commit_oid(self):
        value = _current_git_head()
        self.assertRegex(value, r"^[0-9a-f]{40}$")

    def test_contract_metadata_binds_task_prompt_base_run_and_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task = root / "task.json"
            prompt = root / "prompt.md"
            task.write_text('{"task": true}\n', encoding="utf-8")
            prompt.write_text("frozen prompt\n", encoding="utf-8")
            base_sha = "a" * 40

            with patch.dict(os.environ, {"RUNNER_TEMP": temp_dir}, clear=False):
                _write_contract_metadata(
                    task_path=task,
                    prompt_path=prompt,
                    base_sha=base_sha,
                    run_id="12345",
                    run_attempt="2",
                )

            metadata_path = root / "ledger-task-contract" / "contract-metadata.json"
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["base_sha"], base_sha)
            self.assertEqual(payload["run_id"], "12345")
            self.assertEqual(payload["run_attempt"], "2")
            self.assertEqual(payload["task_sha"], hashlib.sha256(task.read_bytes()).hexdigest())
            self.assertEqual(payload["prompt_sha"], hashlib.sha256(prompt.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
