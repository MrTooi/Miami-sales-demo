import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.readiness_evidence import EvidenceBindingError, augment_evidence


class ReadinessEvidenceTests(unittest.TestCase):
    def _fixtures(self, root: Path) -> tuple[Path, Path, Path]:
        evidence = root / "evidence.json"
        manifest = root / "manifest.json"
        profiles = root / "team_profiles.json"
        evidence.write_text(
            json.dumps({"event": "schedule", "suite": "a", "validation": {"ready": True}}),
            encoding="utf-8",
        )
        manifest.write_text(
            json.dumps({"source_team_profiles_sha256": "a" * 64}),
            encoding="utf-8",
        )
        profiles.write_text(
            json.dumps(
                {
                    "lineup": ["backend", "qa"],
                    "agents": {
                        "backend": {
                            "capabilities": ["backend"],
                            "independent_review": False,
                        },
                        "qa": {
                            "capabilities": ["qa"],
                            "independent_review": True,
                        },
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return evidence, manifest, profiles

    def test_binds_model_effort_actor_and_profile_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path, manifest_path, profiles_path = self._fixtures(Path(tmp))
            result = augment_evidence(
                evidence_path=evidence_path,
                blind_manifest_path=manifest_path,
                sanitized_profiles_path=profiles_path,
                model="test-model",
                effort="high",
                actor="MrTooi",
            )
            self.assertEqual(result["model"], "test-model")
            self.assertEqual(result["effort"], "high")
            self.assertEqual(result["actor"], "MrTooi")
            self.assertEqual(result["source_team_profiles_sha256"], "a" * 64)
            self.assertEqual(
                result["sanitized_team_profiles_sha256"],
                hashlib.sha256(profiles_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                result["blind_profile_fields"],
                ["capabilities", "independent_review"],
            )
            self.assertEqual(json.loads(evidence_path.read_text(encoding="utf-8")), result)

    def test_rejects_missing_model_invalid_effort_and_wrong_actor(self):
        invalid_cases = [
            {"model": "", "effort": "high", "actor": "MrTooi"},
            {"model": "model with spaces", "effort": "high", "actor": "MrTooi"},
            {"model": "test-model", "effort": "turbo", "actor": "MrTooi"},
            {"model": "test-model", "effort": "high", "actor": "someone-else"},
        ]
        for kwargs in invalid_cases:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                evidence_path, manifest_path, profiles_path = self._fixtures(Path(tmp))
                with self.assertRaises(EvidenceBindingError):
                    augment_evidence(
                        evidence_path=evidence_path,
                        blind_manifest_path=manifest_path,
                        sanitized_profiles_path=profiles_path,
                        **kwargs,
                    )

    def test_rejects_inconsistent_sanitized_profile_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path, manifest_path, profiles_path = self._fixtures(Path(tmp))
            profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
            profiles["agents"]["qa"]["unexpected"] = True
            profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
            with self.assertRaises(EvidenceBindingError):
                augment_evidence(
                    evidence_path=evidence_path,
                    blind_manifest_path=manifest_path,
                    sanitized_profiles_path=profiles_path,
                    model="test-model",
                    effort="medium",
                    actor="MrTooi",
                )


if __name__ == "__main__":
    unittest.main()
